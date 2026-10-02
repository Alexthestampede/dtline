"""Update check: daily-cached, stderr-only, never blocks or crashes."""

import os
import re
import threading
import time
from pathlib import Path

PYPROJECT_URL = "https://raw.githubusercontent.com/Alexthestampede/dtline/master/pyproject.toml"


def _cache_path() -> Path:
    home = Path(os.environ.get("DTLINE_HOME", os.path.expanduser("~/.local/dtline")))
    return home / ".update_check"


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


def check_for_updates(current_version: str, check_interval: float = 86400.0) -> None:
    """Run at most once per check_interval. Writes notice to stderr only.

    Never raises: any failure (offline, parse, cache) is silently ignored.
    """
    try:
        if os.environ.get("DTLINE_NO_UPDATE_CHECK") == "1":
            return

        cache = _cache_path()
        now = time.time()
        if cache.exists() and now - cache.stat().st_mtime < check_interval:
            return

        # Touch cache immediately so parallel/failed runs don't re-check
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.touch()

        latest = _fetch_latest_version()
        if not latest:
            return
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
    """Fire the check in a daemon thread so CLI startup is never delayed."""
    t = threading.Thread(
        target=check_for_updates, args=(current_version,), daemon=True
    )
    t.start()