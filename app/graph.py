from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, Send, interrupt

from .nodes.enrich import enrich_node
from .nodes.research import research_node
from .nodes.write import write_node
from .state import GraphState


# ── Human-in-the-loop nodes ───────────────────────────────────────────────────

def topic_selection(state: GraphState) -> dict:
    """First interrupt: suspend so the Streamlit UI can present candidates.

    interrupt() raises GraphInterrupt internally; LangGraph catches it, persists
    state via the checkpointer, and returns control to the caller.

    Resume by calling:
        graph.invoke(Command(resume={"selected_ids": [...]}), config)

    The value passed to Command(resume=...) is returned by interrupt().
    """
    payload = interrupt({
        "stage": "topic_selection",
        "candidates": state.get("candidates", []),
    })

    if isinstance(payload, dict):
        selected_ids = payload.get("selected_ids", [])
    elif isinstance(payload, list):
        selected_ids = payload
    else:
        selected_ids = []

    return {"selected_ids": selected_ids}


def post_review(state: GraphState) -> None:
    """Second interrupt: suspend so the Streamlit UI can display post options.

    Resume by calling:
        graph.invoke(Command(resume=True), config)
    """
    interrupt({
        "stage": "post_review",
        "final_posts": state.get("final_posts", []),
    })


# ── Conditional routing ───────────────────────────────────────────────────────

def route_enrichment(state: GraphState) -> list[Send]:
    """Fan out: one Send per selected candidate, all run in parallel."""
    selected = set(state.get("selected_ids") or [])
    return [
        Send("enrich_node", {"candidate": c})
        for c in (state.get("candidates") or [])
        if c["id"] in selected
    ]


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the LangGraph StateGraph.

    Flow:
        research_node
            → topic_selection          [interrupt — user picks topics]
            → route_enrichment         [conditional Send fan-out]
            → enrich_node × N          [parallel, one per selected candidate]
            → write_node
            → post_review              [interrupt — user reviews posts]
            → END
    """
    g = StateGraph(GraphState)

    g.add_node("research_node", research_node)
    g.add_node("topic_selection", topic_selection)
    g.add_node("enrich_node", enrich_node)
    g.add_node("write_node", write_node)
    g.add_node("post_review", post_review)

    g.set_entry_point("research_node")
    g.add_edge("research_node", "topic_selection")
    g.add_conditional_edges("topic_selection", route_enrichment)
    g.add_edge("enrich_node", "write_node")
    g.add_edge("write_node", "post_review")
    g.add_edge("post_review", END)

    return g.compile(checkpointer=MemorySaver())


# Module-level singleton — Streamlit imports this directly
graph = build_graph()
