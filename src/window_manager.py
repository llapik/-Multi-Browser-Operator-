"""Window enumeration and management for discovering and tracking OS windows."""

import ctypes
import ctypes.wintypes as wt

from .winapi import user32, GUITHREADINFO


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

    def get_client_rect(self) -> tuple:
        """Return (left, top, right, bottom) of client area in screen coords."""
        rect = wt.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        pt_tl = wt.POINT(rect.left, rect.top)
        pt_br = wt.POINT(rect.right, rect.bottom)
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt_tl))
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt_br))
        return pt_tl.x, pt_tl.y, pt_br.x, pt_br.y

    def get_client_size(self) -> tuple:
        """Return (width, height) of the client area."""
        rect = wt.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top


def get_client_size(hwnd: int) -> tuple:
    """Return (width, height) of a window's client area without creating WindowInfo."""
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def enumerate_windows(min_title_len: int = 1) -> list:
    """Return a list of all visible top-level windows with a title."""
    results = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _enum_callback(hwnd, _lparam):
        # IsWindowVisible checks both the window's own visibility and parent chain
        if not user32.IsWindowVisible(hwnd):
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


def screen_to_client(hwnd: int, x: int, y: int) -> tuple:
    """Convert screen coordinates to client-area coordinates."""
    pt = wt.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def client_to_screen(hwnd: int, x: int, y: int) -> tuple:
    """Convert client-area coordinates to screen coordinates."""
    pt = wt.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


# Class names used by Chromium and Firefox for their input render widgets.
# These are the windows that actually process WM_KEYDOWN in background tabs.
_RENDER_WIDGET_CLASSES = frozenset({
    'Chrome_RenderWidgetHostHWND',
    'Chrome_ChildContentWnd',
    'MozillaCompositorWindowClass',
})


def _find_render_widget(hwnd: int) -> int:
    """Search child windows for a known browser render-widget class.

    Used as a fallback when GetGUIThreadInfo returns hwndFocus=NULL
    (e.g. cold-start browser that has never received a click).

    Returns the first matching child HWND, or 0 if none found.
    """
    found = [0]

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _callback(child_hwnd, _lparam):
        cls_buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(child_hwnd, cls_buf, 64)
        if cls_buf.value in _RENDER_WIDGET_CLASSES:
            found[0] = child_hwnd
            return False  # stop enumeration
        return True  # continue

    user32.EnumChildWindows(hwnd, _callback, 0)
    return found[0]


def find_input_child(hwnd: int) -> int:
    """Return the child window that should receive keyboard input for hwnd.

    Modern browsers (Chrome, Edge, Firefox) use a multi-process architecture
    where the actual input-handling window is a deeply nested child
    (e.g. Chrome_RenderWidgetHostHWND), not the top-level HWND.

    When a browser is in the background its Windows focus chain is inactive,
    but the browser's own GUI thread still tracks which child had focus last.
    GetGUIThreadInfo() exposes that per-thread focus state, letting us
    address the right child even for windows that are not in the foreground.

    Falls back to EnumChildWindows class-name search for cold-start windows
    where hwndFocus is NULL (browser opened but never interacted with).

    Returns hwnd unchanged if no suitable child is found.
    """
    pid = wt.DWORD()
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not thread_id:
        return hwnd

    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    if user32.GetGUIThreadInfo(thread_id, ctypes.byref(gti)):
        focus = gti.hwndFocus
        # Accept any child that is a real window and different from the top-level
        if focus and focus != hwnd and user32.IsWindow(focus):
            return focus

    # Fallback: enumerate children looking for known render-widget class names.
    # Handles cold-start browsers that have never received a click/focus event.
    widget = _find_render_widget(hwnd)
    if widget:
        return widget

    return hwnd
