# Build the agent loop from scratch, no SDK

Pelmeni owns its agent loop rather than delegating to a framework such as LangChain, LangGraph, or CrewAI. The loop is the ~100-line core of the system: call the LLM, execute tool calls, append results, repeat. Every message in the Model Context is directly visible and mutable by the loop.

## Considered options

- **LangGraph** — orchestrates steps inside a single agent (branching, pause/resume, durable checkpoints). Our coordination problem is between agents via a message bus, which LangGraph doesn't address. It also hides the message list, which is exactly the thing pelmeni must control to implement context compaction.
- **CrewAI / AutoGen / similar** — introduce the same message-list opacity, plus vendor-specific message formats that would couple agents to one abstraction.
- **Own loop** — chosen. Full control over every token sent to the model, trivial to debug, model-agnostic, and the right fit for our between-agent coordination model.

## Consequences

LangGraph remains a valid option to adopt inside a single, complex Agent Session if its branching and pause/resume capabilities become necessary — without affecting the rest of the system.
