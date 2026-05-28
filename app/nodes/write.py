from __future__ import annotations

import json

from ..llm import call_llm
from ..prompts import WRITE_PROMPT, WRITE_SYSTEM
from ..state import EnrichmentResult, GraphState, PostableContext


def write_node(state: GraphState) -> dict:
    """Generate 3 LinkedIn post options (A/B/C) per enriched candidate.

    Reads:  enriched_candidates, intent, audience
    Writes: final_posts
    """
    candidates: list[PostableContext] = state.get("enriched_candidates", [])
    intent = state.get("intent", "")
    audience = state.get("audience", "engineers")

    final: list[PostableContext] = []
    for candidate in candidates:
        posts = _write_posts(candidate, intent, audience)
        final.append({**candidate, "posts": posts})

    return {"final_posts": final}


def _write_posts(candidate: PostableContext, intent: str, audience: str) -> list[str]:
    """Call the LLM and return [option_a, option_b, option_c]."""
    enrichment_text = _format_enrichment(candidate.get("enrichment", {}))

    prompt = WRITE_PROMPT.format(
        title=candidate.get("title", ""),
        thesis=candidate.get("thesis", ""),
        source_excerpt=candidate.get("source_excerpt", ""),
        intent=intent,
        audience=audience,
        enrichment_text=enrichment_text or "(no enrichment data available)",
    )

    raw = call_llm(
        prompt,
        system=WRITE_SYSTEM,
        max_tokens=2500,
        temperature=0.6,
        response_format={"type": "json_object"},
    )

    return _parse_posts(raw)


def _format_enrichment(enrichment: EnrichmentResult) -> str:
    """Render enrichment data as readable plain text for the LLM prompt."""
    parts: list[str] = []

    if enrichment.get("hn_thread_title") and enrichment.get("hn_thread_url"):
        parts.append(
            f"Hacker News: \"{enrichment['hn_thread_title']}\"\n"
            f"  {enrichment['hn_thread_url']}"
        )

    if enrichment.get("github_repos"):
        repos = "\n  ".join(enrichment["github_repos"][:3])
        parts.append(f"GitHub repos:\n  {repos}")

    if enrichment.get("arxiv_title") and enrichment.get("arxiv_url"):
        parts.append(
            f"arXiv paper: \"{enrichment['arxiv_title']}\"\n"
            f"  {enrichment['arxiv_url']}"
        )

    if enrichment.get("docs_summary") and enrichment.get("docs_url"):
        summary = (enrichment["docs_summary"] or "")[:300]
        parts.append(
            f"Docs ({enrichment['docs_url']}):\n  {summary}"
        )

    return "\n\n".join(parts)


def _parse_posts(raw: str) -> list[str]:
    """Parse LLM response into [option_a, option_b, option_c]."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Return the raw text split into three equal parts as a fallback
        chunk = len(raw) // 3
        return [raw[:chunk], raw[chunk : chunk * 2], raw[chunk * 2 :]]

    a = data.get("option_a") or data.get("a") or data.get("Option A") or ""
    b = data.get("option_b") or data.get("b") or data.get("Option B") or ""
    c = data.get("option_c") or data.get("c") or data.get("Option C") or ""

    return [str(a).strip(), str(b).strip(), str(c).strip()]
