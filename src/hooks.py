"""Low-level mouse and keyboard hooks using SetWindowsHookEx."""

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Callable, Optional

from .winapi import (
    user32,
    kernel32,
    HOOKPROC,
    MSLLHOOKSTRUCT,
    KBDLLHOOKSTRUCT,
    WH_MOUSE_LL,
    WH_KEYBOARD_LL,
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
    HIWORD,
)

# Extra info marker to identify our own injected events (avoid feedback loops)
INJECTED_FLAG = 1

# Callback signature: (msg_type, x, y, mouse_data) for mouse
#                     (msg_type, vk_code, scan_code, flags) for keyboard
MouseCallback = Callable[[int, int, int, int], None]
KeyboardCallback = Callable[[int, int, int, int], None]

WM_QUIT = 0x0012


class InputHooks:
    """Manages low-level mouse and keyboard hooks in a background thread."""

    def __init__(self):
        self._mouse_hook: Optional[int] = None
        self._kb_hook: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self.on_mouse: Optional[MouseCallback] = None
        self.on_keyboard: Optional[KeyboardCallback] = None
        # Must keep references to prevent garbage collection
        self._mouse_proc: Optional[HOOKPROC] = None
        self._kb_proc: Optional[HOOKPROC] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._hook_thread, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None
        self._thread_id = None

    def _hook_thread(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        h_module = kernel32.GetModuleHandleW(None)

        self._mouse_proc = HOOKPROC(self._mouse_callback)
        self._kb_proc = HOOKPROC(self._kb_callback)

        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, h_module, 0
        )
        self._kb_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._kb_proc, h_module, 0
        )

        msg = wt.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        if self._kb_hook:
            user32.UnhookWindowsHookEx(self._kb_hook)
            self._kb_hook = None

    def _mouse_callback(self, ncode, wparam, lparam):
        if ncode >= 0 and self.on_mouse is not None:
            data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            # Skip injected events (from SendInput etc.)
            if not (data.flags & INJECTED_FLAG):
                mouse_data = HIWORD(data.mouseData) if wparam == WM_MOUSEWHEEL else 0
                try:
                    self.on_mouse(wparam, data.pt.x, data.pt.y, mouse_data)
                except Exception:
                    pass
        return user32.CallNextHookEx(self._mouse_hook, ncode, wparam, lparam)

    def _kb_callback(self, ncode, wparam, lparam):
        if ncode >= 0 and self.on_keyboard is not None:
            data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not (data.flags & INJECTED_FLAG):
                try:
                    self.on_keyboard(wparam, data.vkCode, data.scanCode, data.flags)
                except Exception:
                    pass
        return user32.CallNextHookEx(self._kb_hook, ncode, wparam, lparam)
