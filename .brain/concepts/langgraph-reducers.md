---
type: concept
date: 2026-05-28
title: LangGraph state reducers
tags: [langgraph, state-management, send-api]
shareable: true
related_docs: "https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers"
---

# LangGraph state reducers

## The confusion

I thought reducers were "merge logic that runs when two parallel branches both write the same key" — i.e. only relevant inside a `Send()` fan-out. I assumed a node *after* the fan-out, writing the same key, would *replace* the accumulated list. So I almost wrote `return {"enriched_contexts": [...with posts attached]}` from `generate_posts`, expecting it to overwrite the 5 enriched contexts collected by the reducer.

## The mental model

A reducer is bolted to the **field**, not to the fan-out. Once `enriched_contexts: Annotated[list[Context], _append]` is declared, *every* write to `enriched_contexts` — from any node, at any point in the graph — goes through `_append`. There is no "fan-out is over, normal replacement resumes" mode. If you want replacement-write semantics for a derived value, give it its own key with no `Annotated[..., reducer]`.

## The precise version

In `StateGraph`, a state schema field annotated as `Annotated[T, reducer_fn]` causes the runtime to call `reducer_fn(existing_value, node_return_value)` on every node return that includes that key. The reducer applies uniformly: serial nodes, parallel branches, and conditional edges all go through the same merge. The "untouched key" semantics (return value replaces) only applies to fields *without* a reducer annotation. So `_append` collecting parallel Sends is the same code path as a serial node "writing" — both append.

## Code example

```python
from typing import Annotated
from typing_extensions import TypedDict

def _append(left: list, right: list) -> list:
    return (left or []) + (right or [])

class State(TypedDict, total=False):
    fan_out_results: Annotated[list, _append]   # parallel sends accumulate here
    final: list                                 # no reducer — node returns replace this
```

A serial node downstream that wants to publish "the final list with posts attached"
must write to `final`, not `fan_out_results` — otherwise the list doubles.

## Why it matters

Misreading the reducer as fan-out-only causes silent data duplication: lists double, dicts merge in unexpected ways, and downstream nodes operate on what looks like the right shape but contains 2× the contexts. The bug doesn't crash — it just produces nonsense output, which is the worst failure mode.
