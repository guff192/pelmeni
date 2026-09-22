# Workers attempt peer resolution before escalating to the Manager

When a worker Agent Session reaches a situation it cannot resolve alone, it must first judge whether another worker Agent Session can provide what it needs — via a direct Query. Only if peer resolution is inapplicable or fails does the worker raise an Escalation to the Manager.

The alternative — routing all inter-agent communication through the Manager — was rejected because it turns the Manager into a message relay, filling its Model Context with routine clarifications and preventing it from focusing on decisions that genuinely require its authority. Peer resolution keeps the Manager's attention on the situations where its judgment is irreplaceable: conflicts workers cannot settle themselves, and the Final Report.

## Consequences

Workers must be able to identify which Agent Type holds the information they need, and must be able to decide when a situation exceeds peer resolution. This judgment is delegated to the worker's own reasoning; it is not encoded as a routing table.
