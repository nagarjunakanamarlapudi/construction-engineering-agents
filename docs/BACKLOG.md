# Product Backlog

This file records ideas that are worth discussing but are deliberately outside the current
implementation. A backlog item is not a promised or partially implemented feature.

## Retrieval-gated tool selection — “RAG over tools”

**Status:** Deferred for later design discussion.

The current Copilot has a small, explicit set of read-only tools. Its router chooses a route,
and strict rules allow only the tools assigned to that route. This is easier to understand,
test, and demonstrate safely.

If the application later grows to dozens or hundreds of tools, passing every tool description
to the model would waste context and make selection less reliable. A future design could:

1. store a short description, permissions, inputs, and examples for every tool;
2. search that catalogue using the question;
3. give the agent only the most relevant permitted tools; and
4. apply permission and risk checks before any selected tool becomes available.

Before implementation, the team must decide how to measure whether the correct tool was
retrieved, how to guarantee that required tools are not filtered out, and how authorization
overrides similarity. The current explicit allowlist remains the source of truth until those
questions are answered.
