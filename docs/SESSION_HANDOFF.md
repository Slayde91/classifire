# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST).
**Shared-main baseline:** `e17cec31b571bbcec5153df95c9d4f35b16ed348`, merged
[PR #189](https://github.com/Slayde91/classifire/pull/189).
[Main CI 33949738802](https://github.com/Slayde91/classifire/actions/runs/33949738802)
passed on that exact commit (1,072 tests, 141 warnings).
**P4a branch/worktree:** `feat/draft-scope-reports-20260905` at
`C:\CLASSIFIRE\.tmp\draft-scope-reports-20260905`.
**Architecture:** accepted ADR 0001 + approved ADR 0002; prototype-first delivery.
Final P4a artifact/restart, combined regression, migration and static checks passed.
This checkpoint precedes publication. Verify its exact commit/PR/CI/merge before
carrying this snapshot into another session.

## Start Here / Next Session

**First finish the current P4a verification/publication if still outstanding.**
Do not abandon these implemented reporting changes or start a competing branch.
Then the **single next product task is P2a: an independently saved System Match
candidate-review workspace** consuming a selected Scope revision and a governed
technical release. Provide a real inspect/keep/reject/save/reopen/download UI.

**Why next:** P0 editing and P1a JSON exchange are merged; P4a adds a second useful
independent capability. The existing technical library and release checks can supply
candidates without creating an Estimate or canonical Opening. Source ingestion
still needs a real scan producer and storage/retention work. Its absence does not
block a synthetic, unapproved candidate-review prototype over existing valid inputs.
Candidate review is a bounded step toward matching, not complete applicability.

### Inspect before editing

Read `AGENTS.md`, `GOAL.md`, `docs/PROJECT_STATE.md`, the architecture, roadmap,
ADRs 0001/0002 and Draft Scope/report contracts. Inspect branch/HEAD/upstream,
status/diffs/conflicts/worktrees, current main and relevant PR/CI. Reconcile newer
source, tests and runtime evidence before editing. Preserve the conflicted root,
unrelated work and package candidate; use a clean current-main worktree after P4a
publication. Do not rebuild P0/P1a/P4a or seek approval for the accepted architecture.

### P2a minimum input/output contract

- Input: explicit local Scope artifact/revision/hash and technical-release ID/hash;
  owner/admin access and `technical:read` permission are checked by the backend.
- Candidate entries bind stable Scope service/opening IDs to variant/document/source
  references and page/table/figure locators. Record the selected release and source
  identity, not just a current search query or chat context.
- Show a criteria checklist covering material/size, opening/configuration,
  substrate/thickness, plane/orientation, FRL, insulation and installation limits/
  exclusions. Missing facts and unsupported checks stay unresolved. v1/v2 Scope
  does not contain every required field; do not manufacture them.
- Users retain/reject candidates and enter reasons as unapproved review decisions.
  Never treat text ranking as compatibility or confidence. P2a produces unapproved candidates only;
  Applicable decisions belong to P2b, after its evidence and criteria requirements.
- Output: a versioned Draft System Match candidate-review artifact, with dependency
  hashes, candidates, criteria/findings, review notes, local actor/time, predecessor
  identity and checksum. Save/reopen/download exact JSON; do not start estimating.
- Later Scope revision/hash, superseded/ineligible release or changed source
  binding/validity makes the dependency stale. Preserve earlier artifact bytes and
  explain the change; do not silently rerun, overwrite or promote it.

### Relevant files and prerequisites

- `src/classifire/services/draft_scope.py`, `draft_scope_ui.py`, current templates
  and tests: saved v1/v2 inputs, ownership, CSRF, revision/CAS and output patterns.
- `src/classifire/services/technical.py`: `search_variants` ranks five text fields.
  Use it only for retrieval. `search_for_opening` requires canonical Opening/Estimate;
  do not fabricate those records to enter the independent capability.
- `src/classifire/services/release_scope.py`:
  `active_technical_release_ids(db, release)` validates an explicit release without
  an Estimate. `release_pinning.active_release` can locate the current release;
  capture its ID/hash explicitly. The reusable release check permits legacy unbound
  records and older manifests; missing source authority remains unresolved in P2a.
- `src/classifire/services/technical_validity.py`,
  `technical_release_publication.py`, `technical_admin.py`, `release_admin.py` and
  `models.py`: existing source, lifecycle, authority and review boundaries. Link to
  existing technical-source detail screens; do not manufacture technical approvals.
- `tests/test_technical_release_publication.py`,
  `test_technical_import_governance.py`, `test_technical_source_authority_display.py`
  and existing Draft/import/report tests: retain these while adding focused P2a tests.
- `scripts/run_draft_scope_demo.py` and `docs/DRAFT_SCOPE_DEMO.md`: synthetic UI
  launcher. Verify its current options and storage before use; never use customer DBs.

A small synthetic governed library can demonstrate the workflow. Fixture approval
is not evidence of approved customer material. Missing real library evidence must
produce a useful unresolved state, not a hard-coded successful match. No AI,
canonical physical admission, estimating, operational release or deployment is needed.

P1b remains upcoming with an actual scanner producer, verified retained bytes,
PostgreSQL clean-read serialization, retention policy and safe concurrent upload
handling outstanding. `save_upload` records pending/not_configured, and `worker.py`
has no registered processing handler. An optional scanner dependency alone does
not establish working intake. Preserve these guards and report the limitation.

### Definition of done for P2a

1. A fresh authenticated synthetic UI session selects a saved Scope/release, sees
   real library candidates and missing criteria, inspects references, retains or
   rejects alternatives with reasons, saves/reopens and downloads the same artifact.
2. Shared services enforce ownership, technical permissions, valid dependency
   identities, stable many-to-many Scope links and stale-save refusal. No text score,
   manual selection or foreign history becomes technical approval.
3. Tests cover exact allowed release membership, tampered/wrong-type/inactive/missing
   releases, unsafe/expired/missing source bindings and unresolved legacy sources.
   Unknown criteria never produce Applicable; no canonical writes or estimation run.
4. Stale-dependency tests change Scope revision/hash, release status/identity and
   source binding/validity. Existing JSON remains unchanged, the UI explains why it
   is stale, and nothing automatically reruns or overwrites the artifact.
5. Relevant service/UI/security/authority and any forward-migration checks pass;
   inspect the real browser interaction and downloaded JSON. Update factual docs.
6. Classify the full diff, commit/push normally, create/update the PR and merge only
   after exact-head CI and required review permit it. Verify merge and main CI.

This completes only P2a, not full technical matching, all four capabilities,
production readiness or the active product goal. Do not add placeholder success
screens or defer the entire user interaction in favor of schema work alone.

### Validation commands

Run from the isolated worktree with current declared dependencies installed:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$taskTestBase = Join-Path $env:TEMP ('classifire-candidate-review-' + [guid]::NewGuid().ToString('N'))
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTestBase tests/test_technical_release_publication.py tests/test_technical_import_governance.py tests/test_technical_source_authority_display.py tests/test_draft_scope.py tests/test_draft_scope_import.py tests/test_draft_scope_ui.py tests/test_draft_scope_import_ui.py tests/test_draft_scope_reports.py tests/test_draft_scope_reports_ui.py tests/test_draft_scope_outputs.py tests/test_human_session_security.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -r src
git diff --check
```

Add new P2a service/UI tests to the command once created and run syntax checks for
any changed JavaScript. Direct existing public-helper coverage is
`test_technical_release_publication.py::test_publication_snapshots_every_active_variant_and_supersedes_atomically`.
Also retain the same file's exact-manifest and changed-retained-byte tests and
`test_technical_import_governance.py::test_pinned_technical_release_rejects_source_lineage_drift`.
Add direct candidate-adapter failure tests rather than relying only on pinned
Estimate tests. Synthetic release creation must use test fixtures/governed helpers.

If the migration head changes, reconcile deployment-lineage/current-head fixtures
and run the full migration and affected preflight collection. Preserve historical
migration cases. Local PostgreSQL skips are not passes; hosted CI must exercise its
configured disposable database. Mypy requires declared stubs. No real-report UAT,
provider execution, customer `doctor` run, deployment or release is authorized.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE's approved hybrid, independent-capability, prototype-first plan.
Inspect AGENTS.md, GOAL.md, project state, architecture, roadmap, handoff and ADRs;
verify current source/Git/worktrees/diffs/main/PR/CI BEFORE editing. Shared baseline
was e17cec3, merged PR #189. Finish any outstanding P4a report verification/publication
on feat/draft-scope-reports-20260905 first. Preserve the conflicted C:\CLASSIFIRE root,
unrelated changes and package candidate; then use an isolated current-main worktree.

Single next product task: P2a, a saved System Match candidate-review UI. Consume an
explicit Scope v1/v2 revision/hash and governed technical-release ID/hash. Reuse
services/draft_scope.py, technical.py, release_scope.active_technical_release_ids,
technical_validity.py, technical_admin.py and existing UI/security/revision patterns.
No Estimate or canonical Opening is required. Text ranking is retrieval only;
missing material/size/FRL/insulation/configuration or source authority stays unresolved.
Never label relevance, manual selection or imported claims technical approval.
P2a produces unapproved candidates only; Applicable decisions remain P2b work.

Deliver real candidate/reference inspection, retain/reject with reasons, versioned
Draft save/reopen/exact JSON download, owner/technical permissions and CAS protection.
Preserve stable Scope links and source provenance. Scope/library/source changes mark
dependencies stale without altering older bytes or automatically running estimating.
Use synthetic governed-library fixtures; legacy unbound sources stay unresolved.
P1b actual scanning/retention remains required but is not this prototype's prerequisite.

Done: meaningful new service/UI/stale-dependency tests plus technical release/import
and existing Draft/report/authority regressions pass; static/migration checks pass;
a real browser session and downloaded JSON are inspected. Use handoff commands and
isolated storage/PYTHONPATH. Update docs, classify changes, then autonomously commit,
normal push, PR and merge after exact-head CI/reviews permit; verify merge/main CI.
No speculative infrastructure, customer data, AI execution, canonical writes,
operational release or deployment. Report actual evidence, limitations and Git state.
```

## Current P4a evidence and remaining publication work

- Local report service/model/renderers and browser routes are implemented. A new
  `DraftScopeReport` row freezes one selected Scope plus project labels and render
  version, and atomically retains both PDF/XLSX byte streams with hashes.
- Candidate head: `0028_draft_scope_reports`; each output is bounded to 8 MiB.
  The newest 20 reports are listed; older report IDs remain readable. No new
  framework, database or library dependency was added.
- Tests recorded so far: **50 report service passes and one local PostgreSQL skip;
  16 report HTTP passes; 7 output passes**. Combined import/UI/report/authority
  regression: **124 passed**. Full migration/deployment/preflight: **43 passed**.
  Full Ruff, Mypy (149 files), Bandit, JavaScript syntax and whitespace checks passed.
  Existing Starlette/Alembic warnings remain; hosted CI must cover PostgreSQL.
- HTTP tests verified both formats, v1/v2 lineage, immutable historical downloads,
  changed-project/Scope stale indication, ownership, CSRF, revoked sessions and
  corruption refusal. The detected ReportLab logo sizing error was corrected.
- The synthetic browser exercised v2 import, revision 2 reporting, PDF/XLSX download
  and revision 3 stale indication with old bytes unchanged. Three normal PDF pages,
  four long-text pages and nine Excel tabs were visually inspected. Native Excel
  was opened read-only because the available workbook renderer was not compatible
  with Windows. The final title correction is visually verified. Regenerated
  final files passed an actual server restart with identical bytes and no page errors.
- Final PDF SHA-256: `1ed6dbd5f4beda3f720b8095e265bc4899891f2b84c20a0e550fb812c37e6cde`.
  Final XLSX SHA-256: `c20f1e826854f8fb17424c5376dc5d171ffddc91384c0c21be2b1abb6e480dc8`.
  Snapshot SHA-256: `4a331ad21e131eeae4802176f893c3890b6f94604de1b28e173d698852c679fc`.
  Three imported-source records remain unverified. The isolated demo contains four
  Drafts, 11 revisions and three reports; all canonical physical/estimate/lock counts
  remain zero. See the demo guide and local receipts for the selected report link.
- Before publication: inspect/classify the full diff, then commit/push/PR/merge only
  after passing required exact-head checks. Verify main afterward; no P4a merge is claimed here.

## Local context and preserved work

- P4a worktree: `C:\CLASSIFIRE\.tmp\draft-scope-reports-20260905`, branch
  `feat/draft-scope-reports-20260905`, base `e17cec3`. The documentation checkpoint precedes publication; verify current HEAD.
  Changes include reporting, migration 0028, related current-head/deployment fixtures,
  tests and aligned documentation. Do not treat those related fixture updates as
  unrelated work or weaken historical migration assertions.
- Synthetic report artifacts are under `.tmp/draft-scope-report-artifacts`; long
  text/hostile output QA under `.tmp/draft-scope-report-output-qa`. Prior import
  artifacts/tools remain local. Keep generated files, databases and cookies out of Git.
- P0 `.tmp/draft-scope-ui-20260905` and P1a `.tmp/draft-scope-import-20260905`
  worktrees are clean and unchanged. P1a merged as `e17cec3` through PR #189.
- Protected root: `gpt/phase8-linked-original-images`, HEAD `de0cc5a`,
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`, four linked-visual
  conflicts and staged/unstaged/untracked recovery work. Do not reset, clean,
  resolve, broadly stage or publish from it.
- `.tmp/project-package-draft-20260905` retains three unrelated untracked files:
  contract, `services/project_package.py` and tests. Prior 22 synthetic passes are
  historical evidence only; this increment does not requalify that candidate.
- Historical issues #42/#43 and draft PRs #9-#13 are recovery/operations context;
  query their current state when relevant. No real provider/UAT/lock/release or
  deployment operation was authorized or exercised by this reporting increment.

Use [PROJECT_STATE.md](./PROJECT_STATE.md) for facts and health,
[the roadmap](./CLASSIFIRE_ROADMAP.md) for sequencing and
[the architecture](./CLASSIFIRE_ARCHITECTURE.md) for boundaries.
