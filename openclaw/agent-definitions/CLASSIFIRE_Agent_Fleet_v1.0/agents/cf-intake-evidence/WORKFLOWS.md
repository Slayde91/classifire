# WORKFLOWS.md — CLASSIFIRE Intake and Evidence

## Primary workflow

1. Read the source inventory and canonical evidence state.
2. Review the complete page before interpreting embedded images.
3. Classify each displayed image as relevant, non-scope, or uncertain.
4. Inspect each relevant image at native resolution; zoom when needed.
5. Record visible primitives only: barrier clues, opening boundaries, Services, fittings, landmarks, and viewpoint.
6. Create exact-image duplicate groups by content hash.
7. Create multi-view groups using matching landmarks and physical arrangement, not photo count.
8. Record counting instructions such as 'same Opening opposite faces' or 'different Services same Opening'.
9. Register evidence with page, region, photo ID, confidence, and uncertainty.
10. Handoff a structured evidence pack to `cf-physical-model`.

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
  "agent_id": "cf-intake-evidence",
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
