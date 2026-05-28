"""Persistent run-state on disk. Tracks last_run + processed_files across cron runs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict


class RunState(TypedDict):
    last_run: str               # ISO8601 with tz
    processed_files: list[str]  # paths already turned into posts


def _state_path() -> Path:
    return Path(os.environ.get("STATE_FILE", "brain_agent_state.json"))


def load() -> RunState:
    path = _state_path()
    if not path.exists():
        lookback = int(os.environ.get("LOOKBACK_DAYS", "7"))
        seed = datetime.now(timezone.utc) - timedelta(days=lookback)
        return {"last_run": seed.isoformat(), "processed_files": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(state: RunState) -> None:
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def mark_run(processed: list[str]) -> None:
    """Update state after a successful run: bump last_run, append processed paths."""
    cur = load()
    seen = set(cur["processed_files"])
    seen.update(processed)
    save({
        "last_run": datetime.now(timezone.utc).isoformat(),
        "processed_files": sorted(seen),
    })
