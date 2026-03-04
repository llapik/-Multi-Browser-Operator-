"""Window enumeration and management for discovering and tracking OS windows."""

import ctypes
import ctypes.wintypes as wt

from .winapi import user32, GWL_STYLE, WS_VISIBLE


class WindowInfo:
    """Holds metadata about a discovered window."""

    __slots__ = ("hwnd", "title", "class_name", "pid")

    def __init__(self, hwnd: int, title: str, class_name: str, pid: int):
        self.hwnd = hwnd
        self.title = title
        self.class_name = class_name
        self.pid = pid

    def __repr__(self):
        return f"WindowInfo(hwnd=0x{self.hwnd:08X}, title={self.title!r})"

    def is_valid(self) -> bool:
        return bool(user32.IsWindow(self.hwnd))

    def is_visible(self) -> bool:
        return bool(user32.IsWindowVisible(self.hwnd))

    def is_minimized(self) -> bool:
        return bool(user32.IsIconic(self.hwnd))

    def get_client_rect(self) -> tuple[int, int, int, int]:
        """Return (left, top, right, bottom) of client area in screen coords."""
        rect = wt.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        pt_tl = wt.POINT(rect.left, rect.top)
        pt_br = wt.POINT(rect.right, rect.bottom)
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt_tl))
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt_br))
        return pt_tl.x, pt_tl.y, pt_br.x, pt_br.y

    def get_client_size(self) -> tuple[int, int]:
        """Return (width, height) of the client area."""
        rect = wt.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top


def enumerate_windows(min_title_len: int = 1) -> list[WindowInfo]:
    """Return a list of all visible top-level windows with a title."""
    results: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _enum_callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if not (style & WS_VISIBLE):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length < min_title_len:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append(WindowInfo(hwnd, title, cls_buf.value, pid.value))
        return True

    user32.EnumWindows(_enum_callback, 0)
    return results


def get_foreground_hwnd() -> int:
    """Return the HWND of the currently focused window."""
    return user32.GetForegroundWindow()


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert screen coordinates to client-area coordinates."""
    pt = wt.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert client-area coordinates to screen coordinates."""
    pt = wt.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y
