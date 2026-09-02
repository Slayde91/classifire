# CLASSIFIRE Architecture

**Document status:** Current pre-production architecture

**Architecture version:** 4.0

**Verified shared-main implementation:** `5639e26` (PR #122 merge,
2026-09-02)

This document separates the architecture that is implemented now from the
target architecture and known gaps. Read it with [PROJECT_STATE.md](./PROJECT_STATE.md)
and [CLASSIFIRE_ROADMAP.md](./CLASSIFIRE_ROADMAP.md). Source, tests, migrations,
Git state, and retained runtime receipts determine factual implementation state.

## 1. Governing reasoning chain

CLASSIFIRE preserves this order:

```text
Project Evidence
-> Defects
-> Services and Assets
-> Openings
-> Substrate Planes
-> Physical Model
-> Repair Components
-> Technical System Search
-> Compatibility Validation
-> Commercial Applicability
-> Quantity and Labour
-> Reconciliation
-> Estimate, Scope, and Close-out
-> Human Release
```

Physical reality comes before technical selection or pricing. A report label,
Defect, photograph, Opening, Service, Opening-Service link, repair component,
and commercial line are different records. One Defect does not imply one
Opening, one Service, or quantity one.

An assumption-led desk quote is a deliberately parallel proposal-only
commercial scenario. It may support early budgeting from bounded evidence and
assumptions, but it does not enter or bypass the canonical chain above.

## 2. Authority and sources of truth

The governed CLASSIFIRE database is canonical project state. OpenClaw sessions,
Mission Control tasks, prompts, model outputs, chat history, package files, desk
quotes, and temporary receipts are evidence or proposals, not canonical truth.

Authority remains separate for:

1. evidence retention and review;
2. proposal-only inference;
3. human evidence adjudication;
4. canonical Physical Model submission;
5. Physical Model Lock creation;
6. technical-source and TechnicalVariant approval;
7. technical-release publication;
8. commercial approval;
9. deployment; and
10. Human Release.

Approval for one operation never grants a later authority.

### Repository tiers

| Tier | Meaning |
| --- | --- |
| **Shared main** | Reviewed source on the current GitHub `main` lineage. |
| **Isolated branch/worktree** | Candidate work based on current main; not shared implementation until reviewed and merged. |
| **Quarantined legacy root** | Historical and unfinished evidence in the conflicted `C:\CLASSIFIRE` checkout; never a bulk publication or deployment source. |
| **Local runtime evidence** | Receipts and disposable artifacts proving a particular bounded operation; never canonical state or source publication. |

## 3. Implemented application composition

| Layer | Current implementation | Main boundary |
| --- | --- | --- |
| Application | FastAPI, CLI, development HTML UI, worker shell, and audit services | Pre-production; not every merged service has an operator/UI flow |
| Persistence | SQLAlchemy with packaged Alembic migrations | Shared `main` has one Alembic head: `0013_report_defect_scope_admissions` |
| Evidence storage | Content-addressed `StoredFile`, Project/Estimate ownership, immutable metadata, verified reads, quarantine | Exact production use requires PostgreSQL transaction semantics |
| Physical model | Defect, EvidenceSource, Opening, Service, `ServiceOpeningLink`, locks, admissions, submission receipts | No accepted replacement lock for the current UAT estimate |
| Proposal-only inference | Blind inventory, Physical proposal, Validator, bounded correction, receipts | No canonical-write or lock capability |
| Report assessment | Shared components, expected-label admission, and proposal-only runner | The runner requires a caller-owned PostgreSQL clean-byte transaction and injected no-tool port; no CLI, API, UI, persisted package record, or real-provider run exists |
| Technical governance | Document review, clean source-byte checks, source-bound Draft materialisation/variants/revisions, source locators, independent activation, pinned active releases | Manufacturer-neutral lineage and governed publication/supersession remain incomplete |
| Estimating/output | Basic estimate calculation, PDF/XLSX outputs, assumption-led desk quotes | Full technical-to-component recovery and release chain incomplete |
| Orchestration | OpenClaw boundary and Mission Control client/bootstrap | Neither owns canonical estimate state |

Production startup validates configuration before storage work, never runs
`create_all()` or seeds a default administrator in production, and requires the
configured database to match the packaged migration head. Development retains
convenient schema creation/seeding. This is narrow hardening, not deployment
proof.

## 4. Domain model

The current physical graph is:

```text
Project
  -> Estimate
       -> Defect
            -> EvidenceSource
            -> one or more Openings
                 -> zero Services for an explicit blank opening/core hole
                 -> one or more Services through ServiceOpeningLink records
```

An Opening is the aperture or bounded penetration condition. A Service is a
physical item passing through it. Placeholder Services are prohibited.

Barrier/substrate, plane, orientation, opening type and dimensions, FRL or
governed assumption, service identity/material/quantity, link provenance, and
limitations remain independently represented. Unknown or occluded facts must
not be invented to make a proposal complete.

Shared main also implements immutable admission registration and one-shot
initial physical submission. Registration is authority evidence, not a write.
Initial submission does not create a lock. A separate reviewed and signed lock
admission is required before a replacement active Physical Model Lock.

## 5. Evidence and storage architecture

### 5.1 Retained evidence

`StoredFile` retains immutable file metadata and content identity.
`ProjectEvidence` gives each binding exactly one direct owner: either a Project
or an Estimate, never both. Every Estimate is itself owned by a Project.
`EvidenceSource` binds a supported claim or observation to the estimate and
retained source.

For security-sensitive consumption, the PostgreSQL path locks every row sharing
the same SHA-256, requires every shared row to remain clean, opens the exact
retained path without following unsafe substitutions, verifies size and hash,
and holds the transaction through consumption. A malware verdict uses the same
row set and quarantines all matching-byte rows. Binding mismatches cannot roll
back confirmed shared-byte quarantine.

Metadata-only checks are not equivalent to this atomic clean-byte contract.

### 5.2 Report normalisation

The merged report adapter currently supports bounded PDF normalisation:

- report/page metadata hashes;
- text blocks;
- tables;
- annotations;
- drawing locators/hashes;
- embedded-image locators/hashes; and
- stable report/page/item identities and ordered Defect scopes.

Text, table, and annotation items can provide transient documentary content.
Drawing and embedded-image report items are locator/hash evidence without raw
documentary content. Actual visual inference bytes come from a separately
governed retained visual packet. Caption items are currently rejected, and no
caption extractor exists. XLSX, DOCX, general report formats, and multi-report
generalisability remain planned.

On shared main, cardinality is deterministic for the report scopes that already exist in the
database. An approved expected-label manifest record is source-bound to the
report bytes and estimate for runner completeness. New report scopes are admitted
only as one complete, exact label set matching that approval record, and every new
scope retains its approval-record ID. Bound packets emit V2 approval details.
Historical unbound scope packets remain verifiable as V1, but the proposal runner
rejects them rather than treating them as approved coverage.

### 5.3 Linked originals and visual evidence

Linked-original retrieval is limited by approved host/address/TLS/redirect,
path/query, MIME, byte, pixel, and runtime policies. A higher-resolution image
is retained only after binding to the report-provided parent. Lower-resolution
page context, annotations, crops, and alternate views remain relevant when they
contain different evidence.

Photograph count never becomes Opening, Service, or quantity count.

## 6. Proposal-only assessment architecture

The visual controller executes:

```text
Blind Validator inventory
-> Physical proposal
-> Conditioned Validator review
-> Optional bounded correction
-> Approved, Blocked, or Failed receipt
```

The blind inventory cannot see a Physical proposal or human answer. The Physical
role cannot see the blind inventory. Human-reference material is validation-only
and remains hidden from inference.

Schemas enforce separate Openings and Services, links, blank-opening semantics,
unique candidate IDs, uncertainty, evidence references, issue codes, and blind
reconciliation. Correction authority is field-specific. A quantity issue cannot
authorise an unrelated topology, substrate, material, or relationship change.

The report-specific services add:

```text
Owned clean report bytes
-> stable report locators and Defect scopes
-> transient documentary context + governed visual packet
-> v2 property assessment
-> proposal/Validator receipt
-> deterministic JSON + inert Markdown review
-> completion receipt over preceding artifacts
```

`execute_phase8_report_assessment_runner()` composes this sequence as a
proposal-only application service on shared main. It is not an operator surface:
callers must provide the transaction and no-tool port, and no
CLI, API, UI, or persistent review-package record invokes it. No real-provider
run is implemented or authorised.

### Latest operational evidence

The authorised 2026-09-01 proposal-only attempt started inference and failed at
the first blind-inventory call. It safely returned
`VISUAL_PROPOSAL_FAILED`, did not compare a human reference, remained rollback-
only, exposed no write/lock capability, and performed no database write,
canonical submission, or lock creation.

`Phase8OpenResponsesTransportError` owns a stable code intended to exclude
secrets and response content. Historical receipts recorded only the exception
class under `INFERENCE_PORT_FAILED`, so they cannot identify the actual safe
transport reason. New proposal-only receipts retain only codes from the explicit
validated safe-code set; arbitrary exception text remains excluded.

## 7. Human review and canonicalisation

Human evidence review is a post-inference provenance record. It must bind exact
review/proposal lineage, account for every requested item, preserve unresolved
outcomes, and remain invisible to runtime inference. It is not a visual approval
receipt, canonical submission, lock, technical selection, price, or release.

The durable `VisualValidationReceipt` registry hash-binds the reviewed candidate,
controller receipt, evidence manifest, family/review records, policy versions,
and decision. Its verifier is a no-write eligibility check for a future lock
candidate. It neither writes a Physical Model nor creates lock authority.

Canonical submission, semantic acceptance, and Physical Model Lock remain
separate operations. The current estimate has no accepted replacement lock, so
downstream canonical technical and release phases remain blocked.

## 8. Technical authority

Technical selection must use authorised evidence and an immutable active
technical release; commercial pricing cannot prove compatibility.

Current shared-main safeguards include:

- independent technical-document submission and decision;
- clean, immutable, unchanged source-byte checks at review and activation;
- a retained source document on every Draft variant and preserved exact binding
  through a Draft revision;
- a nonblank source locator before technical review and content-safe extraction
  failure diagnostics;
- independent TechnicalVariant activation from `in_review`;
- Draft-only new technical-library imports regardless of source-declared state;
- runtime use only through an active immutable pinned technical release;
- rejection when any manifest TechnicalVariant is missing or inactive; and
- the same eligibility check before refreshing an editable estimate's pins.

Full Draft intake/materialisation, manufacturer-neutral source lineage,
publication/supersession automation, and production technical authority are not
complete. Unsupported compatibility remains unresolved.

## 9. Quantity, commercial recovery, snapshots, and outputs

The target canonical path is:

```text
Locked Physical Model
-> supported technical strategy
-> required repair components
-> deterministic quantities and labour
-> one commercial recovery per component
-> independent validation
-> reproducible immutable snapshot
-> rendered output
-> Human Release
```

Shared main has basic calculation, releases, estimate lines, PDF/XLSX rendering,
and snapshots. It does not yet implement the complete system-derived component,
productivity, and rate-inclusion/recovery ledger. Estimate snapshot V2 keeps
`generated_utc` for audit display but excludes it from `snapshot_hash`; a
separate `snapshot_document_hash` still binds every displayed field, including
that timestamp. The output boundary accepts legacy V1 full-payload hashes and
fails closed for invalid V1/V2 or unsupported packets. This establishes snapshot
integrity foundations only; it does not prove the independent Phase 12 inputs or
Human Release.

### Desk-quote exception boundary

PR #75 added strict assumption-led desk-quote payloads, active pricing-release
bindings, tamper-checked receipt rendering, client qualifications, PDF/XLSX
outputs, and audit events. A desk quote cannot claim an observed site condition,
technical system, canonical model, lock, approved estimate, or release.

The current implementation requires an explicit Project and Estimate reference,
accepts only ProjectEvidence-owned, immutable `project_evidence` with a `clean`
scan state, and reads every retained source through the atomic PostgreSQL
clean-byte reader. It rejects missing, changed, outside-root, link/reparse,
quarantined, wrong-purpose, and cross-estimate evidence. A caller locator must
match a persisted EvidenceSource page/region value or ReportEvidenceLocator.

Both new and cached exports are atomically read and hash-checked before their
bytes are returned. The audit binds the artifact hash and size. An evidence or
cache mismatch fails before an output or audit event; the proposal-only endpoint
still cannot create canonical state, a lock, a technical decision, or a release.
Synthetic SQLite and PostgreSQL race tests cover this boundary. PR #103 review
and CI passed; operational approval remains necessary before use.

Desk quotes also do not complete the canonical rate-inclusion/recovery ledger
and do not mark Phase 11 or Phase 13 complete.

## 10. OpenClaw, Mission Control, and human authority

OpenClaw provides controlled sessions, model routing, workspace/tool policy,
and audit evidence. Proposal roles must have empty effective tool inventories
and cannot submit canonical data, create a lock, approve technical/commercial
decisions, or release an estimate.

Mission Control is an operational task and visibility plane. It may mirror links
and summaries but must not become a second estimate database, technical library,
pricing authority, or release workflow.

Competent humans own source approval, material evidence exceptions, technical
and commercial approvals where required, canonical/lock authorities, deployment,
and final Human Release. Decisions bind exact governed records, hashes, and
reasons.

## 11. Status vocabularies

Several bounded contracts intentionally use different vocabularies:

| Context | Terms |
| --- | --- |
| General governed evidence | Confirmed, Inferred, Provisional, Unresolved |
| Phase 8 v2 property assessment | Confirmed, Approximate, Inferred, Unknown |
| Desk-quote assumption | inferred, provisional, assumed, unresolved |

These terms are not interchangeable. No automatic translation may upgrade a
desk assumption or model estimate into a confirmed canonical fact.

## 12. Current architectural gaps and follow-up

### Completed report-governance integration

PR #104 merged the expected-label manifest, atomic scope admission, V2 runner
preflight, migration-head readiness, and `main` push validation into
`b6409a5`. Pull-request validation passed on `0f6c252`, and the first observed
`main` validation passed on the merge commit (`33516292114`), including tests
and the one-head Alembic check. These are implementation and CI facts only: the
services remain proposal-only and no operator/UI surface or downstream authority
was added.

GitHub protection configuration is still unavailable to inspect on the current
private-repository plan. The standard merge and hosted validation were accepted;
that does not prove a configured required-review or required-check rule.

PRs #105-#118 then merged documentation reconciliation, semantic snapshot
identity, retained-source safeguards, source-bound Draft materialisation, and
contained type-safety hardening through `14ed594`. PR #119 reconciled the
preceding factual records; PR #120 moved PDF timestamps to an aware UTC clock;
and PRs #121-#122 applied current CLASSIFIRE display branding to generated
artifacts and the browser workspace. Their pull-request checks and corresponding
`main` validation runs passed; the latest post-merge run is `33657134992` on
`5639e26`. The technical changes require retained source identity and
locator, preserve exact Draft/revision source binding, and retain content-safe
extraction diagnostics. PR #113 makes admission rejection helpers explicitly
non-returning without altering their fail-closed safe-code behaviour. PR #114
makes rule and UI response types explicit, rejects non-text rule operators
deterministically, and proves existing library-page rendering. PR #116 preserves
release-administration guards while making their type boundaries explicit; PR
#117 clarifies XLSX row handling; and PR #118 rejects non-object task responses
from Mission Control. These safeguards do not approve a system, publish a
release, price work, create a lock, deploy, or release an estimate.

### Required design before a review UI

**Priority 1 - define proposal-review package ownership and persistence.** The
runner returns a deterministic in-memory `Phase8ReportReviewPackage`; the
materialiser writes only to a caller-selected directory. There is no persistent
package aggregate, retention/redaction rule, reviewer-access policy, API route,
or UI route. Decide those ownership and lifecycle rules first, then add a narrow
immutable record that retains only safe hashes, locators, uncertainty, and
receipt/source bindings. It must remain proposal-only and cannot add canonical,
technical, commercial, lock, deployment, or release authority.

### Near term

Complete governed technical-source lineage publication and supersession in
separate reviewed migrations. Treat full-repository lint remediation as its own debt
slice; the CI workflow deliberately checks only changed Python files because the
current repository is not globally Ruff-clean.

### Dependency-bound

Another report/provider attempt requires fresh explicit authority after synthetic
transport diagnosis. Canonical submission, lock creation, Phases 9-14,
deployment, and Human Release remain behind their existing evidence and human
authority gates. Detailed execution order and acceptance criteria are in
[PROJECT_STATE.md](./PROJECT_STATE.md).

## 13. Deprecated or superseded paths

- Whole-file database hashes and count equality as semantic acceptance.
- Placeholder Services for blank openings.
- Generic writer authority or lock creation during initial submission.
- Treating model output, desk quotes, chat, or Mission Control as canonical truth.
- Treating the conflicted legacy root or draft PR stack as a bulk merge path.
- Treating a successful transport, test suite, or CI run as technical approval,
  deployment proof, or Human Release.

Structural-steel protection and complete fire-rated duct runs remain deferred
domains requiring their own schemas, sources, calculations, and acceptance
evidence.
