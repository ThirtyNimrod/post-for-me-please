from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import frontmatter


def _brain_root() -> Path:
    return Path(os.environ.get("BRAIN_PATH", ".brain"))


def read_brain_files(
    days_back: int = 7,
    skip_paths: Iterable[str] | None = None,
) -> list[dict]:
    """Return brain markdown files modified in the last `days_back` days.

    Excludes files where `shareable: false` and files whose POSIX path is in
    `skip_paths`. Each result is `{"path": str, "frontmatter": dict, "content": str}`.
    """
    root = _brain_root()
    if not root.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    skip = set(skip_paths or [])
    out: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        key = path.as_posix()
        if key in skip:
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue
        try:
            post = frontmatter.load(path)
        except Exception:
            continue
        meta = dict(post.metadata or {})
        if meta.get("shareable") is False:
            continue
        out.append({
            "path": key,
            "frontmatter": meta,
            "content": post.content,
        })
    return out


def format_brain_files(files: list[dict]) -> str:
    """Render brain files as readable plain text, one block per file, '---' separated.

    Plain text rather than JSON because Copilot reasons better over prose when the
    content itself is markdown notes — JSON is for structured lookups, not for
    making sense of human-written takeaways.
    """
    blocks: list[str] = []
    for f in files:
        meta = f["frontmatter"]
        kind = meta.get("type", "note")
        tags = meta.get("tags") or []
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        header_lines = [
            f"path: {f['path']}",
            f"type: {kind}",
            f"tags: {tags_str}",
        ]
        if "date" in meta:
            header_lines.append(f"date: {meta['date']}")
        if "title" in meta:
            header_lines.append(f"title: {meta['title']}")
        blocks.append("\n".join(header_lines) + "\n\n" + f["content"].strip())
    return "\n\n---\n\n".join(blocks)
