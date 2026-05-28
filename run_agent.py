"""Entry point. Loads .env (when present) then runs the graph once."""

from __future__ import annotations

import json
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agent.graph import build_graph


def main() -> int:
    graph = build_graph()
    final = graph.invoke({})

    if final.get("error"):
        print(f"Run error: {final['error']}", file=sys.stderr)
        # Don't fail the workflow on "nothing to post" — that's normal for quiet weeks.
        if "no contexts" in final["error"] or "does not exist" in final["error"]:
            return 0
        return 1

    url = final.get("issue_url")
    if url:
        print(f"Issue: {url}")
    else:
        print("No issue created (dry run or no contexts).")

    # Surface a compact summary for Actions logs.
    summary = {
        "brain_files_scanned": len(final.get("brain_files") or []),
        "contexts_extracted":  len(final.get("contexts") or []),
        "contexts_enriched":   len(final.get("enriched_contexts") or []),
        "posts_generated":     len(final.get("posts_by_context") or []),
        "issue_url":           url or "",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
