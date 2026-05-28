from __future__ import annotations

import re
from html.parser import HTMLParser

import requests

_USER_AGENT = "post-for-me-please/1.0"


class _TextExtractor(HTMLParser):
    """Strip HTML tags and return visible text content."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "nav", "footer", "header"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "nav", "footer", "header"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        s = data.strip()
        if s:
            self.parts.append(s)


def fetch_page(url: str, max_chars: int = 4000) -> str:
    """Fetch a URL and return its visible text content, truncated to max_chars.

    Returns an error string prefixed with "(fetch_page failed:" on any failure
    so callers can treat the return value as plain text without try/except.
    """
    try:
        r = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": _USER_AGENT},
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


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://langchain-ai.github.io/langgraph/concepts/"
    print(fetch_page(url))
