# CLASSIFIRE Project State

**Verified snapshot:** 2026-08-28 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Verified shared-main baseline:** `01925237f953275244f2b63e54564533bee81910`
(PR #78 merge)

**Merged Phase 8 scope:** representative rollback package and recovery, evidence-family and human-review validators, direct legacy-route test isolation, the durable visual-validation receipt registry/verifier, and controlled `site_observation` evidence intake

This record distinguishes committed shared-main code from the
current-main-based technical-intake candidate at its Git commit/push boundary, the
mixed legacy checkout,
current tests, migration metadata, retained non-canonical execution receipts,
the later local human-review v2 evidence, and refreshed GitHub state. Source,
tests, Git, and execution evidence outrank older documentation.

Nothing in this document authorises inference, evidence retrieval, admission signing or registration, canonical submission, Physical Model Lock creation, deployment, or release.

## 1. Repository and Git position

The verified shared-main baseline is
`01925237f953275244f2b63e54564533bee81910`, the merge of PR #78.
It includes the earlier PR #74 representative-run/recovery and
`site_observation` foundations, the later documentation reconciliation, and
runtime enforcement that inactive human sessions cannot continue to exercise
authenticated authority.

The isolated worktree
`gpt/technical-intake-draft-boundary-20260827` is based exactly on that
shared-main commit. There were no intervening unpushed commits before the
integrated implementation commit
`d76562e54a7f208c2cab8ea1e9f598065f8e5151`
(`feat: add governed technical intake and shared malware containment`). That
commit was pushed successfully to
`origin/gpt/technical-intake-draft-boundary-20260827`, and the local and
upstream refs were equal at that implementation point. This reconciliation is
the follow-up documentation record. A document cannot embed the hash of the
commit that contains it; the final Git commit/push report and read-only branch
ref record that hash. The work remains a pushed Git feature-branch candidate,
not shared-main or deployed state.

The primary checkout remains on `gpt/phase8-linked-original-images` at
`de0cc5a` with a divergent mixed working tree. It remains a legacy
evidence/development source only: it must not be bulk-staged, merged, cleaned,
reset, or used as a publication base. Its modified and untracked contents were
not touched by this reconciliation.

GitHub remains the canonical shared repository. At this snapshot, PR #75 remains
open and is stacked on superseded site-observation commit `5874dade`, not the
corrected and reviewed PR #74 head. GitHub reporting it as mergeable does not
make it safe to merge; it requires a fresh independent review. Issues #42 and
#43 and draft legacy-stack PRs #9-#13 remain open. Issue #42 still needs a
factual external update recording the merged work and remaining
physical-evidence and lock-design blockers; that is a separate external action.

## 2. Latest verified implementation state

### 2.1 Completed on shared `main`

The verified shared-main baseline at `01925237f` contains:

- the FastAPI, CLI, SQLAlchemy, Alembic, storage, audit, security, UI, import, release-pinning, calculation, snapshot, PDF/XLSX, and Mission Control foundations;
- the canonical Defect, EvidenceSource, Opening, Service, Opening-Service link, Physical Model Lock, admission, and submission-receipt records;
- the published migration lineage through
  `0009_visual_validation_receipts`;
- component-level protected-state fingerprinting and fail-closed admission-bound initial canonicalisation;
- immutable admission registration, P-256 verification, single-use submission, idempotent receipts, and an explicit no-lock submission boundary;
- bounded visual correction, proposal-blind inventory, mandatory reconciliation, strict proposal receipts, retained-evidence adaptation, guarded no-tool transport, managed runtime composition, and dedicated Phase 8 identities;
- guarded linked-original discovery, verification, retention, and the bounded linked-original-to-proposal runner;
- a strict `site_observation` evidence-intake contract requiring one bound
  Defect, immutable admissible source evidence, per-fact locators, explicit
  uncertainty and limitations, and an audit-bound canonical payload digest;
- a post-inference validation-only human-reference comparator;
- the offline Android admission signer and recorded deployment/runbook foundations;
- the immutable `VisualValidationReceipt` registry and exact no-write verifier,
  which are not signed lock-admission enforcement or canonical-write authority;
  and
- revocation of authenticated authority when a human account becomes inactive.

These are foundations and controlled UAT capabilities, not production authorisation.

### 2.2 Pushed current-main technical-intake branch candidate

The pushed current-main-based Git feature-branch candidate adds a coherent
pre-production foundation:

- production configuration/readiness checks, packaged Alembic migrations, and
  an additive candidate migration head at
  `0018_shared_malware_containment`;
- safely screened immutable technical-source intake, exact source identity,
  review and lineage, Draft-only import, retirement, separately published
  registry releases, and pinned-release search;
- owner-bound multi-report batches with per-file isolation, immutable manifests,
  replay receipts, retry, restore, and reconciliation;
- durable Draft extraction runs, pages, retained artifacts, parser reservations,
  terminal receipts, and fail-closed startup reconciliation;
- a default-off, test-only rootless-OCI parser controller and worker boundary;
  and
- an owner-bound, versioned field-level TechnicalIntakeDraft editor with
  digest-bound page preview, stable field/locator/evidence links, save/resume,
  stale-save recovery, and no approval or publication inputs.

The saved payload and authority-neutral boundary are defined in the
[Technical Intake Draft v1 contract](./TECHNICAL_INTAKE_DRAFT_V1.md).

Exact duplicate clean bytes share one verified StoredFile while retaining
separate TechnicalDocument identities and upload audits. If any later
scanner-bound upload or replay detects malware for those exact bytes, that
shared StoredFile is quarantined, every previously
accepted linked intake item and each affected batch becomes `needs_attention`,
and every document referencing those bytes fails clean-file eligibility.
Item-, batch-, and file-level audits preserve the containment transition.
Evidence history is retained; duplicate bytes are not silently copied into a
second trusted blob.

The required first-template coverage contains eight document families:
Full Fire Test Report; Regulatory Information Report; Fire Assessment Report;
Extended Application Report; Field of Application Report; Fire Engineering
Report or Performance Solution; Certificate or Summary of Assessment; and Test
Certificate. These are coverage requirements and must not be inferred from
filenames.

Two structural evidence sets inform, but do not complete, that template:

- an earlier set of eight supplied files (three regulatory-information reports
  and five assessment or assessment-bundle reports), totalling 1,673 pages; and
- an additional attached set of ten Promat reports, totalling 281 pages, for
  which every page was text-bearing in the structural inventory.

Neither set was ingested into the CLASSIFIRE database. The additional inventory
is declaration-only: text references to NCC 2022, AS 1530.4:2014, or
AS 4072.1:2005 are attention flags, not decisions that a document complies, is
applicable, or proves a technical system. An exact reference can become a
governed fact only after locator-backed human review of the retained source.

### 2.3 Shared-main representative-run and recovery capability

Shared main includes this bounded UAT feature slice:

- an explicit approved-package contract pinned to report hash, Git revision, executable source-tree hash, input snapshots, runtime identities, and no-write policy flags;
- verify-only package/snapshot checks and a non-session-creating local Gateway readiness probe;
- a literal-loopback WebSocket RPC fallback for the installed OpenClaw CLI shape, with RFC 6455 SHA-1 explicitly marked as non-security use;
- a disposable SQLite execution boundary that starts an outer transaction, runs the existing proposal-only chain, always rolls back, expires ORM state, and compares the protected fingerprint/counts after rollback;
- full-report linked-original retrieval while restricting the inference packet to current retentions and explicitly mapped ready parents for the selected defect;
- validation of report-derived parent evidence by report hash, page, photo identity, native dimensions, and crop bounds;
- exclusion of nonvisual EvidenceSource rows from visual inference packets;
- stricter blank-opening, candidate-ID, Validator vocabulary, blind-reconciliation, quantity-null, correction-authority, and blocked-receipt rules;
- content-safe evidence-review requests for valid blocked proposals; and
- fully offline recovery that binds retained receipts to local OpenClaw session indexes, transcripts, and final domain payload hashes without rerunning the report.

The source-tree walker now fails closed on nested symbolic links and Windows reparse points, including junctions on supported Python 3.11. The package approval fields remain trusted operator/governance metadata, not a cryptographic, expiring, or single-use production authorisation. The package runner is controlled UAT tooling, not an untrusted production-ingestion endpoint.

### 2.4 Foundational capability that is not roadmap-complete

Current main contains basic technical search, pinned release records, estimating
rules, line calculation, snapshot locking, and PDF/XLSX rendering. The local
candidate expands technical intake and registry governance, but neither tier
implements the complete target chain of Repair Strategy Locks, system-derived
component records, approved productivity for every activity, a
rate-inclusion/recovery ledger, independent full-estimate validation
certificates, snapshot-bound output QA, and explicit Human Release.

The primary legacy checkout contains richer guarded implementations and tests for parts of Phases 9-14, but its lineage is divergent and unsafe to merge wholesale. It is implementation evidence to review later, not current-main completion.

## 3. Latest Phase 8 execution evidence

### 3.1 Representative v17 result

A retained current-main-based v17 run executed the approved full-report package through linked-original retrieval, defect-scoped retention, and four proposal-only inference stages.

| Evidence | Verified result |
| --- | --- |
| Required linked originals | 31 of 31 resolved across 41 report photo occurrences |
| Target-defect evidence supplied to inference | 4 retained originals |
| Controller stages | 4, using separate Physical and Validator roles |
| Visual result | `VISUAL_PROPOSAL_BLOCKED` |
| Human-reference comparison | Correctly skipped because the proposal was not approved |
| Review handoff | 7 review items and 4 unresolved blind observations |
| Protected state after rollback | Unchanged: 10 Defects, 128 EvidenceSources, 0 Openings, 0 Services, 0 links, 0 active locks |
| Canonical submission | Not performed |
| Physical Model Lock | Not created |

The run proved the rollback and authority boundary, but it did not produce an accepted physical model. The later human review resolved the visible service groupings, flexible-duct count, opening relationships, and photo relationship for this Defect. Site-dependent dimensions, depth and obscured boundaries, exact substrate composition, service labels and documentary material proof, and opposite-face continuity remain explicitly unresolved.

"Rollback-only" means no canonical database submission or lock. Retrieval, temporary child-image files, disposable snapshot changes, and output receipts are expected filesystem writes; SQL rollback does not automatically delete those files.

The live v17 run used source-tree fingerprint `5B00545F5A2A7F3F36930B008B3E0802AFB1EBA5D735A7B9123218B5E972CDE1`. Later review, provenance, and receipt hardening changed the source, so v17 is historical execution proof for that exact run source, not exact runtime proof of the later merged tree.

### 3.2 Refreshed offline recovery

The fully offline recovery was rerun as v8 after the completion-receipt byte-hash correction and mechanical formatting. It binds the current source-tree fingerprint `EDBA8858B385BD521D43AB15FAE41C5291356985E47B1792ADC40A0ADD6A8D6F` and current recovery-script bytes.

- Evidence-review request file SHA-256: `58200866211E15E49087986BC1E893DE5D377E1067E57B242B537A42E22B34E1`
- Recovery receipt file SHA-256: `D41A424A7D5500E596B73E340E713BC008D2C11830BEC979D1E164B268134BAF`
- Recovery script SHA-256: `69A926B057900D35F5A509874244A503A0C0CA062F39B72B6C22E4FA6A45B0E2`
- Output: exactly `evidence-review-request.json` and `recovery-receipt.json`
- Retained-report/linked-original file reads, retrieval, inference, canonical submission, locking, and human-reference exposure: all false; the bound local session transcripts were read

Recovery proves correspondence among retained package metadata, no-write receipts, deterministic session keys, local transcript payloads, and final blind/proposal/Validator hashes. The historical v17 representative, controller, and proposal files were written on Windows before the current raw-byte writer hardening; recovery records their matching `LF_RENDERED_JSON_SHA256` bindings separately from their actual retained file hashes. It does not make local OpenClaw history immutable and does not replay Gateway authentication, tool attestation/audit, OpenResponses response identity, or external transport.

### 3.3 Human review v2 and proposal-only validation

On 24 August, the named human reviewer completed a provenance-bound v2 response for the selected representative Defect. It accounts for all seven Validator review items and four unresolved-observation items exactly once across six decisions. A separate local no-write validator produced status `PASS` for a limited proposal-only record containing one Defect, five Openings, six Services, and six Opening-Service links.

The review confirmed that the two questioned openings are separate openings in the same wall; the close and wide duct photographs show the same location; two flexible foil-covered ducts pass through two separate wall openings; one shared opening contains one metal pipe, two PVC conduits, and one cable bundle; and another opening contains one visible three-cable bundle.

This is human visual adjudication, not site verification or canonical truth. Opening dimensions, depth and obscured boundaries, exact substrate composition, service labels, documentary material proof, and opposite-face continuity remain unresolved. The v2 review and evidence-family validators are on shared main; the retained response remains local evidence and is not canonical state or publication authority. Its recording and validation performed no report/image retrieval, runtime inference, canonical database read or write, Gateway call, admission, submission, or lock.

### 3.4 Historical canonicalisation evidence

The v6 canonicalisation preflight remains historical no-write evidence only:

- status `PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED`;
- 17 Openings, 24 normalized Services, and 24 links in that historical payload;
- protected-state fingerprint `18768A9E368C7D0692A950303FCAC9401AFBE7C3632BE6A063FCB67B9671F8F1`;
- submission and lock eligibility false; and
- no database, canonical, or Gateway write.

The independent v17 evidence block means the historical 17/24 topology must not be treated as accepted physical truth or reusable admission authority. Any future preflight must bind a newly accepted exact proposal and then-current protected state.

## 4. Roadmap status

| Phase | Current state |
| --- | --- |
| 0-2 | In progress: a validated current-main-based technical-intake and release-governance candidate is pushed to its Git feature branch through migration `0018_shared_malware_containment`; external pull-request review, merge, real-report intake, materialisation, and operational UAT remain incomplete |
| 3 | In progress: controlled writer and zero-tool foundations exist; shared main includes trusted UAT package/readiness/recovery tooling; production recovery and deployment proof remain incomplete |
| 4 | In progress: Mission Control client/bootstrap scaffolding exists but does not own estimate truth |
| 5 | In progress: one approved report/source path demonstrated full-report linked-original resolution; evidence families, other formats/hosts, retention policy, and multi-report proof remain |
| 6 | In progress and evidence-limited: a local human-adjudicated proposal records the visible 5/6/6 topology for one Defect, but site-dependent facts remain unresolved and no accepted canonical model exists |
| 7 | In progress: representative safety/rollback and limited human review are proven; the durable receipt registry and verifier are merged, but signed lock enforcement is not implemented |
| 8 | In progress and blocked on site evidence, semantic acceptance, and separate canonical/lock authority; no canonical model or replacement Physical Model Lock exists |
| 8C | Planned; only charter/taxonomy/rights preparation is allowed before its admission gates |
| 9-14 | Basic current-main foundations and richer legacy-only foundations exist; operationally blocked and not architecture-complete |
| 15 | In progress: local readiness, malware, upload, and parser-containment foundations exist; deployment, live PostgreSQL concurrency, and production parser UAT remain |
| 16 | Deferred: structural steel and complete fire-rated duct runs require separate design and evidence |

## 5. Verification for this reconciliation

The pushed implementation candidate was verified as follows:

- the exact full candidate suite completed with **1,545 passed, 15 skipped, and
  140 warnings in 3,181.77 seconds**;
- focused catalogue and UI coverage completed with **141 passed**;
- focused lock, review, and containment coverage completed with **154 passed**,
  with four new regression cases recorded;
- every JavaScript harness reported success; and
- Alembic reported one head:
  `0018_shared_malware_containment`.

A disposable local HTTP UAT used only synthetic metadata and isolated
SQLite/storage. Health, login, the technical catalogue, and both synthetic
document-detail routes returned HTTP 200. The live authenticated HTML exposed
the exact eight new-upload report families, kept the three legacy report types
out of ordinary selection while retaining a readable legacy record, and stated
that declarations for NCC 2022, AS 1530.4:2014, and AS 4072.1:2005 are attention
signals rather than proof of compliance or applicability. No supplied PDF was
opened, copied, or ingested during that UAT.

Rendered-browser UAT did **not** pass. Browser control could not start because
the Windows sandbox returned
`windows sandbox failed: helper_unknown_error: setup refresh had errors`.
The authenticated HTTP evidence and JavaScript harnesses do not replace a
rendered interaction check.

Whole-tree static analysis still contains inherited debt and is not a clean
pass:

- Ruff: **207 findings**, compared with **329** on the verified baseline;
- Mypy: **47 errors in 9 files**, compared with **101 errors in 11 files** on
  the verified baseline; and
- Bandit: **7 low-severity findings and 0 medium/high**, compared with **8 low
  and 0 medium/high** on the verified baseline.

Those numeric counts are lower than the baseline, but that does not make the
whole-tree checks clean or prove the absence of semantic regressions. The
remaining findings are open debt. The focused core Ruff check passed, focused
Mypy checked 26 files cleanly, and the focused Bandit check reported no issues.

The structural report checks remained read-only inventories outside CLASSIFIRE.
There was no real-report database ingestion, Draft authoring from a supplied
report, governed locator-backed compliance decision, or technical-authority
write. Live PostgreSQL two-session concurrency, the stateful scanner
clean-to-FOUND path, an eligible rootless parser, and rendered-browser UAT remain
unproven.

The earlier PR #74 evidence-boundary tests and offline recovery remain
historical proof for their exact source fingerprints. No admission was created,
signed, or registered; no canonical model was submitted; and no Physical Model
Lock, deployment, registry publication, or release occurred.

## 6. Boundaries and excluded local state

The primary mixed checkout and its tracked/untracked changes remain untouched.
Customer evidence, reports/images, databases, OpenClaw session history, keys,
tokens, signed URLs, generated packages, caches, Android/Gradle/JDK tooling,
editor files, agent definitions, and branding assets remain local and excluded
from the shared repository.

The merged receipt registry records and verifies evidence bindings only. It did
not create semantic acceptance for the selected Defect, perform a canonical
write, create a Physical Model Lock, sign or register an admission, deploy, or
release anything.

The merged site-observation contract adds no database table, no new writer, and
no live evidence. It validates a narrow payload at the existing
evidence-registration boundary. Merging it did not register evidence or grant
canonical-write, lock, deployment, or release authority.

The pushed current-main technical-intake branch candidate is
authority-neutral at intake and Draft
authoring. Source review, TechnicalVariant review, and registry publication are
separate audited permissions. The parser and reconciliation worker remain
default-off and test-only. The candidate's presence does not authorise use of
private reports, production preview, database migration, deployment, or
Technical Authority Registry publication.

## 7. Recommended Next Actions

### Immediate - exercise shared-byte containment and concurrency

**Order:** 1

**Objective and outcome:** In a disposable non-production environment, prove
the shared-byte safety boundary under real database concurrency and a changing
scanner result. Exercise two PostgreSQL sessions across duplicate upload,
download, Draft, and review operations, then drive the same digest from a
scanner-bound clean result to FOUND. Confirm that containment is atomic,
audited, and authority-neutral.

**Evidence rationale:** The exact candidate suite and focused containment tests
are green, but SQLite and mocked scanner/runtime coverage cannot prove database
locking between real sessions or the stateful clean-to-FOUND operational path.

**Components:** Packaged migration head 0018; disposable PostgreSQL; disposable
storage; stateful ClamAV-compatible test service; duplicate-byte upload/replay;
download, Draft, and source-review eligibility; item/batch/file audit events;
and protected authority-record counts.

**Dependencies and blockers:** A disposable non-production PostgreSQL instance,
isolated storage, and a controlled scanner test service whose verdict can be
changed without touching customer material. No production database, report, or
shared scanner may be used.

**Acceptance criteria:** Two-session races never create two trusted blobs or
leave mixed clean/quarantined eligibility; a later exact FOUND result
quarantines the shared StoredFile, moves all linked accepted items/batches to
attention, blocks every referencing document from clean-file workflows, retains
history, and creates no TechnicalVariant, Approval, LibraryRelease, canonical
model, or Physical Model Lock.

**Validation:** Retain redacted environment and migration identity, request
ordering, exact digest bindings, scanner responses, transaction outcomes,
audit rows, authority-record counts, and teardown evidence. Repeat the critical
interleavings from two independent database sessions.

**Uncertainty:** PostgreSQL/ClamAV operational behaviour remains unproven until
this UAT is completed. Passing it would not authorise production deployment or
technical use of any report.

### Near-term - prove parser isolation and rendered browser behaviour

**Order:** 2, after the immediate containment/concurrency UAT.

**Objective and outcome:** Exercise the default-off parser boundary on an
eligible rootless Linux host, then retry the authenticated rendered-browser
Draft workflow in a working browser environment.

**Evidence rationale:** Focused parser, startup-reconciliation, HTTP, and
JavaScript tests passed, but no admitted rootless image/host has executed the
controller and the Windows browser sandbox prevented rendered interaction UAT.

**Components:** Eligible rootless OCI runtime and admitted parser image;
normal execution and stale-orphan cleanup under the shared fence; authenticated
Draft start/save/resume/stale recovery; verified-page events; and manual-page
fallback.

**Dependencies and blockers:** Approved parser image and supply-chain evidence,
an eligible rootless Linux host, disposable database/storage, approved preview
security/licensing, and a browser runtime that does not fail during sandbox
setup.

**Acceptance criteria:** Parser receipts bind exact source/runtime bytes and
fail closed on timeout, containment loss, or unsettled attempts; browser UAT
visually confirms the eight current families, hidden-but-readable legacy types,
standards warnings, preview binding, save/resume, stale recovery, and absence of
authority controls.

**Validation:** Retain redacted runtime/profile/receipt/cleanup evidence and
teardown counts; capture rendered interaction evidence without confidential
content; and confirm zero unintended technical, canonical, or release authority
writes.

**Uncertainty:** HTTP status and JavaScript harness evidence are not a rendered
browser pass, and the test-only parser must not be described as production-ready
until this operational proof and later production wiring are complete.

### Later - complete reviewed technical authoring and release proof

**Order:** 3, dependent on the immediate candidate and near-term UAT.

**Objective and outcome:** Add reviewer-owned intake revisions,
configuration-family authoring, governed locator-backed decisions, controlled
TechnicalVariant materialisation, and independent publication/pinned-runtime
UAT.

**Evidence rationale:** Current Drafts preserve source-bound fields but cannot
materialise reviewed candidates. The two structural inventories were not
ingested and did not make a compliance decision.

**Components:** The eight required document families, representative-source
coverage matrix, exceptions register, raw/normalised values, many-to-many
locators, configuration inheritance/overrides, review decisions, materialisation
receipts, and publication/pinning.

**Dependencies and blockers:** Obtain a retained primary Full Fire Test Report
and a scanned/image-only source; secure competent technical review; and preserve
private-report handling. Exact mentions of NCC 2022, AS 1530.4:2014, or
AS 4072.1:2005 remain attention flags until a source-bound decision exists.

**Acceptance criteria:** Every material accepted claim has required locators and
roles; missing or contradictory facts remain Unresolved; unsupported
cross-products are impossible; Draft approval does not create runtime
eligibility; and only a separately published, estimate-pinned release is
searchable.

**Validation:** Run representative UI, Excel/JSONL, reviewer-separation,
materialisation, publication, exclusion/retirement, and pinned-search UAT with
retained provenance and zero authority bypass.

**Uncertainty:** The first template and any standards/compliance result remain
unfrozen until representative evidence and competent review are complete.

### Dependency-bound - preserve the separate Phase 8 gate

**Order:** Independent of the technical-intake branch workstream; proceed only when
new physical evidence exists.

**Objective and outcome:** Obtain a site visit or equivalent newly governed
evidence for the selected Defect's dimensions, depth/boundaries, exact
substrate, service labels/material proof, and opposite-face continuity.

**Evidence rationale:** The retained 7+4 human review is complete, but its
limited 5/6/6 topology is non-canonical and those site-dependent facts remain
unresolved.

**Components:** Site measurements and observations, retained admissible source
files, per-fact locators, explicit uncertainty and limitations, independent
semantic review, and any later exact proposal/receipt lineage.

**Dependencies and blockers:** New admissible site evidence and later,
separately authorised semantic acceptance and signed lock-admission design.

**Acceptance criteria:** Retain the new evidence immutably, register only facts
it supports through the governed contract, preserve explicit uncertainty, and
do not create canonical or lock state before the separate gates.

**Validation:** Review each registered fact against its exact locator, rerun an
exact proposal only when the governed evidence has materially changed,
independently validate that proposal, and compare protected state before any
later authorised write.

**Uncertainty:** External signing, admission registration, canonical
submission, and Physical Model Lock creation remain separate operations
requiring separate authority.
