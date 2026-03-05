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

# Map mouse-down messages to button-state flags
_BUTTON_DOWN_FLAGS = {
    WM_LBUTTONDOWN: MK_LBUTTON,
    WM_RBUTTONDOWN: MK_RBUTTON,
    WM_MBUTTONDOWN: MK_MBUTTON,
}

# Map mouse-up messages to button-state flags (for clearing)
_BUTTON_UP_FLAGS = {
    WM_LBUTTONUP: MK_LBUTTON,
    WM_RBUTTONUP: MK_RBUTTON,
    WM_MBUTTONUP: MK_MBUTTON,
}

# Virtual key codes that do NOT produce a printable character via WM_CHAR.
# Control-character VKs (BS, Tab, Enter, Space, Esc) are sent separately.
_NO_CHAR_VKS = frozenset({
    0x10, 0x11, 0x12,       # Shift, Ctrl, Alt
    0x13,                   # Pause
    0x14,                   # Caps Lock
    0x21, 0x22, 0x23, 0x24, # Page Up/Down, End, Home
    0x25, 0x26, 0x27, 0x28, # Arrow keys
    0x2C, 0x2D, 0x2E,       # Print Screen, Insert, Delete
    *range(0x70, 0x88),     # F1–F24
    0x90, 0x91,             # Num Lock, Scroll Lock
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,  # L/R Shift, Ctrl, Alt
    0x5B, 0x5C, 0x5D,       # L/R Win, Apps
})

_MAPVK_VK_TO_CHAR = 2


def _vk_to_char(vk_code: int) -> int:
    """Return Unicode code point for vk_code considering Shift/CapsLock.

    Uses MapVirtualKeyW — no dead-key side-effects, safe inside hook callbacks.
    Returns 0 if the key produces no printable character.
    """
    raw = user32.MapVirtualKeyW(vk_code, _MAPVK_VK_TO_CHAR)
    if not raw or (raw & 0x80000000):   # high bit = dead key
        return 0

    # A–Z: apply Shift XOR CapsLock for case
    if 0x41 <= raw <= 0x5A:
        shift_down = bool(user32.GetKeyState(VK_SHIFT) & 0x8000)
        caps_on = bool(user32.GetKeyState(VK_CAPITAL) & 0x0001)
        return raw if (shift_down ^ caps_on) else raw + 32  # upper vs lower

    # Digits/symbols: return unshifted character.  WM_KEYDOWN/UP carry the
    # correct vk_code, so shortcut-aware apps still handle them correctly.
    return raw


class InputSender:
    """Sends replicated input events to slave windows.

    Button state (which mouse buttons are currently held) must be kept
    accurate even when the user moves focus away from the master window.
    The engine must call update_buttons() for EVERY mouse event it receives,
    and call send_mouse() only for events inside the master.
    """

    def __init__(self):
        # Bitmask of currently-pressed mouse buttons (MK_LBUTTON etc.).
        # Must reflect reality at all times, not just "what we sent".
        self._pressed: int = 0

    # ------------------------------------------------------------------
    # State tracking (call for ALL mouse events, regardless of focus)
    # ------------------------------------------------------------------

    def update_buttons(self, msg_type: int) -> None:
        """Track which buttons are physically held, without sending anything.

        Must be called for every mouse event so that _pressed stays in sync
        with the real hardware state even when focus is not on the master.
        """
        if msg_type in _BUTTON_DOWN_FLAGS:
            self._pressed |= _BUTTON_DOWN_FLAGS[msg_type]
        elif msg_type in _BUTTON_UP_FLAGS:
            self._pressed &= ~_BUTTON_UP_FLAGS[msg_type]

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_mouse(self, hwnd: int, msg_type: int, client_x: int, client_y: int,
                   wheel_delta: int = 0) -> None:
        """Send a mouse event to hwnd using the current button state.

        Caller must have called update_buttons(msg_type) beforehand.
        """
        if not user32.IsWindow(hwnd):
            return

        lparam = MAKELPARAM(client_x, client_y)

        if msg_type == WM_MOUSEWHEEL:
            # wParam: LOWORD = button state, HIWORD = wheel delta (signed)
            wparam = MAKELPARAM(self._pressed, wheel_delta & 0xFFFF)
        else:
            wparam = self._pressed

        user32.PostMessageW(hwnd, msg_type, wparam, lparam)

    def send_key(self, hwnd: int, msg_type: int, vk_code: int, scan_code: int,
                 flags: int = 0) -> None:
        """Send a keyboard event to hwnd."""
        if not user32.IsWindow(hwnd):
            return

        # Build lParam keyboard bit-field (MSDN WM_KEYDOWN/WM_KEYUP spec):
        #   Bits  0–15: repeat count (1)
        #   Bits 16–23: scan code
        #   Bit  24:    extended-key flag (LLKHF_EXTENDED = bit 0 of hook flags)
        #   Bit  29:    context code (1 for SYSKEYDOWN/SYSKEYUP)
        #   Bit  30:    previous key state (1 = key was down)
        #   Bit  31:    transition state (0 = press, 1 = release)
        #
        # Bit 31 makes the value exceed INT32_MAX, so we use c_uint32 to avoid
        # ctypes OverflowError (PostMessageW argtypes use WPARAM = unsigned).
        extended = 1 if (flags & 0x01) else 0
        is_up = msg_type in (WM_KEYUP, WM_SYSKEYUP)
        is_alt = msg_type in (WM_SYSKEYDOWN, WM_SYSKEYUP)

        lparam = ctypes.c_uint32(
            1
            | ((scan_code & 0xFF) << 16)
            | (extended << 24)
            | ((1 << 29) if is_alt else 0)
            | ((1 << 30) if is_up else 0)
            | ((1 << 31) if is_up else 0)
        ).value

        user32.PostMessageW(hwnd, msg_type, vk_code, lparam)

        # Send WM_CHAR for printable keydowns (needed for text input in forms).
        # MapVirtualKeyW is used instead of ToUnicode to avoid modifying the
        # keyboard driver's dead-key state for the master window.
        if msg_type == WM_KEYDOWN:
            if vk_code in (0x08, 0x09, 0x0D, 0x1B, 0x20):
                # Control chars that TranslateMessage produces as WM_CHAR
                user32.PostMessageW(hwnd, WM_CHAR, vk_code, lparam)
            elif vk_code not in _NO_CHAR_VKS:
                char = _vk_to_char(vk_code)
                if char:
                    user32.PostMessageW(hwnd, WM_CHAR, char, lparam)

    def reset(self) -> None:
        """Reset button state (call when starting sync or resuming after pause)."""
        self._pressed = 0
