"""scan_brain — walk .brain/, filter by mtime + shareable, return raw content."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import frontmatter

from agent.state import AgentState
from agent.state_store import load as load_run_state


def _brain_root() -> Path:
    return Path(os.environ.get("BRAIN_PATH", ".brain"))


def _is_shareable(meta: dict) -> bool:
    """Default to True when key absent — only an explicit `shareable: false` blocks."""
    val = meta.get("shareable", True)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() not in {"false", "no", "0"}
    return True


def scan_brain(state: AgentState) -> dict:
    root = _brain_root()
    if not root.exists():
        return {"brain_files": [], "raw_file_contents": {}, "error": f"BRAIN_PATH {root} does not exist"}

    run = load_run_state()
    last_run = datetime.fromisoformat(run["last_run"])
    processed = set(run["processed_files"])

    selected: dict[str, str] = {}

    for path in sorted(root.rglob("*.md")):
        rel = path.as_posix()

        if rel in processed:
            continue

        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=last_run.tzinfo)
        if mtime < last_run:
            continue

        try:
            raw = path.read_text(encoding="utf-8")
            meta, _ = frontmatter.parse(raw)
        except Exception:
            # Malformed frontmatter — skip rather than crash the whole run.
            continue

        if not _is_shareable(meta):
            continue

        # Keep frontmatter in the text so downstream prompts see tags/type/title.
        selected[rel] = raw

    return {
        "brain_files": list(selected.keys()),
        "raw_file_contents": selected,
    }
