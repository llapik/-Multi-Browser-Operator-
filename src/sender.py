"""Send input events to slave windows via PostMessage."""

import ctypes
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
    VK_SHIFT,
    VK_CAPITAL,
)

# Map mouse-down messages to the button-state flags for wParam
_BUTTON_DOWN_STATE = {
    WM_LBUTTONDOWN: MK_LBUTTON,
    WM_RBUTTONDOWN: MK_RBUTTON,
    WM_MBUTTONDOWN: MK_MBUTTON,
}

# Virtual key codes that do NOT produce a character (modifiers, nav keys, etc.)
_NO_CHAR_VKS = frozenset({
    0x08,              # VK_BACK (Backspace — handled separately as WM_CHAR)
    0x09,              # VK_TAB  — idem
    0x0D,              # VK_RETURN — idem
    0x10, 0x11, 0x12,  # VK_SHIFT, VK_CONTROL, VK_MENU (Alt)
    0x13,              # VK_PAUSE
    0x14,              # VK_CAPITAL (Caps Lock)
    0x1B,              # VK_ESCAPE
    0x20,              # VK_SPACE — idem
    0x21, 0x22, 0x23, 0x24,  # Page Up/Down, End, Home
    0x25, 0x26, 0x27, 0x28,  # Arrow keys
    0x2C, 0x2D, 0x2E,        # Print Screen, Insert, Delete
    *range(0x70, 0x88),      # F1–F24
    0x90, 0x91,              # Num Lock, Scroll Lock
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,  # L/R Shift, Ctrl, Alt
    0x5B, 0x5C, 0x5D,        # L/R Win, Apps
})

# MapVirtualKeyW flag: VK → base Unicode character (unshifted)
_MAPVK_VK_TO_CHAR = 2


def _vk_to_char(vk_code: int) -> int:
    """Return the Unicode code point for vk_code, considering Shift/CapsLock.

    Uses MapVirtualKeyW (no dead-key side-effects, safe inside hook callbacks).
    Returns 0 if vk_code doesn't produce a printable character.
    """
    raw = user32.MapVirtualKeyW(vk_code, _MAPVK_VK_TO_CHAR)
    if not raw or (raw & 0x80000000):  # high bit = dead key
        return 0

    # For A–Z: apply Shift and Caps Lock to determine case
    if 0x41 <= raw <= 0x5A:
        shift_down = bool(user32.GetKeyState(VK_SHIFT) & 0x8000)
        caps_on = bool(user32.GetKeyState(VK_CAPITAL) & 0x0001)
        if shift_down ^ caps_on:
            return raw          # uppercase (already uppercase from MapVirtualKeyW)
        else:
            return raw + 32     # lowercase

    # For digits/symbols: apply Shift to pick the shifted character.
    # MapVirtualKeyW only returns the unshifted character; for the shifted
    # variant (e.g. '!' from '1') we check the shift state and use a
    # layout-specific lookup via VkKeyScanW in reverse.  This is complex and
    # layout-dependent, so we emit the unshifted character and let the
    # application re-interpret it.  The WM_KEYDOWN/WM_KEYUP pair is always
    # sent with the correct vk_code, so shortcut-aware apps handle it fine.
    return raw


class InputSender:
    """Sends replicated input events to a set of slave windows."""

    def __init__(self):
        self._pressed_buttons: int = 0  # Track currently held mouse buttons

    def send_mouse(self, hwnd: int, msg_type: int, client_x: int, client_y: int,
                   wheel_delta: int = 0):
        """Send a mouse event to a target window."""
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
            # wParam: LOWORD = button-state flags, HIWORD = wheel delta (signed)
            wparam = MAKELPARAM(self._pressed_buttons, wheel_delta & 0xFFFF)
        else:
            wparam = self._pressed_buttons

        user32.PostMessageW(hwnd, msg_type, wparam, lparam)

    def send_key(self, hwnd: int, msg_type: int, vk_code: int, scan_code: int,
                 flags: int = 0):
        """Send a keyboard event to a target window."""
        if not user32.IsWindow(hwnd):
            return

        # Build lParam bit-field for keyboard messages (Windows MSDN spec):
        #   Bits  0–15: repeat count (always 1)
        #   Bits 16–23: scan code
        #   Bit  24:    extended-key flag
        #   Bit  29:    context code (1 for SYSKEYDOWN/UP)
        #   Bit  30:    previous key state (1 = was down before this event)
        #   Bit  31:    transition state (0 = press, 1 = release)
        #
        # IMPORTANT: bit 31 set makes the value exceed INT32_MAX.
        # ctypes LPARAM is c_long (32-bit signed), so we must store the result
        # in a c_uint32 and pass it as an unsigned WPARAM to avoid OverflowError.
        extended = 1 if (flags & 0x01) else 0   # LLKHF_EXTENDED
        is_up = msg_type in (WM_KEYUP, WM_SYSKEYUP)
        is_alt = msg_type in (WM_SYSKEYDOWN, WM_SYSKEYUP)

        lparam = ctypes.c_uint32(
            1                           # repeat count
            | ((scan_code & 0xFF) << 16)
            | (extended << 24)
            | ((1 << 29) if is_alt else 0)
            | ((1 << 30) if is_up else 0)   # previous state = down
            | ((1 << 31) if is_up else 0)   # transition = releasing
        ).value

        # PostMessageW argtypes use WPARAM (unsigned) for both wParam and lParam
        # so large values like 0x80000001 pass through without OverflowError.
        user32.PostMessageW(hwnd, msg_type, vk_code, lparam)

        # Also send WM_CHAR for printable-character keydowns so that text
        # input in form fields works.  We use MapVirtualKeyW + GetKeyState
        # instead of ToUnicode to avoid modifying the dead-key state of the
        # master window's keyboard driver.
        if msg_type == WM_KEYDOWN:
            if vk_code in (0x08, 0x09, 0x0D, 0x1B, 0x20):
                # Control characters that produce WM_CHAR via TranslateMessage
                user32.PostMessageW(hwnd, WM_CHAR, vk_code, lparam)
            elif vk_code not in _NO_CHAR_VKS:
                char = _vk_to_char(vk_code)
                if char:
                    user32.PostMessageW(hwnd, WM_CHAR, char, lparam)

    def reset(self):
        """Reset tracked button state (call when starting or resuming)."""
        self._pressed_buttons = 0
