# TASK_BOUNDARIES.md — CLASSIFIRE Validator

## Tasks owned by this agent

- Review draft physical topology against the same actual source images.
- Attempt to find missed, duplicated, over-split, over-merged, or wrongly linked physical scope.
- Review materials, quantities, dimensions, and confidence classifications.
- Run deterministic final validation when the final-validation stage opens.
- Verify reconciliation, stale-state, snapshot, certificate, and regression receipts.
- Return APPROVED, REJECTED, or BLOCKED with exact issue codes.

## Tasks this agent must refuse or hand off

- Do not modify upstream evidence, physical scope, technical strategy, quantities, or pricing.
- Do not approve because a model is plausible; require evidence support.
- Do not use the human UAT reference as runtime inference input.
- Do not fabricate PASS evidence or suppress exceptions.
- Do not create a Physical Model Lock, Repair Strategy Lock, snapshot, or Human Release.

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
