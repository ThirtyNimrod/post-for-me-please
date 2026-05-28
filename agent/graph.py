"""LangGraph wiring.

scan_brain → split_into_contexts → (fan-out via Send) → enrich_context →
generate_posts → open_issue → END

The fan-out lives in one conditional edge that either returns END (no contexts) or a
list of Send() invocations (one per context). LangGraph fires them in parallel and waits
for all to complete via the _append reducer on enriched_contexts before continuing.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from agent.nodes.enrich import enrich_context
from agent.nodes.generate import generate_posts
from agent.nodes.issue import open_issue
from agent.nodes.scan import scan_brain
from agent.nodes.split import split_into_contexts
from agent.state import AgentState


def _route_after_split(state: AgentState):
    contexts = state.get("contexts") or []
    if not contexts or state.get("error"):
        return END
    return [Send("enrich_context", {"context": ctx}) for ctx in contexts]


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("scan_brain", scan_brain)
    g.add_node("split_into_contexts", split_into_contexts)
    g.add_node("enrich_context", enrich_context)
    g.add_node("generate_posts", generate_posts)
    g.add_node("open_issue", open_issue)

    g.set_entry_point("scan_brain")
    g.add_edge("scan_brain", "split_into_contexts")

    g.add_conditional_edges(
        "split_into_contexts",
        _route_after_split,
        ["enrich_context", END],
    )

    g.add_edge("enrich_context", "generate_posts")
    g.add_edge("generate_posts", "open_issue")
    g.add_edge("open_issue", END)

    return g.compile()
