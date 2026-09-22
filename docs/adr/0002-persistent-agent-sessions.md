# Agent Sessions persist for the duration of the Session

All Agent Sessions are created when the user's Session begins and kept alive until it ends. A session does not terminate after producing a Brief or a Query response; it waits for the next prompt.

The alternative — spin each Agent Session up on demand and tear it down when its immediate task is complete — was rejected for two reasons. First, a stateless session has no continuity: it cannot reason about earlier Briefs it produced or Queries it answered without reconstructing that history from external storage. Second, spin-up latency compounds across multi-step tasks where agents interact repeatedly.

## Consequences

All Agent Sessions accumulate Model Context pressure over the lifetime of a Session. Context compaction must be applied per Agent Session independently, not globally.
