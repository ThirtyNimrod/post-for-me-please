# Implementation discussion 2 — Reference-first LinkedIn post agent

## Why the shift from brain-first to reference-first matters

The original pipeline (plan 1 LangGraph, plan 2 MCP) started from your notes and
asked: "what from this week is postable?" That's a discovery problem.

This version starts from your intent and asks: "given what I'm pointing at, what's
the best angle?" That's a framing problem. The distinction matters because:

- Discovery requires high-quality source notes. Bad notes → bad contexts → bad posts.
  No amount of prompt engineering rescues weak input.
- Framing works even with just a URL and a sentence. The references are the ground truth.
  Your intent is the editorial filter. The LLM's job is synthesis, not excavation.

The reference-first approach is also lower-friction for weeks when you haven't been
writing brain notes — which will happen. A URL + one sentence is enough to run the
full pipeline.

---

## The research_node is still the most consequential node

The same logic from `implementation-1.md` applies: everything downstream depends on
the quality of `PostableContext` candidates this node produces.

But the failure modes shift slightly:

**Too summarized:** The LLM will want to produce clean, polished thesis statements
from the reference content. Resist this. The `source_excerpt` must be a verbatim
passage from the fetched page — not a paraphrase. The write_node anchors to this
text. Paraphrased excerpts produce generic posts.

**Too literal:** Conversely, if the LLM just extracts bullet points from the page
without synthesizing a *postable angle*, the candidates will be content-dump outlines,
not posts. The `thesis` field is the key: it must be a claim someone would want to
read, not a description of what the page contains.

**Influenced by page structure:** Pages with headers like "Benefits" and "Use cases"
will bias the LLM toward extracting those sections as candidates. The prompt needs to
push against this: "ignore page structure — find the claim that would surprise an
experienced engineer, not the one the author highlighted."

**`has_paper` reliability:** The research node sets `has_paper=True` to trigger arXiv
enrichment. This flag should only be true for concepts with genuine research provenance
(ReAct, CoT, RAG, RLHF, attention mechanisms). The prompt should include an explicit
whitelist rather than asking the LLM to decide — LLMs are optimistic about academic
relevance and will set this too often, wasting a round-trip on irrelevant papers.

---

## The interrupt() pattern in Streamlit — implementation detail

LangGraph's `interrupt()` suspends the graph and returns control to the caller.
Streamlit's execution model re-runs the entire script on every user interaction.
These two patterns conflict in a subtle way that will bite you if not handled carefully.

**The problem:** When the user clicks "Confirm selection" in Stage 2, Streamlit
re-runs `streamlit_app.py` from the top. If you naively call `graph.invoke()` again,
you restart the graph from scratch — losing the research_node output.

**The fix:** `st.session_state` must store:
1. `thread_id` — created once on "Run", never regenerated.
2. `stage` — an integer (1–4) tracking where in the flow you are.
3. `candidates` — stored after the first interrupt returns.

On each Streamlit re-run, check `st.session_state.stage` to decide what to render
and whether to call `graph.invoke()` vs. `graph.invoke(Command(resume=...))`.

```python
if st.session_state.stage == 1:
    render_input_form()
elif st.session_state.stage == 2:
    render_candidate_selection(st.session_state.candidates)
elif st.session_state.stage == 3:
    run_enrichment_and_advance()  # no user input — auto-advances to stage 4
elif st.session_state.stage == 4:
    render_post_options(st.session_state.final_posts)
```

The `MemorySaver` checkpointer stores graph state keyed by `thread_id` — so
`graph.invoke(Command(resume=selected_ids), config)` correctly resumes from the
interrupt point rather than restarting.

**One gotcha:** `MemorySaver` is in-memory and process-scoped. If Streamlit hot-reloads
(code change while running), the checkpointer is wiped and the thread_id becomes stale.
During development, always start a fresh session after a code change that touches
`graph.py` or any node.

---

## Enrichment: same priority order, simpler trigger

The priority logic from `implementation-1.md` still holds:

1. HN thread — highest signal, always call.
2. Docs fetch — high value, call when a relevant URL can be inferred.
3. GitHub repos — medium value, noisy below 50 stars.
4. arXiv — conditional on `has_paper`, explicitly scoped to known research concepts.

One change: in the MCP version, Copilot decided whether to call each enricher.
Here, `enrich_node` calls all applicable enrichers unconditionally (per the priority
logic above) using `concurrent.futures.ThreadPoolExecutor`. This removes the
"Copilot skips arXiv for something that has a paper" failure mode — the code enforces
the logic, not the LLM's inference.

The `concurrent.futures` approach over `asyncio.gather()` is deliberate: `requests`
is synchronous. Wrapping synchronous HTTP calls in `asyncio` requires `loop.run_in_executor`
anyway — ThreadPoolExecutor is cleaner and equally fast for 4 calls.

---

## The write_node prompt: anchoring to enrichment facts

The key constraint from `implementation-1.md` carries forward: every post must contain
one specific, verifiable fact from the enrichment. In `WRITE_PROMPT`, this should be
an explicit requirement with examples:

**Do:** "there's an active HN thread from last week with 200+ points where engineers
are debating exactly this tradeoff"

**Do:** "this pattern was introduced in LangGraph v0.2.4"

**Do:** "langchain-ai/langgraph has 12k stars and this is one of the top-asked patterns
in their GitHub issues"

**Don't:** "this is a well-known topic in the community" (generic, unverifiable)

The `WRITE_PROMPT` should receive the full `EnrichmentResult` as structured text and
require the model to pick one fact and cite it inline. If `enrichment` is empty
(all tools returned nothing), the post should acknowledge this and not fabricate currency.

---

## A/B/C angles: when each works and when it doesn't

This mirrors `implementation-1.md` but adjusted for reference-first context:

**Option A — The mistake** works when the reference page describes a common
misconception or the user's `intent` signals "I got this wrong initially". Best
performer on LinkedIn because it validates that experts make the same mistakes.

The research_node should flag `has_mistake_angle: bool` on each candidate based on
whether the source content contains corrective or "gotcha" language. This gives the
write_node a signal that Option A will be strong — otherwise it may produce a weak
"I assumed X" where X is not something anyone would assume.

**Option B — The mental model** works when the reference content contains a genuine
analogy or abstraction. It does not work when the learning is purely experiential.
The `WRITE_PROMPT` should include a fallback: "if no clean mental model exists in
the source material, Option B should lead with a concrete example instead of forcing
an analogy."

**Option C — The decision** is strongest when the reference content describes a
tradeoff or architecture choice. For reference pages that are purely explanatory
(e.g., docs pages without a decision context), Option C should adapt to
"here's when you'd use X vs. Y" rather than "I decided to use X."

---

## Testing strategy

The implementation-1.md phased approach still applies, adapted for this architecture:

**Phase 1 — Tool layer:** Each tool in `app/tools/` should have a `__main__` block
for manual testing:
```
python -m app.tools.hackernews "LangGraph interrupt patterns"
python -m app.tools.fetch https://langchain-ai.github.io/langgraph/concepts/
```

**Phase 2 — research_node in isolation:** Feed it two fixture URLs (a LangGraph docs
page and an HN discussion) and print the candidates. Iterate on `RESEARCH_PROMPT`
until:
- Candidates are specific (verifiable claim, not summary)
- `source_excerpt` is verbatim text from the fetched content
- `has_paper` is conservatively set

**Phase 3 — enrich_node in isolation:** Feed it a fixture `PostableContext` and
print the `EnrichmentResult`. Check:
- All 4 tools are called (or correctly skipped)
- Failures return `None`, not exceptions
- Runs in under 8 seconds (parallel HTTP calls)

**Phase 4 — write_node in isolation:** Feed it a fixture enriched candidate and
print the 3 posts. Check:
- Each option leads with a structurally different hook
- Each contains one enrichment fact
- Word count ≤200

**Phase 5 — Full graph with fixtures:** Run end-to-end with 2 fixture URLs, manually
call `graph.invoke(Command(resume=["id1"]))` to simulate the UI interrupt, verify
`final_posts` is populated correctly.

**Phase 6 — Streamlit UI:** Only wire the UI after phases 1–5 pass. The UI is thin —
most bugs caught at phase 5 will not resurface in the UI.

---

## Things that will need iteration (same as before, adapted)

**`RESEARCH_PROMPT`** — will need at least 3 rounds of refinement against real URLs.
The excerpt quality is the single most important variable. Budget time for this.

**Candidate count calibration** — 3 seems low, 5 may be too many for the UI. Start
with a cap of 4 and see how the card layout feels in practice. The UI can always
support fewer.

**`fetch_page` content quality** — JavaScript-heavy docs sites (e.g., some React-based
doc systems) return almost no content after HTML stripping. The `_TextExtractor` in
`.backup` handles basic HTML but not SPAs. If a key reference URL returns <500 chars,
warn the user in the UI rather than silently producing a weak candidate.

**Streamlit threading** — `st.spinner` blocks the Streamlit thread while the graph
runs synchronously. For research_node (which makes 3 HTTP calls + 1 LLM call), this
could be 5–15 seconds. Use `st.status` with streaming updates if available in the
installed Streamlit version, or accept the blocking spinner for a local tool.

**GitHub issue format** — same grouped-by-topic structure recommended in
implementation-1.md: topic first, then A/B/C under it. The issue body should be
generated in `write_node` or in a thin helper in `ui/streamlit_app.py` — not in
the GitHub tool itself, which should remain a dumb `create_issue(title, body)` call.
