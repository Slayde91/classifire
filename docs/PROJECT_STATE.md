# CLASSIFIRE Project State

**Verified snapshot:** 2026-08-30 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Verified shared-main tip:** `c8b06d17678b58f49f2ea816f3b12ba2e4af0095` (PR #79 merge)

**Verified application baseline:** `20cb72a14dd3b217cfac7670f047fdc385081990` (PR #74 merge), plus the human-session revocation hardening in `db404b3`; PR #79 adds the reviewed source-control recovery record without changing application code

**Merged Phase 8 scope:** representative rollback package and recovery, evidence-family and human-review validators, direct legacy-route test isolation, the durable visual-validation receipt registry/verifier, and controlled `site_observation` evidence intake

This record reflects committed shared-main code, the mixed legacy checkout, current tests, migration metadata, retained non-canonical execution receipts, the later local human-review v2 evidence, and refreshed GitHub state. Source, tests, Git, and execution evidence outrank older documentation.

Nothing in this document authorises inference, evidence retrieval, admission signing or registration, canonical submission, Physical Model Lock creation, deployment, or release.

## Audit update - 30 August 2026

This section supersedes earlier working-tree counts and next-action wording in
this document where they conflict. It is based on the live primary checkout,
its Git index, all visible isolated worktrees, current `origin/main`, current
open GitHub pull requests, current migration metadata, and focused checks.

### Verified repository reality

| Area | Status | Evidence and consequence |
| --- | --- | --- |
| Shared application | **Completed foundation / in progress overall** | `origin/main` is `c8b06d1`. It contains the PR #74 runtime baseline, PR #78 human-session revocation hardening, and PR #79's documentation-only recovery decision. Alembic reports the single head `0009_visual_validation_receipts`; 48 selected current-main tests pass. |
| Primary checkout | **Quarantined legacy evidence** | `gpt/phase8-linked-original-images` remains at `de0cc5a`, 378 commits ahead and 141 behind `origin/main`, with active cherry-pick `c3e4c81`, 46 unstaged tracked changes (`+1,668/-894`), 14 staged additions (`+3,183`), four unmerged files, and an incomplete untracked inventory because protected pytest directories cannot be read. PR #79 records the reviewed decision to retain current-main versions; it deliberately does not alter this checkout. |
| Report-assessment candidates | **In progress, overlapping, local only** | Three current-main-based worktrees implement overlapping concepts: `gpt/phase8-quote-review-run-20260829` adds `property_assessments` and proposal review; `gpt/field-inference-proposal-20260829` adds `field_assessments`; and `gpt/report-evidence-context-20260829` adds a much larger report intake, evidence, API, UI, and inference surface. Their selected focused suites passed during this audit, but none is a bounded reviewed commit and the competing assessment schemas are not reconciled. |
| Technical-intake candidate | **In progress, separately pushed then continued locally** | `gpt/technical-intake-draft-boundary-20260827` is pushed at `0edeaac` with `0018_shared_malware_containment`; its worktree now includes substantial uncommitted continuation, including proposed `0019_technical_intake_materializations`. Selected materialization and draft-persistence tests pass, but this is not shared-main implementation. |
| Current-main technical authority | **Basic prototype / not production-safe** | A Draft or In Review `TechnicalVariant` can be activated without enforced requester/decider separation, and current main has no `tests/test_technical*` coverage. Richer Draft/review/source-lineage controls exist only in candidates. |
| Snapshot and output identity | **Basic prototype / blocked** | `build_estimate_snapshot()` hashes a payload containing the current `generated_utc`, so reproducible snapshot identity is not proven, and no focused snapshot suite exists. Downstream validation, output, and Human Release remain blocked. |
| Production-hardening candidate | **Local-only candidate** | `gpt/production-boundary-post-pr78-20260827` contains local commit `a3de490` across 28 files and is one commit ahead and three behind current main. It is unpushed and requires current-main review and decomposition before publication. |
| Current-main production/runtime boundary | **Pre-production only** | Startup always runs `Base.metadata.create_all()` and administrator seeding; production findings are warning-only; signed initial submission defaults off; uploads are not scanned by current-main code; migrations are not packaged with the installed Python package; and no Docker/Compose deployment definition exists. |
| GitHub review surface | **Requires review** | PR #75 targets `main`; draft legacy PRs #9-#13 remain open on obsolete stacked lineage. Issues #42 and #43 remain open. Issue #42's latest site-visit-first wording is stale against the report-first evidence rule and needs a separate factual update. The branch-protection API returned a plan-limited 403, so no protection state is claimed. None of these items should be treated as complete or merged wholesale. |
| Continuous integration | **Not started on current main** | No `.github` workflow exists, `gh run list` is empty, and the open PRs have no status-check rollup. Local test evidence is useful, but GitHub mergeability is not CI evidence. |

PR #79 completed the isolated recovery decision: keep the accepted current-main
versions of the four conflicted paths and do not transplant `c3e4c81`. The root
itself remains intentionally untouched and unusable for publication. This audit
therefore uses a clean current-main worktree and does not adopt candidate code.

### Recommended Next Actions

#### Immediate next actions

1. **Reconcile one bounded report-only assessment contract on current main.**
   - **Objective:** choose one proposal-only representation for opening, service, substrate, quantity, size, and confidence assessments from the overlapping `property_assessments`, `field_assessments`, and report-context candidates.
   - **Why:** all three candidates have passing focused tests, but they duplicate schemas and change overlapping validators, prompts, runners, and tests. Publishing one wholesale would create competing domain contracts.
   - **Scope:** start with `phase8_property_assessments.py`, `phase8_proposal_review.py`, the bounded parts of `phase8_visual_proposal.py`, `phase8_visual_prompts.py`, and `visual_validation.py`, plus their focused tests. Preserve bundle quantity separately from cable count; always assess cable count, using null plus Unknown when it is not defensible and requiring a small/medium/large bundle class then; keep cable trays distinct with estimated tray dimensions.
   - **Dependencies/blockers:** compare all three candidates from a clean `c8b06d1` worktree; decide the single field name/schema and proposal-policy version/legacy-receipt compatibility rule; exclude report ingestion, UI, canonical writes, technical selection, and commercial logic from the first slice.
   - **Completion criteria:** one reviewable current-main branch; one assessment schema with units/ranges and credible alternatives; explicit Confirmed/Approximate/Inferred/Unknown states with confidence, reasoning, and evidence; proposal bytes/hash and every evidence reference independently verified against the allowed manifest; no canonical-state interface; and no unrelated candidate changes.
   - **Validation:** fail-closed tests for tampered proposal hashes and out-of-manifest references; compatibility fixtures for historical receipt policy versions; property/proposal-review, visual-proposal, human-reference, linked-run, OpenResponses, representative-run, evidence, and runtime tests; Ruff on changed Python; `git diff --check`; inspect a rendered per-defect review record.
   - **Uncertainty:** the repository does not yet establish whether `field_assessments` or `property_assessments` is the durable public name. It also does not decide how v1 historical receipts remain verifiable after the candidate policy changes. Resolve both before publication.

#### Near-term actions

2. **Reconcile the shared-byte malware containment boundary required by report intake.**
   - **Why:** the local report reader checks scan state and hash before parsing, but it does not prove those checks and the bytes read are one atomic operation. The pushed `0018_shared_malware_containment` candidate addresses the same shared-file boundary and must be reviewed as a narrow dependency, not merged wholesale.
   - **Done when:** clean-to-FOUND transitions quarantine every row sharing the bytes, accepted rows cannot drift to unsafe content, download/preview/read races fail closed, and disposable two-session PostgreSQL tests pass.
3. **Extract project-owned report storage and deterministic package preparation.**
   - **Why:** `gpt/report-evidence-context-20260829` contains useful stored-report, register, measurement, evidence-draft, API, UI, and package-preparation work, but its 14,000-plus-line uncommitted diff is not a safe review unit. Its current reader uses `technical_evidence` for project reports, accepts arbitrary stored-file IDs under `project:read`, and has no StoredFile project/estimate ownership binding.
   - **Done when:** stored reports use the agreed `project_evidence` purpose; every file/package is bound to a project or estimate; cross-project read tests fail; immutable storage/provenance and deterministic package preparation are separate, small current-main slices; and report-derived facts remain Draft/proposal evidence.
4. **Continue Draft technical normalization/materialization separately.**
   - **Why:** pushed `0018` containment work and local proposed `0019_technical_intake_materializations` have different review, schema, and migration boundaries.
   - **Done when:** the materialization slice has one migration path, Draft evidence cannot silently activate a `TechnicalVariant`, and focused persistence/migration tests pass.
5. **Review the local production-hardening commit on current main.**
   - **Why:** `a3de490` is security-relevant but unpushed, broad, and three main commits behind.
   - **Done when:** its 28-file diff is decomposed or justified; production startup does not depend on unconditional `create_all`/seed behaviour; migrations are available from the installed package; production findings and admission-bound initial-submission defaults fail closed as approved; current-main startup/schema/security tests pass; and no unrelated output/UI changes are included.
6. **Independently rebase, transplant, or supersede PR #75.**
   - **Done when:** its actual current-main diff, evidence bindings, output safety, and tests are reviewed; GitHub mergeability alone is not acceptance evidence.
7. **Add a minimal, secret-free pull-request validation workflow.**
   - **Why:** current main has no GitHub workflow or recorded status checks.
   - **Done when:** a supported Python environment runs the agreed Pytest policy, Ruff, and the Alembic one-head check; a deliberately failing change produces a failed check; and a passing branch records reproducible checks without customer evidence or secrets.

#### Later or dependency-bound actions

8. **Run a fresh controlled report-only review only after the bounded assessment and package contracts are published and separate run authority exists.** Use all retained report evidence before asking for site confirmation; keep technical compatibility, pricing, canonicalisation, and release unresolved.
9. **Advance canonical Physical UAT and the signed Physical Model Lock boundary only after evidence resolution and semantic approval.** Phases 9-14 remain blocked until that lock exists; signing, registration, write, lock, deployment, and release each require their own authority.
10. **Make snapshot identity deterministic when Phase 12 becomes eligible.** Exclude volatile generation time from the semantic identity or define an explicit two-hash contract, add snapshot/output regression tests, and keep Human Release bound to the exact validated snapshot and rendered outputs.

## 1. Repository and Git position

The shared application baseline reconciled here is
`20cb72a14dd3b217cfac7670f047fdc385081990`, the merge of PR #74.
PR #78 added human-session revocation hardening and documentation-only PR #79
advanced `origin/main` to `c8b06d1` without changing the application
workflow. Verify the live branch tip directly whenever publication state
matters. The application baseline includes the
earlier representative-run/recovery package, evidence-family and human-review
validators, the direct legacy-route test isolation, and the durable
visual-validation receipt registry and verifier. It also includes the strict
`site_observation` evidence-intake contract at the existing
evidence-registration boundary.

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

The verified application baseline at `20cb72a` contains:

- the FastAPI, CLI, SQLAlchemy, Alembic, storage, audit, security, UI, import, release-pinning, calculation, snapshot, PDF/XLSX, and Mission Control foundations;
- the canonical Defect, EvidenceSource, Opening, Service, Opening-Service link, Physical Model Lock, admission, and submission-receipt records;
- migration head `0009_visual_validation_receipts`, following `0008_retire_legacy_initial_submissions`;
- component-level protected-state fingerprinting and fail-closed admission-bound initial canonicalisation;
- immutable admission registration, P-256 verification, single-use submission, idempotent receipts, and an explicit no-lock submission boundary;
- bounded visual correction, proposal-blind inventory, mandatory reconciliation, strict proposal receipts, retained-evidence adaptation, guarded no-tool transport, managed runtime composition, and dedicated Phase 8 identities;
- guarded linked-original discovery, verification, retention, and the bounded linked-original-to-proposal runner;
- a strict `site_observation` evidence-intake contract requiring one bound
  Defect, immutable admissible source evidence, per-fact locators, explicit
  uncertainty and limitations, and an audit-bound canonical payload digest;
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
| 6 | In progress and evidence-limited: a local human-adjudicated proposal records the visible 5/6/6 topology for one Defect, but report-package assessment and unresolved facts remain incomplete and no accepted canonical model exists |
| 7 | In progress: representative safety/rollback and limited human review are proven; the durable receipt registry and verifier are merged, but signed lock enforcement is not implemented |
| 8 | In progress and blocked on controlled report-package evidence resolution or essential governed confirmation, semantic acceptance, and separate canonical/lock authority; no canonical model or replacement Physical Model Lock exists |
| 8C | Planned; only charter/taxonomy/rights preparation is allowed before its admission gates |
| 9-14 | Basic current-main foundations and richer legacy-only foundations exist; operationally blocked and not architecture-complete |
| 15 | In progress: security, recovery, scale, monitoring, and release hardening remain |
| 16 | Deferred: structural steel and complete fire-rated duct runs require separate design and evidence |

## 5. Verification for this reconciliation

Historical verification evidence for the PR #74 application-baseline tree:

- reviewed PR #74 head `9f5dacacadfab02d6c9aaf8ac0add43c5eedfff8`
  and merge commit `20cb72a14dd3b217cfac7670f047fdc385081990`
  have identical tree hash `6182cf5e3b3d577c9cc0622bf472b42b9e320b1f`;
- complete repository suite: **380 passed** with Python 3.12.10 and Pytest 8.4.2;
- focused evidence-file boundary suite: **14 passed**;
- Ruff on the changed API and test, Mypy on the changed API, Alembic one-head
  check (`0009_visual_validation_receipts`), and `git diff --check` passed;
- GitHub reported no status-check rollup for PR #74, so no CI result is claimed;
  and
- whole-repository Ruff and Mypy were not rerun for PR #74. Previously recorded
  inherited findings outside the changed paths have not been revalidated on
  current main.

Current audit verification on shared-main tip `c8b06d1`:

- Alembic reports one head: `0009_visual_validation_receipts`;
- **48 selected current-main tests passed** across human-session security,
  evidence-family review, human-adjudicated proposal, visual evidence, and the
  linked visual runner; and
- no current full-suite, whole-repository Ruff, Mypy, Bandit, deployment, or
  real-report execution result is claimed by this reconciliation.

The retained offline recovery v8 remains historical, successful hash-binding
evidence for its own source fingerprint. PR #74's controlled `site_observation`
evidence-intake contract is now on shared main. It requires an immutable
admissible technical-evidence file, one bound Defect, capture/governance
provenance, a per-fact evidence locator, explicit uncertainty, and an audit
payload digest before the existing endpoint can retain the evidence.

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

The merged site-observation contract adds no database table, no new writer, and
no live evidence. It validates a narrow payload at the existing
evidence-registration boundary. Merging it did not register evidence or grant
canonical-write, lock, deployment, or release authority.

## 7. Current blockers and next valid task

The retained 7+4 human review is complete and must not be repeated. The next
engineering task is Action 1 above: reconcile one bounded, proposal-only report
assessment contract on current main. Until that contract and the later
project-owned/contained package boundary are published, another real-report run
would test overlapping local designs rather than an accepted CLASSIFIRE path.

After those prerequisites and separate run authority exist, the next
physical-evidence action is controlled report-package assessment using all
retained report text, photographs, drawings, and context. Request a site visit
or equivalent newly governed evidence only when the package cannot support a
defensible estimate or confirmation is essential for a later governed decision.

Do not rerun unchanged inference or convert the limited 5/6/6 record into
canonical truth. The durable visual-validation receipt registry and exact
no-write verifier are now shared-main safeguards, but semantic acceptance and a
separate signed lock-admission boundary remain unresolved. Only after the
remaining facts are governed, the proposal is semantically accepted, and the
validation/admission boundaries are approved may the project consider a fresh
preflight. External signing, admission registration, canonical submission, and
lock creation remain later, separately authorised operations.
