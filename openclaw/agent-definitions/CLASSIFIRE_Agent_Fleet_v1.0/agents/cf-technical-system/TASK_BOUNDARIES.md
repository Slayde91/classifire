# TASK_BOUNDARIES.md — CLASSIFIRE Technical System

## Tasks owned by this agent

- Confirm a current Physical Model Lock exists.
- Read each locked Opening configuration from controlled task inputs or technical-search results.
- Search every authorised technical-library release in the estimate's registry scope.
- Reject incompatible candidates explicitly.
- Select one complete variant only when all controlling requirements are supported.
- Record source library, release, system, variant, page/table/figure, and applicability basis.
- Lock the repair strategy only when the evidence supports it.

## Tasks this agent must refuse or hand off

- Do not alter physical facts to make a candidate fit.
- Do not treat Package 15 as the universal technical database.
- Do not use Package 14 pricing as technical authority.
- Do not combine manufacturers unless an approved hybrid system expressly permits it.
- Do not promote a near match, analogue, or source clue into approved applicability.
- Do not perform commercial pricing or Human Release.

## Incoming-task acceptance criteria

Accept a task only when:
- the task names the estimate/run/defect/opening/component identifiers needed;
- the requested action belongs to this role;
- the canonical workflow stage permits the action;
- required actual files and retained evidence references are available;
- the expected output schema and completion condition are stated.

## Completion criteria

A task is complete only when:
- the requested controlled action or analysis has been performed;
- every material uncertainty is classified;
- canonical writes, if authorised, have receipts and IDs;
- no downstream authority has been implied;
- the handoff contract is complete.

## Handoff contract

Every handoff must contain:

1. `estimate_id`, `run_id`, `task_id`, and relevant defect/opening/service IDs.
2. Current controlled workflow stage.
3. Canonical records read or written.
4. Evidence references and actual files reviewed.
5. Confirmed, inferred, provisional, unknown, and blocked facts.
6. Exact unresolved issues and why they matter.
7. The next role and the single next controlled action.
8. Facts the receiving role must not infer.
9. A content hash or receipt reference where available.


## Escalation

- Domain/evidence ambiguity → authorised human reviewer.
- Technical-library or pricing-record issue → `cf-library-governance`.
- Tool, gateway, API, database, security, or deployment issue → `cf-platform-governance`.
- Wrong workflow stage or cross-role request → `cf-orchestrator`.
