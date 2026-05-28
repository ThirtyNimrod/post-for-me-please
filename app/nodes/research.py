from __future__ import annotations

import json
import logging

from slugify import slugify

from ..llm import call_llm
from ..prompts import RESEARCH_PROMPT, RESEARCH_SYSTEM
from ..state import GraphState, PostableContext
from ..tools.fetch import fetch_page

log = logging.getLogger(__name__)

MAX_CANDIDATES = 5
MAX_CHARS_PER_PAGE = 10_000  # ~7–8 pages of article text; models handle 200k+ tokens


def research_node(state: GraphState) -> dict:
    """Fetch reference URLs and extract postable topic candidates.

    Reads:  reference_urls, intent, audience
    Writes: raw_source_content, candidates
    """
    urls = (state.get("reference_urls") or [])[:3]  # enforce ≤3
    intent = state.get("intent", "")
    audience = state.get("audience", "engineers")

    log.info("[research] Starting. intent=%r  audience=%r  urls=%s", intent, audience, urls)

    # ── 1. Fetch each reference page ─────────────────────────────────────────
    sections: list[str] = []
    for url in urls:
        log.info("[research] Fetching %s", url)
        content = fetch_page(url, max_chars=MAX_CHARS_PER_PAGE)
        log.info("[research] Fetched %d chars from %s", len(content), url)
        sections.append(f"=== SOURCE: {url} ===\n{content}")

    source_content = "\n\n".join(sections)

    # ── 2. Call LLM to extract candidates ────────────────────────────────────
    prompt = RESEARCH_PROMPT.format(
        intent=intent,
        audience=audience,
        source_content=source_content,
    )

    log.info("[research] Calling LLM to extract topic candidates …")
    raw = call_llm(
        prompt,
        system=RESEARCH_SYSTEM,
        max_tokens=3000,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    log.info("[research] LLM raw response (first 800 chars):\n%s", raw[:800])

    # ── 3. Parse and validate JSON response ──────────────────────────────────
    candidates: list[PostableContext] = _parse_candidates(raw)

    # Enforce slug uniqueness and cap
    seen_ids: set[str] = set()
    clean: list[PostableContext] = []
    for c in candidates[:MAX_CANDIDATES]:
        slug = slugify(c.get("title", "topic"))
        while slug in seen_ids:
            slug = slug + "-2"
        seen_ids.add(slug)
        c["id"] = slug
        clean.append(c)

    log.info("[research] Parsed %d candidates:", len(clean))
    for c in clean:
        log.info("  • [%s] %s — %s", c.get("id"), c.get("title"), c.get("thesis", "")[:120])

    return {
        "raw_source_content": source_content,
        "candidates": clean,
    }


def _parse_candidates(raw: str) -> list[PostableContext]:
    """Parse LLM JSON response into a list of PostableContext dicts."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract a JSON array from the response if it's wrapped
        import re
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    # LLM may return {"candidates": [...]} or a bare array
    if isinstance(data, dict):
        for key in ("candidates", "topics", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = list(data.values())[0] if data else []

    if not isinstance(data, list):
        return []

    out: list[PostableContext] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            PostableContext(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                thesis=str(item.get("thesis", "")),
                source_excerpt=str(item.get("source_excerpt", "")),
                has_paper=bool(item.get("has_paper", False)),
                has_mistake_angle=bool(item.get("has_mistake_angle", False)),
                enrichment={
                    "hn_thread_title": None,
                    "hn_thread_url": None,
                    "github_repos": [],
                    "arxiv_title": None,
                    "arxiv_url": None,
                    "docs_summary": None,
                    "docs_url": None,
                },
                posts=[],
            )
        )
    return out
