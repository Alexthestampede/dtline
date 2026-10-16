"""Update check: daily-cached, stderr-only, never blocks or crashes.

Reliability across fast subcommands: the slot only advances on a SUCCESSFUL
fetch. A fast command that exits before the daemon-thread fetch completes
burns neither the 24h day-slot nor the process: the next invocation retries
(at most once per retry_interval, so offline machines don't hammer).
"""

import json
import os
import re
import threading
import time
from pathlib import Path

PYPROJECT_URL = "https://raw.githubusercontent.com/Alexthestampede/dtline/master/pyproject.toml"
CHECK_INTERVAL = 86400.0  # successful check stays valid for 24h
RETRY_INTERVAL = 3600.0  # re-attempt failed checks at most hourly

_SUCCESS = "last_success"
_ATTEMPT = "last_attempt"


def _cache_path() -> Path:
    home = Path(os.environ.get("DTLINE_HOME", os.path.expanduser("~/.local/dtline")))
    return home / ".update_check"


def _read_state() -> dict:
    try:
        raw = json.loads(_cache_path().read_text())
        return {k: float(raw[k]) for k in (_SUCCESS, _ATTEMPT) if k in raw}
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
    except Exception:
        pass


def _parse_version(v: str) -> tuple:
    """Parse calendar version 'YYYYMMDD.N' into a comparable tuple."""
    parts = v.strip().split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return (0,)


def _fetch_latest_version(timeout: float = 4.0) -> str | None:
    import urllib.request

    with urllib.request.urlopen(PYPROJECT_URL, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def check_for_updates(
    current_version: str,
    check_interval: float = CHECK_INTERVAL,
    retry_interval: float = RETRY_INTERVAL,
) -> None:
    """Run at most once per check_interval (successful fetches only).

    Never raises: any failure (offline, parse, cache) is silently ignored.
    The notice goes to stderr only, keeping stdout JSON-clean.
    """
    try:
        if os.environ.get("DTLINE_NO_UPDATE_CHECK") == "1":
            return

        now = time.time()
        state = _read_state()
        if state.get(_SUCCESS, 0) > now - check_interval:
            return
        if state.get(_ATTEMPT, 0) > now - retry_interval:
            return

        # Record the attempt BEFORE fetching: if this process exits mid-fetch
        # (fast subcommands kill the daemon thread), the retry throttle still
        # holds and the day-slot is NOT consumed.
        _write_state({**state, _ATTEMPT: now})

        latest = _fetch_latest_version()
        if not latest:
            return
        _write_state({**state, _ATTEMPT: now, _SUCCESS: time.time()})
        if _parse_version(latest) > _parse_version(current_version):
            import sys

            print(
                f"\nNOTE: dtline {current_version} is outdated. "
                f"Latest version: {latest} — update: git pull in the install dir.",
                file=sys.stderr,
            )
    except Exception:
        pass


def start_update_check(current_version: str) -> None:
    """Fire the check in a daemon thread so a crash never hangs the CLI."""
    global _thread
    _thread = threading.Thread(
        target=check_for_updates, args=(current_version,), daemon=True
    )
    _thread.start()


_thread: threading.Thread | None = None


def finish_update_check(join_timeout: float = 3.0) -> None:
    """At CLI exit, wait briefly for an in-flight check to complete.

    Only waits when a check is actually due (thread still running): done or
    throttled checks return instantly. Keeps fast subcommands reliable —
    without this, they'd exit before the fetch lands and the notice would
    effectively only ever appear on long-running commands.
    """
    t = _thread
    if t is not None and t.is_alive():
        t.join(join_timeout)