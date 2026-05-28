"""open_issue — file the weekly issue + update run-state."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

from agent.state import AgentState, Context
from agent.state_store import mark_run


_GH_API = "https://api.github.com"


def _excerpt_block(excerpt: str) -> str:
    if not excerpt:
        return ""
    return f"<details>\n<summary>Relevant excerpt</summary>\n\n```\n{excerpt}\n```\n\n</details>\n"


def _format_topic(idx: int, ctx: Context) -> str:
    src_files = ", ".join(f"`{p}`" for p in (ctx.get("source_files") or []))
    posts = ctx.get("posts") or ["", "", ""]
    a, b, c = (posts + ["", "", ""])[:3]
    enrichment = ctx.get("enrichment") or {}

    enrichment_lines = []
    if enrichment.get("hn_thread_url"):
        enrichment_lines.append(f"- HN: [{enrichment.get('hn_thread_title','thread')}]({enrichment['hn_thread_url']})")
    if enrichment.get("docs_url"):
        enrichment_lines.append(f"- Docs: {enrichment['docs_url']}")
    if enrichment.get("changelog_note"):
        enrichment_lines.append(f"- Changelog: {enrichment['changelog_note']}")
    if enrichment.get("github_repos"):
        enrichment_lines.append(f"- Repos: {', '.join(enrichment['github_repos'][:3])}")
    if enrichment.get("arxiv_url"):
        enrichment_lines.append(f"- Paper: [{enrichment.get('arxiv_title','arxiv')}]({enrichment['arxiv_url']})")
    enrichment_block = "\n".join(enrichment_lines) or "_no enrichment matches_"

    return f"""## Topic {idx}: {ctx.get('title','(untitled)')}

> Source: **{ctx.get('source_type','?')}** — {src_files or '_unknown_'}

{_excerpt_block(ctx.get('relevant_excerpt',''))}

**Enrichment**
{enrichment_block}

<details open>
<summary>Option A — The mistake / fix</summary>

{a or '_(no draft)_'}
</details>

<details>
<summary>Option B — The mental model</summary>

{b or '_(no draft)_'}
</details>

<details>
<summary>Option C — The decision / tradeoff</summary>

{c or '_(no draft)_'}
</details>

---
"""


def _build_body(contexts: list[Context]) -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (
        f"# Weekly LinkedIn post options — {date_str}\n\n"
        "Pick one post from any topic below. Copy it, post to LinkedIn, close this issue.\n\n"
        "---\n\n"
    )
    body = "".join(_format_topic(i + 1, ctx) for i, ctx in enumerate(contexts))
    return header + body


def open_issue(state: AgentState) -> dict:
    contexts = state.get("posts_by_context") or []
    if not contexts:
        return {"issue_url": "", "error": "no contexts to post"}

    repo = os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        # Local/dry-run: print + persist instead of calling the API.
        body = _build_body(contexts)
        print("=== ISSUE BODY (dry run — set GITHUB_REPO + GITHUB_TOKEN to post) ===")
        print(body)
        return {"issue_url": "", "error": "GITHUB_REPO or GITHUB_TOKEN missing"}

    body = _build_body(contexts)
    title = f"Weekly LinkedIn post options — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    try:
        r = requests.post(
            f"{_GH_API}/repos/{repo}/issues",
            json={"title": title, "body": body, "labels": ["linkedin-post"]},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        r.raise_for_status()
        issue_url = r.json().get("html_url", "")
    except Exception as e:
        return {"issue_url": "", "error": f"issue creation failed: {e}"}

    # Update persistent run-state only after successful issue creation.
    processed = []
    for ctx in contexts:
        processed.extend(ctx.get("source_files") or [])
    mark_run(processed)

    print(f"Issue created: {issue_url}")
    return {"issue_url": issue_url}
