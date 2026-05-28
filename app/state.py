from __future__ import annotations

from typing import Annotated

from typing_extensions import TypedDict


class EnrichmentResult(TypedDict):
    hn_thread_title: str | None
    hn_thread_url: str | None
    github_repos: list[str]   # ["owner/repo (N stars)", ...]
    arxiv_title: str | None
    arxiv_url: str | None
    docs_summary: str | None  # fetched from a relevant docs page
    docs_url: str | None


class PostableContext(TypedDict):
    id: str                       # slugified title, used as Send() key
    title: str                    # short descriptive title
    thesis: str                   # one-sentence postable claim
    source_excerpt: str           # verbatim passage from the reference content
    has_paper: bool               # whether to hit arXiv during enrichment
    has_mistake_angle: bool       # whether source content supports "Option A — mistake" hook
    enrichment: EnrichmentResult  # populated by enrich_node
    posts: list[str]              # populated by write_node — exactly 3 items (A, B, C)


def _append(left: list, right: list) -> list:
    """Reducer: accumulate partial results from parallel Send() calls."""
    return left + right


class GraphState(TypedDict):
    # ── Inputs (set once by the Streamlit UI) ────────────────────────────────
    reference_urls: list[str]   # 1–3 URLs provided by the user
    intent: str                 # what the user wants the post to convey
    audience: str               # target reader, e.g. "engineers", "founders"

    # ── Set by research_node ─────────────────────────────────────────────────
    raw_source_content: str         # concatenated fetched page text (with URL headers)
    candidates: list[PostableContext]  # 3–5 candidates proposed by the LLM

    # ── Set by the user after the first interrupt() ───────────────────────────
    selected_ids: list[str]     # ids of candidates the user chose to enrich

    # ── Accumulated by parallel enrich_node calls ─────────────────────────────
    enriched_candidates: Annotated[list[PostableContext], _append]

    # ── Set by write_node ────────────────────────────────────────────────────
    final_posts: list[PostableContext]  # enriched candidates with posts[] populated
