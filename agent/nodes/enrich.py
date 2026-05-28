"""enrich_context — invoked once per context via Send().

Runs all enrichers in parallel via ThreadPoolExecutor. Returns ONE context appended
to enriched_contexts via the _append reducer.

Send() gotcha: when this node is fired via Send("enrich_context", {"context": ctx}),
the incoming state contains ONLY the keys passed to Send. Do not read brain_files,
raw_file_contents, etc. — read state["context"].
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from agent.enrichers import arxiv, github, hackernews, langgraph_docs
from agent.state import Context, EnrichmentResult


def enrich_context(state: dict) -> dict:
    ctx: Context = state["context"]
    tags: list[str] = ctx.get("tags") or []
    title: str = ctx.get("title") or ""
    has_paper: bool = bool(ctx.get("has_paper"))

    def hn():    return hackernews.search(tags, title)
    def docs():  return langgraph_docs.search(tags, title)
    def gh():    return github.search_repos(tags)
    def arx():   return arxiv.search(tags, title) if has_paper else {"arxiv_title": None, "arxiv_url": None}

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_hn   = pool.submit(hn)
        f_docs = pool.submit(docs)
        f_gh   = pool.submit(gh)
        f_arx  = pool.submit(arx)

        hn_r   = f_hn.result()
        docs_r = f_docs.result()
        gh_r   = f_gh.result()
        arx_r  = f_arx.result()

    enrichment: EnrichmentResult = {
        "hn_thread_title": hn_r["hn_thread_title"],
        "hn_thread_url":   hn_r["hn_thread_url"],
        "docs_url":        docs_r["docs_url"],
        "docs_summary":    docs_r["docs_summary"],
        "changelog_note":  docs_r["changelog_note"],
        "github_repos":    gh_r,
        "arxiv_title":     arx_r["arxiv_title"],
        "arxiv_url":       arx_r["arxiv_url"],
    }

    enriched: Context = {**ctx, "enrichment": enrichment}
    return {"enriched_contexts": [enriched]}
