You are helping me generate LinkedIn post options from my developer notes.

Follow these steps in order:

1. Call `scan_brain` to read this week's .brain files. If it returns nothing,
   stop and tell me there's nothing new to post about.

2. Read the returned files carefully. Identify up to 5 distinct, postable topics.
   A topic is postable if it has a specific, concrete learning — not just
   "I worked on X" but "I discovered that X works like Y when Z".

3. For each topic, call the relevant enrichment tools:
   - Always call `search_hackernews` with the concept name
   - Always call `fetch_langgraph_changelog` (once total, not per topic)
   - Call `fetch_page` with the relevant LangGraph docs URL if one is obvious
   - Only call `search_arxiv` if the topic maps to a research concept like
     ReAct, chain-of-thought, RAG, or similar

4. For each topic, write 3 LinkedIn post options:
   - Option A: Lead with what I got wrong or assumed incorrectly. Relatable hook.
   - Option B: Lead with the mental model or analogy that made it click.
   - Option C: Lead with the tradeoff or design decision.
   Each post: max 200 words, short paragraphs, one question at the end.
   Weave in one specific detail from the enrichment (HN thread, changelog note, etc.)

5. Call `create_github_issue` with all the options formatted by topic.
   Issue title: "Weekly LinkedIn post options — [today's date]"

Don't ask me questions during the process. Work through all steps and create
the issue at the end. Tell me the issue URL when done.
