# Tool access is enforced by a registry, not by convention

Each Agent Type has a fixed tool whitelist enforced by the tool registry. An Agent Session cannot invoke a Tool that is not in its whitelist, regardless of what its system prompt says or what the LLM attempts to call.

The alternative — trusting the system prompt to constrain tool use — was rejected because a system prompt is a soft constraint: a sufficiently persuasive conversation can cause the model to violate it, and there is no enforcement layer to catch the violation before the tool executes. Registry enforcement is a hard constraint applied before any hook runs.

## Consequences

Adding a new Tool requires an explicit decision about which Agent Types may use it. This is intentional friction: it forces the question "who should have access to this?" at the point of addition rather than as an afterthought.
