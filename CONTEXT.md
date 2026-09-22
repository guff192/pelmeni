# Pelmeni

A multi-agent system for automating software development workflows. Specialised agents collaborate within a single user Session to carry out a development task, communicating via structured Briefs, Consults, and Escalations.

## Language

### Agent Types

**Agent Type**:
The specialisation that an Agent Profile implements. Five types exist: Manager, Investigator, Builder, Reviewer, Tester.
_Avoid_: agent role, agent kind

**Manager**:
The Agent Type responsible for gathering requirements from the user at the start of a task, mediating Escalations between workers, and delivering the Final Report. The Manager never directs implementation decisions; its authority is limited to three moments: upfront requirement clarification, conflict resolution, and final reporting. The Manager is reactive — it does not observe peer sessions; it waits to be prompted.
_Avoid_: orchestrator, coordinator

**Investigator**:
The Agent Type responsible for locating relevant code, understanding dependencies, and producing a Findings Brief. The first worker to receive the Manager's requirements; its output initiates the rest of the pipeline.
_Avoid_: explorer, analyser

**Tester**:
The Agent Type responsible for defining what "done" looks like and for verifying it is achieved. One Tester Agent Session participates at two points in the Default Pipeline with different jobs. Before the Build-Test Loop: receives the Investigator's Brief, writes failing tests, and passes a Brief to the Builder. Inside the Build-Test Loop: receives the Builder's Brief or automated test failure output, decides whether to fix trivial test defects or return work to the Builder, and exits the loop when tests pass.
_Avoid_: QA, quality assurance

**Builder**:
The Agent Type responsible for making targeted code changes to satisfy the failing tests produced by the Tester.
_Avoid_: developer, coder, implementer

**Reviewer**:
The Agent Type responsible for auditing the Builder's output for correctness and quality, then reporting results to the Manager. May return work to the Builder for fixes before reporting upward. Decides unilaterally when the Review-Fix Loop is complete.
_Avoid_: auditor, checker

### Agent Execution

**Agent Profile**:
The static definition of one Agent Type: its system prompt, tool whitelist, and model alias. Implies no execution.
_Avoid_: agent config, agent spec, agent definition

**Agent Session**:
A live execution of an Agent Profile. All Agent Sessions are created when the Session starts and persist until it ends. Each session waits to receive Briefs and Consults, processes them, and waits again — it does not terminate between tasks.
_Avoid_: agent run, agent instance, agent process

### The Pipeline

**Pipeline**:
The ordered sequence of Agent Type activations for a task. The user configures the Pipeline before a Session starts and may change it while the Session is running. Each worker Agent Session receives the active Pipeline at the start of its first Round and receives an updated copy on its next turn whenever a change occurs. Workers consult this configuration to determine who to pass their Brief to next.
_Avoid_: workflow, process, sequence

**Default Pipeline**:
The Pipeline configuration that runs when the user provides no customisation. In order: Manager (requirements) → Investigator → Tester (test authoring) → Build-Test Loop → Review-Fix Loop → Manager (final reporting) → User. TDD is the default: tests are written before the Builder makes any change.
_Avoid_: standard workflow, default flow

**Build-Test Loop**:
The repeating sub-sequence within the Default Pipeline where the Builder implements changes and the Tester verifies them, iterating until tests pass. If tests pass on an automated run, the Tester step within the loop may be skipped for that iteration. Subject to a Loop Budget; exhaustion triggers an Escalation.
_Avoid_: implementation loop, dev-test cycle

**Review-Fix Loop**:
The repeating sub-sequence within the Default Pipeline where the Reviewer audits and the Builder fixes, iterating until the Reviewer decides the output is acceptable. Subject to a Loop Budget; exhaustion triggers an Escalation.
_Avoid_: review cycle, QA loop

**Loop Budget**:
The configured execution limits applied to a loop. Up to three dimensions may be active simultaneously: maximum iteration count, maximum wall-clock time, and maximum tokens spent. Also carries an extension allowance — the maximum number of times and by how much the Manager may issue a Budget Extension before the loop must stop.
_Avoid_: loop limit, iteration cap, timeout

**Budget Extension**:
The Manager's decision, in response to a Loop Budget exhaustion Escalation, to grant the loop additional execution resources. Limited by the extension allowance configured in the Loop Budget. When the extension allowance is fully consumed, the Manager must stop the loop and present the situation to the user in the Final Report with options.
_Avoid_: budget increase, limit override, extra iterations

### Communication

**Brief**:
A structured artifact passed from one Agent Session to the next in the Pipeline order. Each Agent Type defines the structure of the Brief it produces. Briefs exchanged between workers and the Manager follow a separate structure from those exchanged between workers.
_Avoid_: handoff, summary artifact, context package

**Consult**:
A free-form request from one worker Agent Session to another for information or an expert read on a specific situation. Not a Brief; carries no required structure and does not follow the Pipeline order. A worker sends a Consult when it needs input from a peer before it can proceed, and peer resolution is faster or more appropriate than an Escalation.
_Avoid_: query, request, message, question

**Escalation**:
A request from a worker Agent Session to the Manager. Raised either when a worker cannot resolve a situation via a Consult with another worker, or when a loop's Loop Budget is exhausted. Carries the exact situation, decision point, and — in the case of peer disagreement — the positions of all involved workers.
_Avoid_: conflict report, manager request, issue

**Ruling**:
The Manager's binding decision in response to an Escalation. All workers accept a Ruling and continue. The Manager may send Consults to workers before issuing one. In the case of Loop Budget exhaustion, the Ruling takes the form of either a Budget Extension or a directive to stop the loop.
_Avoid_: decision, verdict, resolution

**Final Report**:
The Manager's closing communication to the user after the Reviewer has reported that the task is complete, or after the Manager has directed a loop to stop due to budget exhaustion. Presents outcomes and, where work is incomplete, surfaces options for the user rather than making assumptions about acceptability.
_Avoid_: summary, output, result

### Sessions and Traces

**Session**:
One interactive REPL run. Defines the lifetime of all Agent Sessions created within it.
_Avoid_: run, invocation

**Session Log**:
The JSONL trace file recording every request, response, and tool event that occurred during a Session.
_Avoid_: trace, log file, session trace

**Prompt**:
The user's original text input at the start of a Session, captured before any Agent Session processes it.
_Avoid_: user input, user message, request

### Context and Memory

**Model Context**:
The full input presented to the model at a given turn — the token window that must not overflow. Includes the system prompt, all Rounds in the current Agent Session, and any Brief or Consult content the session has received.
_Avoid_: context, context window, input

**Turn**:
A single assistant response or tool result within a Round. The smallest discrete step in a worker Agent Session's execution. Pipeline configuration updates are injected immediately after the next Turn completes when a mid-execution change occurs.
_Avoid_: step, message, iteration

**Round**:
One user message plus all the Turns it generates, before the next user message arrives within the same Agent Session.
_Avoid_: turn, exchange, cycle

**Hook Context**:
The structured snapshot of a tool invocation situation — Agent Type, session identifier, and recent tool history — that a Hook uses to make its verdict.
_Avoid_: context, invocation context

### Tools and Execution

**Tool**:
A named capability an Agent Session may invoke. Access is controlled per Agent Type by a registry; a session cannot invoke a Tool outside its whitelist regardless of what its system prompt says.
_Avoid_: function, capability, command

**Hook**:
A middleware component that intercepts every tool invocation before it executes and returns one of three verdicts: allow, deny, or modify. A Hook that raises an exception is treated as deny.
_Avoid_: interceptor, guard, filter

**Provider**:
An adapter to one LLM API. Translates the canonical message format into provider-specific wire formats and normalises responses back.
_Avoid_: LLM client, model adapter, backend

**Task Payload**:
The structured work description routed between Agent Sessions via the bus. May originate as a user Prompt or as a Brief produced by another Agent Session.
_Avoid_: task, message, work item
