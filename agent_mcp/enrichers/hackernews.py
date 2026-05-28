from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

ALGOLIA = "https://hn.algolia.com/api/v1/search"


def search(query: str, days_back: int = 30) -> str:
    """Return the top 3 HN stories matching `query` from the last `days_back` days."""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff}",
        "hitsPerPage": 3,
    }
    try:
        r = requests.get(ALGOLIA, params=params, timeout=10)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except Exception as e:
        return f"(hackernews search failed: {e})"
    if not hits:
        return ""
    lines: list[str] = []
    for i, h in enumerate(hits, 1):
        title = h.get("title") or h.get("story_title") or "(untitled)"
        pts = h.get("points") or 0
        comments = h.get("num_comments") or 0
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        lines.append(
            f'{i}. "{title}" — {pts} pts, {comments} comments\n   {url}'
        )
    return "\n\n".join(lines)
