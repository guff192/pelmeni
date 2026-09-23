# Development plan for pelmeni

All 18 implementation ticket issues (**#23 through #40**) have been marked with the new label **`ticket`**.

---

### Detailed Dependency Breakdown by Tier

#### Tier 1: The Frontier (Zero Blockers — Ready for Immediate Work)
- **#32: Common Bus Protocol & Zero-Docker InMemoryBus Fallback**
  - *Blocked by:* **None**
  - *Delivers:* `BusProtocol` interface and in-process `InMemoryBus` (`asyncio.Queue` + `dict`), allowing multi-agent tests and local dev to run without Docker or Redis.
- **#33: Domain Agent Profiles & Role System Prompt Loader**
  - *Blocked by:* **None**
  - *Delivers:* Pure domain `AgentProfile` dataclass, baseline prompts for all 5 roles (`manager`, `investigator`, `builder`, `reviewer`, `tester`), and `~/.config/pelmeni/agents/<role>.md` override loader.
- **#34: Project Session Hierarchy & Isolated Subagent Session Logs**
  - *Blocked by:* **None**
  - *Delivers:* Disk layout `~/.pelmeni/sessions/<project>/.../`, `main.jsonl` with fast line-1 `session_header`, and `subagents/<role>_<timestamp>_<id>.jsonl` isolated trace logger.
- **#36: Interactive REPL UX Overhaul with Prompt Toolkit & Command History**
  - *Blocked by:* **None**
  - *Delivers:* `prompt_toolkit` integration with Readline keybindings, multiline `Shift+Enter`, persistent history in `~/.pelmeni/history`, and auto-completing slash-command menu.

---

#### Tier 2: Provider Continuity & Session Execution
- **#35: Bridge Conversation ID Continuity & TPU Prefix Cache Preservation**
  - *Blocked by:* **#34**
  - *Why:* Needs the `session_header` in `main.jsonl` (from #34) to store and reload the remote bridge `conversation_id`, and propagates it to `--conversation <uuid>` on subsequent turns.
- **#38: Consolidate AgentSession Execution Module with Isolated Context & Turn Coordination**
  - *Blocked by:* **#33**
  - *Why:* Needs pure domain `AgentProfile` and role system prompt loader (from #33) to initialize each session's profile, model resolution, and allowed tool whitelist.
  - *Delivers:* Deep `AgentSession` module encapsulating message history, per-session context compaction (`TruncateCompactor`), tool execution without global hook state, and a stepping interface.
- **#39: Refactor RedisBus into Private-Key Adapter with Async PubSub Subscription**
  - *Blocked by:* **#32**
  - *Why:* Needs `BusProtocol` interface from #32 to implement `subscribe()`, encapsulate namespacing methods privately, and satisfy the protocol contract.
  - *Delivers:* Completed `RedisBus` adapter with real pub/sub message delivery, private key formatting, and end-to-end multi-agent event broadcast tests.
- **#40: SessionStore History Deserializer & Domain Round Reconstruction Reader**
  - *Blocked by:* **#34**
  - *Why:* Needs the project session directory hierarchy and `main.jsonl` writer (from #34) to implement session discovery, line-1 header reading, and domain round deserialization.
  - *Delivers:* `SessionStore` reader interface with `find_latest_session()`, `read_header()`, and `read_rounds()`, tested end-to-end against recorded session traces.
- **#37: REPL Session Resumption & Continuation**
  - *Blocked by:* **#36**, **#38**, **#40**
  - *Why:* Needs #40's `SessionStore` reader to parse `main.jsonl` into domain messages and rounds, #36's `prompt_toolkit` loop, and #38's `AgentSession` to hydrate restored message history and resume interactive prompting.

---

#### Tier 3: Multi-Agent Lifecycle Foundation
- **#23: Multi-agent Session lifecycle: five Agent Sessions start together and persist**
  - *Blocked by:* **#32**, **#34**, **#38**
  - *Why:*
    1. Issue #23 explicitly requires: *"The InMemoryBus fallback (planned build step 14) should be usable here so tests don't require Redis."* (requires **#32**).
    2. Sessions are initialized as: *"Five Agent Sessions are created when the Session starts, each backed by the Agent Profile for its Agent Type."* (requires **#38**, which implements the execution lifecycle using profiles from #33).
    3. Sessions record events as: *"All Agent Sessions write to the shared Session Log using their Agent Type as an identifier."* (requires **#34**).

---

#### Tier 4: Pipeline Initiation & Peer Communication
- **#24: Manager requirements gathering and Requirements Brief to Investigator**
  - *Blocked by:* **#23**
  - *Why:* Requires the 5 live Agent Sessions connected to the bus so the Manager can receive the user's prompt and publish the `RequirementsBrief` to the Investigator.
- **#25: Investigator pipeline step and Tester test authoring (TDD)**
  - *Blocked by:* **#24**
  - *Why:* The Investigator step ingests the `RequirementsBrief` produced by the Manager in #24 to emit a `FindingsBrief` to the Tester.
- **#26: Consult mechanism: free-form peer-to-peer worker communication**
  - *Blocked by:* **#23**, **#39**
  - *Why:* Requires concurrent worker Agent Sessions running on the bus (#23) and correlated async pub/sub subscription (#39) to exchange peer-to-peer queries and responses.

---

#### Tier 5: Loops, Escalations, and Budgets
- **#27: Escalation and Ruling: worker conflict resolution via Manager**
  - *Blocked by:* **#24**, **#26**
  - *Why:* ADR-0004 mandates peer-to-peer resolution via Consult (**#26**) before escalation to the Manager (**#24**).
- **#28: Build-Test Loop: Builder implements, Tester verifies, loop until tests pass**
  - *Blocked by:* **#25**
  - *Why:* The Builder-Tester loop implements changes against the authored failing tests and `FindingsBrief` produced in **#25**.
- **#29: Review-Fix Loop and Final Report: full Default Pipeline end-to-end**
  - *Blocked by:* **#28**
  - *Why:* The Review-Fix loop audits code and resolves quality issues only after the Build-Test loop (**#28**) passes all tests.
- **#30: Loop Budget and Budget Extension: execution limits with Manager-mediated extension**
  - *Blocked by:* **#27**, **#28**, **#29**
  - *Why:* Budget limits gate the Build-Test loop (**#28**) and Review-Fix loop (**#29**); exhausting a loop budget triggers an Escalation to the Manager for a `BudgetExtension` Ruling (**#27**).

---

#### Tier 6: REPL Pipeline Controls
- **#31: REPL Pipeline configuration and mid-Session mutation**
  - *Blocked by:* **#29**, **#36**
  - *Why:* Introduces `/pipeline show` and `/pipeline set` in the interactive REPL slash-palette (**#36**) to dynamically mutate the stages of the complete Default Pipeline (**#29**).

---

### Active Frontier Summary

The 4 tickets with **zero blockers** that can be started concurrently right now:
1. **#32** — `Common Bus Protocol & Zero-Docker InMemoryBus Fallback`
2. **#33** — `Domain Agent Profiles & Role System Prompt Loader`
3. **#34** — `Project Session Hierarchy & Isolated Subagent Session Logs`
4. **#36** — `Interactive REPL UX Overhaul with Prompt Toolkit & Command History`
