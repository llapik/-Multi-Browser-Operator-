"""Sync engine: coordinates input capture from master and replication to slaves."""

import threading
from typing import Optional

from .winapi import (
    user32,
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
from .window_manager import screen_to_client, get_client_size

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
        # GUI reads this to show a warning.
        self._dead_removed: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def events_sent(self) -> int:
        return self._events_sent

    @property
    def dead_removed(self) -> int:
        """Total dead slave HWNDs auto-purged since last start()."""
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
        """Return True if the master HWND is set and the window still exists."""
        with self._lock:
            m = self._master_hwnd
        return m is not None and bool(user32.IsWindow(m))

    def set_slaves(self, hwnds: list) -> None:
        with self._lock:
            self._slave_hwnds = list(hwnds)

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
        self._sender.reset()
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
        # ---------------------------------------------------------------
        # ALWAYS update button state, even when paused or out of focus.
        # If a button is released outside the master (e.g. user alt-tabs),
        # _pressed must reflect that release so the next wParam is correct.
        # Without this, slaves permanently believe a button is held down,
        # causing phantom drags and click failures ("stuck button" desync).
        # ---------------------------------------------------------------
        self._sender.update_buttons(msg_type)

        if msg_type not in MOUSE_EVENTS:
            return

        # Single lock acquisition — ensures master + slave list are a
        # consistent snapshot.  Previously two separate acquisitions allowed
        # the GUI thread to change state between reads.
        with self._lock:
            if self._paused:
                return
            master = self._master_hwnd
            slaves = list(self._slave_hwnds)

        if master is None or not user32.IsWindow(master):
            return

        if user32.GetForegroundWindow() != master:
            return

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
                self._sender.send_mouse(hwnd, msg_type,
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
                self._sender.send_mouse(hwnd, msg_type,
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

        if user32.GetForegroundWindow() != master:
            return

        dead: list = []

        for hwnd in slaves:
            if not user32.IsWindow(hwnd):
                dead.append(hwnd)
                continue
            if user32.IsIconic(hwnd):
                continue
            self._sender.send_key(hwnd, msg_type, vk_code, scan_code, flags)
            self._events_sent += 1

        if dead:
            self._purge_dead_slaves(dead)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _purge_dead_slaves(self, dead: list) -> None:
        """Remove destroyed window handles from the slave list.

        Windows can recycle HWNDs: a dead handle might be re-assigned to a
        completely different window.  Keeping dead handles would send mouse/
        keyboard events to the wrong application.
        """
        with self._lock:
            for hwnd in dead:
                try:
                    self._slave_hwnds.remove(hwnd)
                    self._dead_removed += 1
                except ValueError:
                    pass  # already removed by a concurrent call
