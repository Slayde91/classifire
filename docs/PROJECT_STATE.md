# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-03 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Verified shared-main implementation:** 7a33f3477086942d1a09991f22bf559d215a1ea5 (merge of PR #154, 2026-09-03)

This snapshot reconciles executable source, tests, migrations, Git/GitHub state,
the quarantined legacy checkout, and retained non-canonical receipts. Those
sources outrank older handoffs and roadmap prose.

Nothing in this document authorises report retrieval or inference, admission
signing or registration, canonical submission, Physical Model Lock creation,
deployment, technical approval, commercial approval, or Human Release.

## 1. Repository and publication state

| Area | Verified state | Consequence |
| --- | --- | --- |
| Shared main | PR #154 is merged at 7a33f3477086942d1a09991f22bf559d215a1ea5; it includes the reviewed PR #104-#154 lineage. | Report governance, technical-source safeguards, retained proposal-review packages, scoped reader access, exact-approved-manifest enforcement, source-bound captions, and bounded XLSX worksheet/cell locators are shared-main evidence. These changes add no technical, commercial, canonical, lock, deployment, or release authority. |
| Report-governance range | PR #104 contains six reviewed commits: `b36ebb5`, `9a4c2d2`, `e9ac8f0`, `4cba603`, `58c5946`, and `0f6c252`. | Expected-label approval, atomic scope admission, main-push CI, factual docs, and migration-head readiness are integrated together. |
| Pull-request and post-merge CI | PR #104 run `33515411987` passed on `0f6c252`; `main` push run `33516292114` passed on merge `b6409a5`. | The exact candidate and its shared-main merge both passed hosted Python validation, including tests and one Alembic head. |
| Post-PR #104 maintenance series | PRs #105-#126 merged as `6ecd0a6`, `513c9e1`, `d88bd1f`, `6391579`, `a16e246`, `75e6145`, `dc1e4c6`, `c7c9fc9`, `c9aa917`, `14c2269`, `3860b23`, `efff4d9`, `ecd7213`, `14ed594`, `bd3e7ee`, `7167f9e`, `73a9d43`, `5639e26`, `90f701c`, `ff1278f`, `7e26c2f`, and `b33246a`. | Documentation, semantic snapshot identity, technical-source lineage, Draft materialisation, type safety, UTC PDF timestamps, current output/browser branding, Mission Control task-response validation, hosted full-Ruff/Mypy/Bandit validation, and explicit Phase 8 invariant errors were strengthened without granting technical, commercial, lock, or release authority. |
| Current technical-source safeguards | PRs #127-#142 merged as `e5a607d`, `e1c2297`, `4bc9c8e`, `2a7d4a9`, `45e07f4`, `f9c0d82`, `c54065a`, `f9dea2a`, `f3c6d92`, `8c21f18`, `9771ff7`, `1e43756`, `caed547`, `075c9c5`, `981324e`, and `abe8bde`. | Verified-byte extraction, current-authority gates, immutable published source-lineage binding, factual reconciliation, structured release-lineage display, safe navigation to bound source-document records, and read-only revision-source visibility were added without granting technical selection, commercial, canonical, lock, or release authority. |
| Subsequent hosted validation | Each PR #105-#154 check and each corresponding main push run passed; the latest is run 33760450512 on 7a33f34. | Hosted validation is current through the PR #154 merge, while required-check configuration remains unverified. |
| Default-branch governance | Commit `e9ac8f0` now validates pushes to `main`, and its first observed run passed. GitHub's branch-protection API still returns HTTP 403 because this private repository needs GitHub Pro or public visibility for that feature. | Hosted validation is evidenced, but required-check configuration is still not independently inspectable. |
| Open pull requests | Draft PRs #9-#13 remain open on obsolete feature-to-feature bases, have no checks, and are materially diverged from `main`. | Treat them as quarantined legacy candidates, not current-main merge candidates. |
| Issues | Issues #42 and #43 remain open. | Their descriptions may be historical; implementation evidence still wins. |

### Quarantined root checkout

The root checkout at `C:\CLASSIFIRE` remains recovery evidence on
`gpt/phase8-linked-original-images` at `de0cc5a`. It still has an interrupted
cherry-pick, unmerged paths, tracked changes, and an incomplete untracked
inventory because protected pytest directories cannot be read. Its exact dirty
inventory is deliberately not treated as current implementation evidence.

The root contains substantial unfinished Phase 8, plugin, script, UI, and test
work. Its conflicted state makes it unsuitable for this commit, publication,
deployment, or canonical operations. None of it was edited, resolved, staged,
or copied into the isolated worktree.

## 2. Current implementation

### Completed foundations on shared main

The following boundaries are implemented and tested for their stated scope:

- FastAPI, CLI, SQLAlchemy, packaged Alembic migrations, development UI, audit,
  and role/session security foundations.
- The current `Defect -> EvidenceSource -> Opening -> Service/link` physical
  model, explicit blank-opening semantics, protected-state fingerprints,
  admission registration, one-shot initial submission, and separate lock
  creation.
- Proposal-only blind inventory, Physical proposal, Validator review, bounded
  correction, evidence review, human adjudication, and durable visual-validation
  receipt contracts.
- Project/Estimate-owned retained report evidence, exact clean-byte reads,
  cross-project rejection, shared-byte quarantine, stable PDF locators including strict
  explicitly numbered caption locators, plus bounded source-bound XLSX worksheet/cell
  locators, ordered report scopes, deterministic review packages, and no-write
  report-assessment components.
- Production configuration checks before filesystem work, no production
  `create_all()` or default-administrator seeding, packaged migration history,
  an explicit migration command, and exact migration-head readiness checks.
- Technical-document review separation, clean source-byte rechecks, current
  approved/unexpired source-document and clean, immutable `technical_evidence`
  stored-file metadata at current-authority gates, technical-variant
  effective/expiry windows, verified-byte candidate metadata extraction and
  Draft-only metadata refresh after a clean source recheck, Draft-only imports,
  source-document-bound Draft variants, source-preserving revisions, nonblank
  source locators before review, source-bound manual Draft materialisation,
  hash-bound Draft source-document predecessor lineage without automatic retirement,
  independent activation, active immutable technical-release requirements,
  release-manifest eligibility and published source-lineage rechecks, and
  read-only current-authority displays
  on linked TechnicalVariant and TechnicalDocument detail screens, plus a
  structured immutable source-lineage view on TechnicalRelease detail screens.
  Technical extraction failures retain only content-safe diagnostics.
- Governed assumption-led desk-quote PDF/XLSX outputs from PR #75. They remain
  explicitly non-technical, proposal-only commercial scenarios. The current
  shared-main resolver requires Project/Estimate-owned immutable `clean` ProjectEvidence,
  exact atomic retained-byte reads, persisted locators, and artifact-byte audit
  bindings; `technical_evidence` remains rejected. PR #103's checks passed;
  operational approval remains separate.
- PDF timestamps use a timezone-aware UTC clock, and the current browser UI and
  generated PDF/XLSX artifacts use CLASSIFIRE display branding. Legacy persisted
  identifiers and static logo paths remain only where compatibility requires them.
- A secret-free pull-request workflow using Node 24-compatible actions and a
  disposable PostgreSQL 16 service.

Shared main packages migrations through 0017_xlsx_report_evidence_locators. It has one head: 0017_xlsx_report_evidence_locators (legacy_adjudicated_lineage). PR #154 merged source-bound XLSX worksheet/cell locators as 7a33f3477086942d1a09991f22bf559d215a1ea5. PR #154 pull-request run 33760112145 and post-merge main run 33760450512 both succeeded.

### Completed report-governance integration on shared main (PR #104)

- `b36ebb5` introduces an immutable, human-approved expected-label manifest
  bound to retained report bytes and an estimate
  (`0012_report_expected_label_manifests`).
- `9a4c2d2` admits a complete exact approved label set atomically, retains that
  manifest on every new report scope, and prevents V1/unbound scope packets from
  reaching a proposal run (`0013_report_defect_scope_admissions`). Historical
  V1 receipts remain verifiable.
- `e9ac8f0` adds the GitHub Actions `push` validation path for merged `main`
  changes. Changed-file Ruff remains a fast delta check; full-repository Ruff,
  Mypy, and Bandit are separately run for every pull request and `main` push.
- `58c5946` and `0f6c252` align migration-head expectations and deployment
  readiness with `0013`; `4cba603` reconciles the preceding factual records.

### Completed proposal-review controller admission transition on shared main (PR #149)

PR #149 requires the database-backed proposal-review controller to receive the
exact human-approved expected-label manifest. Before it builds a new package, it
checks every selected scope packet is V2 and carries that same manifest ID,
hash, and approval reference. A legacy/unbound scope, or a scope bound to a
different approval record, fails before package assembly. Historical V1 packets
remain verifiable; PR #149 does not rewrite or delete them.

PR #149 passed pull-request validation run 33749820103 and post-merge main run
33750096567. It remains proposal-only and adds no report retrieval, provider
call, canonical submission, technical selection, commercial pricing, Physical
Model Lock, deployment, or Human Release authority.

### Completed source-bound report captions on shared main (PR #151)

PR #151 recognises only an explicitly numbered `Figure`, `Fig`, `Image`,
`Photo`, `Photograph`, or `Plate` text block as a caption. Its persisted locator
contains only the fixed caption category, page, bounds, block index, character
count, sequence, and content hash. The caption wording is re-extracted only in
transient documentary context after the exact retained PDF reproduces that
locator and hash. Ambiguous prose, unrecognised categories, and locators with
raw caption text are refused.

It does not associate a caption with an image, infer physical facts, select a
technical system, price work, call a provider, create canonical state or a lock,
deploy, or release. PR validation run 33753130859 and post-merge main run
33753516838 passed.

### Completed source-bound XLSX report locators on shared main (PR #154)

PR #154 admits only exact retained `.xlsx` bytes into the existing report locator
boundary. It persists visible worksheet shape and non-empty cell positions, fixed
cell categories, and hashes--never worksheet names or cell values. A selected cell
is re-extracted only transiently after the exact workbook reproduces its locator and
hash. Formula text is not executed. Hidden sheets, macros, external links,
drawings/media/charts, comments, pivots, embedded objects, validation rules, and
out-of-policy archive or worksheet shapes fail closed. The forward-only
`0017_xlsx_report_evidence_locators` migration admits only `worksheet` and `cell`
locator kinds.

This remains proposal-only. It adds no report runner route, provider call, canonical
physical-model write, technical selection, commercial pricing, lock, deployment, or
release authority. PR validation run 33760112145 and post-merge main run 33760450512
passed.
### Completed integrity follow-up on shared main (PRs #105-#122)

- PR #106 separates semantic snapshot identity from volatile generation metadata
  while retaining a full-document integrity hash and V1 verification.
- PRs #107-#110 require retained technical sources at activation, bind Draft
  variants and revisions to the exact source document, and require a source
  locator before technical review.
- PR #111 records extraction failures with content-safe diagnostics.
- PR #112 materialises source-bound Draft variants from clean retained documents.
- PR #113 makes admission rejection helpers explicitly non-returning without
  altering their fail-closed safe-code behaviour.
- PR #114 makes rule and UI response types explicit, rejects non-text rule
  operators deterministically, and adds focused geometry/library-page coverage.
- PR #115 reconciles the preceding factual project documents. PR #116 hardens
  release-administration typing without changing the underlying release guards.
- PR #117 clarifies XLSX row handling and adds technical-workbook output
  coverage. PR #118 rejects a non-object successful task response at the Mission
  Control client boundary.
- PR #119 reconciles the preceding factual project records. PR #120 preserves
  the PDF timestamp form while replacing a deprecated naive UTC call with an
  aware UTC clock. PR #121 applies CLASSIFIRE display branding to generated
  PDF/XLSX artifacts, and PR #122 applies it to the browser workspace and serves
  the approved current logo.

### Completed current technical-source safeguards on shared main (PRs #127-#140)

- PR #127 reconciles factual records through the full hosted validation baseline.
- PR #128 requires clean, hash-verified retained bytes before extraction. PR #129
  derives Draft metadata only from those verified bytes after a fresh recheck.
- PR #130 applies current TechnicalVariant effective/expiry windows. PR #131
  rejects expired source authority, and PR #132 also gates bound source document
  approval and retained-file metadata at current-use boundaries.
- PR #133 exposes that current bound-source metadata result on TechnicalVariant
  detail screens. PR #134 exposes the same read-only result on TechnicalDocument
  detail screens and uses the defined blocked visual state. PR #135 reconciles
  those factual records. PR #136 freezes each newly published technical release's
  safe source state: bound document/file identity and locator, or an explicit
  legacy-unbound state; it rejects later source-lineage drift from a pinned release.
  PR #137 reconciles those factual records. PR #138 shows the same published
  source lineage in a structured technical-release detail view without granting
  approval or current-use authority. PR #139 reconciles those factual records. PR #140 safely links an eligible bound document ID to the existing read-only document record; it URL-escapes the row ID and leaves legacy, malformed, and unrecognised bindings as non-links. PR #141 reconciles those factual records. PR #142 makes each TechnicalVariant revision's existing retained-document binding and cited document/page/table/figure locator reviewer-visible; it links only a document record that remains present and labels missing bindings or legacy-unbound records.

These safeguards are current-use and published-manifest lineage checks. They do not approve a source,
activate a variant, re-read source bytes, publish a release, price work, create
canonical state, create a lock, deploy, or Human Release.

None of these safeguards approves a technical system, publishes a release,
prices work, creates a lock, or releases an estimate.

### In progress or incomplete

| Area | Evidence-backed limit |
| --- | --- |
| Desk-quote evidence/output safety | PR #103's shared-main resolver requires a Project/Estimate-owned immutable `clean` `project_evidence` record, verifies retained bytes under the atomic reader, validates stored locators, re-hashes new and cached export bytes, and audits artifact hash/size. Missing, changed, wrong-purpose, cross-project, cross-estimate, unsafe-path, quarantined, and locator-mismatched evidence fails before export or audit. `technical_evidence` remains rejected pending a separately designed owned-byte contract. |
| Report assessment operation | Shared main has one proposal-only application service, execute_phase8_report_assessment_runner(), plus a database-backed controller that assembles only an exact-approved-manifest V2 scope set. The runner requires a caller-owned PostgreSQL clean-byte transaction and injected no-tool port; the controller does not retrieve a report or call a port. Shared main also has CLASSIFIRE-owned package metadata/redaction/hold/deletion, an internal read-only UI, and explicit active/revoked Project/package grants for non-administrator visibility. Neither surface runs assessment or a real-provider route, and neither grants canonical, technical, commercial, lock, deployment, or release authority. |
| Report completeness | New scope admission rejects omitted, duplicate, foreign, or mismatched labels before it writes a scope, and stores the exact approval record on every new scope. Both the runner and the database-backed proposal-review controller reject legacy V1/unbound packets or a different approval record before a port call or package assembly. Historical V1 packets remain verifiable. |
| Report formats and content | Normalisation supports PDF plus bounded source-bound XLSX. PDF text, page, table, annotation, and strict explicitly numbered captions remain supported. XLSX persists only visible worksheet shape and non-empty cell position/category/hash fields; only selected cells are re-extracted transiently, and formulas are not executed. XLSX never persists worksheet names or cell values and fails closed on hidden sheets, macros, links, embedded media, comments, pivots, objects, validation rules, and unsafe shapes. DOCX and multi-report generalisation remain unimplemented. |
| Phase 8 physical truth | Proposal and review contracts exist, but there is no semantically approved canonical Physical Model or active replacement Physical Model Lock for the current UAT estimate. |
| Technical authority | Review, source-document current state, activation, Draft source binding, revision lineage, source-locator, clean-byte candidate metadata extraction and Draft-only refresh after a clean source recheck, manual Draft materialisation, import, and release checks fail closed. A new Draft source document can record a hash-bound historical predecessor only when that predecessor is independently approved and its retained technical-evidence bytes still verify clean and unchanged; it does not retire the predecessor or approve, activate, select, price, lock, deploy, or release anything. A bound source is excluded from normal search, new technical release snapshots, and pinned runtime use when its document is missing, unapproved, or expired, or its retained-file metadata is missing, unsafe, or for another evidence purpose. Newly published technical manifests fix a safe source state: bound document/file identity, digest, and locator, or an explicit legacy-unbound state; pinned runtime rejects later binding or source-hash drift. TechnicalVariant and TechnicalDocument detail screens expose current metadata read-only, and TechnicalVariant revision history now exposes each revision's existing retained document and cited locator read-only. Extraction-assisted and manufacturer-neutral lineage, governed technical-release publication/supersession, and production authority remain incomplete. |
| Quantity and labour | Basic estimate calculation exists; the complete selected-system-to-components-to-productivity chain is not implemented on current main. |
| Commercial recovery | Desk quotes and basic estimating rules exist, but the full component-level rate-inclusion/recovery ledger remains incomplete. |
| Snapshot and release | Estimate snapshot V2 separates semantic identity from `generated_utc`: `snapshot_hash` excludes that volatile generation metadata, while `snapshot_document_hash` still binds the complete displayed document. V1 snapshots retain their historical full-payload verification. Focused synthetic tests cover semantic stability, metadata/semantic tampering, and unsupported schemas. Full independent validation certificates and Human Release are not proven. |
| Product UI | A development UI exists for projects, estimates, libraries, and basic outputs. Technical source and variant details show a read-only current source-authority result; TechnicalVariant revision history also shows every recorded revision's retained-document binding and cited locator, while an eligible bound record in technical-release detail can safely link to the current document record without changing its published binding. Shared main adds a controlled-UAT read-only viewer for registered proposal packages and administrator-only scoped reader grants; it does not execute assessment or create a package from a report. |
| Production operation | Narrow fail-closed startup/browser/diagnostic controls are merged. Clean-machine deployment, observability, backup/restore, performance, incident response, data-rights controls, and production proof remain incomplete. |
| Static analysis | Full `ruff check .`, `mypy src`, and `bandit -q -r src` pass; Mypy covers 115 source files with maintained PyYAML and ReportLab stubs. Hosted CI runs all three checks after tests. | These are static-analysis gates, not proof of production readiness or operational authority. |

## 3. Latest controlled Phase 8 execution evidence

One separately authorised proposal-only assessment of the approved retained
report package was attempted on 2026-09-01. Current local receipts prove:

- runtime inference began;
- the first `blind_inventory` stage, using the Validator role, failed;
- final status was `VISUAL_PROPOSAL_FAILED` with
  `INFERENCE_PORT_FAILED: blind_inventory: Phase8OpenResponsesTransportError`;
- human-reference comparison was `NOT_RUN`;
- rollback-only remained true;
- no controller or runner database write occurred;
- no canonical submission or Physical Model Lock occurred;
- no write-or-lock capability was exposed; and
- the retained completion receipt file hashes to
  `F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.

This is a safe failed attempt, not an assessment result and not evidence that the
report is technically unsuitable. Its historical receipt records the transport
exception type but not the transport's stable safe code, so it cannot distinguish
a timeout from a rejected status, malformed response, audit failure, or another
transport code. New proposal-only receipts on this branch retain only an
established safe code; arbitrary exception text remains excluded. The authorised
run has been consumed and must not be repeated without new authority.

## 4. Roadmap position

| Phase | Status | Current gate |
| --- | --- | --- |
| 0. Repository/change control | **In progress** | Quarantined root; main validation passed through PR #154; GitHub plan prevents branch-protection configuration. |
| 1. Domain/workflow governance | **In progress** | Core physical and authority boundaries exist; complete amendment and lock eligibility remain. |
| 2. Governed libraries | **In progress** | Source-bound Draft/revision/review/materialisation safeguards, hash-bound Draft source-document predecessor lineage, current-authority gates and reviewer visibility, immutable published technical source-lineage checks, and pricing-release controls exist; manufacturer-neutral lineage and technical-release publication governance remain. |
| 3. OpenClaw/controlled write | **In progress** | Least-privilege boundaries and safe receipt codes exist; the proposal runner is shared-main but has no operator route or real report operation. |
| 4. Mission Control | **In progress** | Basic client/bootstrap exists; it is not canonical workflow state. |
| 5. Evidence intake/resolution | **In progress** | Shared main has PDF report services, strict source-bound caption locators, atomic expected-label scope admission, runner and controller verification, the retained proposal-review package lifecycle, and explicit scoped reader grants/revocation. Multi-format support, multi-report evidence-family accuracy, user review, and an operator flow remain. |
| 6. Physical Model | **In progress** | Proposal structures exist; accepted canonical physical truth does not. |
| 7. Independent visual gate | **In progress** | Historical blocked-run proof exists; the latest attempt failed before an inventory result. |
| 8. Corrected real Physical UAT | **Blocked** | First diagnose and harden the transport/orchestration path, then obtain new run authority; semantic approval and lock gates follow. |
| 8C. Accuracy programme | **Planned** | No training or continual learning before its admission gates. |
| 9-14. Technical through Human Release | **Blocked** | No replacement Phase 8 Physical Model Lock. Desk quotes do not bypass this chain. |
| 15. Production hardening | **In progress** | Source safeguards exist; operational proof remains. |
| 16. Structural steel/full duct runs | **Planned / deferred** | Separate domain design and evidence are required. |

## 5. Recommended Next Actions

### Immediate next action

#### Completed shared-main foundation - hash-bound technical source-document supersession (PR #147)

PR #147 permits a new technical document to record a hash-bound predecessor only after verifying that predecessor is independently approved and its retained technical-evidence bytes remain clean and unchanged. The new document stays Draft. It neither retires the predecessor nor grants document approval, TechnicalVariant activation, technical selection, pricing, canonical, lock, deployment, or release authority. A modified lineage snapshot is shown as untrusted rather than a valid predecessor.

PR #147 passed pull-request validation run 33745988740 and post-merge main validation run 33746319101.

#### Completed shared-main foundation - scoped proposal-review reader access (PR #145)

CLASSIFIRE owns registered proposal-review metadata with five-year retention, separate redaction, legal hold/deletion, safe locator, integrity refusal, and a read-only reviewer screen. PR #145 adds auditable active/revoked Project or exact-package grants. Every non-administrator reader now needs both the human read permission and an active matching grant before a list or detail view is returned. Administrators can manage the grants, but a grant does not approve a package or expand any other authority.

PR #145 passed pull-request validation run 33741309950 and post-merge main validation run 33741595397. This remains proposal-only: it does not run a report, call a provider, create canonical state, select a technical system, price work, create a lock, deploy, or release.

#### Completed shared-main foundation - proposal-review controller admission transition (PR #149)

PR #149 makes the database-backed proposal-review controller require the exact
human-approved expected-label manifest before it assembles a new package. Every
selected packet must be V2 and retain the identical manifest ID, hash, and
approval reference. Legacy/unbound packets and packets bound to a different
approval fail before package assembly; historical V1 packets remain verifiable.

PR #149 passed pull-request validation run 33749820103 and post-merge main run
33750096567. It adds no report/provider operation, canonical state, technical or
commercial decision, lock, deployment, or release authority.

#### Priority 2 - Close demonstrated Phase 2 and Phase 12 gaps separately

Complete the remaining extraction-assisted and manufacturer-neutral lineage plus
governed technical-release publication/supersession in separately reviewed migrations, without
automatic activation. Snapshot V2 now separates
semantic identity from volatile generation metadata and preserves V1 validation;
the remaining Phase 12 work is independent physical, technical, quantity,
commercial, formula, recovery, and release validation. Neither activity may
bypass the Phase 8 lock gate.

#### Priority 3 - Maintain full static checks and default-branch governance

The repository is now clean under full Ruff and Bandit scans. Keep the changed-file Ruff fast-path and
full `ruff check .`, `mypy src`, and `bandit -q -r src` checks in the shared workflow. Decide whether
the repository owner will upgrade/configure GitHub protection or document an
equivalent review control; hosted runs alone do not prove required-check
configuration.

### Later or dependency-bound actions

1. Diagnose any remaining transport behaviour with synthetic/fake ports only,
   then seek fresh explicit authority before a further proposal-only report run.
   A successful transport call is not semantic approval.
2. Advance canonical submission and a separately signed Physical Model Lock only
   after evidence resolution, semantic approval, a fresh no-write preflight,
   admission registration, and separate write/lock authorities.
3. Keep Phases 9-14 blocked until the replacement lock exists. Continue Phase 15
   hardening only where it cannot bypass the upstream gates.

## 6. Validation evidence for this snapshot

This reconciliation verified:

- fetched Git refs, branch/upstream relationships, recent commits, open PRs, and issues;
- the clean isolated worktree and the read-only legacy-root classification;
- the single shared-main Alembic head 0017_xlsx_report_evidence_locators;
- current models, API/UI routes, report services, storage/containment, technical guards, desk-quote services/outputs, snapshot code, tests, scripts, and CI;
- PR #147's successful technical-lineage validation, PR #149's successful controller validation, PR #151's successful caption-locator validation, and PR #154's successful XLSX-locator validation on 74f0557 plus post-merge main validation on 7a33f34;
- the retained assessment status and no-write/no-lock flags; and
- the receipt code and tests that retain only validated safe transport codes in new receipts while historical receipts remain verifiable; and
- the snapshot V2 semantic/document hash contract, V1 compatibility, focused synthetic regression suite, current scoped static checks, and the full synthetic suite.

No real report, retained image, Gateway token, provider response, customer data, database, canonical model, lock, deployment, or release was opened or changed by this documentation reconciliation.
