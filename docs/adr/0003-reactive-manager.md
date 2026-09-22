# Manager is reactive, not observing

The Manager Agent Session has no visibility into the work happening inside other Agent Sessions. It does not receive copies of peer Briefs or Queries; it waits to be prompted — by a worker raising an Escalation, by the Reviewer delivering the task-complete Brief, or by the user.

The alternative — a monitoring Manager that observes all sessions in real time — was rejected on two grounds. First, it would flood the Manager's Model Context with implementation detail it has no authority to act on, exhausting the window before it can reason about what matters. Second, it would make the Manager a passive consumer of events rather than a decisive actor, blurring the boundary between coordination and implementation.

Keeping the Manager reactive enforces the boundary: workers handle implementation, the Manager handles decisions that workers cannot make themselves.
