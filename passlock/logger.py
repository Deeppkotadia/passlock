"""
PassLock logger — Activity log and password history with auto-purge.

Stores logs and password history in a JSON file inside the user's
platform-appropriate data directory.
"""

import hashlib
import json
import os
import platform
from datetime import datetime, timedelta
from pathlib import Path

# ── Data directory ────────────────────────────────────────────────────

def _data_dir() -> Path:
    """Return the platform-specific data directory for PassLock."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "PassLock"
    d.mkdir(parents=True, exist_ok=True)
    return d


_LOG_FILE = "activity_log.json"
_HISTORY_FILE = "password_history.json"

# ── Purge schedule options ────────────────────────────────────────────

PURGE_OPTIONS = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "never": None,
}

# ── Activity logger ──────────────────────────────────────────────────

def _load_json(filename: str) -> list | dict:
    path = _data_dir() / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return [] if filename == _LOG_FILE else {}
    return [] if filename == _LOG_FILE else {}


def _save_json(filename: str, data: list | dict) -> None:
    path = _data_dir() / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def log_activity(action: str, target: str, result: str) -> None:
    """Append an activity entry with timestamp."""
    entries = _load_json(_LOG_FILE)
    if not isinstance(entries, list):
        entries = []
    entries.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "target": str(target),
        "result": result,
    })
    _save_json(_LOG_FILE, entries)


def get_activity_log() -> list[dict]:
    """Return all activity log entries."""
    entries = _load_json(_LOG_FILE)
    return entries if isinstance(entries, list) else []


def clear_activity_log() -> None:
    """Clear the entire activity log."""
    _save_json(_LOG_FILE, [])


def purge_old_entries(schedule: str) -> int:
    """Remove log entries older than the given schedule. Returns count removed."""
    days = PURGE_OPTIONS.get(schedule)
    if days is None:
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    entries = get_activity_log()
    original_count = len(entries)
    kept = []
    for e in entries:
        try:
            ts = datetime.strptime(e.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
            if ts >= cutoff:
                kept.append(e)
        except ValueError:
            kept.append(e)
    _save_json(_LOG_FILE, kept)
    return original_count - len(kept)


# ── Password history (hashed, per-file) ──────────────────────────────
# We store a SHA-256 hash of the password — never the plaintext.

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def save_password_entry(target: str, password: str) -> None:
    """Save a hashed password entry for a file/folder path."""
    history = _load_json(_HISTORY_FILE)
    if not isinstance(history, dict):
        history = {}
    key = str(target)
    if key not in history:
        history[key] = []
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "password_hash": _hash_password(password),
    }
    # Avoid duplicate consecutive entries for the same hash
    if not history[key] or history[key][-1]["password_hash"] != entry["password_hash"]:
        history[key].append(entry)
    _save_json(_HISTORY_FILE, history)


def get_password_history() -> dict:
    """Return the full password history {path: [entries]}."""
    data = _load_json(_HISTORY_FILE)
    return data if isinstance(data, dict) else {}


def verify_password(target: str, password: str) -> bool:
    """Check if a password matches the latest stored hash for a target."""
    history = _load_json(_HISTORY_FILE)
    if not isinstance(history, dict):
        return False
    entries = history.get(str(target), [])
    if not entries:
        return False
    return entries[-1]["password_hash"] == _hash_password(password)


def clear_password_history() -> None:
    """Clear all password history."""
    _save_json(_HISTORY_FILE, {})


def get_purge_schedule() -> str:
    """Read the saved purge schedule preference."""
    settings_path = _data_dir() / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            return data.get("purge_schedule", "never")
        except (json.JSONDecodeError, OSError):
            pass
    return "never"


def set_purge_schedule(schedule: str) -> None:
    """Save the purge schedule preference."""
    if schedule not in PURGE_OPTIONS:
        raise ValueError(f"Invalid schedule: {schedule}. Choose from {list(PURGE_OPTIONS.keys())}")
    settings_path = _data_dir() / "settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}
    settings["purge_schedule"] = schedule
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def auto_purge() -> int:
    """Run purge based on the saved schedule. Returns count removed."""
    schedule = get_purge_schedule()
    return purge_old_entries(schedule)
