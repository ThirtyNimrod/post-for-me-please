from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import requests

API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}

# Concepts with genuine research provenance — only hit arXiv for these.
# Avoids wasting a round-trip on implementation learnings that aren't academic topics.
PAPER_CONCEPTS = frozenset({
    "react", "chain-of-thought", "cot", "rag", "retrieval-augmented",
    "rlhf", "reinforcement learning from human feedback",
    "lora", "low-rank adaptation", "attention mechanism",
    "tool use", "tool-use agents", "function calling",
    "planning", "self-consistency", "tree of thought",
})


def is_research_topic(text: str) -> bool:
    """Return True if the text contains a known research concept."""
    lower = text.lower()
    return any(concept in lower for concept in PAPER_CONCEPTS)


def search(query: str, max_results: int = 3) -> str:
    """Return top arXiv papers matching query.

    Returns an empty string if no results. Returns an error string on failure.
    """
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        r = requests.get(f"{API}?{urlencode(params)}", timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as e:
        return f"(arxiv search failed: {e})"

    entries = root.findall("a:entry", NS)
    if not entries:
        return ""

    blocks: list[str] = []
    for i, e in enumerate(entries, 1):
        title = (e.findtext("a:title", default="", namespaces=NS) or "").strip()
        summary = (e.findtext("a:summary", default="", namespaces=NS) or "").strip()
        url = ""
        for link in e.findall("a:link", NS):
            if link.get("rel") == "alternate":
                url = link.get("href") or ""
                break
        authors = [
            (a.findtext("a:name", default="", namespaces=NS) or "").strip()
            for a in e.findall("a:author", NS)
        ]
        authors_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        short = " ".join(summary.split())
        short = short[:400] + ("…" if len(short) > 400 else "")
        blocks.append(f"{i}. {title}\n   {authors_str}\n   {short}\n   {url}".rstrip())

    return "\n\n".join(blocks)


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "ReAct agent tool use"
    print(search(q))
