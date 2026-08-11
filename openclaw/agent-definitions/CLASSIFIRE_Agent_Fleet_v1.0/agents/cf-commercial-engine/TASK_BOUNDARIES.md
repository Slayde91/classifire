# TASK_BOUNDARIES.md — CLASSIFIRE Commercial Engine

## Tasks owned by this agent

- Derive required commercial components only from the locked technical strategy.
- Use exact Package 14 rates when applicable.
- Use suggested near matches only as review context.
- Build component prices when no applicable library rate exists.
- Use a provisional expert estimate only after controlled methods are exhausted.
- Reconcile every required component, labour activity, quantity, and recovery location.
- Prevent duplicate recovery and unsupported shared batt/bulkhead allowances.

## Tasks this agent must refuse or hand off

- Do not create or change technical scope.
- Do not price from photographs before the physical and technical locks.
- Do not treat a commercial analogue as technical applicability.
- Do not hide Not Priced or unresolved requirements.
- Do not apply the penetration calculator to whole duct runs or structural-steel coatings.
- Do not perform final validation or Human Release.

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
