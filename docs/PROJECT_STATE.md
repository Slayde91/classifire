# CLASSIFIRE Project State

**Verified snapshot:** 2026-08-31 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Verified shared-main code baseline:** PR #93 (`143c5b5`) makes every new
technical-library import Draft-only evidence, regardless of a source row's
claimed activity. It builds on PR #91's activation-time source-integrity check,
PR #83's approval separation, PRs #86 and #88's document-review safeguards,
and PR #90's cross-purpose file-reuse rejection. Fetch `origin/main` before any
publication-sensitive decision.

**Verified application baseline:** `20cb72a14dd3b217cfac7670f047fdc385081990` (PR #74 merge), plus human-session revocation hardening in `db404b3`, the PR #79 recovery record, PR #80's merged `efd4641` Phase 8 assessment/review contract, PR #81's merged report-evidence adapter/startup hardening, PR #82's migration packaging and production schema-readiness boundary, PR #83's browser, diagnostics, containment-test, and technical-activation safeguards, and PRs #86, #88, #90, #91, and #93's technical-source integrity safeguards

**Merged Phase 8 scope:** representative rollback package and recovery, evidence-family and human-review validators, direct legacy-route test isolation, the durable visual-validation receipt registry/verifier, controlled `site_observation` evidence intake, the bounded v2 assessment/review contract, project-owned report evidence with deterministic per-Defect reviews, narrow fail-closed production startup, packaged-migration/CLI schema-readiness safeguards, and technical-activation requester/decider separation

**Merged report-evidence scope:** PR #81 merged contained report ownership, exact clean-byte reads, stable locators, deterministic report review packages, and a separately guarded report-assessment transport/runtime. These remain proposal-only shared-main source, not live-report or canonical implementation.

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
| Report-only assessment contract | **Completed branch candidate / not shared main** | `gpt/phase8-assessment-contract-20260830` selects one `property_assessments` v2 contract, retains historical v1 verification, binds every assessed claim to the allowed evidence manifest, and produces hash-bound JSON plus inert Markdown review files. The exact candidate passed the complete 435-test suite and all changed-file checks. |
| Report-package evidence adapter | **Not implemented on this branch** | The broad `gpt/report-evidence-context-20260829` worktree contains useful but overlapping storage/API/UI/package work. No accepted path yet combines report text, tables, captions, drawings, annotations, metadata, and governed images into one report-SHA-bound packet and exactly one review result per report-labelled Defect. |
| Technical-intake candidate | **In progress, separately pushed then continued locally** | `gpt/technical-intake-draft-boundary-20260827` is pushed at `0edeaac` with `0018_shared_malware_containment`; its worktree now includes substantial uncommitted continuation, including proposed `0019_technical_intake_materializations`. Selected materialization and draft-persistence tests pass, but this is not shared-main implementation. |
| Current-main technical authority | **Basic prototype / not production-safe** | A Draft or In Review `TechnicalVariant` can be activated without enforced requester/decider separation, and current main has no `tests/test_technical*` coverage. Richer Draft/review/source-lineage controls exist only in candidates. |
| Snapshot and output identity | **Basic prototype / blocked** | `build_estimate_snapshot()` hashes a payload containing the current `generated_utc`, so reproducible snapshot identity is not proven, and no focused snapshot suite exists. Downstream validation, output, and Human Release remain blocked. |
| Production-hardening candidate | **Local-only candidate** | `gpt/production-boundary-post-pr78-20260827` contains local commit `a3de490` across 28 files and is one commit ahead and three behind current main. It is unpushed and requires current-main review and decomposition before publication. |
| Current-main production/runtime boundary | **Pre-production only** | Startup always runs `Base.metadata.create_all()` and administrator seeding; production findings are warning-only; signed initial submission defaults off; uploads are not scanned by current-main code; migrations are not packaged with the installed Python package; and no Docker/Compose deployment definition exists. |
| GitHub review surface | **Requires review** | PR #75 targets `main`; draft legacy PRs #9-#13 remain open on obsolete stacked lineage. Issues #42 and #43 remain open. Issue #42's latest site-visit-first wording is stale against the report-first evidence rule and needs a separate factual update. The branch-protection API returned a plan-limited 403, so no protection state is claimed. None of these items should be treated as complete or merged wholesale. |
| Continuous integration | **Not started on current main** | No `.github` workflow exists, `gh run list` is empty, and the open PRs have no status-check rollup. Local test evidence is useful, but GitHub mergeability is not CI evidence. |

### Later same-day publication and adapter update

This later update supersedes the present-tense shared-main, assessment-contract,
report-adapter, and CI statements above. The earlier rows remain a record of the
pre-PR #80 audit, not the current repository state.

| Area | Verified current position | Remaining limit |
| --- | --- | --- |
| Shared main | PR #83 merged the current browser, diagnostic, containment-test, and technical-activation safeguards at `ac7de2c`; PR #84 reconciled their status documentation. PRs #86, #88, and #90 then narrowed the technical-source review and reuse boundary; PR #91 (`cf12ed5`) rechecks that source immediately before linked-variant activation; and PR #93 (`143c5b5`) makes new technical imports Draft-only and runtime-ineligible. It also contains PR #80's bounded v2 assessment/review contract, PR #81's project-owned report-evidence adapter/startup guard and PostgreSQL CI service, and PR #82's packaged migrations plus production schema-readiness boundary. Alembic has the single `0011_report_evidence_locators` head. | The merges are source publication only; they do not approve a live report run or canonical state change. |
| GitHub validation | The `CLASSIFIRE pull request validation` workflow completed successfully for PR #81's final head `4ebc531`, PR #82's final head `9ad6ca7`, PR #83's final head `70f8df5`, PR #84's final head `828076c`, PR #91's final head `3777dea`, and PR #93's final head `7b63a9f`. PR #83 completed in 2m13s after focused/local full-suite validation; PRs #84 and #91 completed in 1m37s; PR #93 completed in 1m59s. | The configured disposable PostgreSQL URL enabled the shared-byte quarantine/read race. CI evidence is not deployment or live-report evidence. |
| Report-evidence adapter | PR #81 merged the contained-byte quarantine/read code, Project/Estimate ownership, report-SHA locators/scopes, deterministic per-Defect review packaging, report-bound prompts/receipts, and managed no-tool runtime into shared main. | No real report, OpenClaw, or provider run was made. A controlled report-only assessment still requires separate authority. |
| Production startup boundary | Shared main refuses unsafe production settings before filesystem, schema, or seed work. Valid production startup creates storage only after configuration and packaged-migration readiness validation; it never creates schema or a default administrator. | Live deployment proof and the remaining broad `a3de490` changes remain outside this merge. |
| Installed migration packaging and CLI bootstrap boundary | PR #82 packages immutable Alembic history in `classifire.migrations`, exposes explicit `classifire-migrate` head upgrades, preserves protected preflight/audit hashes, and makes production CLI setup/import commands fail before schema creation or default seeding. Before production storage setup or a database-writing CLI command proceeds, the configured database must prove it is exactly at the packaged Alembic head. | No production, UAT, or customer database was upgraded. |
| Production browser configuration and diagnostics | Shared main (PR #83): documented CSV/JSON `trusted_hosts` and `allowed_origins` inputs parse deterministically; production rejects empty, wildcard, non-canonical, non-HTTPS, or host-mismatched browser settings before storage work; and `doctor` withholds database connection details. | This is limited pre-production hardening, not deployment or production proof. |
| Technical activation separation | Shared main (PR #83): a technical variant now reaches `active` only from `in_review`, with a pending activation request, a different deciding user, and an approved linked technical document where one exists. PR #91 rechecks that linked document's retained source bytes are clean, immutable, and unchanged immediately before activation. | This is a fail-closed guard around the existing UI workflow, not full Draft technical-intake/source-lineage governance or production proof. |
| Technical-document review separation | Shared main (PRs #86 and #88): a Draft or Rejected technical source document must be submitted for review, then receive a pending-review decision from a different user before approval. Its retained source bytes must be clean, immutable, and unchanged at submission and approval. | This reuses the existing Approval record without a migration. It is not full source-lineage governance or production proof. |
| Technical-library import boundary | Shared main (PR #93): imported technical rows, even if the source calls them active, become Draft candidates with retained source flags, a source hash, and runtime exclusion. Source/version and variant-content collisions fail without overwriting existing data. | Existing active imports are left unchanged, while the broader Draft intake, source lineage, approval, and release-publication model remains incomplete. |

**Current next action:** obtain separate authority for one controlled,
proposal-only report assessment and human-review every resulting artifact. That
authority must not be used for technical selection, pricing, canonical writes,
locking, deployment, or release.

PR #79 completed the isolated recovery decision: keep the accepted current-main
versions of the four conflicted paths and do not transplant `c3e4c81`. The root
itself remains intentionally untouched and unusable for publication. This
reconciliation selectively adopts only the bounded, tested assessment-contract
slice in the isolated current-main worktree; it does not adopt the overlapping
report-context, technical-intake continuation, production-hardening, or root
changes.

### Historical pre-PR #80 recommended actions

#### Immediate next actions

**Publication prerequisite (Priority 0):** independently review the exact
`gpt/phase8-assessment-contract-20260830` diff and merge it only if accepted.
If review finds a defect, correct or supersede this branch first. Do not build
the adapter against an unaccepted or competing assessment schema. This is a
repository gate, not a separate product feature.

1. **Build the contained, project-owned, report-SHA-bound evidence adapter and deterministic per-defect review flow.**
   - **Objective:** combine all controlled report evidence into one immutable package and produce exactly one proposal-only review artifact for every report-labelled Defect.
   - **Why:** the branch candidate now defines how opening, service, substrate, size, quantity, confidence, and evidence claims must be represented, but it still receives an image-oriented manifest. It does not ingest report text, tables, captions, drawings, annotations, or general metadata, and retrieval-blocked Defects currently receive no proposal-review file.
   - **Ordered scope:** first make scan-state/hash validation atomic with the bytes read or served and quarantine all rows sharing unsafe bytes; then bind every report file/package to its Project or Estimate using the agreed `project_evidence` purpose; then create stable report/page/item locators and feed documentary plus visual evidence into the existing v2 assessment boundary; finally emit a safe result for successful, insufficient-evidence, malformed, and retrieval-blocked Defects.
   - **Dependencies/blockers:** review the narrow `0018_shared_malware_containment` candidate without taking its dirty continuation wholesale; decide the StoredFile ownership/migration contract; keep API/UI expansion, technical selection, pricing, canonical writes, locks, and release out of this slice.
   - **Completion criteria:** the approved report hash and selected Defect range are package-bound; cross-project reads fail; every Defect label has exactly one deterministic review; each claim has a stable evidence locator and Confirmed/Approximate/Inferred/Unknown status; cable bundles and cable trays retain the v2 semantics; each review binds its report/package, manifest, prompt/runtime profile, proposal, and controller receipt, while the later completion receipt hashes every preceding emitted artifact; protected state remains unchanged.
   - **Validation:** disposable two-session PostgreSQL quarantine/read-race tests; cross-project ownership tests; documentary/visual locator and report-hash tamper tests; per-Defect cardinality tests including retrieval-blocked and evidence-insufficient cases; focused and full suites; Ruff, Mypy, Bandit, Alembic one-head, `git diff --check`; and inspection of representative review files.
   - **Uncertainty:** the accepted ownership schema and exact documentary-evidence record shape are not yet on shared main. Resolve them through the smallest new migration and service boundary rather than adopting the broad report-context worktree wholesale.

#### Near-term actions

2. **Run a fresh controlled report-only review after Action 1 and separate run authority.**
   - **Done when:** the approved Quote/report hash and Defect range produce one review file per label, a human reviews the proposal-only results, and technical compatibility, pricing, canonicalisation, locking, and release remain unresolved.
3. **Continue Draft technical normalization/materialization separately.**
   - **Why:** pushed `0018` containment work and local proposed `0019_technical_intake_materializations` have different review, schema, and migration boundaries.
   - **Done when:** the materialization slice has one migration path, Draft evidence cannot silently activate a `TechnicalVariant`, and focused persistence/migration tests pass.
4. **Review the local production-hardening commit on current main.**
   - **Why:** `a3de490` is security-relevant but unpushed, broad, and three main commits behind.
   - **Done when:** its 28-file diff is decomposed or justified; production startup does not depend on unconditional `create_all`/seed behaviour; migrations are available from the installed package; production findings and admission-bound initial-submission defaults fail closed as approved; current-main startup/schema/security tests pass; and no unrelated output/UI changes are included.
5. **Independently rebase, transplant, or supersede PR #75.**
   - **Done when:** its actual current-main diff, evidence bindings, output safety, and tests are reviewed; GitHub mergeability alone is not acceptance evidence.
6. **Add a minimal, secret-free pull-request validation workflow.**
   - **Why:** current main has no GitHub workflow or recorded status checks.
   - **Done when:** a supported Python environment runs the agreed Pytest policy, Ruff, and the Alembic one-head check; a deliberately failing change produces a failed check; and a passing branch records reproducible checks without customer evidence or secrets.

#### Later or dependency-bound actions

7. **Advance canonical Physical UAT and the signed Physical Model Lock boundary only after evidence resolution and semantic approval.** Phases 9-14 remain blocked until that lock exists; signing, registration, write, lock, deployment, and release each require their own authority.
8. **Make snapshot identity deterministic when Phase 12 becomes eligible.** Exclude volatile generation time from the semantic identity or define an explicit two-hash contract, add snapshot/output regression tests, and keep Human Release bound to the exact validated snapshot and rendered outputs.

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

### 2.4 Completed on the pre-PR #80 branch candidate

The isolated `gpt/phase8-assessment-contract-20260830` candidate is based
exactly on `c8b06d1` and adds one bounded proposal-only contract:

- `CLASSIFIRE-PHASE8-PROPERTY-ASSESSMENTS-v2` requires field-level
  Confirmed, Approximate, Inferred, or Unknown status, confidence where
  applicable, reasoning, allowed-manifest evidence references, credible
  alternatives, and optional additional-evidence requests;
- opening, service, and substrate properties are assessed independently, with
  bounded measurement values/ranges and no undeclared technical or commercial
  fields;
- bundle quantity, individual cable count, bundle size class, and cable-tray
  dimensions are distinct, so a tray cannot be relabelled as a bundle;
- fresh controller requests and receipts use the v2 policy/schema while
  historical paired v1 policy/receipt records remain verifiable;
- proposal, evidence-manifest, prompt, runtime-profile, recovery, and human
  adjudication bindings fail closed on mutation, relabelling, missing manifests,
  or out-of-manifest references;
- the runner writes hash-bound `proposal-review.json` and inert
  `proposal-review.md` artifacts for a visual result; and
- no service in this slice can select a technical system, price work, submit
  canonical data, create a lock, deploy, or release.

This is complete for the bounded contract and suitable for branch review. It is
not yet shared-main implementation, a report-document ingestion path, a
report-wide batch processor, or proof from a fresh real-report run.

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
| 5 | In progress: one approved report/source path demonstrated full-report linked-original resolution and the branch candidate defines manifest-bound property claims; documentary report evidence, project ownership, containment, other formats/hosts, and multi-report proof remain |
| 6 | In progress: the branch candidate completes the bounded v2 assessment/review representation, but no accepted canonical model or report-wide per-Defect flow exists |
| 7 | In progress: representative safety/rollback and limited human review are proven; the branch candidate strengthens assessment and review receipts, while signed lock enforcement remains unimplemented |
| 8 | In progress and blocked on contained report-package evidence resolution, report-wide semantic review, and separate canonical/lock authority; it is not blocked on a mandatory site visit |
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
- no current shared-main full-suite, deployment, or real-report execution result
  is claimed by this reconciliation.

Current verification for the exact uncommitted branch candidate:

- complete repository suite: **435 passed, 139 warnings** in 112.77 seconds;
- Ruff passed across all 24 changed/new implementation and test files;
- Mypy and Python syntax compilation passed across the 13 changed production
  and script files;
- Bandit completed with no finding (only suppression-annotation warnings);
- Alembic reports the unchanged single head
  `0009_visual_validation_receipts`;
- `git diff --check`, the credential-pattern scan, and both independent
  architecture and policy audits passed; and
- a representative rendered review was inspected and contained every
  opening/service assessment, evidence reasoning, proposal-only warning, and no
  validator error.

The retained offline recovery v8 remains historical, successful hash-binding
evidence for its own source fingerprint. PR #74's controlled `site_observation`
evidence-intake contract is now on shared main. It requires an immutable
admissible technical-evidence file, one bound Defect, capture/governance
provenance, a per-fact evidence locator, explicit uncertainty, and an audit
payload digest before the existing endpoint can retain the evidence.

No real report or OpenClaw model call was run for this reconciliation or branch
candidate. No admission was created, signed, or registered; no canonical model
was submitted; no lock, deployment, or release occurred.

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

The retained 7+4 human review is complete and must not be repeated. The bounded
assessment contract is also complete on this branch for its stated scope. The
next engineering task is Action 1 above: connect that contract to contained,
project-owned, report-SHA-bound documentary and visual evidence and guarantee one
safe review result per report-labelled Defect.

After that dependency and separate run authority exist, run the controlled
report-package assessment using all retained report text, photographs, tables,
captions, drawings, annotations, metadata, and context. Request a site visit or
equivalent newly governed evidence only when those sources cannot support a
defensible estimate or confirmation is essential for a later governed decision.

Do not rerun unchanged inference or convert the limited 5/6/6 record into
canonical truth. The durable visual-validation receipt registry and exact
no-write verifier are now shared-main safeguards, but semantic acceptance and a
separate signed lock-admission boundary remain unresolved. Only after the
remaining facts are governed, the proposal is semantically accepted, and the
validation/admission boundaries are approved may the project consider a fresh
preflight. External signing, admission registration, canonical submission, and
lock creation remain later, separately authorised operations.
