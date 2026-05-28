from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from ..state import EnrichmentResult, PostableContext
from ..tools import arxiv, hackernews
from ..tools.fetch import fetch_page
from ..tools.github import search_repos

log = logging.getLogger(__name__)

# Docs domains where a search path can be inferred from the candidate title
_DOCS_HINT_DOMAINS = {
    "langchain-ai.github.io",
    "python.langchain.com",
    "docs.python.org",
    "developer.mozilla.org",
}


def enrich_node(state: dict) -> dict:
    """Enrich a single PostableContext with external data.

    Receives a sub-state injected by Send() containing only {"candidate": ...}.
    All tool calls run in parallel via ThreadPoolExecutor.
    Failures return None/empty fields — never raise.

    Reads:  state["candidate"]
    Writes: appends one enriched PostableContext to enriched_candidates
    """
    candidate: PostableContext = state["candidate"]
    title = candidate.get("title", "")
    thesis = candidate.get("thesis", "")
    has_paper = candidate.get("has_paper", False)

    log.info("[enrich] Starting enrichment for candidate: %r", title)
    log.info("[enrich]   thesis: %s", thesis[:120])
    log.info("[enrich]   has_paper=%s", has_paper)

    query = f"{title} {thesis}".strip()[:120]

    # ── Parallel tool calls ────────────────────────────────────────────────
    tasks: dict[str, callable] = {
        "hn": lambda: hackernews.search(query),
        "repos": lambda: search_repos(title),
    }

    # Docs fetch — try to infer a docs URL from title keywords
    docs_url = _infer_docs_url(title, thesis)
    if docs_url:
        tasks["docs"] = lambda u=docs_url: fetch_page(u, max_chars=2000)

    # arXiv — only for known research concepts
    if has_paper:
        tasks["arxiv"] = lambda: arxiv.search(title)

    log.info("[enrich] Running tools: %s", list(tasks.keys()))

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
                log.info("[enrich] tool=%s  result_len=%d", key, len(results[key] or ""))
            except Exception as exc:
                log.warning("[enrich] tool=%s  FAILED: %s", key, exc)
                results[key] = ""

    # ── Parse tool results into EnrichmentResult ─────────────────────────
    hn_raw = results.get("hn", "")
    hn_title, hn_url = _parse_first_hn_result(hn_raw)

    repos_raw = results.get("repos", "")
    repo_list = _parse_repo_list(repos_raw)

    arxiv_raw = results.get("arxiv", "")
    arxiv_title, arxiv_url = _parse_first_arxiv_result(arxiv_raw)

    docs_raw = results.get("docs", "")
    docs_summary = docs_raw[:600] if docs_raw and not docs_raw.startswith("(") else None

    enrichment: EnrichmentResult = {
        "hn_thread_title": hn_title,
        "hn_thread_url": hn_url,
        "github_repos": repo_list,
        "arxiv_title": arxiv_title,
        "arxiv_url": arxiv_url,
        "docs_summary": docs_summary,
        "docs_url": docs_url if docs_summary else None,
    }

    log.info(
        "[enrich] Done. hn=%r  repos=%d  arxiv=%r  docs=%s",
        hn_title,
        len(repo_list),
        arxiv_title,
        "yes" if docs_summary else "no",
    )
    enriched = {**candidate, "enrichment": enrichment}
    return {"enriched_candidates": [enriched]}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _infer_docs_url(title: str, thesis: str) -> str | None:
    """Try to return a relevant LangGraph docs URL from the candidate text."""
    text = f"{title} {thesis}".lower()
    # Only attempt for LangGraph concepts — extend this list as needed
    if "langgraph" in text:
        slug_map = {
            "interrupt": "concepts/human_in_the_loop",
            "send": "concepts/low_level",
            "reducer": "concepts/low_level",
            "state": "concepts/low_level",
            "checkpoint": "concepts/persistence",
            "memory": "concepts/memory",
            "streaming": "concepts/streaming",
            "subgraph": "concepts/subgraphs",
        }
        for keyword, path in slug_map.items():
            if keyword in text:
                return f"https://langchain-ai.github.io/langgraph/{path}/"
    return None


def _parse_first_hn_result(raw: str) -> tuple[str | None, str | None]:
    if not raw or raw.startswith("("):
        return None, None
    # Format: '1. "Title" — N pts, ...\n   URL'
    title_match = re.search(r'"([^"]+)"', raw)
    url_match = re.search(r"https?://\S+", raw)
    return (
        title_match.group(1) if title_match else None,
        url_match.group(0) if url_match else None,
    )


def _parse_repo_list(raw: str) -> list[str]:
    if not raw or raw.startswith("("):
        return []
    # Format: "1. owner/repo — N,NNN stars\n   desc\n   url"
    repos = re.findall(r"\d+\.\s+(\S+/\S+)\s+—\s+([\d,]+)\s+stars", raw)
    return [f"{name} ({stars.replace(',', '')} stars)" for name, stars in repos]


def _parse_first_arxiv_result(raw: str) -> tuple[str | None, str | None]:
    if not raw or raw.startswith("("):
        return None, None
    lines = raw.strip().splitlines()
    title = lines[0].lstrip("0123456789. ") if lines else None
    url_match = re.search(r"https?://arxiv\.org/\S+", raw)
    return title or None, url_match.group(0) if url_match else None
