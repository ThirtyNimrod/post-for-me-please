---
type: decision
date: 2026-05-28
title: Use Azure OpenAI GPT-4o via a thin LLMManager class instead of the Anthropic SDK
tags: [architecture, langgraph, azure-openai, llm-abstraction]
shareable: true
---

# Use Azure OpenAI GPT-4o via a thin LLMManager class

## Context

`docs/plan/code-plan-1.md` specified the Anthropic Python SDK (`anthropic>=0.28.0`) with Claude as the LLM behind `split_into_contexts`, `generate_posts`, and the docs summariser. At the point of execution we had an Azure OpenAI GPT-4o key available and no Anthropic key. Three LLM call sites with different desired decoding params (low-temp structured JSON, mid-temp prose generation, low-temp short summary) need a single place to configure model + auth.

## Options considered

**Option A — Direct Anthropic SDK as planned**
Use `anthropic.Anthropic()` and call the messages API directly. Matches the plan verbatim. Requires sourcing an Anthropic key. No LangChain dependency.

**Option B — Direct `AzureChatOpenAI` instantiation in every node**
Use `langchain-openai`'s `AzureChatOpenAI` but build one inline at each call site. Fastest to write. Three duplicate config blocks; swapping deployments means touching three files.

**Option C — Thin `LLMManager` class wrapping `AzureChatOpenAI`**
One module with `for_split()`, `for_generate()`, `for_docs_summary()` classmethods, each returning a cached `AzureChatOpenAI` with the right temp/tokens. Nodes ask for a purpose, not a model.

## Decision

Chose **Option C**. The LangChain wrapper gives `with_structured_output(pydantic_model)` for free, which the structured-JSON output of `split_into_contexts` benefits from heavily — that's the most consequential prompt in the pipeline (per `docs/dicussion/implementation-1.md`) and it shouldn't be one stray `}` away from a JSON parse failure. The manager indirection means a future swap to Anthropic, Bedrock, or a different deployment is a one-file change rather than three.

## Tradeoffs accepted

- Adds `langchain-openai` + `langchain-core` to the dependency set (~30 MB install). Acceptable for a weekly cron job.
- LangChain wrapper has measurable overhead vs raw SDK on cold start — irrelevant for batch.
- `with_structured_output` shape coercion adds one retry on schema mismatch, which silently masks prompt drift. Mitigation: log the raw response when the parsed object is missing required fields. Not yet wired — TODO.
- Locks the agent to Azure region quota — if the deployment is throttled, the entire weekly run fails. Acceptable while we're on a single key.

## Outcome

_To be filled after the first end-to-end run against a real `.brain/` snapshot._
