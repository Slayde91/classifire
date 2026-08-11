# WORKFLOWS.md — CLASSIFIRE Technical System

## Primary workflow

1. Read the workflow stage and verify the Physical Model Lock.
2. For each Opening, obtain the locked barrier, Service inventory, dimensions, FRL, and uncertainties.
3. Read the active Technical Authority Registry and authorised library releases.
4. Run opening-specific candidate search.
5. Build a requirement matrix: MATCH, MISMATCH, UNKNOWN, or NOT_APPLICABLE.
6. Reject candidates with incompatible service, substrate, orientation, FRL, size, spacing, support, or evidence status.
7. Rank remaining complete candidates without commercial bias.
8. Select one complete variant or return Blocked/Manual Review.
9. Record full provenance and required installation components.
10. Create and lock the repair strategy through controlled tools.

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
  "agent_id": "cf-technical-system",
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
