---
type: concept
date: 2026-05-28
title: Tool errors as prefixed return strings, not exceptions
tags: [python, api-design, error-handling, agentic-systems, tool-use]
shareable: true
related_docs: ""
---

# Tool errors as prefixed return strings, not exceptions

## The confusion

I assumed enrichment tools should raise on HTTP failure / parse error / missing API key — the standard Python idiom is "exceptions for exceptional cases, callers `try/except`". When I first read `enrich_node`, I expected to see a per-future `try/except` block around `future.result()`. The code does have one — but the *tools themselves* never raise on the typical failure modes. They return strings.

## The mental model

Read tools encode failure into the **return type**, not the control flow. Every search/fetch function returns a string. Success = formatted content. Failure = a string prefixed with `"("` like `"(fetch_page failed: ConnectionError ...)"`. Downstream parsers check `startswith("(")` and skip cleanly. There is no try/except needed at the parse layer because the failure value is already a valid string of the same type.

The exception: **write** tools (`github.create_issue`) still raise. Read failures degrade gracefully (one missing enrichment field); write failures must surface to the UI so the user knows the post wasn't published.

## The precise version

The pattern is "errors as values" via a sentinel prefix. Tool contracts:

- Read tools (`fetch_page`, `hackernews.search`, `github.search_repos`, `arxiv.search`) return `str` — never raise on transport/parse errors.
- On error, they return `"(<tool name> failed: <error>)"`. The `"("` prefix is the sentinel — any well-formed result starts with a digit, letter, or markdown.
- Callers in `enrich.py` route everything through `_parse_first_*` / `_parse_repo_list`, all of which check `raw.startswith("(")` and return empty/None.
- The `ThreadPoolExecutor` block in `enrich_node` still has a `try/except future.result()` — but only to catch genuinely unexpected raises (bugs, OOM). The expected failure modes go through the string channel.
- Write tools raise. They're called from the UI's `try/except` block and surface errors via `st.error()`.

## Code example

```python
# In app/tools/fetch.py
def fetch_page(url: str, max_chars: int = 4000) -> str:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "..."})
        r.raise_for_status()
    except Exception as e:
        return f"(fetch_page failed: {e})"   # ← failure is a valid str
    # ... happy path ...

# In app/nodes/enrich.py
def _parse_first_hn_result(raw: str) -> tuple[str | None, str | None]:
    if not raw or raw.startswith("("):       # ← sentinel check, no try/except
        return None, None
    # ... parse the happy-path string ...
```

## Why it matters

Mixing exceptions with `ThreadPoolExecutor` is brittle: each `future.result()` needs its own try/except, and partial failures across N tools get noisy. With the string-sentinel convention, the executor loop stays one block, parsers stay one branch, and a failed HN search just means `hn_thread_title = None` in the final `EnrichmentResult` — the post gets written with whatever enrichment succeeded.

If you add a new read tool, follow the convention: return `"(<name> failed: ...)"` on every expected failure mode. If you make it raise, every downstream parser needs an extra try/except and the symmetry breaks.
