# WORKFLOWS.md — CLASSIFIRE Validator

## Primary workflow

1. Read the task, draft model, retained evidence, and actual source images.
2. Review all images independently rather than relying only on upstream summaries.
3. Check barrier count and barrier-plane identity.
4. Check physical Opening count and photo/view reconciliation.
5. Check zero/one/many Service relationships for every Opening.
6. Check mixed-service inventory and homogeneous grouping.
7. Check materials, quantities, sizes, assumptions, and unresolved relationships.
8. Return issue codes and evidence references.
9. Approve only when no material topology error remains.
10. At final stage, invoke deterministic independent validation and report exact blockers.

## Mission Control task lifecycle

1. Task begins in `assigned`.
2. Confirm identifiers, role ownership, inputs, and current CLASSIFIRE stage.
3. Move to `in_progress` only when required inputs are available.
4. Perform the bounded work and retain receipts.
5. Move to `review` with a structured resolution and handoff.
6. A reviewer may approve, reject with issue codes, or block for human evidence.
7. Mission Control `done` does not itself advance a CLASSIFIRE gate.
8. The orchestrator advances only after the canonical CLASSIFIRE receipt confirms success.

## Retry and resume

- Reuse retained evidence and successful stage receipts.
- Keep the same idempotency/request identity for safe retries.
- Do not reprocess unchanged documents or images.
- Do not create duplicate canonical records.
- After repeated transport failure, preserve partial non-canonical task receipts and escalate.
- After validator rejection, create a bounded correction task addressing only the listed issues.

## Required output envelope

```json
{
  "agent_id": "cf-validator",
  "task_id": "<mission-control-task-id>",
  "estimate_id": "<estimate-id>",
  "run_id": "<run-id>",
  "status": "COMPLETED|REVIEW_REQUIRED|BLOCKED|FAILED",
  "canonical_stage": "<stage>",
  "inputs_reviewed": [],
  "canonical_records": [],
  "findings": [],
  "assumptions": [],
  "unknowns": [],
  "blockers": [],
  "receipts": [],
  "next_role": null,
  "next_action": null
}
```
