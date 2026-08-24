# CLASSIFIRE Project State

**Verified snapshot:** 2026-08-25 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Shared `main` verified:** `1b3d7c976dd726a663c105e99d0b38ab22460d66`, equal to `origin/main` at reconciliation

**Merged Phase 8 scope:** representative rollback package and recovery, evidence-family and human-review validators, direct legacy-route test isolation, and the durable visual-validation receipt registry/verifier

This record reflects committed shared-main code, the mixed legacy checkout, current tests, migration metadata, retained non-canonical execution receipts, the later local human-review v2 evidence, and refreshed GitHub state. Source, tests, Git, and execution evidence outrank older documentation.

Nothing in this document authorises inference, evidence retrieval, admission signing or registration, canonical submission, Physical Model Lock creation, deployment, or release.

## 1. Repository and Git position

At reconciliation, shared `main` and `origin/main` both resolve to
`1b3d7c976dd726a663c105e99d0b38ab22460d66`, the merge of PR #73. The merged
tree includes the earlier representative-run/recovery package, evidence-family
and human-review validators, the direct legacy-route test isolation, and the
durable visual-validation receipt registry and verifier.

The primary checkout remains on `gpt/phase8-linked-original-images` at
`de0cc5a` with a divergent mixed working tree. It remains a legacy
evidence/development source only: it must not be bulk-staged, merged, cleaned,
reset, or used as a publication base. Its modified and untracked contents were
not touched by this reconciliation.

GitHub remains the canonical shared repository. Issues #42 and #43 and draft
legacy-stack PRs #9-#13 remain open. Issue #42 still needs a factual external
update recording the merged work and remaining physical-evidence and lock-design
blockers; that is an external action requiring separate authority.

## 2. Latest verified implementation state

### 2.1 Completed on shared `main`

Shared `main` at `1b3d7c9` contains:

- the FastAPI, CLI, SQLAlchemy, Alembic, storage, audit, security, UI, import, release-pinning, calculation, snapshot, PDF/XLSX, and Mission Control foundations;
- the canonical Defect, EvidenceSource, Opening, Service, Opening-Service link, Physical Model Lock, admission, and submission-receipt records;
- migration head `0009_visual_validation_receipts`, following `0008_retire_legacy_initial_submissions`;
- component-level protected-state fingerprinting and fail-closed admission-bound initial canonicalisation;
- immutable admission registration, P-256 verification, single-use submission, idempotent receipts, and an explicit no-lock submission boundary;
- bounded visual correction, proposal-blind inventory, mandatory reconciliation, strict proposal receipts, retained-evidence adaptation, guarded no-tool transport, managed runtime composition, and dedicated Phase 8 identities;
- guarded linked-original discovery, verification, retention, and the bounded linked-original-to-proposal runner;
- a post-inference validation-only human-reference comparator; and
- the offline Android admission signer and recorded deployment/runbook foundations; and
- the immutable `VisualValidationReceipt` registry and exact no-write verifier,
  which are not signed lock-admission enforcement or canonical-write authority.

These are foundations and controlled UAT capabilities, not production authorisation.

### 2.2 Shared-main representative-run and recovery capability

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

### 2.3 Current-main foundational capability that is not roadmap-complete

Current main also contains basic technical search, pinned release records, estimating rules, line calculation, snapshot locking, and PDF/XLSX rendering. Those services do not yet implement the complete target chain of Repair Strategy Locks, system-derived component records, approved productivity for every activity, a rate-inclusion/recovery ledger, independent full-estimate validation certificates, snapshot-bound output QA, and explicit Human Release.

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
| 0-2 | In progress: repository consolidation, governance, and source-library release controls remain incomplete |
| 3 | In progress: controlled writer and zero-tool foundations exist; shared main includes trusted UAT package/readiness/recovery tooling; production recovery and deployment proof remain incomplete |
| 4 | In progress: Mission Control client/bootstrap scaffolding exists but does not own estimate truth |
| 5 | In progress: one approved report/source path demonstrated full-report linked-original resolution; evidence families, other formats/hosts, retention policy, and multi-report proof remain |
| 6 | In progress and evidence-limited: a local human-adjudicated proposal records the visible 5/6/6 topology for one Defect, but site-dependent facts remain unresolved and no accepted canonical model exists |
| 7 | In progress: representative safety/rollback and limited human review are proven; the durable receipt registry and verifier are merged, but signed lock enforcement is not implemented |
| 8 | In progress and blocked on site evidence, semantic acceptance, and separate canonical/lock authority; no canonical model or replacement Physical Model Lock exists |
| 8C | Planned; only charter/taxonomy/rights preparation is allowed before its admission gates |
| 9-14 | Basic current-main foundations and richer legacy-only foundations exist; operationally blocked and not architecture-complete |
| 15 | In progress: security, recovery, scale, monitoring, and release hardening remain |
| 16 | Deferred: structural steel and complete fire-rated duct runs require separate design and evidence |

## 5. Verification for this reconciliation

Current verification evidence for the exact merged source tree:

- `origin/main` and the verified pre-merge combined worktree have identical tree
  hash `7eb06c1fee6bccb0761d17f4010f6ce1d866953c`;
- complete repository suite: **371 passed**, 139 warnings, with
  `CLASSIFIRE_ADJUDICATED_INITIAL_SUBMISSION_ENABLED=true`;
- focused Phase 8 receipt/provenance tests after the type correction: **57
  passed**, 32 warnings;
- Ruff lint and formatting checks on changed paths, Mypy on the changed Phase 8
  service and associated changed production paths, Bandit, syntax compilation,
  Alembic one-head check (`0009_visual_validation_receipts`), and `git diff
  --check` passed; and
- a whole-repository Ruff/Mypy run still reports inherited baseline debt outside
  these merged changes (Ruff reformat findings across 39 existing files; Mypy
  104 errors in 12 existing files). The three new review-service type errors
  found during that run were corrected before merge.

The retained offline recovery v8 remains historical, successful hash-binding
evidence for its own source fingerprint. A staged local `site_observation`
evidence-intake contract is not part of shared main; its complete isolated suite
passed **377**, 139 warnings on 25 August. It requires an immutable scanned file,
one bound Defect, capture/governance provenance, a per-fact evidence locator, explicit uncertainty, and an audit payload digest
before the existing endpoint can retain the evidence.

No real report was rerun for this documentation reconciliation or local contract
work. No admission was created, signed, or registered; no canonical model was
submitted; no lock, deployment, or release occurred.

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

The staged local site-observation contract adds no database table, no new writer,
and no live evidence. It validates a narrow payload at the existing evidence
registration boundary and remains unpublished until separately committed and
reviewed.

## 7. Current blockers and next valid task

The retained 7+4 human review is complete and must not be repeated. The next
physical-evidence action for the selected Defect is a site visit or equivalent
newly governed evidence for dimensions, depth/boundaries, exact substrate,
service labels/material proof, and opposite-face continuity.

Do not rerun unchanged inference or convert the limited 5/6/6 record into
canonical truth. The durable visual-validation receipt registry and exact
no-write verifier are now shared-main safeguards, but semantic acceptance and a
separate signed lock-admission boundary remain unresolved. Only after the
remaining facts are governed, the proposal is semantically accepted, and the
validation/admission boundaries are approved may the project consider a fresh
preflight. External signing, admission registration, canonical submission, and
lock creation remain later, separately authorised operations.
