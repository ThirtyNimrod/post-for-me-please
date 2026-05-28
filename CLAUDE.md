# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick start

```bash
# Requires Python 3.13+
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

The project is installed as an editable package (see `pyproject.toml`). Both `app` and `ui` are included, so `from app.graph import graph` works after install.

## Running the app

```bash
streamlit run ui/streamlit_app.py
```

Opens on `http://localhost:8501`. Four-stage workflow:

1. **Input** — ≤3 reference URLs + post intent + target audience
2. **Topic selection** — pick 1–2 candidates from LLM-proposed list (graph paused at `interrupt()`)
3. **Enrichment** — parallel tool calls (HN, GitHub, arXiv, docs); spinner only, no user input
4. **Post review** — A/B/C post options per candidate; optional publish to GitHub issue

## Stack and design principles

Streamlit (UI) + LangGraph (orchestration) + LiteLLM (LLM abstraction) + Azure OpenAI (default backend).

- **`interrupt()` for HITL**, **`Send()` for parallel fan-out**. These two LangGraph primitives are the load-bearing design choices — see `.brain/decisions/003-langgraph-vs-crewai-vs-autogen.md` for why CrewAI/Autogen were rejected.
- **All tool I/O is pure Python.** No `@mcp.tool()` decorators, no MCP server. (Prior MCP design lives in git history; see `.brain/decisions/002-...` for the pivot rationale.)
- **Tool failure convention:** every tool in `app/tools/` returns a string prefixed `"(<name> failed: ...)"` on error — they never raise. Callers detect failure via `startswith("(")`. Exception: `github.create_issue` raises (write op, errors must surface to the UI).

## Project structure

```
app/
  state.py              # TypedDicts: EnrichmentResult, PostableContext, GraphState
  graph.py              # StateGraph + route_enrichment + interrupt() nodes
  llm.py                # call_llm wrapper; Azure env aliases + explicit kwargs
  prompts.py            # RESEARCH_PROMPT, WRITE_PROMPT, *_SYSTEM templates
  nodes/
    research.py         # research_node: fetch URLs → LLM → 3–5 topic candidates
    enrich.py           # enrich_node: parallel tool calls → EnrichmentResult
    write.py            # write_node: enriched candidates → 3 posts per candidate
  tools/
    fetch.py            # fetch_page(url, max_chars) — stdlib HTMLParser
    hackernews.py       # search(query, days_back)
    github.py           # search_repos(query, min_stars) + create_issue(title, body)
    arxiv.py            # search(query) — stdlib ElementTree, no feedparser
ui/
  streamlit_app.py      # 4-stage UI with st.session_state + graph.invoke()
.brain/                 # session logs, decisions, concepts (feeds the post agent later)
docs/plan/              # design history: code-plan-1/2/3.md
```

## State and graph flow

`GraphState` (app/state.py) keys, by stage:

| Key | Set by | Notes |
|---|---|---|
| `reference_urls`, `intent`, `audience` | UI stage 1 | Inputs |
| `raw_source_content`, `candidates` | `research_node` | LLM returns 3–5 `PostableContext` |
| `selected_ids` | UI stage 2 (via `Command(resume=...)`) | User picks ≤2 |
| `enriched_candidates` | parallel `enrich_node` calls | **Has `_append` reducer** — every write merges, never replaces |
| `final_posts` | `write_node` | Candidates with `posts: [A, B, C]` populated |

Graph wiring (`app/graph.py`):
```
research_node
  → topic_selection      [interrupt — UI extracts candidates]
  → route_enrichment     [conditional Send fan-out]
  → enrich_node × N      [parallel, results merged by _append reducer]
  → write_node
  → post_review          [interrupt — UI shows posts, optionally publishes]
  → END
```

### Reducer gotcha

`enriched_candidates: Annotated[list[PostableContext], _append]`. Any node that returns this key **appends** to the list. Writing the post-augmented list back to this key would double the entries (N → 2N). `write_node` writes to a separate `final_posts` key for exactly this reason — see `.brain/sessions/2026-05-28.md` "Debug: the reducer trap".

### How interrupts drive the UI

LangGraph state is checkpointed in process memory (`MemorySaver`). The UI flow:

1. `graph.invoke(initial_state, config)` → graph runs `research_node`, hits `topic_selection` interrupt, returns.
2. UI calls `graph.get_state(config)` and reads `state_snapshot.tasks[0].interrupts[0].value` to extract the interrupt payload (candidates).
3. User picks topics in Streamlit. UI calls `graph.invoke(Command(resume={"selected_ids": [...]}), config)`.
4. Graph resumes, fans out, writes posts, hits second interrupt at `post_review`. UI reads `final_posts` and renders.

`thread_id = uuid.uuid4()` per run, stored in `st.session_state`. Every `graph.invoke()` passes `{"configurable": {"thread_id": ...}}` so the checkpointer keys state to this thread.

## Key file specifics

### `app/llm.py` — LiteLLM call wrapper

Accepts two env var formats and aliases between them at import time:

- **LiteLLM-native:** `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_BASE`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_DEPLOYMENT`
- **Alias:** `API_KEY`, `AZURE_ENDPOINT`, `API_VERSION`, `AZURE_DEPLOYMENT`, `MODEL`

`call_llm()` passes `api_base`, `api_key`, `api_version` **explicitly as kwargs** to `litellm.completion()` when the model starts with `azure/`. This avoids cross-SDK-version env-name ambiguity. To swap providers (OpenAI direct, Gemini), set the corresponding env vars and adjust `_resolve_model()` if needed.

`response_format={"type": "json_object"}` is supported for structured JSON output — both `research_node` and `write_node` use it.

### `app/nodes/enrich.py` — parallel enrichment

Tools dispatched via `ThreadPoolExecutor`:

- `hackernews.search(query)` — always
- `github.search_repos(title)` — always
- `fetch_page(docs_url)` — **only when `_infer_docs_url()` returns a hit**, currently scoped to LangGraph concepts via a hardcoded `slug_map` (keywords `interrupt`, `send`, `reducer`, etc. → `langchain-ai.github.io/langgraph/concepts/...`)
- `arxiv.search(title)` — only when `candidate["has_paper"] is True`

To enable docs enrichment for a new framework, extend the `slug_map` in `_infer_docs_url`.

Parsing helpers (`_parse_first_hn_result`, `_parse_repo_list`, `_parse_first_arxiv_result`) regex-parse the tool output strings. They tolerate the `"("` error prefix by returning empty results. Keep tool output formats stable, or update parsers in lockstep.

### `app/nodes/research.py` — topic extraction

1. `fetch_page(url, max_chars=4000)` per URL, concatenated with `=== SOURCE: {url} ===` headers.
2. LLM call with `RESEARCH_PROMPT` → JSON array of candidates.
3. Slug uniqueness enforced by `slugify(title)` + `-2` suffix on collision.
4. Capped at `MAX_CANDIDATES = 5`.

Prompt enforces specificity: source_excerpt **must be verbatim**, thesis must be a one-sentence postable claim. Vague candidates get rejected.

### `app/nodes/write.py` — post generation

Parses JSON with keys `option_a/b/c` (case variants tolerated). Falls back to splitting raw text into three equal chunks if JSON parsing fails — see `_parse_posts`. Each post: ≤200 words, must include one verifiable detail from enrichment.

### `app/tools/fetch.py`

Uses stdlib `html.parser.HTMLParser` with a `_TextExtractor` subclass that skips `script`, `style`, `noscript`, `nav`, `footer`, `header`. Collapses 3+ newlines to 2. Truncates with `…(truncated)` marker.

Each tool file has a `if __name__ == "__main__":` block for smoke testing:
```bash
python -m app.tools.fetch https://example.com
python -m app.tools.github "LangGraph"
python -m app.tools.hackernews "agentic"
python -m app.tools.arxiv "ReAct"
```

## Environment setup

Copy `.env.example` to `.env`. Required:

```bash
# Azure OpenAI (either Format A or Format B works)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_BASE=https://your-endpoint.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-5

# GitHub — required only if you use the "publish to GitHub issue" feature
GITHUB_TOKEN=ghp_...
GITHUB_REPOSITORY=ThirtyNimrod/post-for-me-please
```

`.env` is loaded by `python-dotenv` at the top of `ui/streamlit_app.py`, **before** the graph is imported — order matters because `app/llm.py` reads env vars at import time.

## Testing and iteration

No test framework yet. Patterns currently used:

**Node isolation:** Construct a `GraphState` dict, call `research_node(state)` directly, inspect the returned `candidates`. Same pattern for `enrich_node` (pass `{"candidate": ...}` as the sub-state) and `write_node`.

**Tool smoke tests:** Run any tool as a script (see fetch.py example above).

**Prompt iteration:** Edit `RESEARCH_PROMPT` or `WRITE_PROMPT` in `app/prompts.py`, rerun Streamlit. No graph rebuild required.

**State inspection at interrupt:** Add `st.write(state_snapshot.values)` in `ui/streamlit_app.py` between stages to dump full state.

## Common tasks

**Add a new enrichment tool:**
1. Create `app/tools/my_tool.py` with `def my_search(query) -> str` returning `"(my_tool failed: ...)"` on error.
2. Add a key to `EnrichmentResult` in `app/state.py`.
3. Wire into `enrich_node`'s `tasks` dict in `app/nodes/enrich.py`, add a `_parse_*` helper if the output format needs structuring.
4. Reference the new field in `_format_enrichment` (write.py) and the `WRITE_PROMPT`.

**Switch LLM providers:**
1. Update env vars to the new provider's keys.
2. Adjust `_resolve_model()` in `app/llm.py` if the model string isn't already `<provider>/<model>` shape.
3. The Azure-specific kwargs branch in `call_llm` is skipped automatically when `_MODEL` doesn't start with `azure/`.

**Add a new input field:**
1. Add to `GraphState` in `app/state.py`.
2. Add form widget in `render_stage_1` (ui/streamlit_app.py).
3. Pass in the `initial_state` dict.
4. Read via `state.get("field_name")` in nodes.

**Persist state across restarts:** Swap `MemorySaver()` for `SqliteSaver()` (or `PostgresSaver`) in `app/graph.py` `build_graph()`. No other changes needed.

## Architectural decisions worth knowing

All in `.brain/decisions/`:

- **001** — Azure OpenAI via LLMManager (superseded by direct LiteLLM)
- **002** — MCP server replacing LangGraph (later reverted; see plan-3)
- **003** — LangGraph over CrewAI/Autogen for structured HITL pipelines

Read these before making framework-level changes. The pivot history matters: this is the **third** iteration of the orchestration approach.
