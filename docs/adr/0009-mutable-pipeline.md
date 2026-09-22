# The Pipeline is mutable mid-Session

The user may reconfigure the active Pipeline while a Session is running, not only before it starts. A mid-task Pipeline change takes effect on the next step that has not yet begun.

The alternative — a fixed Pipeline locked at Session start — was rejected because development tasks change shape as investigation reveals scope. A user who discovers mid-task that the Reviewer step is unnecessary for a trivial change should be able to remove it without abandoning the Session and starting over.

## Consequences

Workers must consult the active Pipeline configuration to determine who they pass a Brief to next, rather than relying on a hardwired successor. A Pipeline change does not affect Agent Sessions that are already executing their current step; it affects routing at the next handoff point.
