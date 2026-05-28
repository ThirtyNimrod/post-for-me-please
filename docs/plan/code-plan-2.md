# Code plan 2 — MCP server for GitHub Copilot

## The architecture shift

The LangGraph plan (code-plan.md) treats the agent as a standalone pipeline:
your code orchestrates LLM calls, your code reasons about contexts, your code
decides what to enrich and how. It needs an Anthropic API key because it's
driving the LLM.

This plan inverts that. The MCP server exposes the I/O work as tools —
file reading, API calls, GitHub issue creation. GitHub Copilot in the VS Code
chat window becomes the orchestrator. It reads the tools, decides what to call
and in what order, reasons about the contexts, writes the posts, and calls
`create_github_issue` when it's done.

```
LangGraph plan:   your code → LLM (Anthropic API)
MCP plan:         Copilot (LLM) → your tools (MCP server)
```

No LangGraph. No Anthropic SDK. No `state.py`, no `graph.py`, no `nodes/`,
no `prompts.py`. Just a Python MCP server exposing 7 tools, and a one-time
prompt you paste into Copilot chat.

---

## Project structure

```
linkedin-brain-agent/
├── agent_mcp/
│   ├── __init__.py
│   ├── server.py              # MCP server + all tool definitions
│   ├── brain_reader.py        # .brain file reading + frontmatter parsing
│   ├── state.py               # brain_agent_state.json read/write
│   └── enrichers/
│       ├── __init__.py
│       ├── hackernews.py
│       ├── github.py
│       ├── langgraph_docs.py
│       └── arxiv.py
├── .vscode/
│   └── mcp.json               # VS Code Copilot MCP configuration
├── requirements.txt
└── README.md
```

Everything under `agent_mcp/` is pure I/O — no LLM calls, no prompt templates,
no orchestration logic. The server is a thin wrapper that gives Copilot hands.

---

## MCP server — `agent_mcp/server.py`

```python
from mcp.server.fastmcp import FastMCP
from .brain_reader import read_brain_files
from .state import load_state, save_state
from .enrichers import hackernews, github, langgraph_docs, arxiv

mcp = FastMCP("brain-linkedin-agent")
```

### Tool 1 — `scan_brain`

```python
@mcp.tool()
def scan_brain(days_back: int = 7) -> str:
    """
    Read .brain markdown files modified in the last N days.
    Returns each file's path, frontmatter, and content.
    Automatically skips files where shareable: false.
    """
```

Returns a formatted string — one block per file, separated by `---`.
Each block includes the file path, the frontmatter tags, source type
(session/decision/concept), and the full markdown content.

Internally: calls `brain_reader.read_brain_files(days_back)`. Loads
`brain_agent_state.json` to skip already-processed files.

This is the first tool Copilot should call. Everything else follows from
what this returns.

---

### Tool 2 — `search_hackernews`

```python
@mcp.tool()
def search_hackernews(query: str, days_back: int = 30) -> str:
    """
    Search Hacker News for recent discussions about a topic or concept.
    Returns the top 3 results: title, URL, points, comment count.
    Returns empty string if no results found in the time window.
    """
```

API: `https://hn.algolia.com/api/v1/search` — no auth, no rate limits worth
worrying about. Copilot calls this once per context it identifies.

Return format (plain text, easy for Copilot to read):
```
1. "Why LangGraph's reducer pattern is underrated" — 847 pts, 134 comments
   https://news.ycombinator.com/item?id=...

2. "Ask HN: How are you handling state in LangGraph agents?" — 203 pts, 67 comments
   https://news.ycombinator.com/item?id=...
```

---

### Tool 3 — `fetch_langgraph_changelog`

```python
@mcp.tool()
def fetch_langgraph_changelog(num_releases: int = 5) -> str:
    """
    Fetch the most recent LangGraph release notes from GitHub.
    Returns release version, date, and headline changes for each.
    Useful for checking if a concept you learned was recently added or changed.
    """
```

Fetches `https://github.com/langchain-ai/langgraph/releases` and parses
the last `num_releases` entries. Returns structured plain text. No auth needed
for public repo releases.

Copilot uses this to check: "did this behaviour change recently?" If yes,
it weaves the version note into the post.

---

### Tool 4 — `fetch_page`

```python
@mcp.tool()
def fetch_page(url: str, max_chars: int = 3000) -> str:
    """
    Fetch and return the text content of a web page.
    Use for LangGraph docs pages, blog posts, or any URL worth referencing.
    Content is truncated to max_chars to stay within context limits.
    """
```

General-purpose. Copilot uses this to fetch the specific LangGraph docs page
for whatever concept it identified, or to pull a blog post it found via HN.
Copilot decides the URL — you don't hard-code a docs scraper.

This replaces `langgraph_docs.py` as a dedicated enricher. Simpler and more
flexible — Copilot can fetch any relevant page, not just LangGraph docs.

---

### Tool 5 — `search_github_repos`

```python
@mcp.tool()
def search_github_repos(query: str, min_stars: int = 50) -> str:
    """
    Search GitHub for repositories related to a concept or pattern.
    Returns repo name, star count, description, and URL.
    Filters out repos below min_stars to reduce noise.
    """
```

Uses `https://api.github.com/search/repositories`. Reads `GITHUB_TOKEN` from
environment — already available since Copilot runs in VS Code where you're
authenticated.

---

### Tool 6 — `search_arxiv`

```python
@mcp.tool()
def search_arxiv(query: str) -> str:
    """
    Search arXiv for papers related to an AI/ML concept.
    Only use this when the concept maps to a research area
    (e.g. ReAct, chain-of-thought, RAG, tool-use, RLHF).
    Returns paper title, authors, abstract summary, and URL.
    """
```

The docstring instructs Copilot on when to call this — Copilot reads tool
descriptions to decide whether to invoke them. "Only use this when..." is
load-bearing guidance, not documentation.

---

### Tool 7 — `create_github_issue`

```python
@mcp.tool()
def create_github_issue(title: str, body: str) -> str:
    """
    Create a GitHub issue in the current repository with the given title and body.
    Use this as the final step after generating all post options.
    Returns the URL of the created issue.
    """
```

Reads `GITHUB_TOKEN` and `GITHUB_REPOSITORY` from environment.
After creating the issue, calls `save_state()` to mark the processed files
and update `last_run`.

This is the only tool with a side effect on external state. Copilot calls it
last, after it has written all posts into the issue body.

---

## VS Code configuration — `.vscode/mcp.json`

```json
{
  "servers": {
    "brain-linkedin-agent": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "agent_mcp.server"],
      "env": {
        "BRAIN_PATH": "${workspaceFolder}/.brain",
        "STATE_FILE": "${workspaceFolder}/brain_agent_state.json",
        "GITHUB_REPOSITORY": "your-username/your-repo"
      }
    }
  }
}
```

`GITHUB_TOKEN` does not need to be set here — VS Code passes the token from
your authenticated GitHub session automatically when running MCP servers.

Copilot picks up MCP servers from `.vscode/mcp.json` automatically when you
open the folder. No extension install, no manual registration.

---

## The prompt you paste into Copilot chat

This is the equivalent of `run_agent.py`. Save it somewhere (a `prompts/`
folder, a note, wherever) and paste it into Copilot chat each time you want
to run the weekly workflow.

```
You are helping me generate LinkedIn post options from my developer notes.

Follow these steps in order:

1. Call `scan_brain` to read this week's .brain files. If it returns nothing,
   stop and tell me there's nothing new to post about.

2. Read the returned files carefully. Identify up to 5 distinct, postable topics.
   A topic is postable if it has a specific, concrete learning — not just
   "I worked on X" but "I discovered that X works like Y when Z".

3. For each topic, call the relevant enrichment tools:
   - Always call `search_hackernews` with the concept name
   - Always call `fetch_langgraph_changelog` (once total, not per topic)
   - Call `fetch_page` with the relevant LangGraph docs URL if one is obvious
   - Call `search_github_repos` with the main concept tag
   - Only call `search_arxiv` if the topic maps to a research concept like
     ReAct, chain-of-thought, RAG, or similar

4. For each topic, write 3 LinkedIn post options:
   - Option A: Lead with what I got wrong or assumed incorrectly. Relatable hook.
   - Option B: Lead with the mental model or analogy that made it click.
   - Option C: Lead with the tradeoff or design decision.
   Each post: max 200 words, short paragraphs, one question at the end.
   Weave in one specific detail from the enrichment (HN thread, changelog note, etc.)

5. Call `create_github_issue` with all the options formatted by topic.
   Issue title: "Weekly LinkedIn post options — [today's date]"

Don't ask me questions during the process. Work through all steps and create
the issue at the end. Tell me the issue URL when done.
```

---

## `agent_mcp/brain_reader.py`

Same logic as `nodes/scan.py` from code-plan.md. No changes needed:
- Walk `.brain/**/*.md`
- Filter by `mtime` >= `now - days_back`
- Parse YAML frontmatter with `python-frontmatter`
- Skip `shareable: false`
- Skip paths in `state["processed_files"]`
- Return list of `{path, frontmatter, content}` dicts

Format the return value as readable plain text, not JSON. Copilot works better
with prose-formatted tool output than with raw JSON when it needs to reason
about the content — JSON is for structured lookups, not for understanding notes.

---

## `agent_mcp/state.py`

Identical to the state tracking in code-plan.md.

```python
def load_state() -> dict:
    # reads brain_agent_state.json
    # returns {"last_run": ISO string | None, "processed_files": [...]}

def save_state(processed_files: list[str]) -> None:
    # updates last_run to now
    # appends processed_files to existing list
```

Called by `scan_brain` (read) and `create_github_issue` (write).

---

## Dependencies — `requirements.txt`

```
mcp[cli]>=1.0.0         # MCP server SDK (FastMCP)
requests>=2.31.0
python-frontmatter>=1.1.0
python-slugify>=8.0.0
```

No `anthropic`, no `langgraph`. The dependency list nearly halves.

---

## What this gives up vs. the LangGraph plan

**Scheduling:** The MCP server runs on demand from Copilot chat. There's no
cron job. You run it manually each week by pasting the prompt.

If you want a scheduled run back, you can still add a GitHub Actions workflow
that runs `python -m agent_mcp.run_headless` — a thin script that constructs
the full prompt and calls the GitHub Models API (free tier) or Copilot API
rather than the Anthropic API. But this is optional and additive.

**Parallelism:** Copilot calls tools sequentially — there's no `Send()` fan-out.
Enrichment for 5 contexts will make ~20 serial tool calls. In practice this
takes 15–30 seconds in a Copilot chat session. Not a problem for a weekly
workflow you're present for.

**Determinism:** Copilot's reasoning is less controllable than a hard-coded
LangGraph node. If Copilot decides to skip `search_arxiv` for something that
does have a paper, you can't programmatically catch it. The prompt mitigates
this but doesn't eliminate it. Accept that occasional runs will be slightly
off and correct via prompt iteration.

---

## What this gains

No external API key. No secrets to manage beyond `GITHUB_TOKEN` (already in
your VS Code session). No LangGraph version pinning. No state machine to debug
when a node fails. The "agent" is just a prompt and 7 small Python functions.

The MCP server is also immediately useful beyond the LinkedIn workflow — you
can call any of these tools ad hoc from Copilot chat whenever you want.
`search_hackernews` and `fetch_langgraph_changelog` are useful standalone.