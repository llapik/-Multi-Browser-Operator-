"""Launch multiple independent incognito browser instances with separate sessions.

Each instance gets its own --user-data-dir (Chrome/Edge/Brave/Opera) or
--profile (Firefox), stored under %TEMP%\mbo_sessions\.  This guarantees
that cookies, logins, and localStorage are fully isolated between instances.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Base directory for all session profiles
_SESSIONS_BASE = Path(os.environ.get("TEMP", "C:/Temp")) / "mbo_sessions"

# Supported browsers: name → configuration dict
#   exes      - candidate executable paths (first found wins)
#   private   - flag to enable private/incognito mode
#   profile   - flag prefix for a custom profile directory
#   extra     - additional flags for clean first-launch experience
#   no_remote - True for Firefox: needed to allow multiple separate instances
_BROWSERS: dict = {
    "Google Chrome": {
        "exes": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "private": "--incognito",
        "profile": "--user-data-dir",
        "extra": ["--no-first-run", "--no-default-browser-check", "--disable-sync"],
        "no_remote": False,
    },
    "Microsoft Edge": {
        "exes": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ],
        "private": "--inprivate",
        "profile": "--user-data-dir",
        "extra": ["--no-first-run", "--no-default-browser-check"],
        "no_remote": False,
    },
    "Mozilla Firefox": {
        "exes": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "private": "--private-window",
        "profile": "--profile",
        "extra": ["--no-remote"],  # required for multiple simultaneous instances
        "no_remote": True,
    },
    "Brave": {
        "exes": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ],
        "private": "--incognito",
        "profile": "--user-data-dir",
        "extra": ["--no-first-run", "--no-default-browser-check", "--disable-sync"],
        "no_remote": False,
    },
    "Opera": {
        "exes": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
            r"C:\Program Files\Opera\launcher.exe",
        ],
        "private": "--private",
        "profile": "--user-data-dir",
        "extra": ["--no-first-run"],
        "no_remote": False,
    },
}


class BrowserLauncher:
    """Launch and track independent incognito browser instances."""

    def __init__(self):
        self._processes: list = []
        self._session_dirs: list = []

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def available_browsers() -> list:
        """Return names of browsers whose executables are present on this PC."""
        return [
            name for name, cfg in _BROWSERS.items()
            if any(os.path.isfile(p) for p in cfg["exes"])
        ]

    @staticmethod
    def find_exe(browser_name: str) -> Optional[str]:
        """Return the first existing executable path for the given browser."""
        cfg = _BROWSERS.get(browser_name)
        if not cfg:
            return None
        for path in cfg["exes"]:
            if os.path.isfile(path):
                return path
        return None

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def launch(self, browser_name: str, count: int,
               url: str = "", start_index: Optional[int] = None) -> int:
        """Launch `count` independent incognito instances.

        Each instance gets a unique session directory so it has its own
        cookies, localStorage, and saved passwords — fully isolated.

        Args:
            browser_name: Key from the _BROWSERS dict (e.g. "Google Chrome").
            count:        Number of new instances to open.
            url:          Optional URL to open in each instance.
            start_index:  Index of the first session directory (auto if None).

        Returns:
            Number of processes actually started.
        """
        cfg = _BROWSERS.get(browser_name)
        exe = self.find_exe(browser_name)
        if not cfg or not exe:
            return 0

        _SESSIONS_BASE.mkdir(parents=True, exist_ok=True)
        slug = browser_name.lower().replace(" ", "_")

        if start_index is None:
            start_index = len(self._processes) + 1

        launched = 0
        for i in range(start_index, start_index + count):
            session_dir = _SESSIONS_BASE / f"{slug}_{i:03d}"
            session_dir.mkdir(parents=True, exist_ok=True)

            cmd = [exe, cfg["private"]]
            cmd.append(f"{cfg['profile']}={session_dir}")
            cmd.extend(cfg["extra"])
            if url:
                cmd.append(url)

            try:
                proc = subprocess.Popen(cmd)
                self._processes.append(proc)
                self._session_dirs.append(session_dir)
                launched += 1
            except OSError:
                pass

        return launched

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    @property
    def launched_count(self) -> int:
        """Number of browser processes that are still running."""
        return sum(1 for p in self._processes if p.poll() is None)

    @property
    def total_launched(self) -> int:
        """Total number of processes ever launched in this session."""
        return len(self._processes)

    def close_all(self):
        """Terminate all launched browser processes."""
        for proc in self._processes:
            try:
                proc.terminate()
            except OSError:
                pass
        self._processes.clear()

    def cleanup_sessions(self, remove_dirs: bool = True):
        """Remove session profile directories (wipes all cookies/logins).

        Call this only after close_all(), otherwise the browser may be
        writing to the directory and deletion could fail or corrupt data.
        """
        if remove_dirs:
            for d in self._session_dirs:
                if isinstance(d, Path) and d.exists():
                    shutil.rmtree(d, ignore_errors=True)
        self._session_dirs.clear()
