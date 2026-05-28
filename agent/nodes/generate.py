"""generate_posts — three angles per context. Sequential by context (not by post)."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from agent.llm_manager import LLMManager
from agent.prompts import GENERATE_POSTS_PROMPT
from agent.state import AgentState, Context, EnrichmentResult


def _format_enrichment(e: EnrichmentResult) -> str:
    lines = []
    if e.get("hn_thread_title") and e.get("hn_thread_url"):
        lines.append(f"HN discussion: \"{e['hn_thread_title']}\" — {e['hn_thread_url']}")
    if e.get("docs_summary"):
        url = e.get("docs_url") or ""
        lines.append(f"LangGraph docs: {e['docs_summary']} ({url})")
    repos = e.get("github_repos") or []
    if repos:
        lines.append(f"Real-world usage: {', '.join(repos[:2])}")
    if e.get("changelog_note"):
        lines.append(f"Changelog: {e['changelog_note']}")
    if e.get("arxiv_title") and e.get("arxiv_url"):
        lines.append(f"Paper: \"{e['arxiv_title']}\" — {e['arxiv_url']}")

    return "\n".join(lines) if lines else "(no enrichment matches found — write from the excerpt alone)"


_POST_RE = re.compile(r"---POST\s+([ABC])---\s*(.*?)(?=---POST\s+[ABC]---|\Z)", re.S)


def _parse_posts(text: str) -> list[str]:
    matches = _POST_RE.findall(text)
    by_letter = {letter: body.strip() for letter, body in matches}
    return [by_letter.get("A", ""), by_letter.get("B", ""), by_letter.get("C", "")]


def generate_posts(state: AgentState) -> dict:
    enriched = state.get("enriched_contexts") or []
    if not enriched:
        return {"enriched_contexts": []}

    llm = LLMManager.for_generate()
    out: list[Context] = []

    for ctx in enriched:
        confusion = ctx.get("confusion")
        confusion_block = f"Confusion from the original note:\n{confusion}\n" if confusion else ""

        prompt = GENERATE_POSTS_PROMPT.format(
            title=ctx.get("title", ""),
            source_type=ctx.get("source_type", "session"),
            relevant_excerpt=ctx.get("relevant_excerpt", ""),
            confusion_block=confusion_block,
            enrichment_summary=_format_enrichment(ctx.get("enrichment") or {}),
        )

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            posts = _parse_posts(resp.content if hasattr(resp, "content") else str(resp))
        except Exception as e:
            posts = ["", "", ""]
            ctx = {**ctx, "error": f"generate failed: {e}"}

        out.append({**ctx, "posts": posts})

    # `enriched_contexts` has the _append reducer — writing back doubles the list.
    # Write under a no-reducer key instead. issue.py reads posts_by_context.
    return {"posts_by_context": out}
