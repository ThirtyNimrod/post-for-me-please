"""arXiv search. Only invoked when context.has_paper=True. Atom XML response."""

from __future__ import annotations

from typing import TypedDict
from urllib.parse import quote

import feedparser
import requests


class ArxivHit(TypedDict):
    arxiv_title: str | None
    arxiv_url: str | None


_API = "https://export.arxiv.org/api/query"


def search(tags: list[str], title: str, timeout: float = 8.0) -> ArxivHit:
    if not (tags or title):
        return {"arxiv_title": None, "arxiv_url": None}

    q_title = quote(title.replace('"', ""))
    q_abs = quote(tags[0]) if tags else q_title
    query = f"ti:{q_title}+OR+abs:{q_abs}"

    try:
        r = requests.get(
            _API,
            params={"search_query": query, "max_results": 1, "sortBy": "relevance"},
            timeout=timeout,
        )
        r.raise_for_status()
        feed = feedparser.parse(r.text)
    except Exception:
        return {"arxiv_title": None, "arxiv_url": None}

    if not feed.entries:
        return {"arxiv_title": None, "arxiv_url": None}

    e = feed.entries[0]
    # arXiv links: e.id is the abs URL, e.title is the paper title.
    return {
        "arxiv_title": (e.get("title") or "").replace("\n", " ").strip(),
        "arxiv_url": e.get("id"),
    }


if __name__ == "__main__":
    import json
    import sys
    args = sys.argv[1:] or ["tool-use"]
    print(json.dumps(search(args, " ".join(args)), indent=2))
