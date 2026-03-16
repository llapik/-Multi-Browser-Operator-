"""Launch multiple independent browser instances with separate sessions.

Two launch modes:

Incognito mode (launch):
  Temporary profiles under %TEMP%\mbo_sessions\<browser>_NNN.
  Each run starts fresh — no saved logins or cookies.

Persistent mode (launch_group):
  Profiles stored permanently under %APPDATA%\MBO\profiles\<browser>\account_NNN.
  Cookies and logins survive between app restarts — no need to re-authenticate.
  Used for the "account groups" feature where each profile belongs to one account.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Temporary sessions (incognito launcher)
_SESSIONS_BASE = Path(os.environ.get("TEMP", "C:/Temp")) / "mbo_sessions"

# Persistent account profiles — survive between app restarts
_PROFILES_BASE = Path(os.environ.get("APPDATA", "C:/Users/User/AppData/Roaming")) / "MBO" / "profiles"

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
    """Launch and track independent browser instances.

    Supports two modes:
    - Incognito (launch): temporary %TEMP% profiles, fresh session each run.
    - Persistent (launch_group): permanent %APPDATA% profiles, saved logins.
    """

    def __init__(self):
        self._processes: list = []           # incognito launcher processes
        self._session_dirs: list = []        # incognito temp dirs
        self._group_procs: dict = {}         # group_id → list[subprocess.Popen]

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
    # Persistent account groups
    # ------------------------------------------------------------------

    @staticmethod
    def profile_dir(browser_name: str, account_index: int) -> Path:
        """Return the persistent profile directory for an account.

        The directory is created on first use and survives between runs,
        preserving cookies, logins, and localStorage.
        """
        slug = browser_name.lower().replace(" ", "_")
        return _PROFILES_BASE / slug / f"account_{account_index:03d}"

    def launch_group(self, group_id: str, browser_name: str,
                     account_indices: list, url: str = "") -> int:
        """Open browser windows for the given account indices with saved sessions.

        Unlike launch(), this does NOT use incognito mode, so each account's
        cookies and passwords persist between runs.  Profiles are stored in
        %APPDATA%\\MBO\\profiles\\<browser>\\account_NNN.

        Args:
            group_id:        Unique identifier string for this group (e.g. "1").
            browser_name:    Browser key (e.g. "Google Chrome").
            account_indices: List of account numbers to open (e.g. [1, 2, ..., 11]).
            url:             Optional URL to open in each window.

        Returns:
            Number of processes actually started.
        """
        cfg = _BROWSERS.get(browser_name)
        exe = self.find_exe(browser_name)
        if not cfg or not exe:
            return 0

        procs = []
        for idx in account_indices:
            profile = self.profile_dir(browser_name, idx)
            profile.mkdir(parents=True, exist_ok=True)

            cmd = [exe, f"{cfg['profile']}={profile}"]
            cmd.extend(cfg["extra"])
            # No --incognito / --private flag — we want persistent sessions
            if url:
                cmd.append(url)

            try:
                proc = subprocess.Popen(cmd)
                procs.append(proc)
            except OSError:
                pass

        self._group_procs[group_id] = procs
        return len(procs)

    def close_group(self, group_id: str) -> None:
        """Terminate all browser windows that belong to group_id."""
        for proc in self._group_procs.get(group_id, []):
            try:
                proc.terminate()
            except OSError:
                pass
        self._group_procs.pop(group_id, None)

    @staticmethod
    def delete_profile(browser_name: str, account_index: int) -> bool:
        """Delete the persistent profile directory for one account.

        This wipes all cookies, saved passwords, and history for that account.
        The browser must NOT be running when this is called, otherwise the
        deletion may fail or corrupt the profile.

        Returns True if the directory was deleted, False if it didn't exist.
        """
        d = BrowserLauncher.profile_dir(browser_name, account_index)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            return True
        return False

    @staticmethod
    def profile_exists(browser_name: str, account_index: int) -> bool:
        """Return True if a persistent profile already exists for this account."""
        return BrowserLauncher.profile_dir(browser_name, account_index).exists()

    def group_running_count(self, group_id: str) -> int:
        """Return number of still-running processes in the group."""
        return sum(
            1 for p in self._group_procs.get(group_id, [])
            if p.poll() is None
        )

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
        """Terminate all launched browser processes (incognito launcher only)."""
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
