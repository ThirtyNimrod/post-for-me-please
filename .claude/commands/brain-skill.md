---
description: Proactively capture high-signal developer learnings into .brain session, decision, and concept notes with strict structure and privacy rules.
---

# brain-skill

Developer knowledge capture skill for `.brain`.

## Reference examples

Use these files as canonical format examples when creating or updating notes:

- `.claude/brain-skill/001-send-api-for-parallel-enrichment.md` for `type: decision`
- `.claude/brain-skill/2025-05-26.md` for `type: session`
- `.claude/brain-skill/langgraph-reducers.md` for `type: concept`

When in doubt between template text in this file and stylistic details in those examples,
follow this file's required fields/sections first, then match wording style and density from
the corresponding example file.

## What this skill does

When this skill is active, you proactively maintain a `.brain` folder during the session.
You write three types of notes — session logs, decision records, and concept notes — at
specific moments without being asked. The notes feed a LinkedIn post agent that runs weekly,
so quality and consistency of structure matters more than volume.

**Core principle:** Capture the confusion, not just the answer. A note that says
"LangGraph's `add_messages` reducer silently deduplicates by message ID" is useful.
A note that says "learned about reducers" is not.

---

## Folder structure

```
.brain/
  sessions/        ← one file per coding day
  decisions/       ← one file per significant architectural choice
  concepts/        ← one file per mental model that clicked
```

Create the folders if they don't exist. Never write outside `.brain/`.

---

## File type 1 — Session log

**Path:** `.brain/sessions/YYYY-MM-DD.md`
If a session file for today already exists, append to it — do not create a new one.

### When to write

| Trigger | What to write |
|---|---|
| Session starts (this skill is invoked) | Write the session header (see template) |
| A bug or error is resolved — user says "that fixed it", "it works", "perfect" | Append a `## Debug` entry |
| A significant chunk of code is completed or merged | Append a `## Built` entry |
| User says "wrap up", "good for now", "let's stop here", or ends the session | Append the `## Summary` section |

### Template

```markdown
---
type: session
date: YYYY-MM-DD
tags: []          # fill with tech tags: langgraph, state-management, tool-use, etc.
shareable: true   # set false if any internal/org context appears anywhere in this file
---

# Session: YYYY-MM-DD

**Goal:** [one line — what were we trying to build or fix today]

---

## Debug: [short title of the problem]

**Symptom:** [what the error or wrong behaviour looked like]
**Wrong assumption:** [what we thought was happening]
**Root cause:** [what was actually happening]
**Fix:** [what resolved it]
**Takeaway:** [one sentence — what would prevent this mistake next time]

---

## Built: [short title of what was completed]

[2–4 sentences describing what was built and any non-obvious implementation detail worth remembering]

---

## Summary

**What I learned today:**
- [specific learning 1]
- [specific learning 2]
- [specific learning 3]

**What surprised me:**
- [something that was counterintuitive or unexpected]

**What I'd do differently:**
- [a tradeoff or decision that felt wrong in hindsight, or one still unresolved]
```

### Writing rules for session logs

- Under each `## Debug` entry, the **Takeaway** line is mandatory — this is what the LinkedIn agent uses. If there's no takeaway, the debug entry has no value.
- The `## Summary` section is the most important part of the whole file. Write it as if explaining the session to a colleague who wasn't there.
- If internal systems, company names, team names, or client names appear anywhere in the file, set `shareable: false` in the frontmatter.

---

## File type 2 — Decision record

**Path:** `.brain/decisions/NNN-kebab-title.md`
Where `NNN` is a zero-padded incrementing number (`001`, `002`, etc.).
Check the existing files to find the next number.

### When to write

Write a decision record when:
- The user asks "should I use X or Y", "what's the tradeoff between...", or "is it better to..."
- A genuine architectural or design choice is weighed with real options considered
- The user says "let's go with X" after deliberation

Write it **at the moment of choice**, immediately after the decision is made.
One record per decision — do not bundle multiple decisions into one file.

### Template

```markdown
---
type: decision
date: YYYY-MM-DD
title: [human-readable title, e.g. "Use Send() API over fan-out subgraphs"]
tags: []          # tech tags relevant to this decision
shareable: true   # false if internal context is involved
---

# [Title]

## Context

[2–3 sentences: what problem were we solving, what constraints existed]

## Options considered

**Option A — [name]**
[what it is, its key tradeoff]

**Option B — [name]**
[what it is, its key tradeoff]

## Decision

Chose **Option [X]** because [specific reason — not "it seemed better", but the actual
technical reason: performance, simplicity, LangGraph's intended pattern, etc.]

## Tradeoffs accepted

- [what we give up with this choice]
- [what remains uncertain or could change the decision later]

## Outcome

[Fill in later if possible: did the decision hold up? Would we make the same choice again?]
```

---

## File type 3 — Concept note

**Path:** `.brain/concepts/kebab-topic-name.md`
If a concept file for this topic already exists, update it rather than creating a new one.

### When to write

Write a concept note when a **mental model shift** happens. The signal is not that Claude
explained something — it's that the user demonstrated they understood it. Look for:

- User says "oh that makes sense", "ah so it's like...", "wait I get it now"
- User asks a follow-up question that shows the underlying concept clicked
- User correctly applies a concept they were confused about earlier in the session
- Claude gives an analogy and the user responds positively to it

When you see these signals, write the concept note **immediately** — the mental model is
freshest right now, not at the end of the session.

If a concept comes up repeatedly across sessions and you see a growing concept note,
enrich it — don't start a new file.

### Template

```markdown
---
type: concept
date: YYYY-MM-DD
title: [the concept name, plain English]
tags: []          # tech tags: always include the framework/library if applicable
shareable: true   # almost always true — pure technical concepts rarely contain org context
related_docs: ""  # URL to official docs for this concept, if known
---

# [Concept name]

## The confusion

[What was misunderstood or unclear before? Write this in first person — "I thought X meant Y"
or "I assumed Z worked like W". This is the most valuable part for LinkedIn posts — the
relatable starting point.]

## The mental model

[The plain-English explanation that made it click. Not the official definition — the analogy,
the reframe, the "oh it's actually like X" version. Keep it to 3–5 sentences.]

## The precise version

[The technically accurate version, once the mental model is established. Include any
important caveats, edge cases, or "this breaks when..." notes.]

## Code example

```python
# Minimal example showing the concept in action
# Keep this to 5–15 lines — the smallest thing that demonstrates the idea
```

## Why it matters

[One sentence: what goes wrong if you misunderstand this concept.]
```

---

## Privacy rules

These rules are non-negotiable. Apply them before writing any file.

1. **Company / org names** — never write the name of an employer, client, or internal product. Replace with neutral terms: "the platform", "an internal tool", "the codebase I'm working on".
2. **Team or person names** — omit entirely. "My team" is fine. "The infra team at [Company]" is not.
3. **Internal system names** — replace with generic descriptions. "Our event bus" → "a message queue". "ProjectX's API" → "an internal REST API".
4. **`shareable` flag** — if you had to sanitise anything in a file, set `shareable: false`. The LinkedIn agent will not touch files flagged false. When in doubt, set false.

---

## Tag vocabulary

Use these tags consistently so the LinkedIn agent can match concepts to enrichment sources.

**LangGraph / LangChain:** `langgraph`, `langchain`, `langgraph-agents`, `state-graph`, `tool-use`, `rag`, `memory`, `checkpointing`
**Agent patterns:** `agentic-systems`, `multi-agent`, `orchestration`, `planning`, `reflection`
**Python:** `python`, `async`, `pydantic`, `typing`
**General:** `debugging`, `architecture`, `api-design`, `performance`, `testing`

Add tags not in this list freely — the list is a starting point, not a constraint.

---

## What NOT to write

- Do not write a note just because something was discussed. Only write when a genuine debug resolution, decision, or mental model shift occurred.
- Do not summarise the conversation. The notes are not a transcript — they are distilled takeaways.
- Do not write vague notes. "Learned about state management" is not a note. "Learned that LangGraph's `Annotated` reducer runs on every state update, not just on explicit writes" is a note.
- Do not write during rapid back-and-forth debugging. Wait for the resolution before writing.

---

## Initialisation checklist

When this skill is invoked at the start of a session:

1. Check if `.brain/sessions/YYYY-MM-DD.md` exists for today. If not, create it with the session header template.
2. Ask: "What are we working on today?" — one line, for the **Goal** field.
3. Confirm `.brain/decisions/` and `.brain/concepts/` exist. Create them if not.
4. Resume silently — no further announcements until a trigger fires.
