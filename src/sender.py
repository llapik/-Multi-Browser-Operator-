"""Send input events to slave windows via PostMessage."""

import ctypes.wintypes as wt

from .winapi import (
    user32,
    MAKELPARAM,
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
    WM_CHAR,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
    MK_LBUTTON,
    MK_RBUTTON,
    MK_MBUTTON,
)

# Map mouse-down messages to the button-state flags for wParam
_BUTTON_DOWN_STATE: dict[int, int] = {
    WM_LBUTTONDOWN: MK_LBUTTON,
    WM_RBUTTONDOWN: MK_RBUTTON,
    WM_MBUTTONDOWN: MK_MBUTTON,
}


class InputSender:
    """Sends replicated input events to a set of slave windows."""

    def __init__(self):
        self._pressed_buttons: int = 0  # Track currently held mouse buttons

    def send_mouse(self, hwnd: int, msg_type: int, client_x: int, client_y: int,
                   wheel_delta: int = 0):
        """Send a mouse event to a target window.

        Args:
            hwnd: Target window handle.
            msg_type: WM_MOUSEMOVE, WM_LBUTTONDOWN, etc.
            client_x: X coordinate relative to client area.
            client_y: Y coordinate relative to client area.
            wheel_delta: Wheel delta for WM_MOUSEWHEEL events.
        """
        if not user32.IsWindow(hwnd):
            return

        lparam = MAKELPARAM(client_x, client_y)

        if msg_type in _BUTTON_DOWN_STATE:
            self._pressed_buttons |= _BUTTON_DOWN_STATE[msg_type]
        elif msg_type == WM_LBUTTONUP:
            self._pressed_buttons &= ~MK_LBUTTON
        elif msg_type == WM_RBUTTONUP:
            self._pressed_buttons &= ~MK_RBUTTON
        elif msg_type == WM_MBUTTONUP:
            self._pressed_buttons &= ~MK_MBUTTON

        if msg_type == WM_MOUSEWHEEL:
            wparam = MAKELPARAM(self._pressed_buttons, wheel_delta)
        elif msg_type in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP,
                          WM_RBUTTONDOWN, WM_RBUTTONUP,
                          WM_MBUTTONDOWN, WM_MBUTTONUP):
            wparam = self._pressed_buttons
        else:
            wparam = 0

        user32.PostMessageW(hwnd, msg_type, wparam, lparam)

    def send_key(self, hwnd: int, msg_type: int, vk_code: int, scan_code: int,
                 flags: int = 0):
        """Send a keyboard event to a target window.

        Args:
            hwnd: Target window handle.
            msg_type: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP.
            vk_code: Virtual key code.
            scan_code: Hardware scan code.
            flags: Key flags.
        """
        if not user32.IsWindow(hwnd):
            return

        # Build lParam for keyboard messages:
        # Bits 0-15: repeat count (1)
        # Bits 16-23: scan code
        # Bit 24: extended key flag
        # Bit 29: context code (1 for SYSKEYDOWN)
        # Bit 30: previous key state
        # Bit 31: transition state (0=pressed, 1=released)
        extended = 1 if (flags & 0x01) else 0  # LLKHF_EXTENDED
        is_up = msg_type in (WM_KEYUP, WM_SYSKEYUP)
        is_alt = msg_type in (WM_SYSKEYDOWN, WM_SYSKEYUP)

        lparam = 1  # repeat count
        lparam |= (scan_code & 0xFF) << 16
        lparam |= extended << 24
        if is_alt:
            lparam |= 1 << 29
        if is_up:
            lparam |= 1 << 30  # previous state = down
            lparam |= 1 << 31  # transition = releasing

        user32.PostMessageW(hwnd, msg_type, vk_code, lparam)

        # Also send WM_CHAR for keydown of printable characters
        if msg_type == WM_KEYDOWN and 0x20 <= vk_code <= 0x7E:
            user32.PostMessageW(hwnd, WM_CHAR, vk_code, lparam)

    def reset(self):
        """Reset tracked button state."""
        self._pressed_buttons = 0
