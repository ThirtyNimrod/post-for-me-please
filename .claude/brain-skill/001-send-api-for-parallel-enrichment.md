---
type: decision
date: 2025-05-26
title: Use Send() API for parallel enrichment over fan-out subgraphs
tags: [langgraph, multi-agent, orchestration, performance]
shareable: true
---

# Use Send() API for parallel enrichment over fan-out subgraphs

## Context

Building a node that needs to enrich N independent contexts simultaneously. Each context
hits multiple external APIs (HN, GitHub, docs). The contexts are independent — there's
no reason to run them sequentially.

## Options considered

**Option A — Sequential loop in a single node**
Iterate over contexts in Python, making all API calls in a for loop. Simple to write,
easy to debug.
Tradeoff: slow — N contexts × M APIs = N×M sequential calls. With 3 contexts and 4 APIs
that's 12 serial round trips.

**Option B — Fan-out subgraph with parallel branches**
Create a subgraph with a branch per context. LangGraph runs branches in parallel.
Tradeoff: requires knowing N at graph compile time. Contexts are dynamic — there might
be 2 or 6 depending on the week's notes.

**Option C — Send() API with a dynamic fan-out node**
The `Send()` API lets a node dynamically dispatch to another node multiple times with
different state payloads. Each dispatch runs in parallel. Results are collected back into
a list on the main state via a reducer.
Tradeoff: less familiar pattern, requires understanding how reducers collect `Send()` results.

## Decision

Chose **Option C — Send() API** because the number of contexts is dynamic and unknown at
compile time. The `Send()` pattern is exactly designed for this: map a list into parallel
node invocations without pre-defined branches.

## Tradeoffs accepted

- More complex to understand than a simple loop — anyone reading the graph needs to know
  how `Send()` works
- Error handling is less obvious: if one enrichment call fails, need to decide whether
  to fail the whole batch or collect partial results

## Outcome

[To be filled in after implementation]
