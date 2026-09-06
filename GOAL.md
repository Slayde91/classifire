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

## Demonstrated candidate-review increment

P2a provides saved candidate retrieval and human keep/reject notes over an explicit
Scope revision, technical release and selected opening/service target. Source-bound
references, missing criteria and stale dependencies remain visible. Saved JSON does
not grant approval. See PROJECT_STATE.md for validation and publication evidence.
Full applicability remains P2b; text relevance must never become a matching verdict.

## Demonstrated manual estimating increment

P3a adds an independent Draft Estimate UI over an exact saved Scope, optionally
retaining an unapproved candidate review. It supports explicit AUD unit sell rates,
unknown quantities/rates, original values and reasoned overrides, omit/restore,
partial tax-excluded subtotals and immutable JSON downloads. A synthetic Chrome
journey and actual restart verified eight estimate revisions with unchanged older
bytes. The supplied CLASSIFIRE logo is now used by the sign-in screen and sidebar.
See PROJECT_STATE.md for current checks and publication evidence.

This is manual provisional costing, not complete governed estimating. No library,
AI, canonical Estimate, Physical Model Lock or technical approval is required or
created. The supported recovery boundary excludes nonblank-opening closure work.

## Demonstrated estimate-report increment

The first P4b profile previews one saved Draft Estimate and retains PDF/XLSX from
one immutable snapshot. Exact amounts, originals/changes, missing work and partial
coverage survive later edits and restart. It runs independently without AI or
canonical recalculation. See PROJECT_STATE.md for measured checks/publication.

## Demonstrated first PDF evidence increment

P1b now has a local real-scanner browser demonstration: retain a supported PDF,
inspect its raster page, explicitly save an observation with exact page/source/review
provenance, reopen after restart and download a v3 Scope revision. Older revisions
survive edits; imported page claims confer no local access or approval. PostgreSQL
provides the existing clean-byte/quarantine boundary; manual entry remains available
without the scanner. This is bounded evidence review, not complete automated Scope
analysis. See PROJECT_STATE.md for current validation and publication status.

## Demonstrated first measured-limit review

The current P2b increment saves explicit substrate thickness and measured gap range
against a selected candidate's pinned source limits. New technical releases freeze
public fields; old releases remain unresolved for these checks. Chrome and restart
preserved within/outside/unknown outcomes and exact history. This is partial,
unapproved review, not full applicability. See PROJECT_STATE.md for publication.

## Demonstrated first workbook-rate selection

PR #196 merged source-bound XLSX upload, scanning, explicit column mapping and rate
selection. Original rates, manual overrides and exact cells survive export/restart.
This remains unapproved workbook selection, not complete pricing governance.

## Demonstrated scope-and-system reporting

PR #197 merged independent reporting of one saved candidate review and its exact
Scope, including technical-read boundaries and visible staleness. PDF/XLSX survive
edits/restart and retain unapproved status. No Estimate or matching run is required.

## Merged reports and current package download increment

PR #198 merged explicit service-size review; PR #199 merged complete Draft reports.
All four Draft report choices exist. Their partial/unapproved status remains explicit.

The selected Draft ProjectPackage UI, merged in PR #200, configures one coherent saved Scope,
optional review/Estimate and retained report pairs, previews without writes, saves a
new package revision and downloads exact ZIP bytes. Source files stay external or
withheld; existing artifact provenance and history are preserved. This is selected
workspace portability, not all project records, original evidence or a database backup.
See PROJECT_STATE.md for evidence/publication and remaining limitations.

The current import work adds a no-write ZIP inspection screen and shared semantic
validation of all selected artifacts. It does not yet create an imported project.
Do not substitute this preview for the required editable round trip.

Prioritize **safe new-project package import** across selected
capability artifacts and outputs. Validate complete declared membership and schemas,
preserve original provenance, map local identities explicitly, and keep missing
sources/foreign approval unresolved. Never silently discard unsupported artifacts or
grant authority from imported claims. Deliver the shared import use case and UI
together, then expose proven commands through ChatGPT.

The full goal remains active: broader Scope analysis, actual applicability, pricing
defaults/inference, complete package coverage/exchange, ChatGPT and production readiness
remain unfinished. OpenClaw retirement requires proven replacement protections.
