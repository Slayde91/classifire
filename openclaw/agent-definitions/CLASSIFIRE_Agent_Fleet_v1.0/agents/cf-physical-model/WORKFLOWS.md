# WORKFLOWS.md — CLASSIFIRE Physical Model

## Primary workflow

1. Read retained evidence and attach the actual full-resolution defect images.
2. Pass 1 — View reconciliation: confirm same-area, opposite-face, and distinct-plane relationships.
3. Pass 2 — Barrier topology: enumerate each physical barrier plane and supporting construction.
4. Pass 3 — Opening topology: enumerate each physically distinct aperture in each barrier.
5. Pass 4 — Service inventory: identify each distinct Service or homogeneous Service group.
6. Pass 5 — Relationships: assign zero, one, or many Services to each Opening.
7. Pass 6 — Attributes: record substrate, plane, orientation, dimensions, material, quantity, and confidence.
8. Apply `-/120/120` only as an explicit missing-FRL assumption for current penetration/fire-seal estimating.
9. Produce a draft topology and hand it, with the same actual images, to `cf-validator`.
10. Resolve validator findings without changing evidence to force approval.
11. Submit canonical Openings, Services, and links through controlled write tools.
12. Request the Physical Model Lock and preserve its hash and critical unknowns.

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
  "agent_id": "cf-physical-model",
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
