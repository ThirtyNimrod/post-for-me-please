# Code plan — LinkedIn brain agent

## Project structure

```
linkedin-brain-agent/
├── agent/
│   ├── __init__.py
│   ├── state.py          # all TypedDicts and data models
│   ├── graph.py          # LangGraph graph definition and wiring
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── scan.py           # scan_brain
│   │   ├── split.py          # split_into_contexts
│   │   ├── enrich.py         # enrich_context (called via Send())
│   │   ├── generate.py       # generate_posts
│   │   └── issue.py          # open_issue
│   ├── enrichers/
│   │   ├── __init__.py
│   │   ├── hackernews.py     # HN Algolia API
│   │   ├── github.py         # GitHub search API
│   │   ├── langgraph_docs.py # LangGraph docs + changelog fetch
│   │   └── arxiv.py          # arXiv API (conditional)
│   └── prompts.py            # all LLM prompt strings
├── run_agent.py
├── requirements.txt
└── .github/
    └── workflows/
        └── weekly-post.yml
```

---

## State schema — `agent/state.py`

Three TypedDicts. Build bottom-up: `EnrichmentResult` → `Context` → `AgentState`.

```python
from typing import Annotated
from typing_extensions import TypedDict


class EnrichmentResult(TypedDict):
    hn_thread_title: str | None      # title of top HN thread found
    hn_thread_url: str | None        # link to that thread
    docs_url: str | None             # canonical docs page for the concept
    docs_summary: str | None         # 2-3 sentence summary of docs content
    changelog_note: str | None       # relevant LangGraph release note, if any
    github_repos: list[str]          # ["owner/repo", ...] — repos using this pattern
    arxiv_title: str | None          # paper title (only set when context has_paper=True)
    arxiv_url: str | None


class Context(TypedDict):
    id: str                          # slugified title, used as Send() key
    title: str                       # e.g. "LangGraph retry logic via state"
    source_type: str                 # "session" | "decision" | "concept"
    source_files: list[str]          # paths of .brain files this came from
    tags: list[str]                  # from frontmatter, drives enrichment queries
    has_paper: bool                  # whether to hit arXiv
    relevant_excerpt: str            # the specific passage the post should be about
    confusion: str | None            # "The confusion" section, if source is a concept note
    enrichment: EnrichmentResult     # populated by enrich_context node
    posts: list[str]                 # populated by generate_posts — exactly 3 items


def _append(left: list, right: list) -> list:
    """Reducer: collect enriched contexts returned by parallel Send() calls."""
    return left + right


class AgentState(TypedDict):
    brain_files: list[str]
    raw_file_contents: dict[str, str]              # path -> markdown content
    contexts: list[Context]                        # set by split_into_contexts
    enriched_contexts: Annotated[list[Context], _append]  # collected from Send()
    issue_url: str
    error: str
```

Key point: `enriched_contexts` uses the `_append` reducer so parallel `Send()` results
accumulate into a list rather than overwriting each other.

---

## Graph wiring — `agent/graph.py`

```python
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from .state import AgentState, Context
from .nodes.scan import scan_brain
from .nodes.split import split_into_contexts
from .nodes.enrich import enrich_context
from .nodes.generate import generate_posts
from .nodes.issue import open_issue


def route_enrichment(state: AgentState) -> list[Send]:
    """Fan out: one Send per context, all run in parallel."""
    return [
        Send("enrich_context", {"context": ctx})
        for ctx in state["contexts"]
    ]


def has_contexts(state: AgentState) -> str:
    if not state["contexts"] or state.get("error"):
        return "empty"
    return "ok"


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
        has_contexts,
        {"ok": "enrich_context", "empty": END},  # Send() handles the fan-out
    )

    # route_enrichment returns a list[Send] — LangGraph fans them out automatically
    g.add_conditional_edges("split_into_contexts", route_enrichment)

    g.add_edge("enrich_context", "generate_posts")
    g.add_edge("generate_posts", "open_issue")
    g.add_edge("open_issue", END)

    return g.compile()
```

Note: the `route_enrichment` conditional edge replaces a linear edge from
`split_into_contexts` to `enrich_context`. LangGraph fires all `Send()` calls in
parallel and waits for all of them before proceeding to `generate_posts`.

---

## Node specifications

### `nodes/scan.py` — `scan_brain(state)`

**Reads:** nothing from state (reads disk + state file)
**Writes:** `brain_files`, `raw_file_contents`

Logic:
1. Load `brain_agent_state.json` (last_run timestamp + processed_files list)
2. Walk `.brain/**/*.md`, filter files modified since `last_run` (default: 7 days)
3. Skip files already in `processed_files`
4. Parse YAML frontmatter for each file; skip any where `shareable: false`
5. Read content; store in `raw_file_contents` as `{path: content}`
6. Return `brain_files` (list of paths), `raw_file_contents`

State file shape:
```json
{
  "last_run": "2025-05-20T08:00:00+00:00",
  "processed_files": ["path/to/file.md"]
}
```

---

### `nodes/split.py` — `split_into_contexts(state)`

**Reads:** `raw_file_contents`
**Writes:** `contexts`

Logic:
1. Combine all file contents with path headers into one prompt
2. Call Claude: identify distinct postable topics, max 5
3. Parse response into `list[Context]`; assign `id` as `slugify(title)`
4. Return `{"contexts": [...]}`

What "distinct postable topic" means:
- Has a specific, concrete learning (not "I worked on agents today")
- Can stand alone — doesn't require understanding another context to make sense
- Maps clearly to one of: a debug resolution, a design decision, or a concept that clicked

Each `Context` must include `relevant_excerpt` — the actual passage from the notes
that the post is anchored to. The prompt should return this verbatim.

Prompt lives in `prompts.py` as `SPLIT_CONTEXTS_PROMPT`.
Cap contexts at 5 to keep the issue readable.

---

### `nodes/enrich.py` — `enrich_context(state)`

**Reads:** `state["context"]` (a single `Context`, injected by `Send()`)
**Writes:** appends one enriched `Context` to `enriched_contexts`

Note: when called via `Send()`, the node receives a sub-state containing only the keys
passed to `Send()`. Access the context as `state["context"]`.

Logic:
1. Extract `tags` and `title` from the context
2. Run all enrichers in parallel using `asyncio.gather()` or `concurrent.futures`
3. Assemble `EnrichmentResult`
4. Return `{"enriched_contexts": [{**context, "enrichment": result}]}`

Enricher call plan:
```python
results = await asyncio.gather(
    hn.search(tags, title),
    langgraph_docs.search(tags),
    github.search_repos(tags),
    arxiv.search(tags, title) if context["has_paper"] else asyncio.sleep(0),
)
```

---

### `enrichers/hackernews.py`

API: `https://hn.algolia.com/api/v1/search`
No auth required.

```python
params = {
    "query": " ".join(tags[:3]),  # top 3 tags
    "tags": "story",
    "numericFilters": f"created_at_i>{thirty_days_ago_unix}",
    "hitsPerPage": 3,
}
```

Return the highest-`points` result. If no results in 30 days, return `None` for both fields.
Do not return forum or Ask HN threads — only `story` type.

---

### `enrichers/langgraph_docs.py`

Two fetches:

1. **Docs page**: if `context.confusion` or `related_docs` is set, fetch that URL directly.
   Otherwise, build a search URL:
   `https://langchain-ai.github.io/langgraph/` + the most specific tag as a path hint.
   Summarise the page in 2–3 sentences using Claude (small call, `max_tokens=200`).

2. **Changelog**: fetch `https://github.com/langchain-ai/langgraph/releases`
   Parse the last 5 release titles and bodies. Check if any mention the concept's tags.
   If a match is found, extract the release version + the relevant line.

---

### `enrichers/github.py`

API: `https://api.github.com/search/repositories`
Auth: `GITHUB_TOKEN` (already available in the environment).

```python
query = f"{tags[0]} topic:langgraph language:python"
params = {"q": query, "sort": "stars", "per_page": 3}
```

Return top 3 as `["owner/repo (N stars)", ...]`.
Skip repos with fewer than 50 stars — low-signal.

---

### `enrichers/arxiv.py`

Only called when `context["has_paper"] is True`.
The `split_into_contexts` prompt sets `has_paper=True` when the concept maps to a
known ML/AI research area (ReAct, CoT, RAG, tool-use, RLHF, etc.).

API: `https://export.arxiv.org/api/query`
```python
params = {
    "search_query": f"ti:{title} OR abs:{tags[0]}",
    "max_results": 1,
    "sortBy": "relevance",
}
```

Parse the Atom XML response. Return title + `https://arxiv.org/abs/{id}`.

---

### `nodes/generate.py` — `generate_posts(state)`

**Reads:** `enriched_contexts`
**Writes:** `enriched_contexts` (mutates posts field on each context)

Logic:
1. For each context in `enriched_contexts`, call Claude with `GENERATE_POSTS_PROMPT`
2. Pass: `relevant_excerpt`, `confusion` (if set), `enrichment` summary
3. Parse 3 posts from the structured response (same `---POST N---` format as before)
4. Store on `context["posts"]`

The enrichment summary passed to the prompt should be pre-formatted:
```
HN discussion: "{title}" — {url}
LangGraph docs: {docs_summary} ({docs_url})
Real-world usage: {github_repos[0]}, {github_repos[1]}
Changelog: {changelog_note}
```

This keeps the prompt clean — the node does the formatting, not the prompt template.

---

### `nodes/issue.py` — `open_issue(state)`

**Reads:** `enriched_contexts`
**Writes:** `issue_url`

Issue structure:
```markdown
# Weekly LinkedIn post options — YYYY-MM-DD

Pick one post from any topic below. Copy it, post to LinkedIn, close this issue.

---

## Topic 1: {context.title}

> Source: {context.source_type} — {context.source_files[0]}

**Option A — The mistake / fix**
{posts[0]}

**Option B — The mental model**
{posts[1]}

**Option C — The decision}**
{posts[2]}

---

## Topic 2: ...
```

After creating the issue:
1. Update `brain_agent_state.json`: set `last_run` to now, append `brain_files` to `processed_files`
2. Print the issue URL to stdout (captured in Actions logs)

---

## Prompts — `agent/prompts.py`

Three prompts total:

| Constant | Used by | Approx tokens in |
|---|---|---|
| `SPLIT_CONTEXTS_PROMPT` | `split_into_contexts` | ~3000 (all .brain content) |
| `GENERATE_POSTS_PROMPT` | `generate_posts` | ~500 (one enriched context) |
| `DOCS_SUMMARISE_PROMPT` | `langgraph_docs.py` | ~1500 (one docs page) |

`SPLIT_CONTEXTS_PROMPT` is the most complex. It must instruct Claude to return structured
JSON — a list of context objects matching the `Context` TypedDict shape (minus `enrichment`
and `posts`). Instruct: return only JSON, no markdown fences, no preamble.

---

## Dependencies — `requirements.txt`

```
anthropic>=0.28.0
langgraph>=0.2.0
requests>=2.31.0
python-frontmatter>=1.1.0    # parse YAML frontmatter from .brain files
python-slugify>=8.0.0        # generate context IDs from titles
```

No async HTTP library needed — `requests` with `concurrent.futures.ThreadPoolExecutor`
is sufficient for the enrichment fan-out and avoids the complexity of managing an
async event loop inside LangGraph nodes.

---

## GitHub Actions — `.github/workflows/weekly-post.yml`

No changes to the workflow file from the previous version.
The `brain_agent_state.json` cache key remains `brain-agent-state-`.

Secrets required:
- `ANTHROPIC_API_KEY`
- `GITHUB_TOKEN` (provided automatically)

Env vars to configure per repo:
- `BRAIN_PATH` — path to `.brain` folder (default: `.brain`)
- `STATE_FILE` — path to state JSON (default: `brain_agent_state.json`)