"""Sync engine: coordinates input capture from master and replication to slaves."""

import threading
from typing import Optional

from .winapi import (
    user32,
    WM_ACTIVATE,
    WM_SETFOCUS,
    WA_ACTIVE,
    WM_MOUSEMOVE,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_MBUTTONDOWN,
    WM_MBUTTONUP,
    WM_MOUSEWHEEL,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
)
from .hooks import InputHooks
from .sender import InputSender
from .window_manager import screen_to_client, get_client_size, find_input_child

# How many WM_MOUSEMOVE events to skip between sends (0 = no throttle, 1 = every other, etc.)
# Avoids overflowing slave message queues when many windows are running.
_MOUSEMOVE_SKIP = 1

MOUSE_EVENTS = frozenset({
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP,
    WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP,
    WM_MOUSEWHEEL,
})

KEY_EVENTS = frozenset({WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP})


class SyncEngine:
    """Core synchronization engine.

    Captures input from the master window and replicates it to slave windows.
    Supports proportional coordinate scaling when windows differ in size.

    Background-window activation
    ----------------------------
    Modern browsers (Chrome, Edge, Firefox) only process PostMessage-based
    input when their window believes it has focus.  When the master is in the
    foreground all slave windows are in the background, so Chrome silently
    drops our WM_KEYDOWN / WM_LBUTTONDOWN messages.

    Fix: every time the master window *transitions into* the foreground we
    send each slave:
        PostMessage(top_level,     WM_ACTIVATE, WA_ACTIVE, 0)
        PostMessage(focused_child, WM_SETFOCUS, 0, 0)

    The focused child is found via GetGUIThreadInfo() — it returns the
    per-thread focus state of the slave's UI thread, independent of which
    window the OS considers the foreground.  For Chromium browsers this is
    typically Chrome_RenderWidgetHostHWND.

    After receiving WM_ACTIVATE + WM_SETFOCUS, Chrome sets is_active_ = true
    in its view hierarchy and starts processing subsequent PostMessage input.

    Keyboard events are routed directly to the focused child (find_input_child)
    because Chrome's render widget processes WM_KEYDOWN at the child level.
    Mouse events go to the top-level HWND — Chrome routes them internally
    via its own hit-testing, and coordinates stay relative to the top-level
    client area, avoiding nested-child coordinate conversion complexity.
    """

    def __init__(self):
        self._hooks = InputHooks()
        self._sender = InputSender()
        self._lock = threading.Lock()

        self._master_hwnd: Optional[int] = None
        self._slave_hwnds: list = []
        self._active = False
        self._paused = False
        self._scale_coords = False

        self._events_sent: int = 0
        # Count of slave HWNDs auto-removed because the window was destroyed.
        self._dead_removed: int = 0
        # Tracks whether master was in foreground on the last event.
        # When this transitions False → True we (re-)activate all slaves.
        self._master_was_fg: bool = False

        # Target cache: hwnd → focused child HWND for keyboard events.
        # Pre-computed outside hook thread to avoid expensive IPC per keystroke.
        self._target_cache: dict = {}
        self._cache_lock = threading.Lock()

        # WM_MOUSEMOVE throttle counter (per-engine, not per-slave).
        self._mousemove_skip_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def events_sent(self) -> int:
        return self._events_sent

    @property
    def dead_removed(self) -> int:
        return self._dead_removed

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def scale_coords(self) -> bool:
        return self._scale_coords

    @scale_coords.setter
    def scale_coords(self, value: bool) -> None:
        self._scale_coords = value

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_master(self, hwnd: Optional[int]) -> None:
        with self._lock:
            self._master_hwnd = hwnd

    def get_master(self) -> Optional[int]:
        with self._lock:
            return self._master_hwnd

    def is_master_valid(self) -> bool:
        with self._lock:
            m = self._master_hwnd
        return m is not None and bool(user32.IsWindow(m))

    def set_slaves(self, hwnds: list) -> None:
        with self._lock:
            self._slave_hwnds = list(hwnds)
        # New slave list → force re-activation on next foreground event
        self._master_was_fg = False
        # Rebuild target cache asynchronously so the hook thread has fresh data
        threading.Thread(target=self._rebuild_target_cache, daemon=True).start()

    def get_slaves(self) -> list:
        with self._lock:
            return list(self._slave_hwnds)

    def slave_count(self) -> int:
        with self._lock:
            return len(self._slave_hwnds)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        self._paused = False
        self._events_sent = 0
        self._dead_removed = 0
        self._master_was_fg = False  # triggers activation on first fg event
        self._mousemove_skip_count = 0
        self._sender.reset()
        # Pre-build target cache before hooks start so first keystroke is cached
        threading.Thread(target=self._rebuild_target_cache, daemon=True).start()
        self._hooks.on_mouse = self._on_mouse
        self._hooks.on_keyboard = self._on_keyboard
        self._hooks.start()

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        self._hooks.on_mouse = None
        self._hooks.on_keyboard = None
        self._hooks.stop()
        self._sender.reset()
        self._master_was_fg = False
        with self._cache_lock:
            self._target_cache.clear()

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False
        self._sender.reset()

    def toggle_pause(self) -> None:
        with self._lock:
            self._paused = not self._paused
        if not self._paused:
            self._sender.reset()

    # ------------------------------------------------------------------
    # Hook callbacks (run on the hook thread)
    # ------------------------------------------------------------------

    def _on_mouse(self, msg_type: int, screen_x: int, screen_y: int,
                  mouse_data: int) -> None:
        # Always track button state regardless of focus.
        # If a button is released outside master the state must still update
        # so the next wParam sent to slaves is correct (no "phantom held button").
        self._sender.update_buttons(msg_type)

        if msg_type not in MOUSE_EVENTS:
            return

        # Throttle WM_MOUSEMOVE: skip every other event to prevent slave message
        # queue overflow when running 10+ windows (each move → N PostMessages).
        if msg_type == WM_MOUSEMOVE:
            self._mousemove_skip_count += 1
            if self._mousemove_skip_count % (_MOUSEMOVE_SKIP + 1) != 0:
                return

        # Single lock — consistent snapshot of paused + master + slave list.
        with self._lock:
            if self._paused:
                return
            master = self._master_hwnd
            slaves = list(self._slave_hwnds)

        if master is None or not user32.IsWindow(master):
            return

        fg = user32.GetForegroundWindow()
        if fg != master:
            self._master_was_fg = False
            return

        # Master just gained foreground → re-activate all background slaves
        # so Chrome/Edge start processing our PostMessage input.
        if not self._master_was_fg:
            self._master_was_fg = True
            self._activate_slaves(slaves)

        client_x, client_y = screen_to_client(master, screen_x, screen_y)

        dead: list = []

        if self._scale_coords:
            mw, mh = get_client_size(master)
            if mw <= 0 or mh <= 0:
                return
            rel_x = client_x / mw
            rel_y = client_y / mh
            for hwnd in slaves:
                if not user32.IsWindow(hwnd):
                    dead.append(hwnd)
                    continue
                if user32.IsIconic(hwnd):
                    continue
                sw, sh = get_client_size(hwnd)
                # Scroll → render widget (same as keyboard); other mouse → top-level
                target = self._get_target(hwnd) if msg_type == WM_MOUSEWHEEL else hwnd
                self._sender.send_mouse(target, msg_type,
                                        int(rel_x * sw), int(rel_y * sh),
                                        mouse_data)
                self._events_sent += 1
        else:
            for hwnd in slaves:
                if not user32.IsWindow(hwnd):
                    dead.append(hwnd)
                    continue
                if user32.IsIconic(hwnd):
                    continue
                # Scroll → render widget (same as keyboard); other mouse → top-level
                target = self._get_target(hwnd) if msg_type == WM_MOUSEWHEEL else hwnd
                self._sender.send_mouse(target, msg_type,
                                        client_x, client_y, mouse_data)
                self._events_sent += 1

        if dead:
            self._purge_dead_slaves(dead)

    def _on_keyboard(self, msg_type: int, vk_code: int, scan_code: int,
                     flags: int) -> None:
        if msg_type not in KEY_EVENTS:
            return

        with self._lock:
            if self._paused:
                return
            master = self._master_hwnd
            slaves = list(self._slave_hwnds)

        if master is None or not user32.IsWindow(master):
            return

        fg = user32.GetForegroundWindow()
        if fg != master:
            self._master_was_fg = False
            return

        if not self._master_was_fg:
            self._master_was_fg = True
            self._activate_slaves(slaves)

        dead: list = []

        for hwnd in slaves:
            if not user32.IsWindow(hwnd):
                dead.append(hwnd)
                continue
            if user32.IsIconic(hwnd):
                continue
            # Keyboard → route to the focused child window (e.g. render widget).
            # Use pre-computed cache to avoid expensive IPC in the hook hot-path.
            target = self._get_target(hwnd)
            self._sender.send_key(target, msg_type, vk_code, scan_code, flags)
            self._events_sent += 1

        if dead:
            self._purge_dead_slaves(dead)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _activate_slaves(self, slaves: list) -> None:
        """Initial activation of slave windows on master foreground transition.

        Sends WM_ACTIVATE(WA_ACTIVE) to each slave's top-level window so that
        Chrome draws its title bar as active and initialises internal state.

        Note: we intentionally do NOT send WM_SETFOCUS here.  Per-slave
        WM_SETFOCUS is now sent by InputSender.send_key() immediately before
        every WM_KEYDOWN in the message queue, which correctly handles the
        case where multiple Chrome windows share one browser process / UI thread.
        Sending WM_SETFOCUS in bulk here would leave only the last slave focused.
        """
        for hwnd in slaves:
            if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                continue
            user32.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0)
        # Rebuild cache ~500ms after activation to pick up newly focused children
        threading.Timer(0.5, self._rebuild_target_cache).start()

    def _rebuild_target_cache(self) -> None:
        """Pre-compute hwnd→child mappings for all current slaves.

        Calls find_input_child (GetGUIThreadInfo + optional EnumChildWindows)
        for each slave outside the hook thread so the hook callback can do
        an O(1) dict lookup instead of expensive per-keystroke IPC.
        """
        with self._lock:
            slaves = list(self._slave_hwnds)

        new_cache = {}
        for hwnd in slaves:
            if user32.IsWindow(hwnd):
                new_cache[hwnd] = find_input_child(hwnd)

        with self._cache_lock:
            self._target_cache = new_cache

    def _get_target(self, hwnd: int) -> int:
        """O(1) cache lookup for the keyboard-input child of hwnd.

        Falls back to hwnd itself if no entry in cache (e.g. newly added slave).
        """
        with self._cache_lock:
            return self._target_cache.get(hwnd, hwnd)

    def refresh_target_cache(self) -> None:
        """Public method for GUI timer to trigger periodic cache rebuilds."""
        if self._active:
            threading.Thread(target=self._rebuild_target_cache, daemon=True).start()

    def _purge_dead_slaves(self, dead: list) -> None:
        """Remove destroyed HWNDs from the slave list and target cache.

        Windows recycles HWNDs: a dead handle can be reassigned to a different
        window.  Keeping it would send events to the wrong application.
        """
        with self._lock:
            for hwnd in dead:
                try:
                    self._slave_hwnds.remove(hwnd)
                    self._dead_removed += 1
                except ValueError:
                    pass
        with self._cache_lock:
            for hwnd in dead:
                self._target_cache.pop(hwnd, None)
