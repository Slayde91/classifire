# CLASSIFIRE - Product goal and current delivery priority

**Direction approved:** 2026-09-05. The owner approved ADR 0002 and prioritized a
working, testable UI prototype before broad polish and edge-case refinement.
This document states the target and delivery priority; it is not evidence that the
target is implemented. Current facts belong in [PROJECT_STATE.md](./docs/PROJECT_STATE.md).

## Ultimate outcome

Build CLASSIFIRE into a production-ready AI-assisted passive-fire platform with four
independently usable capabilities:

1. **Scope analysis:** create and review defensible scope and physical observations
   from authorized evidence or attributed manual input.
2. **System matching:** evaluate valid saved/manual scope against authorized technical
   sources, preserving constraints, uncertainty and human review.
3. **Estimating:** calculate transparent quantities, labour and commercial recovery
   from sufficient validated inputs, without hiding unsupported assumptions.
4. **Reporting:** create requested partial or combined PDF/XLSX reports from explicit
   saved revisions and one consistent snapshot, without rerunning upstream work.

Users can stop after any capability, inspect or modify a Draft, save a revision,
export it and return later. They choose when to run another capability. Required
information and authority still apply, whether supplied by a preceding capability,
a saved artifact or manual input. No capability depends on hidden chat context.

Support a standalone interface and a ChatGPT-native interface over the same backend
use cases and domain rules. Use the current approved ChatGPT integration model when
that adapter is built; the product does not depend on the legacy plugin label.
The backend owns permissions, validation, durable state and downloads.

Support creating, configuring, editing, validating, saving, importing and downloading
portable capability artifacts and complete ProjectPackage revisions. The governed
database and retained storage hold live canonical state; exported packages describe
explicit revisions. Declare included, external, omitted and restricted content.
Imports preserve evidence/history but confer no local approval, lock or release power.

The accepted architecture is a modular CLASSIFIRE application with deterministic
workflows and optional bounded AI. Preserve the existing domain foundations. Reuse
shared services across interfaces; do not build a fleet or separate server for each
capability. Remove OpenClaw only when its required protections have proven replacements.
See [ADR 0001](./docs/ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md) and
[ADR 0002](./docs/ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md).

## Long-term domain coverage retained

The prototype reorders delivery; it does not remove the broader product needs:

- Retain original defect and technical sources, provenance and interpretations;
  support PDF, DOCX, XLSX, images/drawings and other explicitly supported inputs
  without silently omitting unsupported content. Human review governs technical
  library authority; extracted text or similarity alone is not compatibility.
- Import the authorized pricing workbook with version/worksheet/cell provenance.
  Keep technical applicability independent of cost. Preserve original and override
  values, units, rate inclusions and transparent exact/mapped/component/inferred/
  user-defined/unresolved price bases. Validate inferred methods before claiming
  reliability; no forced prices or quantities to fill gaps.
- Preserve independently reviewable Scope, System Match and Estimate packages,
  consistent partial/combined PDF and XLSX, traceable scopes/estimates/close-out
  records, and human-only final release. Upstream edits identify stale downstream
  dependencies without silently overwriting prior approvals or totals.

## Immediate priority: a usable manual Draft Scope workbench

Deliver one small, complete UI workflow on the existing application stack. A user
must be able to create or open a project, enter a manual Draft Scope, save it, reopen
it, validate it and download the exact saved Draft Scope revision as JSON.

This is the highest-value next task because CLASSIFIRE has substantial deterministic
and governance foundations, while independent capability use still needs a visible
interaction that users can test. A small end-to-end workflow exposes practical gaps
so later contract, API and product decisions can follow observed behavior.

Build only the shared Scope artifact fields and application services necessary for
that workflow in the same implementation slice. Reuse FastAPI, `src/classifire/ui.py`,
SQLAlchemy and established service/security patterns. Keep Draft persistence and
permissions explicit. Existing opening/service UI writes guarded canonical physical
records; do not use those writers as Draft editing shortcuts or relax their guards.
The prototype must not admit a physical model, activate a lock or produce a Released
claim simply because a user saved, validated or exported a Draft.

### Demonstration and completion evidence

A fresh user interaction must demonstrate all of the following with synthetic data:

- Create/open a project and start a clearly labeled manual Draft Scope.
- Add one defect with multiple distinct openings and multiple services, including a
  shared relationship and a blank opening; do not equate defect count with quantity.
- Record explicit evidence/observation states and unresolved facts. Attribute manual
  claims and leave missing evidence visible.
- Edit the Draft, save a revision, reopen it and confirm the same data survives an
  application restart. Preserve stable IDs and intentional relationship changes.
- Validate required fields and relationships. Show actionable errors separately from
  unresolved evidence; validation does not imply technical approval or readiness.
- Download the selected saved revision as JSON and inspect its project identity,
  artifact/schema version, revision identity, content, uncertainty and Draft status.
- Confirm that saving, validating and downloading do not invoke matching, estimating,
  AI providers, canonical physical admission, locking or release.
- Pass meaningful service/API tests and existing relevant authority-guard regressions;
  run and inspect the UI interaction and downloaded content. Record actual results.

Use synthetic fixtures and isolated development/test storage. Project access and
Draft-only writes must be checked by the backend, not only hidden by UI controls.
An available route, schema or unit-test suite without the demonstrated UI path does
not satisfy this milestone. A passing demo does not establish production readiness.

### Keep the first prototype bounded

Safe import/replacement of the downloaded Draft Scope is the next bounded UI
increment. It must validate version, ownership, relationships and authority before
any permitted local persistence; a downloaded document must not become a trusted
local record merely because its JSON parses.

Do not put the full ProjectPackage ZIP, all four capability schemas, whole-database
projection, bulk evidence ingestion, automatic system matching, reliable price
inference, production ChatGPT distribution, full orchestration replacement or every
edge case on the first demo's critical path. The existing unpublished package draft
is review material to reconcile and selectively reuse, not the prototype milestone
or an automatically approved contract.

## What follows the first demo

[The roadmap](./docs/CLASSIFIRE_ROADMAP.md) owns the detailed sequence and status.
Develop subsequent increments from user feedback and verified dependencies:

- Safe Draft Scope import/replacement and revision handling.
- Independent matching and estimating with explicit saved/manual input boundaries.
- Partial reporting from selected immutable revisions, with consistent PDF/XLSX.
- Shared ChatGPT access, complete portable project revisions and governed downloads.
- Selected AI assistance when it improves evaluated outcomes, and OpenClaw retirement
  only after security, authority, reliability and audit replacement gates pass.

Fine tuning, broad optimization and low-priority edge cases follow observable user
workflows. Security, privacy, integrity, evidence traceability and human authority
remain requirements throughout. Production phase gates still govern authoritative
outputs; they are not blanket blockers for independent, permissioned Draft prototypes.

## Durable instructions for continuing work

Inspect repository state before editing and preserve unrelated local work. Read
`AGENTS.md`, the project state, relevant roadmap section, architecture decisions,
current services/UI and tests. Implement the single next demonstrable slice;
avoid speculative rewrites and schema-only completion. Continue through appropriate
validation, local-change classification, commit, normal push, PR and merge when
within the authorized scope and all required checks/review permit it. Deployment,
release, real-provider/customer workflows and operational canonical actions remain
separate authorization boundaries.

Use [SESSION_HANDOFF.md](./docs/SESSION_HANDOFF.md) for the current self-contained
next-session task and verified commands. Update claims from actual source, test and
runtime evidence. Keep this goal distinct from a claim that the product is finished.
