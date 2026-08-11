# WORKFLOWS.md — CLASSIFIRE Commercial Engine

## Primary workflow

1. Verify the Repair Strategy Lock and active commercial releases.
2. Derive the exact required-component inventory.
3. Retrieve quantities and labour activities with provenance.
4. For each component, attempt exact Package 14 applicability.
5. Where no exact applicable rate exists, test approved parameterisation, then component build.
6. Record expert estimates only as provisional with basis and review requirement.
7. Build a rate-inclusion and recovery ledger.
8. Reconcile shared work and prevent duplicate recovery.
9. Run equal-price and anomaly checks.
10. Submit commercial derivation through controlled tools and preserve receipts.

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
  "agent_id": "cf-commercial-engine",
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
