"""GitHub repo search. Filter to >=50 stars. Returns 'owner/repo (N stars)' strings."""

from __future__ import annotations

import os

import requests


_API = "https://api.github.com/search/repositories"


def search_repos(tags: list[str], timeout: float = 8.0) -> list[str]:
    if not tags:
        return []

    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    query = f"{tags[0]} topic:langgraph language:python"

    try:
        r = requests.get(
            _API,
            params={"q": query, "sort": "stars", "per_page": 5},
            headers=headers,
            timeout=timeout,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception:
        return []

    out = []
    for it in items:
        if it.get("stargazers_count", 0) < 50:
            continue
        out.append(f"{it['full_name']} ({it['stargazers_count']} stars)")
        if len(out) == 3:
            break
    return out


if __name__ == "__main__":
    import json
    import sys
    args = sys.argv[1:] or ["state-management"]
    print(json.dumps(search_repos(args), indent=2))
