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

    Captures input from the master window and replicates it to all slave windows.
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
        self._scale_coords = False  # Proportional coordinate scaling

        # Statistics — accessed from both hook thread and GUI thread.
        # Python's GIL guarantees atomic int reads, but we use the lock
        # for writes that happen alongside other state changes.
        self._events_sent = 0

    @property
    def events_sent(self) -> int:
        return self._events_sent

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
    def scale_coords(self, value: bool):
        self._scale_coords = value

    def set_master(self, hwnd: Optional[int]):
        with self._lock:
            self._master_hwnd = hwnd

    def get_master(self) -> Optional[int]:
        return self._master_hwnd

    def set_slaves(self, hwnds: list):
        with self._lock:
            self._slave_hwnds = list(hwnds)

    def get_slaves(self) -> list:
        with self._lock:
            return list(self._slave_hwnds)

    def start(self):
        if self._active:
            return
        self._active = True
        self._paused = False
        self._sender.reset()
        self._hooks.on_mouse = self._on_mouse
        self._hooks.on_keyboard = self._on_keyboard
        self._hooks.start()

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._hooks.on_mouse = None
        self._hooks.on_keyboard = None
        self._hooks.stop()
        self._sender.reset()

    def pause(self):
        with self._lock:
            self._paused = True

    def resume(self):
        with self._lock:
            self._paused = False
        self._sender.reset()

    def toggle_pause(self):
        with self._lock:
            self._paused = not self._paused
        if not self._paused:
            self._sender.reset()

    def _on_mouse(self, msg_type: int, screen_x: int, screen_y: int,
                  mouse_data: int):
        # Read paused flag under lock to avoid race with GUI thread
        with self._lock:
            if self._paused:
                return

        if msg_type not in MOUSE_EVENTS:
            return

        master = self._master_hwnd
        if master is None or not user32.IsWindow(master):
            return

        # Only replicate when the master window is in the foreground
        if user32.GetForegroundWindow() != master:
            return

        # Convert screen coords to master client coords
        client_x, client_y = screen_to_client(master, screen_x, screen_y)

        with self._lock:
            slaves = list(self._slave_hwnds)

        if self._scale_coords:
            mw, mh = get_client_size(master)
            if mw <= 0 or mh <= 0:
                return
            rel_x = client_x / mw
            rel_y = client_y / mh

            for hwnd in slaves:
                if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                    continue
                sw, sh = get_client_size(hwnd)
                sx = int(rel_x * sw)
                sy = int(rel_y * sh)
                self._sender.send_mouse(hwnd, msg_type, sx, sy, mouse_data)
                self._events_sent += 1
        else:
            for hwnd in slaves:
                if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                    continue
                self._sender.send_mouse(hwnd, msg_type, client_x, client_y,
                                        mouse_data)
                self._events_sent += 1

    def _on_keyboard(self, msg_type: int, vk_code: int, scan_code: int,
                     flags: int):
        with self._lock:
            if self._paused:
                return

        if msg_type not in KEY_EVENTS:
            return

        master = self._master_hwnd
        if master is None or not user32.IsWindow(master):
            return

        if user32.GetForegroundWindow() != master:
            return

        with self._lock:
            slaves = list(self._slave_hwnds)

        for hwnd in slaves:
            # Skip destroyed or minimized slave windows (consistent with mouse)
            if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                continue
            self._sender.send_key(hwnd, msg_type, vk_code, scan_code, flags)
            self._events_sent += 1
