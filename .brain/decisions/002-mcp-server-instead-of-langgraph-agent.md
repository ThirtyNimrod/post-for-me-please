---
type: decision
date: 2026-05-28
title: Replace the LangGraph agent with an MCP server driven by GitHub Copilot
tags: [architecture, mcp, langgraph, agentic-systems, github-copilot]
shareable: true
---

# Replace the LangGraph agent with an MCP server driven by GitHub Copilot

## Context

Earlier today the LangGraph pipeline from `docs/plan/code-plan-1.md` was implemented end-to-end (see [[2026-05-28]]) — `state.py`, `graph.py`, five nodes, four enrichers, `Send()` fan-out, weekly GH Actions cron, Azure OpenAI behind `LLMManager` (see [[001-azure-openai-via-llm-manager]]). With nothing yet committed and a sharper `code-plan-2.md` on disk, the question became: keep the LLM-driving Python pipeline, or invert the architecture so an LLM (Copilot in the VS Code chat) drives a tool surface we expose via MCP.

## Options considered

**Option A — Ship code-plan-1 as-is**
Python orchestrates: nodes call LLM, reducers merge fan-out, weekly cron runs headless. We own scheduling, retries, determinism. We also own an LLM key, a LangGraph version pin, a state machine to debug, and three prompt templates that we have to evolve in lockstep with the model.

**Option B — Pivot to code-plan-2 (MCP server + Copilot as orchestrator)**
Expose 7 tools (`scan_brain`, `search_hackernews`, `fetch_langgraph_changelog`, `fetch_page`, `search_github_repos`, `search_arxiv`, `create_github_issue`). Copilot reads the tool surface from `.vscode/mcp.json`, decides which to call and in what order, drafts the posts, and opens the issue. No `anthropic`, no `langgraph`, no `prompts.py`. The "agent" is the Copilot chat plus a pasted weekly prompt.

**Option C — Keep LangGraph internals, add an MCP server on top**
Wrap the existing nodes as MCP tools too, so both invocation styles work. Maximal optionality, double the surface to maintain, and we still own the LLM key and the state machine.

## Decision

Chose **Option B**. The reasoning, in order of weight:

1. **Auth surface shrinks to one token.** No Anthropic key, no Azure deployment, no quota tied to a single region. `GITHUB_TOKEN` is already in the VS Code session for `search_github_repos` and `create_github_issue`; no other secret to manage.
2. **The orchestration we wrote isn't load-bearing.** `Send()` fan-out, the conditional-edge router, the reducer trap — solving these was educational, but a weekly LinkedIn workflow doesn't need a state machine. Copilot calling tools sequentially is fine at this cadence.
3. **The tools are independently useful.** `search_hackernews` and `fetch_langgraph_changelog` are valuable in ad-hoc Copilot sessions, not only inside the weekly workflow. The LangGraph version was a closed pipeline; the MCP version is a kit.
4. **Prompt iteration moves out of Python.** The three prompts in `prompts.py` (split / generate / docs-summary) become a single paste-in prompt at `prompts/weekly-linkedin.md`. Iterating doesn't require a code change or a rerun of the graph.

## Tradeoffs accepted

- **No scheduled execution.** The weekly GitHub Actions cron from plan-1 doesn't survive — Copilot chat is interactive. Workaround if needed later: a headless `agent_mcp/run_headless.py` that constructs the full prompt and calls GitHub Models or Copilot API. Out of scope for now.
- **Serial tool calls only.** Copilot doesn't fan out — 5 contexts × ~4 enrichments will be ~20 serial calls (15–30s in chat). Acceptable for a weekly workflow the user is present for.
- **Determinism drops.** Copilot's reasoning is less controllable than a hard-coded node. If it skips `search_arxiv` on a topic that does have a paper, the prompt instruction is the only mitigation. Expect occasional misses; correct via prompt iteration rather than code.
- **The plan-1 work is shelved, not deleted.** `docs/plan/code-plan-1.md` and decision [[001-azure-openai-via-llm-manager]] stay as design history. The `agent/` directory had no committed source — only stale `__pycache__/` — so wiping it cost nothing.

## Outcome

_To be filled after the first end-to-end run with Copilot driving the tool surface against a real `.brain/` snapshot._
