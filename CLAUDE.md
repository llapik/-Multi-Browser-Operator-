# CLAUDE.md — Multi-Browser Operator

This file provides guidance for AI assistants (Claude, Copilot, etc.) working in this repository.

---

## Project Overview

**Multi-Browser Operator** is a Windows desktop application for synchronous control of multiple windows. The user designates one "master" window — all mouse movements, clicks, scrolling, and keyboard input are replicated in real time to any number of "slave" windows.

**Primary use case:** Running the same actions across 15–20 browser instances simultaneously (e.g., filling forms, clicking through surveys, navigating pages on multiple accounts at once).

**Platform:** Windows 10/11 only (uses Win32 API directly via ctypes).

---

## Repository Layout

```
-Multi-Browser-Operator-/
├── CLAUDE.md              # This file — AI assistant guidance
├── LICENSE                # MIT License (Copyright 2026 llapik)
├── README.md              # User-facing documentation (Russian)
├── requirements.txt       # Python dependencies (PyQt5, PyInstaller)
├── run.py                 # Convenience launcher (run from project root)
├── build.bat              # PyInstaller build script → dist/MultiBrowserOperator.exe
├── .gitignore             # Standard ignores for Python/IDE/OS
└── src/
    ├── __init__.py
    ├── main.py            # Entry point (alternative to run.py)
    ├── winapi.py          # Win32 API ctypes definitions and constants
    ├── window_manager.py  # Window enumeration, coordinate conversion
    ├── hooks.py           # Low-level mouse/keyboard hooks (WH_MOUSE_LL, WH_KEYBOARD_LL)
    ├── sender.py          # Input replication via PostMessage to slave windows
    ├── engine.py          # Sync engine — coordinates hooks ↔ sender
    ├── gui.py             # PyQt5 GUI with system tray support
    └── config.py          # JSON config persistence (mbo_config.json)
```

---

## Architecture

### Module Dependencies

```
gui.py  →  engine.py  →  hooks.py    (captures input from master)
                       →  sender.py   (replicates input to slaves)
                       →  window_manager.py  (coordinate conversion)
        →  config.py   (settings persistence)

All modules  →  winapi.py  (shared Win32 API definitions)
```

### How Synchronization Works

1. **Hooks thread** — `hooks.py` installs global low-level hooks (`WH_MOUSE_LL`, `WH_KEYBOARD_LL`) in a dedicated thread running a Win32 message pump.
2. **Event filtering** — `engine.py` checks if the foreground window is the master. If not, the event is ignored.
3. **Coordinate conversion** — Screen coordinates are converted to master client-area coordinates. Optionally, proportional scaling maps them to differently-sized slave windows.
4. **Replication** — `sender.py` sends events to each slave via `PostMessageW`. This is non-blocking and does not steal focus from the master.
5. **Feedback prevention** — PostMessage-based input does not trigger `WH_MOUSE_LL` hooks, so no feedback loops occur.

### Threading Model

| Thread | Responsibility |
|---|---|
| Main (GUI) thread | PyQt5 event loop, user interaction |
| Hook thread | Win32 message pump, `SetWindowsHookEx` callbacks |

Shared state (master HWND, slave list) is protected by `threading.Lock` in `engine.py`.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| GUI | PyQt5 (Fusion style) |
| Win32 API | ctypes (no pywin32 dependency) |
| Config | JSON (`mbo_config.json`) |
| Packaging | PyInstaller (single-file `.exe`) |

---

## Development Conventions

### Code Style

- Python 3.10+ with type hints on public APIs.
- No external linter configured yet — follow PEP 8 conventions.
- Prefer explicit over implicit; use named constants (defined in `winapi.py`).
- Keep functions small and single-purpose.
- Only add comments where logic is not self-evident (Win32 API calls, bitwise operations).

### Win32 API Guidelines

- All ctypes definitions live in `winapi.py` — do not scatter `ctypes.windll` calls across modules.
- Always set `.argtypes` and `.restype` for every Win32 function to catch type errors early.
- Use `MAKELPARAM`, `HIWORD`, etc. helpers from `winapi.py` for packing/unpacking message params.

### Error Handling

- Handle errors at system boundaries (Win32 calls, file I/O).
- Hook callbacks must never raise — wrap in `try/except` with silent pass (a crash in a hook callback can freeze the system).
- Check `IsWindow()` before sending messages to a window handle.

### Security

- Never commit `mbo_config.json` (in `.gitignore`).
- No network access — this is a purely local desktop tool.
- PostMessage-based input replication is the safest approach (no `SendInput` focus-stealing).

---

## Getting Started

### Prerequisites

- Windows 10/11
- Python 3.10 or newer
- pip

### Install & Run

```bash
# Clone
git clone <repo-url>
cd -Multi-Browser-Operator-

# Install dependencies
pip install -r requirements.txt

# Run
python run.py
```

### Build Standalone .exe

```bash
# On Windows
build.bat

# Or manually:
pyinstaller --noconfirm --onefile --windowed --name MultiBrowserOperator run.py
```

The output is `dist/MultiBrowserOperator.exe`.

### Usage Flow

1. Launch the app.
2. Click **"Обновить список окон"** to refresh the window list.
3. Select a row and click **"Назначить выбранное"** to set the master window.
4. Check the boxes next to slave windows.
5. Click **"Старт"** — all input in the master is now replicated to slaves.
6. Press **F8** to pause/resume synchronization.
7. Close the window to minimize to system tray; right-click tray icon to quit.

---

## Git Workflow

### Branches

| Branch pattern | Purpose |
|---|---|
| `master` | Stable, production-ready code |
| `claude/<task-id>` | AI-assisted development branches |
| `feature/<name>` | Human-driven feature development |
| `fix/<name>` | Bug fixes |

### Commit Messages

Use short, imperative commit messages:

```
Add multi-browser session manager
Fix race condition in hook thread shutdown
Refactor coordinate scaling logic
```

- Present tense, imperative mood ("Add", not "Added" or "Adds")
- 72 characters max for the subject line

### Push Rules

- Never force-push to `master`.
- Claude branches must start with `claude/`.
- Always push with `-u`: `git push -u origin <branch>`.

---

## Working with AI Assistants

### Do

- Read existing code before suggesting modifications.
- Make only the changes directly requested or clearly necessary.
- Keep all Win32 API definitions in `winapi.py`.
- Test on Windows — this project cannot run on Linux/macOS.

### Avoid

- Do not create files unless absolutely necessary.
- Do not add abstractions for hypothetical future requirements.
- Do not refactor working Win32 hook/sender code without a concrete reason.
- Do not introduce additional threading without careful consideration of the hook callback constraints.

---

## Known Limitations & Future Work

- **PostMessage vs SendInput:** Some applications may ignore PostMessage-based input. A future `SendInput` mode could handle these cases (at the cost of focus-stealing).
- **DPI scaling:** High-DPI displays may affect coordinate mapping. Not yet handled.
- **Global hotkey:** F8 pause only works when the app window has focus. A global hotkey (`RegisterHotKey`) would improve usability.
- **Window size mismatch:** Proportional scaling mode exists but is opt-in. Default is 1:1 coordinate mapping.

---

## License

MIT — see [LICENSE](./LICENSE) for full terms.
