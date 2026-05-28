"""HN Algolia search. No auth. Highest-points story in last 30 days for the tag set."""

from __future__ import annotations

import time
from typing import TypedDict

import requests


class HNHit(TypedDict):
    hn_thread_title: str | None
    hn_thread_url: str | None


_API = "https://hn.algolia.com/api/v1/search"


def search(tags: list[str], title: str, timeout: float = 8.0) -> HNHit:
    if not tags and not title:
        return {"hn_thread_title": None, "hn_thread_url": None}

    query = " ".join(tags[:3]) if tags else title
    thirty_days_ago = int(time.time()) - 30 * 86400

    try:
        r = requests.get(
            _API,
            params={
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{thirty_days_ago}",
                "hitsPerPage": 5,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except Exception:
        return {"hn_thread_title": None, "hn_thread_url": None}

    stories = [h for h in hits if h.get("points") is not None]
    if not stories:
        return {"hn_thread_title": None, "hn_thread_url": None}

    top = max(stories, key=lambda h: h.get("points", 0))
    return {
        "hn_thread_title": top.get("title"),
        "hn_thread_url": f"https://news.ycombinator.com/item?id={top.get('objectID')}",
    }


if __name__ == "__main__":
    import json
    import sys
    args = sys.argv[1:] or ["langgraph", "state"]
    print(json.dumps(search(args, " ".join(args)), indent=2))
