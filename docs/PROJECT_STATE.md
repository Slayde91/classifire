# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-01 (AEST)

**Product status:** Pre-production implementation and controlled UAT

**Shared-main baseline:** `d9b19fcee60fd82d0d317eae2f94f22b2a0ac7ab`
(merge of PR #103)

This snapshot reconciles executable source, tests, migrations, Git/GitHub state,
the quarantined legacy checkout, and retained non-canonical receipts. Those
sources outrank older handoffs and roadmap prose.

Nothing in this document authorises report retrieval or inference, admission
signing or registration, canonical submission, Physical Model Lock creation,
deployment, technical approval, commercial approval, or Human Release.

## 1. Repository and publication state

| Area | Verified state | Consequence |
| --- | --- | --- |
| Shared `main` | PR #103 is merged at `d9b19fc`. | This is the current shared implementation baseline. |
| Current branch | `gpt/phase8-report-evidence-adapter-20260830` is clean, matches its upstream, and has published candidate commits `b36ebb5`, `9a4c2d2`, and `e9ac8f0` beyond `main`. | They remain candidate evidence until a new PR is reviewed and merged. |
| Pull-request CI | PR #103 run `33492628353` passed Python validation. | This proves the exact PR head, not a post-merge run of `d9b19fc`. |
| Default-branch governance | Commit `e9ac8f0` adds a `main` push validation trigger, but it is not yet merged. GitHub's branch-protection API returns HTTP 403 because this private repository needs GitHub Pro or public visibility for that feature. | There is no hosted `main` push result and no verified required-check configuration. |
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
  cross-project rejection, shared-byte quarantine, stable PDF locators, bounded
  report scopes, deterministic review packages, and no-write report-assessment
  components.
- Production configuration checks before filesystem work, no production
  `create_all()` or default-administrator seeding, packaged migration history,
  an explicit migration command, and exact migration-head readiness checks.
- Technical-document review separation, source-byte rechecks, Draft-only new
  technical imports, independent TechnicalVariant activation, active immutable
  technical-release requirements, and release-manifest eligibility rechecks.
- Governed assumption-led desk-quote PDF/XLSX outputs from PR #75. They remain
  explicitly non-technical, proposal-only commercial scenarios. The current
  shared-main resolver requires Project/Estimate-owned immutable `clean` ProjectEvidence,
  exact atomic retained-byte reads, persisted locators, and artifact-byte audit
  bindings; `technical_evidence` remains rejected. PR #103's checks passed;
  operational approval remains separate.
- A secret-free pull-request workflow using Node 24-compatible actions and a
  disposable PostgreSQL 16 service.

Shared `main` packages migrations through `0011_report_evidence_locators`. It
has not yet received the current branch's two report-governance migrations.

### Published candidate on the current branch, not yet shared main

- `b36ebb5` introduces an immutable, human-approved expected-label manifest
  bound to retained report bytes and an estimate
  (`0012_report_expected_label_manifests`).
- `9a4c2d2` admits a complete exact approved label set atomically, retains that
  manifest on every new report scope, and prevents V1/unbound scope packets from
  reaching a proposal run (`0013_report_defect_scope_admissions`). Historical
  V1 receipts remain verifiable.
- `e9ac8f0` adds the GitHub Actions `push` validation path for merged `main`
  changes. It intentionally lints only changed Python files because full-
  repository Ruff currently reports pre-existing violations outside this candidate.

The current branch's packaged migration lineage has one head:
`0013_report_defect_scope_admissions (legacy_adjudicated_lineage)`.

### In progress or incomplete

| Area | Evidence-backed limit |
| --- | --- |
| Desk-quote evidence/output safety | PR #103's shared-main resolver requires a Project/Estimate-owned immutable `clean` `project_evidence` record, verifies retained bytes under the atomic reader, validates stored locators, re-hashes new and cached export bytes, and audits artifact hash/size. Missing, changed, wrong-purpose, cross-project, cross-estimate, unsafe-path, quarantined, and locator-mismatched evidence fails before export or audit. `technical_evidence` remains rejected pending a separately designed owned-byte contract. |
| Report assessment operation | The current branch has one proposal-only application service, `execute_phase8_report_assessment_runner()`. It requires a caller-owned PostgreSQL clean-byte transaction, exact Project/Estimate/report/package/profile bindings, and a human-approved expected-label manifest bound to report bytes and estimate; it checks the same approval on every V2 scope packet before an injected no-tool port call. There is no API/CLI/UI route, persisted review-package record, or real-provider run. |
| Report completeness | New scope admission rejects omitted, duplicate, foreign, or mismatched labels before it writes a scope, and stores the exact approval record on every new scope. The runner rejects legacy V1/unbound scope packets or a different approval record before any port call. Historical V1 packets remain verifiable. |
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
report is technically unsuitable. Its historical receipt records the transport
exception type but not the transport's stable safe code, so it cannot distinguish
a timeout from a rejected status, malformed response, audit failure, or another
transport code. New proposal-only receipts on this branch retain only an
established safe code; arbitrary exception text remains excluded. The authorised
run has been consumed and must not be repeated without new authority.

## 4. Roadmap position

| Phase | Status | Current gate |
| --- | --- | --- |
| 0. Repository/change control | **In progress** | Quarantined root; candidate-only `main` push CI; GitHub plan prevents branch-protection configuration. |
| 1. Domain/workflow governance | **In progress** | Core physical and authority boundaries exist; complete amendment and lock eligibility remain. |
| 2. Governed libraries | **In progress** | Narrow technical and pricing-release safeguards exist; full intake/publication governance remains. |
| 3. OpenClaw/controlled write | **In progress** | Least-privilege boundaries and safe receipt codes exist; the proposal runner is candidate-only and no operator route or real report operation exists. |
| 4. Mission Control | **In progress** | Basic client/bootstrap exists; it is not canonical workflow state. |
| 5. Evidence intake/resolution | **In progress** | Shared main has PDF report services; the candidate adds atomic expected-label scope admission and runner verification. Legacy-scope transition, package persistence, caption/multi-format support, and an operator flow remain. |
| 6. Physical Model | **In progress** | Proposal structures exist; accepted canonical physical truth does not. |
| 7. Independent visual gate | **In progress** | Historical blocked-run proof exists; the latest attempt failed before an inventory result. |
| 8. Corrected real Physical UAT | **Blocked** | First diagnose and harden the transport/orchestration path, then obtain new run authority; semantic approval and lock gates follow. |
| 8C. Accuracy programme | **Planned** | No training or continual learning before its admission gates. |
| 9-14. Technical through Human Release | **Blocked** | No replacement Phase 8 Physical Model Lock. Desk quotes do not bypass this chain. |
| 15. Production hardening | **In progress** | Source safeguards exist; operational proof remains. |
| 16. Structural steel/full duct runs | **Planned / deferred** | Separate domain design and evidence are required. |

## 5. Recommended Next Actions

### Immediate next action

#### Priority 0 - Integrate and prove the published report-governance candidate

**Objective:** review the complete `origin/main...HEAD` range, create a current-
main pull request, merge only after it is green, then record the first hosted
`push` validation result for the merge on `main`.

**Why this is first:** the candidate contains the expected-label approval,
atomic scope-admission, and post-merge CI changes needed to make Phase 5 safer,
but none is shared-main evidence yet. The new `push` workflow cannot produce its
first `main` result until that same candidate is merged. This is a publication
and verification action, not a report, OpenClaw, provider, canonical, lock, or
release operation.

**Relevant components:** `0012_report_expected_label_manifests`,
`0013_report_defect_scope_admissions`, `report_expected_label_manifest.py`,
`report_evidence_adapter.py`, `phase8_report_assessment_runner.py`, their
focused tests, and `.github/workflows/pull-request-validation.yml`.

**Dependencies and blockers:** fresh reviewer approval and separate merge
authority; GitHub's current private-repository plan prevents branch-protection
rules, so review discipline and observed CI are the available controls.

**Done when:** the PR covers only the reviewed range, GitHub validates it, the
merge lands on `main`, a `push` run for that merge passes the full test and
one-head migration jobs, and the run URL/SHA are recorded. A clean local test is
not a substitute for the hosted post-merge result.

**Validation:** fetch first; inspect `git diff origin/main...HEAD`; run the
focused report tests with synthetic fixtures, `python -m alembic heads`, and
`git diff --check`; then inspect the GitHub PR and `main` workflow result.

**Uncertainty:** the protection API does not reveal a usable rule set because of
the GitHub plan. It is unknown whether the repository owner will change that
plan or use another documented protection mechanism.

### Near-term actions

#### Priority 1 - Add governed persistence before a report-review UI

**Objective:** define and implement the smallest immutable, proposal-only
storage contract for a generated report-review package, then expose it through a
read-only reviewer surface.

**Why:** the runner builds a deterministic in-memory package and can materialise
files only to a caller-supplied path. `models.py`, `api/`, and `ui.py` contain no
`ReportReviewPackage` record or report-review route, so building a UI first would
create a second, ungoverned source of truth.

**Scope and acceptance:** retain only hash-bound package metadata, receipt and
source/approval references, reviewer-visible uncertainty, and a safe storage
locator. Prove immutable reads, project/estimate isolation, redaction, tamper
failure, and absence of canonical, technical, commercial, lock, or release
authority with a migration, service, route/UI tests, and synthetic fixtures.

**Dependencies and uncertainty:** first decide retention, redaction/deletion,
and reviewer-access ownership for proposal artifacts. No evidence currently
defines that policy, so this design decision must precede a migration.

#### Priority 2 - Close demonstrated Phase 2 and Phase 12 gaps separately

Complete Draft technical materialisation/source-lineage publication in separately
reviewed migrations, without automatic activation. In parallel, split semantic
snapshot identity from `generated_utc` in `services/snapshot.py` and add focused
snapshot/output regression tests. These have clear source-level gaps and do not
need to bypass the Phase 8 lock gate.

#### Priority 3 - Make CI debt and default-branch governance explicit

Keep changed-file Ruff in the candidate workflow until a separate full-repository
lint remediation is scoped; full `ruff check .` currently fails outside this
candidate. After the first `main` push result, decide whether the repository
owner will upgrade/configure GitHub protection or document an equivalent review
control. Do not present changed-file lint as proof that the whole repository is
lint-clean.

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

- fetched Git refs, branch/upstream relationships, recent commits, open PRs, and
  issues;
- the clean isolated worktree and the read-only legacy-root classification;
- the single packaged Alembic head `0013_report_defect_scope_admissions`;
- current models, API/UI routes, report services, storage/containment, technical
  guards, desk-quote services/outputs, snapshot code, tests, scripts, and CI;
- PR #103's successful hosted Python validation result;
- the retained assessment status and no-write/no-lock flags; and
- the receipt code and tests that retain only validated safe transport codes in
  new receipts while historical receipts remain verifiable.

No real report, retained image, Gateway token, provider response, customer data,
database, canonical model, lock, deployment, or release was opened or changed by
this documentation reconciliation.
