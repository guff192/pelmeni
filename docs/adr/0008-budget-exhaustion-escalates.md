# Loop budget exhaustion triggers an Escalation, not an automatic failure

When a loop's Loop Budget is exhausted before its natural exit condition, the loop raises an Escalation to the Manager rather than failing automatically or surfacing the situation directly to the user.

The Manager then issues a Ruling: either a Budget Extension (if the extension allowance permits) or a directive to stop. Stopping does not mean accepting partial work — the Manager presents the situation to the user in the Final Report with explicit options.

## Considered options

- **Auto-fail** — loop terminates immediately, task marked failed. Rejected: throws away potentially valuable partial progress without giving the user or Manager a chance to make a judgment call.
- **Direct user notification** — bypass Manager, prompt the user immediately. Rejected: inconsistent with the model where Manager is the sole interface to the user during a task; it also breaks the Manager's ability to add context or consult workers before the user sees the situation.
- **Accept partial work silently** — mark the loop done and proceed. Rejected explicitly: the user must always have visibility into what is incomplete and a choice about what to do next.
- **Escalation to Manager** — chosen. Consistent with the rest of the model; the Manager is the right authority for decisions that workers cannot make themselves, and budget extension is exactly that kind of decision.
