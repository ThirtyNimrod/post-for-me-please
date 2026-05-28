"""LangGraph docs + GitHub release notes lookup.

Two outputs:
- docs_url + docs_summary: a relevant docs page summarised by the LLM
- changelog_note: a release note line that mentions the topic, if any
"""

from __future__ import annotations

import re
from typing import TypedDict

import requests
from langchain_core.messages import HumanMessage

from agent.llm_manager import LLMManager
from agent.prompts import DOCS_SUMMARISE_PROMPT


class DocsHit(TypedDict):
    docs_url: str | None
    docs_summary: str | None
    changelog_note: str | None


_DOCS_BASE = "https://langchain-ai.github.io/langgraph/"
_RELEASES_API = "https://api.github.com/repos/langchain-ai/langgraph/releases?per_page=5"


def _fetch_text(url: str, timeout: float = 8.0) -> str | None:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        # Strip HTML tags crudely — good enough for summarisation input.
        text = re.sub(r"<script.*?</script>", "", r.text, flags=re.S)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000] if text else None
    except Exception:
        return None


def _summarise(url: str, content: str) -> str | None:
    try:
        llm = LLMManager.for_docs_summary()
        msg = HumanMessage(content=DOCS_SUMMARISE_PROMPT.format(url=url, content=content))
        resp = llm.invoke([msg])
        return resp.content.strip() if hasattr(resp, "content") else None
    except Exception:
        return None


def _fetch_changelog(tags: list[str], title: str, timeout: float = 8.0) -> str | None:
    try:
        r = requests.get(_RELEASES_API, timeout=timeout)
        r.raise_for_status()
        releases = r.json()
    except Exception:
        return None

    needles = [t.lower() for t in tags] + [w.lower() for w in title.split() if len(w) > 4]
    for rel in releases[:5]:
        body = (rel.get("body") or "")
        body_lc = body.lower()
        for n in needles:
            if n and n in body_lc:
                # Pull the matching line.
                for line in body.splitlines():
                    if n in line.lower():
                        return f"{rel.get('name') or rel.get('tag_name')}: {line.strip()}"
        # Fall back to title-only match.
        if any(n in (rel.get("name") or "").lower() for n in needles):
            return f"{rel.get('name')}: {(body.splitlines() or [''])[0].strip()}"

    return None


def search(tags: list[str], title: str, related_docs: str | None = None) -> DocsHit:
    if related_docs:
        url = related_docs
    elif tags:
        # Best-effort: try docs root with the tag as a path hint.
        url = f"{_DOCS_BASE}reference/{tags[0].replace('-', '_')}/"
    else:
        url = _DOCS_BASE

    content = _fetch_text(url) or _fetch_text(_DOCS_BASE)
    docs_summary = _summarise(url, content) if content else None
    docs_url = url if docs_summary else (_DOCS_BASE if content else None)
    changelog_note = _fetch_changelog(tags, title)

    return {
        "docs_url": docs_url,
        "docs_summary": docs_summary,
        "changelog_note": changelog_note,
    }


if __name__ == "__main__":
    import json
    import sys
    args = sys.argv[1:] or ["langgraph", "state"]
    print(json.dumps(search(args, " ".join(args)), indent=2))
