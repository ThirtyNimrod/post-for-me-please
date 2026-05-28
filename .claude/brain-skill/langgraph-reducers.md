---
type: concept
date: 2025-05-26
title: LangGraph reducers
tags: [langgraph, state-graph, state-management]
shareable: true
related_docs: "https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers"
---

# LangGraph reducers

## The confusion

I thought state fields in LangGraph worked like regular Python attributes — each node
overwrites the field with whatever it returns, and the last write wins. So if two nodes
both write to `messages`, whichever ran last would clobber the other's output.

## The mental model

A reducer is a rule attached to a state field that says "when multiple updates come in
for this field, here's how to combine them." It's the same idea as a Redux reducer or
a database aggregate function — it defines *merge behaviour*, not just *write behaviour*.

The default (no reducer) is last-write-wins. `add_messages` is a reducer that says
"append new messages, but deduplicate by ID." You can write your own reducer for any
field — it's just a function `(current_value, new_value) -> merged_value`.

## The precise version

Reducers are defined via `Annotated` in the state TypedDict:

```python
from typing import Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # uses the add_messages reducer
    result: str                               # no reducer — last write wins
```

When a node returns `{"messages": [new_msg]}`, LangGraph calls
`add_messages(current_messages, [new_msg])` to produce the next state.
The node never sees or manages the merge — it just returns its contribution.

Important caveat: `add_messages` deduplicates by message `id`. If you're creating
messages programmatically and not setting unique IDs, you can accidentally lose messages.

## Code example

```python
from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage

class State(TypedDict):
    messages: Annotated[list, add_messages]

# Node returns only its new message — reducer handles the append
def my_node(state: State) -> dict:
    return {"messages": [AIMessage(content="hello")]}
```

## Why it matters

If you don't understand reducers and use a list field without one, parallel nodes will
race to overwrite each other's output and you'll lose data in ways that are very hard
to debug.
