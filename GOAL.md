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

## Demonstrated first prototype: manual Draft Scope

P0 is merged in PR #188 at `96d6869` and locally demonstrated: the existing UI creates a new project
and owner-scoped manual Draft, supports multiple openings/services and explicit
uncertainty, validates, saves/reopens after restart and downloads exact saved JSON.
The [demo guide](./docs/DRAFT_SCOPE_DEMO.md) gives runnable instructions and evidence.
This is not complete Scope Analysis or production readiness. Verify newer repository
state before extending it; P1a publication is recorded separately below.

The prototype uses shared application services and separate Draft revision tables.
Existing canonical physical guards remain intact. Saving, validating and exporting
a Draft does not run AI, matching, estimating, admission, locking or release.
Manual Confirmed facts remain unreviewed assertions. Existing project metadata
visibility is shared; the demonstrated environment contains synthetic data only.

## Demonstrated portability increment: Draft Scope import

P1a extends the working UI with bounded saved-JSON upload, no-write preview and
explicit replacement as a new local revision. v1 downloads retain their original
bytes; imported revisions use explicit v2 lineage, preserved through manual edits
and reimport. Foreign project/author/history claims remain unverified. Preview
confirmation binds the exact file, local destination/revision and current session.
The actual synthetic browser round trip and server restart passed; consult current
Git/PR evidence for later changes and PROJECT_STATE.md for the measured checks.
P1a is merged in PR #189 at `e17cec3`, with main CI 33949738802 passing 1,072 tests.

## Demonstrated reporting increment: scope-only PDF and XLSX

P4a adds a real report interaction over selected saved Scope revisions. A frozen
snapshot captures Scope content, project labels and rendering version. PDF/XLSX
are retained together, checked on download and never regenerated by a read.
Later Scope/project edits flag the earlier report as stale while preserving bytes.
Unknown quantities remain unknown; technical and pricing information is unavailable.
See PROJECT_STATE.md for current validation/publication, not this goal statement.

## Immediate priority: saved technical-candidate review

After P4a publication, deliver P2a: an independent candidate-review workspace over
an explicit Scope revision and technical release. Users inspect source references,
missing applicability criteria and alternatives, keep/reject with notes, save a
revision, reopen/download it and stop. Existing keyword ranking is relevance only.
No unchecked material, size, FRL, insulation or configuration may become an Applicable
claim. Legacy unbound or unsafe source records remain unresolved.

This extends the usable prototype with a technical decision-support interaction
using existing release and source governance. It does not complete full technical
matching; broader applicability remains P2b. P1b evidence intake stays required with
actual scanning, PostgreSQL verified reads and retained-source prerequisites. Keep
manual/imported Scope usable without AI while those dependencies are addressed.

Continue one demonstrated interaction at a time. Preserve exact revision dependencies,
visible staleness, permissions and human authority. Do not introduce a separate
framework, fleet, database or mandatory chain between capabilities.

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
