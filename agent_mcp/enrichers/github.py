from __future__ import annotations

import os

import requests

API = "https://api.github.com"


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def search_repos(query: str, min_stars: int = 50) -> str:
    """Return up to 5 GitHub repos matching `query` with at least `min_stars` stars."""
    q = f"{query} stars:>={min_stars}"
    try:
        r = requests.get(
            f"{API}/search/repositories",
            params={"q": q, "sort": "stars", "order": "desc", "per_page": 5},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        return f"(github search failed: {e})"
    if not items:
        return ""
    lines: list[str] = []
    for i, it in enumerate(items, 1):
        name = it.get("full_name")
        stars = it.get("stargazers_count", 0)
        desc = (it.get("description") or "").strip()
        url = it.get("html_url")
        lines.append(f"{i}. {name} — {stars} stars\n   {desc}\n   {url}")
    return "\n\n".join(lines)


def create_issue(title: str, body: str) -> str:
    """Open an issue on `GITHUB_REPOSITORY`. Returns the issue HTML URL."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY env var is not set")
    if not os.environ.get("GITHUB_TOKEN"):
        raise RuntimeError("GITHUB_TOKEN env var is not set")
    r = requests.post(
        f"{API}/repos/{repo}/issues",
        json={"title": title, "body": body},
        headers=_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("html_url", "")
