"""All LLM prompt templates. Kept separate so they can be iterated without touching node logic."""

SPLIT_CONTEXTS_PROMPT = """\
You are reading a week of raw developer notes from a `.brain/` folder. Your job is to
extract 1–5 *independently postable* topics for LinkedIn.

A postable topic must:
- have a specific, concrete learning (not a category like "agents" or "state management")
- stand alone — readable without context from other topics
- map to one of: a debug resolution, an architectural decision, or a concept that clicked

Rules:
- HARD CAP at 5 topics. If a week is busy, pick the strongest 5.
- Reject vague topics. Heuristic: if you can't write the first sentence of a LinkedIn post
  from the title alone, the topic is too vague — refine it or drop it.
- No overlap. Two topics that produce near-identical posts should be merged or one dropped.
- `relevant_excerpt` MUST be the EXACT verbatim text from the notes — not a paraphrase,
  not a summary. The post generator anchors to this language.
- `source_type` is "session" | "decision" | "concept" based on which note the topic came from.
- `confusion` is set only when `source_type=="concept"` AND the note has a "The confusion"
  section — copy that section verbatim. Otherwise null.
- `has_paper` is true ONLY when the topic explicitly maps to one of:
  ReAct, chain-of-thought, RAG, RLHF, LoRA, attention mechanisms, tool-use research.
  Default false.
- `tags` come from the source file frontmatter — propagate them.
- `id` is a kebab-case slug of `title`.
- `source_files` lists every `.brain/` path that contributed to the topic.

Return ONLY valid JSON matching the requested schema. No markdown fences, no preamble.

--- NOTES ---
{notes}
--- END NOTES ---
"""

GENERATE_POSTS_PROMPT = """\
You are writing three LinkedIn post drafts for the same technical topic, each from a
structurally DIFFERENT angle. Not three styles — three angles.

Topic: {title}
Source type: {source_type}

Relevant excerpt from my notes (use this language — do not paraphrase away its texture):
{relevant_excerpt}

{confusion_block}

Enrichment context (incorporate ONE specific verifiable fact from this into each post):
{enrichment_summary}

ANGLES:

**Option A — The mistake**
Lead with what I got wrong. Pattern: "I assumed X. I was wrong. Here's what's actually
true." Use the confusion section if present. This is the most relatable angle.

**Option B — The mental model**
Lead with the analogy or reframe. Pattern: "The way to think about X is Y." If the topic
has no clean teachable abstraction, fall back to: "Here's the concrete example that made
it click."

**Option C — The decision / tradeoff**
For source_type=="decision": lead with the tradeoff. "You have two options. Here's why
I picked one." For session/concept: lead with "Here's when you'd use X vs Y instead."

CONSTRAINTS for every post:
- 100–180 words
- First line is the hook — must work as a standalone preview
- One specific, verifiable fact from the enrichment summary
- No hashtags, no emoji, no "thoughts?" closing
- First person, plain language, no LinkedIn-speak ("game changer", "unlock", "10x")

Output format — exactly this, no other text:

---POST A---
<post A text>
---POST B---
<post B text>
---POST C---
<post C text>
"""

DOCS_SUMMARISE_PROMPT = """\
Summarise the following documentation page in 2–3 sentences. Focus on what the page
*teaches* — not what features it lists. Write for someone who already knows the broader
framework and wants the specific behaviour of this page.

URL: {url}

CONTENT:
{content}
"""
