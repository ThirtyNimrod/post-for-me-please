"""LangGraph state schema for the LinkedIn brain agent."""

from __future__ import annotations

from typing import Annotated
from typing_extensions import TypedDict


class EnrichmentResult(TypedDict):
    hn_thread_title: str | None
    hn_thread_url: str | None
    docs_url: str | None
    docs_summary: str | None
    changelog_note: str | None
    github_repos: list[str]
    arxiv_title: str | None
    arxiv_url: str | None


class Context(TypedDict, total=False):
    id: str
    title: str
    source_type: str          # "session" | "decision" | "concept"
    source_files: list[str]
    tags: list[str]
    has_paper: bool
    relevant_excerpt: str
    confusion: str | None
    enrichment: EnrichmentResult
    posts: list[str]


def _append(left: list, right: list) -> list:
    """Reducer: accumulate enriched contexts from parallel Send() invocations."""
    return (left or []) + (right or [])


class AgentState(TypedDict, total=False):
    brain_files: list[str]
    raw_file_contents: dict[str, str]
    contexts: list[Context]
    enriched_contexts: Annotated[list[Context], _append]
    posts_by_context: list[Context]   # written by generate_posts (no reducer — overwrites)
    issue_url: str
    error: str


EMPTY_ENRICHMENT: EnrichmentResult = {
    "hn_thread_title": None,
    "hn_thread_url": None,
    "docs_url": None,
    "docs_summary": None,
    "changelog_note": None,
    "github_repos": [],
    "arxiv_title": None,
    "arxiv_url": None,
}
