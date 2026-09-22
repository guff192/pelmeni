# Workers are Pipeline-aware; there is no central routing layer

Each worker Agent Session receives the active Pipeline configuration at the start of its first Round. When the Pipeline changes mid-Session, the updated configuration is delivered to each Agent Session immediately after its next Turn completes — after the next tool call finishes, not at the Round boundary. Workers consult this configuration when deciding who to pass their Brief to next.

The alternative — a central routing layer that reads the Pipeline and delivers Briefs on workers' behalf — was rejected because it introduces infrastructure with no benefit at this scale. Workers already receive and act on structured inputs (Briefs, Consults); receiving the Pipeline configuration is the same pattern. A central router would add a new component that owns routing logic that belongs naturally to the worker.

## Consequences

A worker that is mid-execution when the Pipeline changes will route its current Brief using the Pipeline copy it currently holds. The updated configuration arrives immediately after the worker's next Turn completes (after the next tool call finishes), not at the Round boundary.
