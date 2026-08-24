# Phase 8 Visual Validation Receipt Contract

## Status and scope

`CLASSIFIRE-PHASE8-VISUAL-VALIDATION-RECEIPT-v1` is immutable, content-free
semantic-review evidence for a **future** signed Physical Model Lock admission.
It is not a canonical physical model, an admission, a canonical submission
receipt, a Physical Model Lock, a technical decision, a quantity, a price, or a
release decision.

The initial canonical writer and generic lock route are intentionally unchanged.
No API or agent tool records a receipt in this slice. The registry service is
transaction-owned by its future accountable human-governance caller and never
commits, submits a model, or creates a lock.

## Required binding

Each canonical receipt binds exactly one:

- receipt, project, and estimate UUID;
- source visual run identifier;
- candidate normalised physical-submission payload SHA-256;
- controller receipt, visual-evidence manifest, evidence-family inventory, and
  reviewed evidence-family record SHA-256 values;
- human-review request and response SHA-256 values;
- approval reference, reviewed UTC timestamp, reviewed defect references,
  policy versions, and implementation revision.

No source report, image, transcript, signed URL, or human-review content is
stored in the receipt. All SHA-256 values are uppercase and receipt bytes are
canonical UTF-8 JSON. The database retains those bytes and their exact hash.

## Semantic statuses

| Status | Meaning | Future lock eligibility |
| --- | --- | --- |
| `SEMANTICALLY_APPROVED` | A governed review found no unresolved material item in the stated scope. | Potentially eligible, but only after exact binding revalidation by a future signed lock-admission boundary. |
| `WITHHELD` | The review remains retained with one or more explicit unresolved items. | Never eligible. |

The schema rejects an approved receipt with unresolved items and rejects a
withheld receipt with no stated reason.

## Storage and integrity

Migration `0009_visual_validation_receipts` creates an additive immutable
receipt table. It has unique receipt IDs and hashes, foreign keys to the project
and estimate, and an estimate/status index. Exact replays are idempotent; a
reused ID with changed content fails closed. Any stored JSON or duplicated-column
drift is detected when eligibility is checked.

The migration has no destructive downgrade because deleting retained review
evidence would break auditability.

## Future lock boundary

A separately designed, signed, and explicitly authorised lock-admission flow
must supply the receipt hash and all of its bound hashes, then call
`require_semantically_approved_visual_validation_receipt`. That verifier is
side-effect free and rejects absent, withheld, corrupt, stale, or mismatched
records.

This contract does **not** authorise such a lock flow, external signing,
admission registration, canonical submission, or lock creation. It only creates
the durable evidence primitive those later gates must bind.