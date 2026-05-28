# Code plan 3 — Reference-first LinkedIn post agent (Streamlit + LangGraph)

## Architecture shift from plan 2

Plan 2 (MCP) exposed I/O as tools and delegated all reasoning to Copilot chat.
Plan 3 inverts back to a real graph — but the trigger is no longer `.brain` file
scanning. Instead:

1. You paste ≤3 reference links and type your post intent in a Streamlit UI.
2. A research agent deep-reads those pages and proposes 3–5 postable topic candidates.
3. You pick 1–2 candidates in the UI (LangGraph `interrupt()` breakpoint).
4. Enrichment agents fan out in parallel via `Send()` — HN, GitHub, arXiv, docs per candidate.
5. A writer agent produces A/B/C post options per enriched candidate.
6. You review posts in the UI and optionally publish to a GitHub issue.

LiteLLM wrapper throughout. Initial backend: Azure OpenAI (GPT-5).
No Anthropic SDK, no MCP server, no `.brain` file dependency.

---

## Project structure

```
app/
  __init__.py
  state.py          # TypedDicts: PostableContext, EnrichmentResult, GraphState
  llm.py            # LiteLLM call wrapper (reads AZURE_OPENAI_* from env)
  graph.py          # LangGraph StateGraph + route_enrichment + interrupt() points
  prompts.py        # RESEARCH_PROMPT, WRITE_PROMPT constants (no logic)
  nodes/
    __init__.py
    research.py     # research_node: fetch ≤3 URLs → LLM → 3-5 PostableContext candidates
    enrich.py       # enrich_node: one candidate via Send() → 4 tools → EnrichmentResult
    write.py        # write_node: enriched candidates → A/B/C posts per candidate
  tools/
    __init__.py
    fetch.py        # fetch_page(url, max_chars) — ported from .backup
    hackernews.py   # search(query, days_back) — ported from .backup
    github.py       # search_repos(query, min_stars) + create_issue — ported from .backup
    arxiv.py        # search(query) — ported from .backup
ui/
  streamlit_app.py  # 4-stage UI
.env.example
requirements.txt
README.md
```

Everything under `app/tools/` is pure I/O with no LLM calls — same split as plan 2's
enrichers, just without the `@mcp.tool()` wrappers.

---

## State schema — `app/state.py`

```python
from typing import Annotated
from typing_extensions import TypedDict


class EnrichmentResult(TypedDict):
    hn_thread_title: str | None
    hn_thread_url: str | None
    github_repos: list[str]          # ["owner/repo (N stars)", ...]
    arxiv_title: str | None
    arxiv_url: str | None
    docs_summary: str | None         # from fetch_page on a relevant docs URL
    docs_url: str | None


class PostableContext(TypedDict):
    id: str                          # slugified title
    title: str
    thesis: str                      # one-sentence postable claim
    source_excerpt: str              # verbatim passage from reference content
    has_paper: bool                  # whether to hit arXiv
    enrichment: EnrichmentResult     # populated by enrich_node
    posts: list[str]                 # populated by write_node — exactly 3 items


def _append(left: list, right: list) -> list:
    """Reducer: accumulate partial results from parallel Send() calls."""
    return left + right


class GraphState(TypedDict):
    # Inputs (set once by the UI)
    reference_urls: list[str]        # ≤3 URLs
    intent: str                      # user's post intent
    audience: str                    # e.g. "engineers", "founders"

    # Set by research_node
    raw_source_content: str          # concatenated fetched page text
    candidates: list[PostableContext]

    # Set by user interrupt (UI picks from candidates)
    selected_ids: list[str]

    # Accumulated by parallel enrich_node calls
    enriched_candidates: Annotated[list[PostableContext], _append]

    # Set by write_node
    final_posts: list[PostableContext]  # candidates with posts[] populated
```

---

## Graph wiring — `app/graph.py`

```python
from langgraph.graph import StateGraph, END
from langgraph.types import Send, interrupt
from .state import GraphState
from .nodes.research import research_node
from .nodes.enrich import enrich_node
from .nodes.write import write_node


def route_enrichment(state: GraphState) -> list[Send]:
    """Fan out: one Send per selected candidate, all run in parallel."""
    return [
        Send("enrich_node", {"candidate": c})
        for c in state["candidates"]
        if c["id"] in state["selected_ids"]
    ]


def after_research(state: GraphState) -> str:
    """interrupt() pause — Streamlit resumes with selected_ids."""
    interrupt({"candidates": state["candidates"]})
    return "route"


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("research_node", research_node)
    g.add_node("after_research", after_research)
    g.add_node("enrich_node", enrich_node)
    g.add_node("write_node", write_node)

    g.set_entry_point("research_node")
    g.add_edge("research_node", "after_research")
    g.add_conditional_edges("after_research", route_enrichment)
    g.add_edge("enrich_node", "write_node")
    g.add_edge("write_node", END)

    return g.compile(checkpointer=MemorySaver())
```

`MemorySaver` keeps graph state between the two UI interactions (topic pick → post
review) without a database. Replace with `SqliteSaver` if persistence across process
restarts is needed later.

---

## Node specifications

### `nodes/research.py` — `research_node(state)`

**Reads:** `reference_urls`, `intent`, `audience`
**Writes:** `raw_source_content`, `candidates`

Logic:
1. Call `fetch_page(url)` for each URL (≤3) with `max_chars=4000`.
2. Concatenate results with URL headers as separators.
3. Call LLM with `RESEARCH_PROMPT` — includes fetched content + user intent + audience.
4. Parse LLM JSON response into `list[PostableContext]` (3–5 items, capped at 5).
5. Assign `id = slugify(title)` to each candidate.

`RESEARCH_PROMPT` drives the hard part: the LLM must extract *specific, verifiable
claims* from the source pages — not generic summaries. The prompt enforces: if you
can't write the first sentence of a post from the thesis alone, the candidate is
too vague. See `app/prompts.py`.

---

### `nodes/enrich.py` — `enrich_node(state)`

**Reads:** `state["candidate"]` (single `PostableContext`, injected by `Send()`)
**Writes:** appends one enriched `PostableContext` to `enriched_candidates`

Logic:
1. Extract `title`, `thesis`, `has_paper` from candidate.
2. Call tools in parallel (`concurrent.futures.ThreadPoolExecutor`):
   - `hackernews.search(title)` — always
   - `github.search_repos(title)` — always
   - `fetch_page(docs_url)` if a docs URL can be inferred from the thesis — conditional
   - `arxiv.search(title)` — only if `has_paper is True`
3. Assemble `EnrichmentResult`; failures return `None` fields, never raise.
4. Return `{"enriched_candidates": [{**candidate, "enrichment": result}]}`

---

### `nodes/write.py` — `write_node(state)`

**Reads:** `enriched_candidates`, `intent`, `audience`
**Writes:** `final_posts`

Logic:
1. For each enriched candidate, call LLM with `WRITE_PROMPT`.
2. Parse exactly 3 post strings from the response:
   - **Option A — The mistake:** "I assumed X. I was wrong."
   - **Option B — The mental model:** "The way to think about X is Y."
   - **Option C — The decision:** "You have two options. Here's why I picked one."
3. Each post: ≤200 words, short paragraphs, one question at the end.
4. Each post must include one verifiable detail from `enrichment` (HN thread, repo, paper).
5. Return `{"final_posts": [...]}`

---

## Tool specifications — `app/tools/`

All ported from `.backup/agent_mcp/enrichers/`. Only change: remove `@mcp.tool()`
decorators and the FastMCP import. Logic is identical.

| Tool | Source file | Change |
|------|------------|--------|
| `fetch.py` | `langgraph_docs.py` | Rename; keep `fetch_page` + `fetch_changelog` |
| `hackernews.py` | `hackernews.py` | Remove decorator only |
| `github.py` | `github.py` | Remove decorator only; keep both `search_repos` + `create_issue` |
| `arxiv.py` | `arxiv.py` | Remove decorator only |

`search_github_repos` was missing from the old MCP `server.py` as an exposed tool —
it's now a direct call from `enrich_node`, so the gap is closed.

---

## Streamlit UI — `ui/streamlit_app.py`

Four sequential stages. Stage transitions are driven by LangGraph `interrupt()` and
Streamlit `st.session_state`.

### Stage 1 — Input

```
st.title("Post for me, please")
url_1, url_2, url_3 = st.text_input × 3     # ≤3 reference links
intent = st.text_area("What's the post about?")
audience = st.selectbox(["engineers", "founders", "general tech"])
[Run] button → validate ≥1 URL, then invoke graph
```

On Run: create a `thread_id`, store in `session_state`, call
`graph.invoke(initial_state, {"configurable": {"thread_id": tid}})`.

### Stage 2 — Topic candidates

Shown after research_node resolves (graph hits first `interrupt()`).

```
st.subheader("Pick 1–2 topics to post about")
for candidate in candidates:
    st.checkbox(f"**{candidate['title']}**\n{candidate['thesis']}")
    with st.expander("Source excerpt"):
        st.write(candidate["source_excerpt"])
[Confirm selection] → resumes graph with selected_ids
```

### Stage 3 — Enrichment progress

Auto-runs immediately after confirm. Spinner per selected candidate.
No user input — the graph handles this stage automatically.

### Stage 4 — Post options

```
for candidate in final_posts:
    st.subheader(candidate["title"])
    tabs = st.tabs(["Option A — Mistake", "Option B — Mental model", "Option C — Decision"])
    for tab, post in zip(tabs, candidate["posts"]):
        with tab:
            st.write(post)
            st.code(post)   # copy-to-clipboard affordance
with st.expander("Publish to GitHub issue"):
    if st.button("Create issue"):
        url = github.create_issue(title=..., body=...)
        st.success(f"Issue created: {url}")
```

---

## Environment variables

```
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
AZURE_OPENAI_API_KEY=sk-...
AZURE_OPENAI_DEPLOYMENT=gpt-5          # or gpt-4o, etc.
AZURE_OPENAI_API_VERSION=2025-01-01

GITHUB_TOKEN=ghp_...
GITHUB_REPOSITORY=ThirtyNimrod/post-for-me-please
```

LiteLLM model string: `azure/<AZURE_OPENAI_DEPLOYMENT>`.
Swapping to OpenAI direct or Gemini requires only changing `AZURE_OPENAI_*` vars
and the model string — no code changes.

---

## Dependencies — `requirements.txt`

```
langgraph>=0.3.0
litellm>=1.40.0
streamlit>=1.35.0
requests>=2.31.0
python-slugify>=8.0.0
python-dotenv>=1.0.0
```

No `anthropic`, no `mcp`, no `python-frontmatter`. Dependency count halves vs. plan 2.

---

## What this gives up vs. plan 2 (MCP)

**No `.brain` file scanning.** The entry point is explicit links + intent, not
automated file discovery. This is intentional — you control the source material.

**No GitHub Actions scheduling.** The workflow is on-demand from Streamlit.
A cron trigger can be added later by wiring a headless `graph.invoke()` call in a
GitHub Actions job.

**No ad-hoc tool calls from chat.** The MCP tools (`search_hackernews`,
`fetch_page`, etc.) are no longer callable from Copilot chat. The `.backup/`
preserves the MCP server if you ever want both modes.

---

## What this gains

**Visibility into intermediate state.** Streamlit shows candidates before enrichment
runs — you only enrich topics you actually care about. The MCP approach was all-or-nothing.

**Richer intent signal.** The `intent` + `audience` fields go into every LLM call.
The research prompt is grounded in what you want to say, not just what was in the notes.

**Testable in isolation.** Each node has a clear input/output contract. Run
`research_node` with fixture URLs, inspect candidates, iterate on the prompt — before
wiring the graph or the UI.

**Provider-agnostic.** LiteLLM means any model switch is one env var change.
