"""split_into_contexts — the most consequential node.

Given a week of .brain notes, identify 1–5 independently postable topics. Output is the
foundation for every downstream node, so the prompt + structured output schema both
push hard for specificity.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from slugify import slugify

from agent.llm_manager import LLMManager
from agent.prompts import SPLIT_CONTEXTS_PROMPT
from agent.state import AgentState, Context, EMPTY_ENRICHMENT


class _ContextOut(BaseModel):
    title: str = Field(description="Specific learning, not a category. Refine until first sentence of a post is writable from the title alone.")
    source_type: Literal["session", "decision", "concept"]
    source_files: list[str] = Field(description="All .brain paths that contributed.")
    tags: list[str] = Field(default_factory=list)
    has_paper: bool = Field(description="True only for ReAct/CoT/RAG/RLHF/LoRA/attention/tool-use research.")
    relevant_excerpt: str = Field(description="EXACT verbatim text from notes. No paraphrase.")
    confusion: str | None = Field(default=None, description="The confusion section verbatim, only when source_type=concept.")


class _SplitResponse(BaseModel):
    contexts: list[_ContextOut] = Field(max_length=5)


def _format_notes(raw_file_contents: dict[str, str]) -> str:
    chunks = []
    for path, content in raw_file_contents.items():
        chunks.append(f"=== FILE: {path} ===\n{content}\n=== END FILE ===\n")
    return "\n".join(chunks)


def split_into_contexts(state: AgentState) -> dict:
    raw = state.get("raw_file_contents") or {}
    if not raw:
        return {"contexts": []}

    notes = _format_notes(raw)
    prompt = SPLIT_CONTEXTS_PROMPT.format(notes=notes)

    llm = LLMManager.for_split().with_structured_output(_SplitResponse)
    try:
        result: _SplitResponse = llm.invoke([HumanMessage(content=prompt)])
    except Exception as e:
        return {"contexts": [], "error": f"split_into_contexts failed: {e}"}

    contexts: list[Context] = []
    seen_ids: set[str] = set()
    for c in result.contexts:
        cid = slugify(c.title)[:80] or "untitled"
        # Avoid duplicate IDs from near-identical titles.
        base, n = cid, 1
        while cid in seen_ids:
            n += 1
            cid = f"{base}-{n}"
        seen_ids.add(cid)

        contexts.append({
            "id": cid,
            "title": c.title,
            "source_type": c.source_type,
            "source_files": c.source_files,
            "tags": c.tags,
            "has_paper": c.has_paper,
            "relevant_excerpt": c.relevant_excerpt,
            "confusion": c.confusion,
            "enrichment": dict(EMPTY_ENRICHMENT),
            "posts": [],
        })

    return {"contexts": contexts}
