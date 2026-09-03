# Proposal-review package lifecycle policy

**Status:** adopted for controlled CLASSIFIRE UAT on 2026-09-03.

This policy covers a generated Phase 8 report-review package. It does not turn a
proposal into a physical model, a technical selection, a price, a lock, a
deployment, or a released output.

## 1. Owner and contents

CLASSIFIRE is the records owner. A retained record belongs to one Project and
one Estimate and remains bound to its retained report evidence and approved
expected-label manifest.

The record may retain only:

- package, receipt, source, approval, and manifest identifiers and hashes;
- a safe locator made only from those identifiers and hashes;
- the selected scope identifiers, safe labels, outcome state, and safe blocker
  codes needed for a reviewer to understand uncertainty; and
- the retention and legal-hold lifecycle state.

It must not retain report bytes, images, prompts, model/provider responses,
local paths, storage paths, signed URLs, credentials, tokens, or hidden source
content. A safe locator is a reference, not a file path or a way to bypass
retained-evidence controls.

## 2. Who may see or manage it

Only authenticated internal human users with `proposal_review:read` may open a
review record. The initial role map grants that to CLASSIFIRE administrators,
project managers/estimators, technical reviewers, and records/compliance users.
It grants nothing to agents, OpenClaw, Gateway, providers, unauthenticated
users, or customer/external accounts.

Only a CLASSIFIRE administrator may create a retained package record, create a
redacted view, place or clear a legal hold, or delete an eligible record. The
read-only reviewer route has no execution, approval, technical, commercial,
lock, deployment, or release operation.

The current application has role-based internal access rather than a separate
per-project assignment table. Do not use this controlled-UAT role map for a
customer-facing rollout; adding named project assignments requires a separately
reviewed access-control change.

## 3. Immutability, redaction, retention, and deletion

Package metadata is immutable after registration. An exact replay is harmless;
a different record with the same package ID or manifest hash is rejected.

Redaction never changes the original package record. It creates a separately
hash-bound reviewer view that omits selected scopes and records only a safe
redaction reason code.

Retain a package record for at least five years from successful registration.
CLASSIFIRE does not delete it automatically. A human administrator may delete
the package metadata and its redacted views only after `retention_until` and
only when no legal hold is active. The deletion audit event is the retained
tombstone; it contains identifiers and hashes, not package content.

A legal hold overrides the normal retention clock. It may be changed only by a
human administrator and must use a safe, controlled reason code.

## 4. Integrity and tamper response

Every reviewer read recalculates the stored summary and safe-locator hashes and
checks their Project, Estimate, report-evidence, and expected-label bindings.
If any check fails, CLASSIFIRE refuses to render the package or a redacted view.
The reviewer surface records a content-safe tamper audit event and does not
silently repair, replace, export, or grant authority from the record.

This lifecycle record is proposal evidence only. A later canonical submission
or Physical Model Lock must independently revalidate its own evidence and
admission requirements; it may not treat this record as authority.