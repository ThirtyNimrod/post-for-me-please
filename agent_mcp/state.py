from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _state_file() -> Path:
    return Path(os.environ.get("STATE_FILE", "brain_agent_state.json"))


def load_state() -> dict:
    """Return {"last_run": ISO string | None, "processed_files": [...]}.

    Missing or unreadable state files yield an empty default rather than
    raising — the agent treats every brain file as new on first run.
    """
    path = _state_file()
    if not path.exists():
        return {"last_run": None, "processed_files": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"last_run": None, "processed_files": []}
    data.setdefault("last_run", None)
    data.setdefault("processed_files", [])
    return data


def save_state(processed_files: list[str]) -> None:
    """Merge `processed_files` into the existing set and update `last_run`."""
    current = load_state()
    seen = set(current.get("processed_files") or [])
    seen.update(processed_files)
    out = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "processed_files": sorted(seen),
    }
    _state_file().write_text(json.dumps(out, indent=2), encoding="utf-8")
