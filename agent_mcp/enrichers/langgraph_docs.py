from __future__ import annotations

import re
from html.parser import HTMLParser

import requests

GH_RELEASES = "https://api.github.com/repos/langchain-ai/langgraph/releases"


def fetch_changelog(num_releases: int = 5) -> str:
    """Return the most recent LangGraph release notes via the public GitHub API.

    No auth required for public-repo release reads; works the same in CI and locally.
    """
    try:
        r = requests.get(
            GH_RELEASES,
            params={"per_page": num_releases},
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        r.raise_for_status()
        releases = r.json()
    except Exception as e:
        return f"(langgraph changelog fetch failed: {e})"
    if not releases:
        return ""
    blocks: list[str] = []
    for rel in releases[:num_releases]:
        tag = rel.get("tag_name") or rel.get("name") or "?"
        date = (rel.get("published_at") or "")[:10]
        body = (rel.get("body") or "").strip()
        head = body.splitlines()[:8]
        body_trim = "\n".join(head).strip()
        blocks.append(f"{tag} ({date})\n{body_trim}".rstrip())
    return "\n\n---\n\n".join(blocks)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        s = data.strip()
        if s:
            self.parts.append(s)


def fetch_page(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and return its text content (HTML stripped), truncated to `max_chars`."""
    try:
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "brain-linkedin-agent"},
        )
        r.raise_for_status()
    except Exception as e:
        return f"(fetch_page failed: {e})"
    ctype = r.headers.get("Content-Type", "")
    text = r.text
    if "html" in ctype.lower() or text.lstrip().startswith("<"):
        ex = _TextExtractor()
        try:
            ex.feed(text)
        except Exception:
            pass
        text = "\n".join(ex.parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n…(truncated)"
    return text
