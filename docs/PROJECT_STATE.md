# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-01 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Shared-main baseline:** `db28c6384f624cee09fb74dd1c01ea35702fd295`
(merge of PR #100)

This snapshot reconciles executable source, tests, migrations, Git/GitHub state,
the quarantined legacy checkout, and retained non-canonical receipts. Those
sources outrank older handoffs and roadmap prose.

Nothing in this document authorises report retrieval or inference, admission
signing or registration, canonical submission, Physical Model Lock creation,
deployment, technical approval, commercial approval, or Human Release.

## 1. Repository and publication state

| Area | Verified state | Consequence |
| --- | --- | --- |
| Shared `main` | PR #100 is merged at `db28c638`. | This is the current shared implementation baseline. |
| Documentation branch | `gpt/phase8-report-evidence-adapter-20260830` was clean and fast-forwarded locally from `be04258` to `db28c638` before this reconciliation. | The 23 fast-forward commits were already public on `main`; no unpublished implementation was imported. |
| Pull-request CI | PR #100 run `33330916501` passed 577 tests, changed-Python Ruff, the PostgreSQL containment setup, and the single Alembic-head check. | This proves the exact PR head, not a post-merge run of `db28c638`. |
| Default-branch governance | The workflow runs on pull requests only. GitHub reports no required checks or branch protection on `main`. | A direct branch push does not create CI evidence; this remains a repository-governance gap. |
| Open pull requests | Draft PRs #9-#13 remain open on obsolete feature-to-feature bases, have no checks, and are materially diverged from `main`. | Treat them as quarantined legacy candidates, not current-main merge candidates. |
| Issues | Issues #42 and #43 remain open. | Their descriptions may be historical; implementation evidence still wins. |

### Quarantined root checkout

The root checkout at `C:\CLASSIFIRE` remains recovery evidence on
`gpt/phase8-linked-original-images` at `de0cc5a`. The read-only inventory found:

- an active interrupted cherry-pick;
- four unmerged Phase 8 files;
- 50 tracked paths with unstaged or unmerged differences;
- 14 staged additions; and
- an incomplete untracked inventory because protected pytest directories could
  not be read.

The root contains substantial unfinished Phase 8, plugin, script, UI, and test
work. Its conflicted and partially understood state makes it unsuitable for this
commit, publication, deployment, or canonical operations. None of it was edited,
resolved, staged, or copied into the clean worktree.

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
  cross-project rejection, shared-byte quarantine, stable PDF locators, bounded
  report scopes, deterministic review packages, and no-write report assessment
  service components.
- Production configuration checks before filesystem work, no production
  `create_all()` or default-administrator seeding, packaged migration history,
  an explicit migration command, and exact migration-head readiness checks.
- Technical-document review separation, source-byte rechecks, Draft-only new
  technical imports, independent TechnicalVariant activation, active immutable
  technical-release requirements, and release-manifest eligibility rechecks.
- Governed assumption-led desk-quote PDF/XLSX outputs from PR #75. They bind
  evidence metadata and active pricing records and remain explicitly
  non-technical, proposal-only commercial scenarios. Their retained-byte and
  locator boundary still requires hardening before operational use.
- A secret-free pull-request workflow using Node 24-compatible actions and a
  disposable PostgreSQL 16 service.

The current packaged migration lineage has one head:
`0011_report_evidence_locators (legacy_adjudicated_lineage)`.

### In progress or incomplete

| Area | Evidence-backed limit |
| --- | --- |
| Desk-quote evidence/output safety | The resolver trusts stored metadata, accepts `not_configured`, does not open/re-hash bytes through the atomic PostgreSQL reader, and does not match caller locator text to persisted page/region or report-locator data. Cached exports are reused without re-hashing their bytes, and the audit records the snapshot hash rather than the artifact hash. Current tests use metadata-only nonexistent file paths. |
| Report assessment operation | The report ownership, locator, context, assessment, runtime-input, controller, and review-package services exist, but no application service, CLI, API, or script composes them into one supported operator flow. The existing representative-package script does not call the new report adapter. |
| Report completeness | Cardinality is enforced over report scopes already stored in the database, but no approved expected-Defect-label manifest proves that all intended labels were created before assessment. |
| Report formats and content | Normalisation is PDF-only. Text, page, table, and annotation content are supported. Drawings and embedded images are locator/hash records with no documentary payload; visual bytes come through a separate governed packet. Caption extraction is explicitly rejected. XLSX, DOCX, and multi-report generalisation are not implemented. |
| Phase 8 physical truth | Proposal and review contracts exist, but there is no semantically approved canonical Physical Model or active replacement Physical Model Lock for the current UAT estimate. |
| Technical authority | Important fail-closed review, activation, source-integrity, import, and release checks exist. Full governed technical intake, materialisation, source-lineage publication, supersession, and production authority remain incomplete. |
| Quantity and labour | Basic estimate calculation exists; the complete selected-system-to-components-to-productivity chain is not implemented on current main. |
| Commercial recovery | Desk quotes and basic estimating rules exist, but the full component-level rate-inclusion/recovery ledger remains incomplete. |
| Snapshot and release | `build_estimate_snapshot()` includes the current generation time in the hashed payload and has no focused snapshot regression suite. Reproducible semantic identity, full validation certificates, and Human Release are not proven. |
| Product UI | A development UI exists for projects, estimates, libraries, and basic outputs. There is no supported user-facing report-assessment/review workflow for the merged Phase 8 report services. |
| Production operation | Narrow fail-closed startup/browser/diagnostic controls are merged. Clean-machine deployment, observability, backup/restore, performance, incident response, data-rights controls, and production proof remain incomplete. |

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
report is technically unsuitable. The current controller records the transport
exception type but discards the transport's stable safe code. The receipt cannot
distinguish a timeout from a rejected status, malformed response, audit failure,
or another transport code. The authorised run has been consumed and must not be
repeated without new authority.

## 4. Roadmap position

| Phase | Status | Current gate |
| --- | --- | --- |
| 0. Repository/change control | **In progress** | Quarantined root, unprotected `main`, and PR-only CI remain. |
| 1. Domain/workflow governance | **In progress** | Core physical and authority boundaries exist; complete amendment and lock eligibility remain. |
| 2. Governed libraries | **In progress** | Narrow technical and pricing-release safeguards exist; full intake/publication governance remains. |
| 3. OpenClaw/controlled write | **In progress** | Least-privilege boundaries exist; operational report orchestration and diagnosable transport receipts remain incomplete. |
| 4. Mission Control | **In progress** | Basic client/bootstrap exists; it is not canonical workflow state. |
| 5. Evidence intake/resolution | **In progress** | PDF report services are merged; expected-label completeness, caption/multi-format support, and an operator flow remain. |
| 6. Physical Model | **In progress** | Proposal structures exist; accepted canonical physical truth does not. |
| 7. Independent visual gate | **In progress** | Historical blocked-run proof exists; the latest attempt failed before an inventory result. |
| 8. Corrected real Physical UAT | **Blocked** | First diagnose and harden the transport/orchestration path, then obtain new run authority; semantic approval and lock gates follow. |
| 8C. Accuracy programme | **Planned** | No training or continual learning before its admission gates. |
| 9-14. Technical through Human Release | **Blocked** | No replacement Phase 8 Physical Model Lock. Desk quotes do not bypass this chain. |
| 15. Production hardening | **In progress** | Source safeguards exist; operational proof remains. |
| 16. Structural steel/full duct runs | **Planned / deferred** | Separate domain design and evidence are required. |

## 5. Recommended Next Actions

### Immediate next actions

#### Priority 0 - Harden desk-quote evidence before operational use

**Objective:** narrow the current desk-quote slice to `project_evidence`, then
use ProjectEvidence ownership, the atomic PostgreSQL exact clean-byte reader,
and persisted evidence locators. Keep `technical_evidence` rejected unless a
separate Estimate-owned exact-byte contract is designed and approved.

**Why:** the endpoint is a tangible PDF/XLSX feature, so accepting metadata-only
or `not_configured` evidence is a higher immediate risk than expanding another
workflow.

**Relevant files:**

- `src/classifire/services/desk_quote.py`
- `src/classifire/api/router.py`
- `src/classifire/services/storage.py`
- `src/classifire/services/project_evidence.py`
- `tests/test_desk_quote.py`
- `tests/test_shared_file_containment.py`

**Done when:** only owned, immutable, `clean`, exact retained bytes are accepted;
missing/tampered/unsafe-path/quarantined sources and locator mismatches fail
before export/cache/audit; cross-project and cross-estimate evidence fails;
rendered/cached artifact bytes are verified and their hash is audited; the
PostgreSQL quarantine race stays serialized; and focused, full, Ruff, Mypy,
Alembic-head, and diff checks pass using disposable synthetic data.

#### Priority 1 - Preserve receipt-safe transport diagnostics

**Objective:** retain the existing stable `Phase8OpenResponsesTransportError`
code in the outer failed receipt while continuing to exclude arbitrary exception
messages, response content, credentials, and report content.

**Why:** the authorised attempt failed safely, but the current receipt discarded
the only safe diagnostic needed to identify the failing transport layer.

**Relevant files:**

- `src/classifire/services/phase8_visual_proposal.py`
- `src/classifire/services/phase8_openresponses_transport.py`
- `tests/test_phase8_visual_proposal.py`
- `tests/test_phase8_openresponses_transport.py`
- `tests/test_phase8_report_openresponses_transport.py`
- `tests/test_phase8_report_assessment_controller.py`

**Done when:**

1. an explicitly safe code such as `GATEWAY_TIMEOUT` is retained under
   `INFERENCE_PORT_FAILED`;
2. generic exception messages and malformed or secret-like codes remain absent;
3. historical receipt verification remains valid, new receipts deterministically
   hash the safe code, and protected-state/no-write semantics remain valid;
4. focused tests, Ruff, the report/visual regression suite, the complete suite,
   Alembic one-head, and `git diff --check` pass; and
5. no report, Gateway, OpenClaw, provider, canonical, lock, deployment, or
   release operation is performed to verify the code change.

#### Priority 2 - Add one bounded report-assessment operator flow

**Objective:** compose the merged report services into one proposal-only runner
with an offline/fake-transport preflight and an approved expected-Defect-label
manifest.

**Why:** the primitives are well tested but service-only. There is no supported
entry point proving the intended report-SHA, ownership, locator, assessment,
review-package, and completion-receipt sequence as one operation.

**Expected outcome:** one deterministic safe outcome for every approved label,
including retrieval-blocked, malformed, insufficient-evidence, and transport-
failed cases, with every artifact hash-bound and protected state unchanged.

**Dependencies:** Priority 1; an explicit package/expected-label contract;
PostgreSQL for the atomic clean-byte transaction; fake transport for normal
implementation tests. A real provider run still requires separate authority.

**Validation:** cross-project, report-hash, locator, expected-label, profile,
and source-byte tamper tests; fake-transport end-to-end tests; the PostgreSQL
two-session containment race; focused/full suites; Ruff, Mypy, Alembic head,
and output inspection.

### Near-term actions

3. Add a small user-facing report review surface only after the operator flow is
   deterministic and fail-closed. It must show evidence locators, confidence,
   alternatives, unresolved facts, and receipt status without creating canonical
   authority.
4. Reconcile Draft technical materialisation and source-lineage publication as
   separate migrations and reviews; never activate imported Draft evidence
   automatically.
5. Define deterministic semantic snapshot identity separately from generation
   metadata and add focused snapshot/output regression tests before Phase 12.
6. Add required pull-request checks and branch protection to `main` after the
   repository owner approves the governance change.

### Later or dependency-bound actions

7. After Priorities 1-2 pass and the transport problem is understood, seek new
   authority for one controlled proposal-only assessment. Human-review every
   artifact; do not treat a successful transport as semantic approval.
8. Advance canonical submission and a separately signed Physical Model Lock
   only after evidence resolution, semantic approval, fresh preflight, external
   signature, admission registration, and separate write/lock authorities.
9. Keep Phases 9-14 blocked until the replacement lock exists. Continue Phase 15
   operational hardening independently where it cannot bypass upstream gates.

## 6. Validation evidence for this snapshot

This reconciliation verified:

- fetched Git refs, branch/upstream relationships, recent commits, open PRs, and
  issues;
- the clean isolated worktree and the read-only legacy-root classification;
- the single packaged Alembic head `0011_report_evidence_locators`;
- current models, API/UI routes, report services, storage/containment, technical
  guards, desk-quote services/outputs, snapshot code, tests, scripts, and CI;
- PR #100's successful hosted result: 577 passed, 140 warnings;
- the retained assessment status and no-write/no-lock flags; and
- the exact controller code that drops the nested safe transport code.

No real report, retained image, Gateway token, provider response, customer data,
database, canonical model, lock, deployment, or release was opened or changed by
this documentation reconciliation.
