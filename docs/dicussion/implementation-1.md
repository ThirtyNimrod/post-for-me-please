# Implementation discussion — LinkedIn brain agent

## The one node that determines everything else

`split_into_contexts` is the most consequential node in the entire graph. Everything
downstream — the enrichment queries, the post quality, the issue structure — depends on
the quality of what this node outputs. It deserves the most careful prompt engineering
and should be the first thing tested in isolation before anything else is wired up.

The hard problem it's solving: given a week of raw developer notes across multiple file
types, identify the 1–5 things that are *independently postable*. Not just "interesting
things that happened" — specifically things that have a concrete learning, a relatable
starting point, and enough texture to anchor a post that's useful to someone else.

A few failure modes to design against in the prompt:

**Too broad:** "LangGraph state management" is not a context. "LangGraph's `add_messages`
reducer silently deduplicates by message ID, which causes unexpected data loss in retry
loops" is a context. The prompt needs to push Claude toward specificity — the rule of
thumb is: if you can't write the first sentence of a post from the context title alone,
the context is too vague.

**Too many:** If there are 8 `.brain` files from a busy week, Claude will want to surface
8 contexts. Cap at 5 hard in the prompt. A week with 5 posts is a great problem to have;
a GitHub issue with 15 post options is unusable.

**Overlapping:** Two contexts that are really the same learning will produce near-identical
posts. The prompt should explicitly ask: "are these contexts distinct enough that someone
could post both in the same week without repetition?"

The `relevant_excerpt` field is critical and easy to get wrong. It should be the *exact
passage from the notes* — not a paraphrase, not a summary, the literal text. The post
generation node anchors to this. If it's paraphrased, the posts will feel generic because
they've lost the specific language that came from your actual experience.

---

## The Send() pattern — what it actually does

Using LangGraph's `Send()` API for the enrichment fan-out is the right call, but it's
worth being precise about what it does and what the gotchas are, because the docs are
thin on detail.

`Send("node_name", state_payload)` creates a deferred invocation of `node_name` with
`state_payload` as its input state. When `route_enrichment` returns a list of `Send()`
objects, LangGraph fires all of them concurrently. Each invocation of `enrich_context`
runs independently and returns a partial state update. Those partial updates are merged
back using the reducer defined on the field they write to — in our case `_append` on
`enriched_contexts`.

Two things that will bite you if you don't account for them:

1. **The node receives only the keys passed to Send().** If `enrich_context` tries to
   read `state["brain_files"]`, it will get a KeyError. The node must only read from
   the keys explicitly passed in the `Send()` payload. In our design that's just
   `state["context"]`.

2. **generate_posts will not run until all Send() invocations complete.** LangGraph
   waits for the full fan-out to resolve before moving to the next edge. This is the
   correct behaviour — you want all contexts enriched before generating posts. But it
   means one slow enrichment call (e.g. arXiv timing out) blocks the entire batch.
   Enforce a timeout on every external HTTP call, and return `None` fields on failure
   rather than raising.

---

## Enrichment: what to keep, what to drop

Not all enrichment sources will return useful results every week. The post generation
prompt needs to handle this gracefully — a context with no HN thread and no matching
changelog note should still produce a good post. The enrichment is additive colour,
not load-bearing structure.

Practical priority order:

**Always worth having:** HN thread (if found) and docs URL. The HN thread gives the post
currency ("this was debated last week"). The docs URL gives readers somewhere to go.
These two alone justify the enrichment step.

**High value when present:** Changelog note. "This behaviour changed in v0.2.4" is a
genuinely useful data point that you wouldn't know to include without fetching the
releases page. The fetch is cheap (one HTML page, parse 5 releases).

**Medium value:** GitHub repos. Useful for the "real-world usage" angle but the search
results are noisy — a repo that has `langgraph` as a topic isn't necessarily using the
specific pattern you learned. Apply a stars filter (50+) and don't treat this as
authoritative.

**Conditional:** arXiv. Only hit this when `has_paper=True`. For most LangGraph learnings
this will be false — it's relevant for things like ReAct agent design, chain-of-thought,
RAG architectures. When it's relevant, the paper citation elevates the post significantly.
When it's not, you're wasting a round trip and potentially hallucinating relevance.

One enrichment source not in the current plan worth considering later: the official
LangGraph `#announcements` or `#general` Discord channel via public scraping, or the
LangChain blog RSS feed. Either could surface "this was just officially announced"
context for learnings that overlap with new releases.

---

## The generate_posts prompt: three angles, not three styles

The post generation prompt from the previous version distinguished posts by *tone*
(hook, story, list). The revised version should distinguish by *angle* — the same
content approached from structurally different starting points:

- **Option A — The mistake:** Lead with what you got wrong. "I assumed X. I was wrong."
  This angle is the most relatable and consistently performs best on LinkedIn because it
  validates that experts make the same mistakes. The `confusion` field from concept notes
  is the direct source for this.

- **Option B — The mental model:** Lead with the analogy or reframe. "The way to think
  about X is Y." This works when the concept has a good teachable abstraction. It doesn't
  work when the learning was purely experiential — if there's no clean mental model, this
  angle will produce a weak post. The prompt should acknowledge this and allow Option B
  to fall back to a "here's the concrete example" format instead.

- **Option C — The decision:** Lead with the tradeoff or choice. "You have two options.
  Here's why I picked the one I did." This is natural for decision records and forced for
  concept notes. The prompt should only use this angle fully when `source_type == "decision"`.
  For sessions and concepts, it should adapt to "here's when you'd use X vs Y instead."

One constraint to add to the prompt that wasn't in the original: every post must contain
one specific, verifiable fact that came from the enrichment. Not "I found a HN discussion"
but "there's an active HN thread from last week where people are debating exactly this."
This is the "keep learning" value-add for your connections — it's not just your opinion,
it's a breadcrumb into a broader conversation.

---

## The issue format: designed for quick decision-making

The GitHub issue is the interface you'll interact with every week, so it's worth thinking
about its UX deliberately.

The most important design decision: group by topic, not by post option. The instinct is
to show all "Option A" posts together, then all "Option B" posts. Resist this. You don't
pick by angle — you pick by topic first, then angle. Structure the issue as:

```
## Topic 1: [title]
Option A | Option B | Option C

## Topic 2: [title]
Option A | Option B | Option C
```

This way, if Topic 2 is clearly the most interesting thing from your week, you can skip
Topic 1 entirely and focus on picking an angle for Topic 2.

Also worth adding to the issue: the source file reference and a collapsed `<details>`
block with the relevant excerpt. This gives you a quick sanity check — "is this actually
what I wanted to post about this week?" without having to open the `.brain` file.

---

## Implementation order

Build and test each layer independently before wiring the graph. The failure modes are
cleanest when caught in isolation.

**Phase 1 — File reading and parsing**
`scan_brain` + frontmatter parsing. Test with your actual `.brain` folder.
Verify: shareable filtering works, last_run tracking works, nothing leaks private content.

**Phase 2 — Context splitting (the critical one)**
`split_into_contexts` in isolation. Feed it sample `.brain` files and inspect the output.
Iterate on the prompt until the contexts are specific, distinct, and have good excerpts.
Don't move to enrichment until this is consistently good — everything else depends on it.

**Phase 3 — Enrichment (one source at a time)**
Build and test each enricher independently: HN, then docs, then GitHub, then arXiv.
Each enricher should have a simple `__main__` block for manual testing:
`python -m agent.enrichers.hackernews "conditional edges langgraph"`

**Phase 4 — Wire Send() fan-out**
Connect `split_into_contexts` → `enrich_context` via `route_enrichment`.
Test with two contexts, confirm parallel execution, confirm reducer accumulates correctly.

**Phase 5 — Post generation**
`generate_posts` against enriched context fixtures. Iterate on prompt.
Check all three angles are genuinely distinct.

**Phase 6 — GitHub issue**
`open_issue` last — it has side effects, so test it against a throwaway repo first.
Verify the issue format is readable and grouped correctly.

**Phase 7 — GitHub Actions**
Wire the workflow only after all nodes work end-to-end locally.
First run: use `workflow_dispatch` (manual trigger), not the cron schedule.

---

## Things that will probably need iteration

**The SPLIT_CONTEXTS_PROMPT** — this will almost certainly need at least 3 rounds of
refinement against real `.brain` files before the contexts are reliably specific and
distinct. Budget time for this.

**Enrichment quality vs. latency tradeoff** — with 5 contexts × 4 API calls each, you're
making 20 external calls in parallel. In GitHub Actions, this will be fast. Locally, you
may hit rate limits. The HN Algolia API is generous; the GitHub search API has a 10
requests/minute unauthenticated limit (60 authenticated). Always pass the token.

**`generate_posts` for weak contexts** — if `split_into_contexts` produces a context with
a vague excerpt and no enrichment hits, the posts will be generic. The solution is to fix
this in Phase 2 (prompt quality) rather than trying to handle it downstream. A context
that produces a bad post is a signal that `split_into_contexts` shouldn't have extracted it.

**arXiv relevance** — arXiv search by title/abstract keyword is noisy. A search for
"tool use agents" will return papers that aren't relevant to what you actually learned.
Consider constraining `has_paper=True` to a specific whitelist of concepts
(ReAct, CoT, RAG, RLHF, LoRA, attention) rather than having the LLM decide.