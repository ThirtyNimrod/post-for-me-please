# post-for-me-please

A LinkedIn post generator from my learnings.

It exposes my `.brain/` notes and a handful of enrichment APIs as MCP tools.
GitHub Copilot in VS Code becomes the orchestrator: it reads the notes,
decides what to enrich, drafts post options, and opens a GitHub issue with
the results.

## Layout

```
agent_mcp/
  server.py          # FastMCP server + 7 tools
  brain_reader.py    # .brain file walk + frontmatter parsing
  state.py           # brain_agent_state.json read/write
  enrichers/         # hackernews / github / langgraph_docs / arxiv
.vscode/mcp.json     # MCP server registration for VS Code Copilot
prompts/
  weekly-linkedin.md # the prompt you paste into Copilot chat each week
docs/plan/           # design history (code-plan-1.md = older LangGraph plan)
.brain/              # source notes — sessions, decisions, concepts
```

No `anthropic`, no `langgraph`. The "agent" is the Copilot chat session plus
these 7 Python functions.

## Install

```
python -m venv .venv
.venv\Scripts\activate           # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set `GITHUB_TOKEN` in your shell (or in `.vscode/mcp.json` env) so
`create_github_issue` and `search_github_repos` can call the GitHub API.

## Use

1. Open the folder in VS Code. Copilot reads `.vscode/mcp.json` and starts
   the MCP server automatically.
2. Paste the contents of `prompts/weekly-linkedin.md` into the Copilot chat.
3. Copilot calls `scan_brain`, runs enrichment, drafts posts, and opens an
   issue titled `Weekly LinkedIn post options — <date>`.

## Tools

| Tool                          | What it does                                                                |
| ----------------------------- | --------------------------------------------------------------------------- |
| `scan_brain`                  | Read `.brain/**/*.md` modified in the last N days, skip processed/private.  |
| `search_hackernews`           | Top 3 HN stories for a query within a time window.                          |
| `fetch_langgraph_changelog`   | Latest LangGraph GitHub releases — version, date, headline notes.           |
| `fetch_page`                  | Generic URL fetch with HTML stripped, truncated to a char budget.           |
| `search_arxiv`                | arXiv search (use only for research-paper-shaped concepts).                 |
| `create_github_issue`         | Open an issue on `GITHUB_REPOSITORY`; marks the surfaced brain files as processed. |

## State

`brain_agent_state.json` lives at the repo root. It tracks `last_run` and the
list of brain-file paths already turned into post options. Delete the file to
reset.
