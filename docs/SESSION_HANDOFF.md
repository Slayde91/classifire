# CLASSIFIRE Session Handoff

**Verified:** 2026-08-30 (AEST)

**Status:** Pre-production prototype; PR #81 merged the contained report-evidence
adapter and narrow production-startup hardening, PR #82 merged migration
packaging plus production schema-readiness safeguards, and PR #83 merged the
technical-activation separation guard into shared main. There is still no
approved canonical Physical Model or active replacement Physical Model Lock.

PR #82 has no authority to upgrade a production, UAT, or customer database.

This handoff is a factual audit record. It does not grant authority to run inference, retrieve report evidence, write canonical data, sign or register an admission, create a lock, deploy, release, merge, or open a pull request.

## 1. Verified shared state

- `origin/main` is `ac7de2c6f544088de0092a3b4d9bfdc0aec64b6d`
  (PR #83). It contains the PR #74 application baseline, `db404b3` human-session
  hardening, the PR #79 recovery decision, PR #80's bounded assessment/review
  contract, PR #81's contained report-evidence adapter/startup hardening, and
  PR #82's migration packaging/schema-readiness boundary, and PR #83's
  technical-activation separation guard.
- Current shared-main Alembic state has one head: `0011_report_evidence_locators` on `legacy_adjudicated_lineage`. The technical-intake candidate migration is not on main.
- The final PR #81 `CLASSIFIRE pull request validation` workflow completed
  successfully for `4ebc531` at 2026-08-30 12:50:43 UTC: 500 tests passed,
  changed-file style passed, and one Alembic head was verified. The disposable
  PostgreSQL configuration enabled the shared-byte quarantine/read race.
- PR #82's `CLASSIFIRE pull request validation` workflow completed successfully
  for `9ad6ca7` at 2026-08-30 14:25:21 UTC. It validated the migration/CLI
  boundary before the PR merged at `e894a17`.
- PR #83's `CLASSIFIRE pull request validation` workflow completed successfully
  for `70f8df5` in 2m13s before the PR merged at `ac7de2c`.
- The report ownership/bytes, stable locators, deterministic review packages,
  report-aware assessment bindings, managed no-tool runtime, migration
  packaging, and production schema-readiness safeguards are shared-main source.
- Open GitHub work remains reviewable rather than automatically mergeable: PR #75 is open; PRs #9-#13 are retained draft stack work; issues #42 and #43 are open. Issue #42 still has stale site-visit-first wording.
- Current main has the secret-free pull-request workflow. Its successful PR #80 run
  is CI evidence for that exact head, not a blanket approval for later branches.
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
| Report assessment and cable semantics | **Merged in PR #80** | `property_assessments` v2, historical-v1 verification, manifest-bound reviews, and bundle/tray rules are shared-main source. They remain proposal-only and do not create canonical truth. |
| Report-evidence adapter | **Merged shared-main foundation** | PR #81 binds project ownership, verified clean bytes, report-SHA locators/scopes, deterministic review packages, and a guarded report transport/runtime. The disposable PostgreSQL shared-byte race passed in CI. |
| Governed technical intake | **Separate pushed candidate plus local continuation** | `d76562e` and `0edeaac` are not on shared main. Their worktree has proposed `0019` and substantial uncommitted follow-on material, so it is not a clean merge candidate. |
| Technical activation separation | **Merged shared-main hardening (PR #83)** | The existing UI workflow now requires `in_review`, a pending request, a different deciding user, and an approved linked source document before a variant can become active. It remains a narrow fail-closed guard, not full technical-intake authority or production proof. |
| Production startup boundary | **Merged narrow hardening** | Main rejects unsafe production configuration before filesystem or lifespan work and skips schema creation/administrator seeding in production. The remaining broad `a3de490` changes are still local-only and unreviewed. |
| Installed migration packaging and CLI bootstrap | **Merged shared-main hardening** | PR #82 moved immutable history under `classifire.migrations`; `classifire-migrate` explicitly upgrades only to its current head, while production CLI setup/import commands refuse to create schema or seed defaults. Production startup and database-writing CLI paths require the configured database to prove the exact packaged migration head before proceeding. Source, wheel, focused, full-suite, and PR CI checks used no production, UAT, or customer database. |
| Production browser configuration and diagnostics | **Validated current-branch candidate** | Documented CSV/JSON `trusted_hosts` and `allowed_origins` inputs parse correctly, while unsafe production host/origin configuration fails before lifespan storage work. The read-only `doctor` command reports only the database type and a generic connection failure, never a raw database URL or exception. This remains unshared-main code, not deployment or production proof. |
| Report review / UAT | **Proposal-only, authority-gated** | A report package can support cautious evidence assessment, but it cannot create technical compatibility truth, commercial truth, a canonical model, a lock, or a release. |

## 4. Start Here / Next Session

**Required first gate:** obtain separate authority for one controlled,
proposal-only report assessment, then human-review every resulting artifact.
PRs #81 and #82 are reviewed, merged, and CI-proven; their source publication
does not grant run authority.

**Recommended next engineering task:** obtain separate authority for one
controlled, proposal-only report assessment and human-review every resulting
artifact. It must not be used for canonical submission, technical selection,
pricing, locking, deployment, or release.

### Prerequisites for the next authorised step

1. Do not use or modify the root checkout.
2. The PR workflow supplies only a disposable PostgreSQL database for the
   containment race. A local rerun, if needed, must use a literal-loopback
   `CLASSIFIRE_POSTGRES_TEST_URL` for the dedicated
   `classifire_containment_test` database and set the explicit
   `CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN` acknowledgement. The test
   rejects any other host or database before it resets tables, and must never
   point at a project, production, or UAT database.
3. Keep the merged report adapter proposal-only; any controlled run must not
   acquire a canonical-write path.
4. Obtain separate authority before a controlled report assessment. Technical
   selection, pricing, canonical submission, lock creation, deployment, and
   release remain outside that authority.

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

### Completed candidate implementation order

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

**Candidate done means:** one contained branch change; one Project/Estimate-owned
report and package boundary; atomic safe-byte reads; stable documentary and
visual locators; exactly one safe review per selected Defect; passing focused,
database, full-suite, and static checks; inspected output; and no canonical or
downstream authority interface.

## 5. Then, in order

1. **Run the approved report package through the controlled report-only flow**
   only with separate run authority, then human-review every generated file.
2. **Continue Draft technical materialization separately.** Review proposed
   migration `0019` without silently activating a `TechnicalVariant`.
3. **Independently review the current production browser-boundary candidate.**
   Keep it separate from the broader `a3de490` work and do not treat it as
   deployment proof.
4. **Review or supersede PR #75 independently.** A mergeable label is not
   acceptance evidence.
5. **Keep canonical UAT, signed lock admission, downstream technical/commercial
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
