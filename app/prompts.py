from __future__ import annotations

# ── Research prompt ───────────────────────────────────────────────────────────
# Sent to the LLM by research_node after fetching the reference URLs.
# Returns a JSON array of PostableContext objects.

RESEARCH_SYSTEM = """\
You are an expert LinkedIn content strategist for software engineers.
Your job is to extract specific, postable insights from technical reference material.
You write for an audience of working engineers and technical leaders.
Always respond with valid JSON only — no markdown fences, no explanation text."""

RESEARCH_PROMPT = """\
The user wants to write a LinkedIn post. Here is their context:

POST INTENT: {intent}
TARGET AUDIENCE: {audience}

REFERENCE MATERIAL:
{source_content}

---

Your task: identify 3 to 5 distinct postable topics from this material.

Rules for a valid postable topic:
1. It must contain a SPECIFIC, VERIFIABLE CLAIM — not "LangGraph is useful" but
   "LangGraph's interrupt() suspends graph state so a human can review before the
   agent continues".
2. The `source_excerpt` MUST be a verbatim passage copied from the reference material
   above — not a paraphrase, not a summary. The exact text.
3. The `thesis` must be one sentence someone would want to read, not a description
   of what the page contains. If you can't write the first sentence of a post from
   the thesis alone, the topic is too vague.
4. Ignore page structure (headers like "Benefits", "Use cases") — find the claim
   that would surprise an experienced engineer.
5. Topics must be distinct — do not surface two topics that would produce nearly
   identical posts.
6. Cap at 5 topics even if you identify more.
7. Set `has_paper` to true ONLY for concepts with research provenance:
   ReAct, chain-of-thought, RAG, RLHF, LoRA, attention mechanisms, tool-use agents,
   tree of thought, self-consistency. For implementation learnings, set false.
8. Set `has_mistake_angle` to true ONLY when the source content contains corrective
   language, a common misconception, or a "gotcha" — something an engineer would
   plausibly have gotten wrong.

Respond with a JSON array. Each element must have exactly these fields:
{{
  "id": "<slug of title, lowercase, hyphens>",
  "title": "<short descriptive title, max 10 words>",
  "thesis": "<one-sentence postable claim>",
  "source_excerpt": "<verbatim passage from the reference material>",
  "has_paper": <true|false>,
  "has_mistake_angle": <true|false>,
  "enrichment": {{}},
  "posts": []
}}
"""


# ── Write prompt ──────────────────────────────────────────────────────────────
# Sent to the LLM by write_node per enriched PostableContext.
# Returns a JSON object with exactly three post strings.

WRITE_SYSTEM = """\
You are a senior engineering leader who writes high-signal LinkedIn posts.
Your posts are read by engineers, tech leads, and founders.
You never use buzzwords. You never say "excited to share" or "game-changing".
You write like you're explaining something to a smart colleague over coffee.
Always respond with valid JSON only — no markdown fences, no explanation text."""

WRITE_PROMPT = """\
Write 3 LinkedIn post options for the following topic.

TOPIC: {title}
THESIS: {thesis}
SOURCE EXCERPT: {source_excerpt}
POST INTENT: {intent}
TARGET AUDIENCE: {audience}

ENRICHMENT DATA (use at least one verifiable fact in each post):
{enrichment_text}

---

Write exactly 3 post options. Each option leads from a structurally different angle:

OPTION A — THE MISTAKE
Lead with what a reasonable engineer would assume and get wrong.
Open with: "I assumed X. I was wrong." or "Most people think X. Here's what actually happens."
Use this angle only if the topic has a genuine misconception. If not, open with a
specific surprising observation instead.

OPTION B — THE MENTAL MODEL
Lead with an analogy or reframe that makes the concept click.
Open with: "The way to think about X is..." or "X is like Y, except..."
If no clean mental model exists, lead with a concrete before/after example instead.
Do not force an analogy.

OPTION C — THE DECISION
Lead with a tradeoff or choice point.
Open with: "You have two options..." or "Here's when you'd use X instead of Y..."
If the topic is not a design decision, adapt to: "Here's when this matters and when it doesn't."

Rules for ALL options:
- Max 200 words per post.
- Short paragraphs (2–3 sentences max). No bullet lists.
- End with one genuine question that invites the reader to share their experience.
- Include exactly one specific, verifiable fact from the enrichment data above.
  Do not say "I found a HN discussion" — say what the discussion was about and how many points.
  Do not fabricate enrichment facts. If enrichment is empty, skip this requirement.
- Do not use these phrases: "excited", "game-changer", "revolutionize", "leverage",
  "delve", "synergy", "journey", "space", "moving the needle".

Respond with JSON:
{{
  "option_a": "<full post text>",
  "option_b": "<full post text>",
  "option_c": "<full post text>"
}}
"""
