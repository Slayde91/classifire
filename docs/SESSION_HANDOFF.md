# CLASSIFIRE Session Handoff

**Verified:** 2026-08-30 (AEST)

**Status:** Pre-production prototype; shared main has controlled Phase 8 foundations, and the current branch has a completed proposal-only assessment/review candidate, but no approved canonical Physical Model or active replacement Physical Model Lock.

This handoff is a factual audit record. It does not grant authority to run inference, retrieve report evidence, write canonical data, sign or register an admission, create a lock, deploy, release, merge, or open a pull request.

## 1. Verified shared state

- `origin/main` is `c8b06d17678b58f49f2ea816f3b12ba2e4af0095`
  (PR #79). The application baseline is `20cb72a`; `db404b3` later hardened
  human-session revocation; PR #79 adds only the reviewed root-recovery decision.
- Current shared-main Alembic state has one head: `0009_visual_validation_receipts` on `legacy_adjudicated_lineage`. The technical-intake candidate migration is not on main.
- A focused current-main suite covering human-session security, evidence-family review, human-adjudicated proposal, visual evidence, and linked visual runs passed: **48 tests**.
- The current `gpt/phase8-assessment-contract-20260830` branch is based exactly
  on `c8b06d1`. Its 24-file implementation candidate passed the complete
  **435-test** suite plus Ruff, Mypy, syntax, Bandit, diff, and independent
  architecture/policy checks. It is not shared main until reviewed and merged.
- Open GitHub work remains reviewable rather than automatically mergeable: PR #75 is open; PRs #9-#13 are retained draft stack work; issues #42 and #43 are open. Issue #42 still has stale site-visit-first wording.
- Current main has no GitHub workflow, recorded Actions run, or PR status-check rollup. Mergeability is not CI evidence.
- GitHub's branch-protection endpoint returned a plan-limited 403, so this audit
  does not claim that main is protected or unprotected.

## 2. What must not be used as a publication source

The primary checkout is on `gpt/phase8-linked-original-images` at `de0cc5a`. It is **not** a safe branch for staging, committing, or merging:

- it is 378 commits ahead and 141 commits behind `origin/main`;
- it has an active interrupted cherry-pick for `c3e4c810`;
- four files are unmerged: `phase8_linked_visual_run.py`, `phase8_visual_evidence.py`, and their two tests;
- it has 46 unstaged tracked modifications (+1,668/-894) and 14 staged added files (+3,183), plus generated/untracked artefacts.

PR #79 records the isolated decision to keep the accepted current-main versions
of the four conflict paths and not transplant the stale cherry-pick. It does not
resolve or clean the root itself. Do not run bulk staging, clean, reset, force
operations, or normal publication from that checkout. This audit deliberately
did not modify it.

## 3. Current work, classified honestly

| Workstream | State | Meaning |
| --- | --- | --- |
| Shared-main Phase 8 foundations | **Merged and focused-tested** | Controlled evidence, visual-proposal, review, and rollback safeguards exist for their stated scope. They do not authorise canonicalisation or release. |
| Root Phase 8 continuation | **Quarantined / superseded as a build path** | The recovery decision is complete in PR #79. The conflicted checkout remains evidence only and is no longer the next current-main blocker. |
| Report assessment | **Completed branch candidate / not shared main** | The current branch selects `property_assessments` v2, retains paired historical v1 verification, and adds manifest-bound JSON/Markdown proposal reviews. |
| Cable semantics | **Completed branch candidate / not shared main** | Bundle quantity counts bundles, cable count is separate, an indefensible count is null/Unknown with a required small/medium/large bundle class, and cable trays remain trays with their own dimensions. |
| Report intake | **Broad local candidate / blocked on containment and ownership** | Stored reports are not project/estimate-bound, use a conflicting evidence purpose, and do not prove an atomic clean-byte read. Do not expose its generic readout/UI yet. |
| Governed technical intake | **Separate pushed candidate plus local continuation** | `d76562e` and `0edeaac` are not on shared main. Their worktree has proposed `0019` and substantial uncommitted follow-on material, so it is not a clean merge candidate. |
| Production hardening | **Local-only commit** | `a3de490` is unpushed, broad, one commit ahead and three behind main. Main remains pre-production with unconditional schema/seed startup and warning-only production findings. |
| Report review / UAT | **Proposal-only, authority-gated** | A report package can support cautious evidence assessment, but it cannot create technical compatibility truth, commercial truth, a canonical model, a lock, or a release. |

## 4. Start Here / Next Session

**Required first gate:** independently review the exact
`gpt/phase8-assessment-contract-20260830` branch and merge it only if accepted.
If review finds a defect, correct or supersede this branch before extending it.

**Recommended first engineering task after that gate:** build the contained,
project-owned, report-SHA-bound evidence adapter and deterministic per-Defect
review flow on a clean current-main branch.

### Prerequisites

1. Begin from the reviewed assessment-contract branch or its eventual shared-main
   merge. Do not use or modify the root.
2. Review the narrow shared-byte containment commit and broad report-context
   candidate as evidence only; do not copy either worktree wholesale.
3. Decide the smallest additive StoredFile/report ownership migration and the
   stable documentary-evidence locator schema before exposing an API or UI.
4. Keep technical selection, pricing, canonical submission, lock creation,
   deployment, and release outside this task.

### Relevant files

- `src/classifire/models.py` and the next additive migration
- `src/classifire/services/storage.py`
- the narrow shared-byte containment service from the technical-intake candidate
- bounded report-document/package services extracted from
  `gpt/report-evidence-context-20260829`
- `src/classifire/services/phase8_visual_evidence.py`
- `src/classifire/services/phase8_linked_visual_run.py`
- `src/classifire/services/phase8_property_assessments.py`
- `src/classifire/services/phase8_proposal_review.py`
- `scripts/run_phase8_representative_package.py`
- new `tests/test_shared_file_containment.py`,
  `tests/test_report_evidence_ownership.py`, and
  `tests/test_report_evidence_adapter.py` coverage
- existing `tests/test_physical_evidence_file_boundary.py`,
  `tests/test_phase8_property_assessments.py`,
  `tests/test_phase8_proposal_review.py`, and
  `tests/test_run_phase8_representative_package.py` regression coverage

### Implementation order

1. Make malware state, content hash, and the exact bytes read/served one atomic
   trust decision. A clean-to-FOUND transition must quarantine every row sharing
   those bytes, and concurrent preview/download/read must fail closed.
2. Bind each report StoredFile and generated package to its Project or Estimate
   under the agreed `project_evidence` purpose. Reject cross-project access.
3. Bind the approved report SHA-256 and selected Defect range. Give report text,
   tables, captions, drawings, annotations, metadata, pages, and governed images
   stable report/page/item locators.
4. Feed those locators through the existing v2 assessment/review boundary
   without weakening its evidence, confidence, range, cable, prompt, policy,
   receipt, or historical-v1 rules.
5. Emit exactly one deterministic review artifact per selected report-labelled
   Defect, including retrieval-blocked, malformed, and insufficient-evidence
   outcomes.
6. Bind each review to its report/package, manifest, prompt/runtime profile,
   proposal, and controller receipt. Make the later completion receipt hash
   every preceding emitted artifact, and prove protected state is unchanged.

### Suggested validation

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$focusedTests = @(
  'tests/test_shared_file_containment.py',
  'tests/test_report_evidence_ownership.py',
  'tests/test_report_evidence_adapter.py',
  'tests/test_physical_evidence_file_boundary.py',
  'tests/test_phase8_property_assessments.py',
  'tests/test_phase8_proposal_review.py',
  'tests/test_run_phase8_representative_package.py'
)
& C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest $focusedTests -q -p no:cacheprovider --basetemp C:\CLASSIFIRE\.tmp\pytest-report-evidence-adapter
```

Also run disposable two-session PostgreSQL race tests, Alembic upgrade/head
checks, the complete suite, Ruff, Mypy, Bandit, `git diff --check`, report-hash
and locator tampering, cross-project access, blocked-result cardinality, and
inspection of representative review files.

**Done means:** one contained current-main change; one Project/Estimate-owned
report and package boundary; atomic safe-byte reads; stable documentary and
visual locators; exactly one safe review per selected Defect; passing focused,
database, full-suite, and static checks; inspected output; and no canonical or
downstream authority interface.

## 5. Then, in order

1. **Run the approved report package through the controlled report-only flow**
   only with separate run authority, then human-review every generated file.
2. **Continue Draft technical materialization separately.** Review proposed
   migration `0019` without silently activating a `TechnicalVariant`.
3. **Review `a3de490` on current main.** Make production startup migration-only
   and fail closed on unsafe configuration/admission defaults; package migrations
   for installed operation.
4. **Review or supersede PR #75 independently.** A mergeable label is not
   acceptance evidence.
5. **Add minimal secret-free PR validation.** Run the agreed Pytest policy, Ruff,
   and Alembic one-head check; prove both a deliberately failed check and a
   reproducible passing check.
6. **Keep canonical UAT, signed lock admission, downstream technical/commercial
   work, deterministic snapshots, deployment, and Human Release behind their
   documented prerequisites and separate authorities.**

## 6. Report-only evidence rule

For a proposal-only review, use the supplied report package first: report text, defect register, photographs, annotations, drawings, page context, visible scale clues, repeated items, and normal industry dimensions where they do not contradict evidence. Do not default a field to Unknown solely because it lacks an exact measurement.

Label each conclusion as **Confirmed**, **Approximate**, **Inferred**, or **Unknown**, and give a confidence level for Approximate or Inferred values. Ask for extra evidence only after these methods are exhausted, or where confirmation is essential to a later governed technical or commercial decision. A site visit is one possible confirmation route, not the immediate default.

## 7. Important architectural boundary

The required order remains:

**Evidence -> physical model proposal -> technical-system search -> compatibility validation -> commercial applicability -> quantities/labour -> reconciliation -> estimate/scope -> human release.**

A rate, a product, chat context, or a proposal-only visual inference cannot make a technical system compatible or turn uncertain physical facts into approved truth. Keep uncertain facts explicit and do not let transient inference overwrite approved data.

## 8. Audit verification performed

- fetched and reconciled the current remote branch and open pull requests;
- checked root branch divergence, interrupted cherry-pick, conflict paths, and working-tree classifications without changing them;
- checked the current-main migration head, production startup, upload/storage,
  technical approval, snapshot, and deployment/CI boundaries;
- inspected the separate report-assessment, report-context, technical-intake,
  production-hardening, and PR #75 candidate worktrees;
- verified the unchanged Alembic head
  `0009_visual_validation_receipts (legacy_adjudicated_lineage)`;
- ran the exact current-branch complete suite: **435 passed, 139 warnings**;
- passed Ruff on all 24 implementation/test files, Mypy and syntax compilation
  on all 13 production/script files, Bandit with no finding, `git diff --check`,
  and a credential-pattern scan;
- inspected a representative rendered proposal review; and
- obtained independent architecture and policy audits with no remaining blocker
  in the bounded contract.

No canonical database, report package, model endpoint, OpenClaw token, external
inference service, migration, deployment, or root source file was changed. No
fresh real-report review was executed.

## 9. Publication record

This handoff and implementation were prepared in
`C:\CLASSIFIRE\.tmp\phase8-assessment-contract-20260830` on
`gpt/phase8-assessment-contract-20260830`, based exactly on current
`origin/main` at `c8b06d1`.

The intended publication scope is exactly 30 files:

- four scripts:
  `compare_phase8_human_reference.py`,
  `recover_phase8_evidence_review_request.py`,
  `run_phase8_representative_package.py`, and
  `validate_phase8_human_adjudicated_proposal.py`;
- nine production service/validation files:
  `phase8_human_adjudicated_proposal.py`,
  `phase8_human_reference_comparison.py`,
  `phase8_openresponses_transport.py`,
  `phase8_property_assessments.py`,
  `phase8_proposal_review.py`,
  `phase8_visual_prompts.py`,
  `phase8_visual_proposal.py`, `physical_scope.py`, and
  `visual_validation.py`;
- eleven corresponding Phase 8 test files; and
- six documentation files: `docs/PROJECT_STATE.md`,
  `docs/CLASSIFIRE_ARCHITECTURE.md`, `docs/CLASSIFIRE_ROADMAP.md`,
  `docs/SESSION_HANDOFF.md`, `docs/PHASE8_REPRESENTATIVE_RUN_PACKAGE.md`, and
  `docs/PHASE8_HUMAN_REVIEW_V2_CONTRACT.md`.

The conflicted root, earlier overlapping assessment/report-context worktrees,
technical-intake continuation, `a3de490`, the dirty PR #75 continuation,
customer evidence, generated artifacts, and every other local worktree remain
excluded and untouched. No migration, dependency, configuration, UI, report,
image, database, token, or generated review file belongs in this publication.
