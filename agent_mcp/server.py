from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .brain_reader import format_brain_files, read_brain_files
from .enrichers import arxiv, github, hackernews, langgraph_docs
from .state import load_state, save_state

mcp = FastMCP("brain-linkedin-agent")

# Paths returned by the most recent scan_brain call within this server process.
# create_github_issue uses this list to mark exactly those files as processed,
# so the next run's scan_brain skips them. Module-global is fine because each
# MCP session is a single process.
_LAST_SCAN_PATHS: list[str] = []


@mcp.tool()
def scan_brain(days_back: int = 7) -> str:
    """Read .brain markdown files modified in the last N days.

    Returns each file's path, frontmatter, and content as one plain-text block
    per file, separated by '---'. Automatically skips files where
    `shareable: false` and files already processed in a prior run.
    """
    global _LAST_SCAN_PATHS
    state = load_state()
    processed = set(state.get("processed_files") or [])
    files = read_brain_files(days_back=days_back, skip_paths=processed)
    _LAST_SCAN_PATHS = [f["path"] for f in files]
    if not files:
        return ""
    return format_brain_files(files)


@mcp.tool()
def search_hackernews(query: str, days_back: int = 30) -> str:
    """Search Hacker News for recent discussions about a topic or concept.

    Returns the top 3 results: title, URL, points, comment count.
    Returns empty string if no results found in the time window.
    """
    return hackernews.search(query, days_back=days_back)


@mcp.tool()
def fetch_langgraph_changelog(num_releases: int = 5) -> str:
    """Fetch the most recent LangGraph release notes from GitHub.

    Returns release version, date, and headline changes for each.
    Useful for checking if a concept you learned was recently added or changed.
    """
    return langgraph_docs.fetch_changelog(num_releases=num_releases)


@mcp.tool()
def fetch_page(url: str, max_chars: int = 3000) -> str:
    """Fetch and return the text content of a web page.

    Use for LangGraph docs pages, blog posts, or any URL worth referencing.
    Content is truncated to max_chars to stay within context limits.
    """
    return langgraph_docs.fetch_page(url, max_chars=max_chars)


@mcp.tool()
def search_github_repos(query: str, min_stars: int = 50) -> str:
    """Search GitHub for repositories related to a concept or pattern.

    Returns repo name, star count, description, and URL.
    Filters out repos below min_stars to reduce noise.
    """
    return github.search_repos(query, min_stars=min_stars)


@mcp.tool()
def search_arxiv(query: str) -> str:
    """Search arXiv for papers related to an AI/ML concept.

    Only use this when the concept maps to a research area
    (e.g. ReAct, chain-of-thought, RAG, tool-use, RLHF).
    Returns paper title, authors, abstract summary, and URL.
    """
    return arxiv.search(query)


@mcp.tool()
def create_github_issue(title: str, body: str) -> str:
    """Create a GitHub issue in the current repository with the given title and body.

    Use this as the final step after generating all post options.
    Returns the URL of the created issue. After success, marks every brain file
    surfaced by the most recent scan_brain call as processed so the next run
    won't re-emit them.
    """
    url = github.create_issue(title=title, body=body)
    if _LAST_SCAN_PATHS:
        save_state(_LAST_SCAN_PATHS)
    return url


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
