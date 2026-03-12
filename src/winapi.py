"""Windows API definitions via ctypes for input hooking and window management."""

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# --- Window message constants ---
WM_QUIT = 0x0012
WM_ACTIVATE = 0x0006      # wParam: WA_ACTIVE / WA_INACTIVE
WM_SETFOCUS = 0x0007      # sent to window gaining keyboard focus
WM_KILLFOCUS = 0x0008     # sent to window losing keyboard focus
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

# WM_ACTIVATE wParam values
WA_INACTIVE = 0
WA_ACTIVE = 1

# --- Hook constants ---
WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13

# Injected-event flags for low-level hook structs.
# IMPORTANT: the bit positions differ between mouse and keyboard hooks.
# Mouse (MSLLHOOKSTRUCT.flags):    LLMHF_INJECTED = bit 0 (0x01)
# Keyboard (KBDLLHOOKSTRUCT.flags): LLKHF_INJECTED = bit 4 (0x10)
LLMHF_INJECTED = 0x00000001   # mouse event injected via SendInput or similar
LLKHF_INJECTED = 0x00000010   # keyboard event injected via SendInput or similar

# --- Mouse event flags ---
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010

# --- Window style flags ---
GWL_STYLE = -16
WS_VISIBLE = 0x10000000
WS_MINIMIZE = 0x20000000

# --- Virtual key codes ---
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12   # Alt
VK_CAPITAL = 0x14  # Caps Lock

# --- Structures ---
# ULONG_PTR is a pointer-sized unsigned integer (4 bytes on x86, 8 bytes on x64).
# ctypes.c_size_t matches this on both architectures.
ULONG_PTR = ctypes.c_size_t


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wt.POINT),
        ("mouseData", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


# --- Hook callback types ---
HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_int, wt.WPARAM, wt.LPARAM)

# --- Function prototypes ---

# Hooks
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.UnhookWindowsHookEx.restype = wt.BOOL

user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_long

# Message loop
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.TranslateMessage.restype = wt.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = wt.LONG

user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostThreadMessageW.restype = wt.BOOL

# Window functions
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL

user32.EnumChildWindows.argtypes = [wt.HWND, ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.EnumChildWindows.restype = wt.BOOL

user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL

user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL

user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL

user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetClientRect.restype = wt.BOOL

user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.ClientToScreen.restype = wt.BOOL

user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.ScreenToClient.restype = wt.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wt.HWND

user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.WPARAM]
user32.PostMessageW.restype = wt.BOOL

user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.WPARAM]
user32.SendMessageW.restype = wt.LONG

user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD

user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL

user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wt.LONG

kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wt.DWORD

# Keyboard state — GetKeyState returns the state of a key at message-processing time.
# HIGH bit (bit 15) set = key is down. Bit 0 = toggled state (Caps Lock etc.).
# Returns SHORT (signed 16-bit).
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short

# MapVirtualKeyW: translate virtual key code ↔ scan code ↔ character value.
# MAPVK_VK_TO_CHAR (=2): return the Unicode character produced by the key
# ignoring modifier keys; high bit set if dead key.
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
user32.MapVirtualKeyW.restype = wt.UINT

# GetGUIThreadInfo — returns GUI focus/capture state for any thread.
# Used to find the focused child window inside a background browser process
# (e.g. Chrome_RenderWidgetHostHWND) so keyboard events reach the right target.
class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",      wt.DWORD),
        ("flags",       wt.DWORD),
        ("hwndActive",  wt.HWND),
        ("hwndFocus",   wt.HWND),   # <-- child that has keyboard focus
        ("hwndCapture", wt.HWND),
        ("hwndMenuOwner", wt.HWND),
        ("hwndMoveSize",  wt.HWND),
        ("hwndCaret",   wt.HWND),
        ("rcCaret",     wt.RECT),
    ]

user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wt.BOOL


def MAKELPARAM(low, high):
    """Pack two 16-bit values into a 32-bit LPARAM (unsigned)."""
    return (high & 0xFFFF) << 16 | (low & 0xFFFF)


def GET_WHEEL_DELTA(wparam):
    """Extract wheel delta from MOUSEWHEEL wParam (high word, signed)."""
    return ctypes.c_short((wparam >> 16) & 0xFFFF).value


def HIWORD(dword):
    """Extract high 16-bit word (signed)."""
    return ctypes.c_short(((dword & 0xFFFFFFFF) >> 16) & 0xFFFF).value
