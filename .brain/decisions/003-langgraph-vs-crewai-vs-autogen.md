---
type: decision
date: 2026-05-28
title: LangGraph over CrewAI and Autogen for structured HITL pipelines
tags: [langgraph, agentic-systems, orchestration, multi-agent, architecture, state-graph]
shareable: true
---

# LangGraph over CrewAI and Autogen for structured HITL pipelines

## Context

Choosing the orchestration framework for a 4-stage LinkedIn post generator:
1. Research node (fetch URLs → LLM → topic candidates)
2. **HITL interrupt** — user picks 1–2 candidates in Streamlit
3. Parallel enrichment of selected candidates (HN, GitHub, arXiv, docs fetch)
4. **HITL interrupt** — user reviews post options, optionally publishes to GitHub

Requirements: two human-in-the-loop breakpoints, parallel fan-out with state accumulation, Streamlit integration across page reruns, deterministic graph topology.

## Options considered

**Option A — LangGraph**
Explicit `StateGraph` with typed state, `interrupt()` for HITL, `Send()` for parallel task dispatch, and a `MemorySaver` checkpointer. Low-level but precise — every edge and node is explicit code.

**Option B — CrewAI**
Role-based agents (Researcher, Enricher, Writer) that delegate tasks between each other. Simpler to define "who does what", but orchestration is semi-autonomous — agents decide handoff order. No native HITL interrupt mechanism. No parallel fan-out equivalent to `Send()`.

**Option C — Autogen**
Conversational multi-agent loop — agents chat until task is complete. Good for open-ended research or code review where the stopping condition is fuzzy. No explicit interrupt/checkpoint concept. Conversation model assumes sequential message exchange.

## Decision

Chose **Option A — LangGraph** because the two HITL breakpoints are non-negotiable requirements, and `interrupt()` is LangGraph's core HITL primitive. No equivalent exists in CrewAI or Autogen. The parallel enrichment (`Send()` + `Annotated` reducer) is a close second reason — the other frameworks would require manual `ThreadPoolExecutor` threading *outside* the orchestration layer, losing visibility into partial state.

The pipeline is deterministic and structured. CrewAI's role-agent model and Autogen's conversational loop are both optimised for open-ended, negotiated reasoning — overkill and wrong shape for a clear 4-stage flow.

## Tradeoffs accepted

- LangGraph is more verbose. Each edge, node, and state key is explicit code. CrewAI lets you describe agent roles in English and infers the handoff graph.
- Debugging LangGraph state requires reading TypedDicts and graph snapshots. CrewAI's task logs are more human-readable.
- `MemorySaver` is in-process only — no persistence across server restarts. Acceptable for Streamlit (one session per user, one process). Would require `SqliteSaver` or `PostgresSaver` if the app went multi-user or long-lived.

## Outcome

LangGraph already ships in the codebase (`app/graph.py`, `app/state.py`). The `interrupt()` + `Send()` combination maps cleanly to the 4-stage flow. `MemorySaver` holds state across the two Streamlit `graph.invoke()` calls without a database. The decision held up through full implementation.

The rule of thumb that emerged: if the pipeline has *explicit user checkpoints* (not just retries or branching), reach for LangGraph. CrewAI/Autogen are for open-ended agent loops where the framework decides when to stop.
