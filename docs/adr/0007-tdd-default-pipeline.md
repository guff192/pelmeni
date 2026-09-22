# TDD is the default pipeline order: Tester before Builder

In the Default Pipeline, the Tester writes failing tests from the Investigator's findings before the Builder makes any code change. The Builder's job is then to make those tests pass, not to define what "done" looks like.

The alternative — Builder implements first, Tester verifies after — was rejected as the default because it leaves "done" undefined during the implementation phase. The Builder makes implementation decisions without a concrete target, which produces more Review-Fix Loop iterations and more Escalations about scope.

TDD is the default, not the only option. The Pipeline is configurable: the Tester's first appearance can be removed or repositioned for tasks where upfront test authoring is impractical (e.g. exploratory changes, infrastructure work with no clear unit boundary).

## Consequences

The Tester Agent Session appears at two structurally different points in the Default Pipeline with different jobs: test authoring before the Build-Test Loop, and test running within it. The Brief the Tester receives at each appearance must carry enough context for it to know which role it is filling.
