# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST).
**Shared-main baseline:** `3b437dad9e42ec7ba2adf512b8ee67816d243473` (PR #186).
**Executable baseline:** `73c428e` (PR #185).
**Architecture:** ADR 0001 + explicitly approved ADR 0002; prototype-first delivery.

## Start Here / Next Session

**Single first task: implement P0, the persisted Draft Scope workspace in the
existing UI.** Users must be able to create/open a project, manually edit a Draft
scope, validate, save, reopen after restart and download its exact versioned JSON.
Build the minimum shared data contract and storage with that screen. A schema-only
or backend-only result does not finish this task.

**Why next:** the source already has a FastAPI/Jinja application, authentication,
projects and domain foundations. The independent Draft Scope workflow is missing.
The user has approved four independent capabilities and explicitly prioritizes
an interactive prototype over broad refinement. The old instruction to finish
all package infrastructure before UI is superseded. Do not seek approval again
for ADR 0002 or require production OpenClaw assurance for manual P0.

### Inspect before editing

Read tracked `AGENTS.md`, `GOAL.md`, the four maintained docs under `docs/` and
ADRs 0001/0002. Check current branch/HEAD/upstream/conflicts, fetch main, and
reconcile PRs/CI/newer implementation before selecting edits. Use an isolated
current-main worktree; preserve unrelated work and the conflicted legacy root.
Verify actual publication of PR #187 rather than treating approval as a merge.

Relevant components:

- `src/classifire/main.py`, `ui.py`, `templates/base.html`, project/estimate
  templates and `proposal_review_admin.py`: extend existing navigation/forms.
- `security.py`, `db.py`, `models.py`, `physical_models.py`: reuse authentication,
  CSRF, ownership, persistence and rules. Existing opening/service forms write
  canonical rows; never weaken their guards to obtain a Draft editor.
- `services/project_evidence.py`, `services/proposal_review_package.py`,
  `services/snapshot.py` and `api/router.py`: reuse only compatible validation/
  storage patterns. A review package is not a Scope Package; snapshot building
  recalculates, and canonical output routes keep their lock requirements.
- `tests/test_human_session_security.py`, `test_physical_api_boundary.py`,
  `test_initial_canonicalisation_boundary.py`, `test_snapshot.py`: existing
  synthetic UI/security and canonical-boundary regression patterns.

Abbreviated paths above are relative to `src/classifire/` or `tests/` as stated.
Check exact current filenames; do not invent implementation claims from this list.

### Existing work to preserve

The package candidate is at `C:\CLASSIFIRE\.tmp\project-package-draft-20260905`,
branch `feat/project-package-draft-20260905`, based on `73c428e`. It had three
untracked files: `docs/PROJECT_PACKAGE_V1_CONTRACT.md`,
`src/classifire/services/project_package.py`, `tests/test_project_package.py`.
The earlier documentation review ran its 22 tests successfully; this session
has not changed or fully qualified it. Inspect and reuse compatible concepts
selectively without discarding its originals or making generic ZIP publication
a dependency of P0. Do not claim that declared membership proves DB completeness.

### Definition of done for P0

1. A real authenticated screen is reachable from existing navigation. In isolated
   synthetic storage, create/open a project and manually enter a Draft with one
   defect, multiple openings/services, a blank opening, dimensions/units and an
   unresolved observation. Manual attribution and Draft status are visible.
2. Users can edit and validate fields/relationships, see readable errors and
   unresolved findings, save a revision, reload, restart the isolated app and
   reopen the same data. Stale saves cannot silently overwrite newer revisions.
3. Download the selected saved Scope JSON with stable IDs, schema/revision/hash,
   declared evidence/manual provenance, uncertainty and blockers. Inspect and
   validate the bytes; editing later cannot change a previous downloaded revision.
4. Use shared application validation/persistence rather than UI-only logic. Map
   exact Draft read/write/export authority and object ownership; no permissive
   default based merely on a role name. Keep Draft records distinct from guarded
   canonical physical state and do not activate imported/manual approvals.
5. Prove login/CSRF and object-access refusal, invalid relationships/schema,
   malformed/bounded input, stale-save refusal, restart persistence and safe
   download behavior. Prove no automatic AI, matching, pricing, canonical physical
   promotion, lock or release. Fix supported-path correctness/security failures.
6. Run targeted service/HTTP tests and affected guard regressions; inspect the
   actual browser flow and downloaded artifact. Record commands, results and
   remaining limitations. Align docs and complete normal Git/PR/CI/merge workflow.

Safe import/replacement, automated report extraction, other capability workspaces,
PDF/XLSX profiles, complete ProjectPackage ZIP, generalized jobs and ChatGPT are
later bounded slices. Do not expand P0 to all of them. A restricted, honestly
labeled prototype is acceptable; a fake screen or silent missing work is not.

### Prerequisites, decisions and blockers

There is no unresolved architecture-approval blocker. P0 needs a minimal Draft
schema/storage mapping and explicit access policy chosen from verified existing
boundaries. Make the smallest coherent change, using forward migrations if
required; do not invent a new database/framework or bypass physical guards.
Only material permission/data-policy decisions uncovered during implementation
may need clarification. Existing production/provider/UAT blockers do not block
synthetic manual P0. No real customer evidence or operational authority is granted.

### Validation and isolated demo

The existing interpreter is `C:\CLASSIFIRE\.venv\Scripts\python.exe`; use its
source/dependencies only after verification or install declared dev dependencies
in an isolated equivalent. Example existing regression baseline:

~~~powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$prototypePython = 'C:\CLASSIFIRE\.venv\Scripts\python.exe'
$prototypeTemp = Join-Path $env:TEMP ('classifire-prototype-' + [guid]::NewGuid().ToString('N'))
& $prototypePython -m pytest -o addopts= -q -p no:cacheprovider --basetemp $prototypeTemp tests/test_human_session_security.py tests/test_physical_api_boundary.py tests/test_initial_canonicalisation_boundary.py tests/test_snapshot.py
& $prototypePython -m ruff check . --no-cache
& $prototypePython -m mypy src
& $prototypePython -m bandit -q -r src
& $prototypePython -m alembic heads
git diff --check
~~~

Add the new Draft service/UI tests and any changed storage/permission/migration
regressions. Check each exit code. Run Ruff after formatting. Full hosted CI and
required reviews must pass; never run destructive PostgreSQL fixtures against
project/UAT/production databases.

For the browser demo, explicitly configure a disposable database, storage path,
synthetic user/project and unused loopback port before startup. Inspect settings
first: development startup can create tables/seed data. Do not inherit the root
`.env`, start against existing data, or claim a browser inspection that was not
performed. Record reproducible startup/teardown and the actual demo evidence.

## Recommended Prompt for New Session

~~~text
Continue CLASSIFIRE at C:\CLASSIFIRE (github.com/Slayde91/classifire). Before editing,
read AGENTS.md, GOAL.md, the four docs under docs/ and ADRs 0001/0002. ADR0002 is
approved; the user prioritizes a working UI prototype before broad refinement.
Inspect Git/worktrees, HEAD/upstream/conflicts/local changes; fetch/reconcile main,
PRs and CI. Verified baseline was 3b437da (PR186), main CI33943428434 passed 974 tests;
verify publication/newer changes from PR187. Preserve the conflicted root and all
unrelated work; use an isolated current-main tree. Do not redo merged work.

Single task: P0 persisted Draft Scope workspace in the existing FastAPI/Jinja UI.
Deliver create/open project, manually edit distinct defects/openings/services and
uncertainty, validate, save/reopen after restart, and download exact saved versioned
Scope JSON. Build only the minimum shared schema, persistence and permissions needed
for this screen. No schema-only/backend-only completion or all-four-capability rewrite.

Inspect src/classifire/{main.py,ui.py,security.py,models.py,physical_models.py,db.py},
templates, proposal_review_admin.py, services/project_evidence.py,
services/proposal_review_package.py, services/snapshot.py and api/router.py. Existing physical forms
write guarded canonical rows: keep Draft storage/authority separate. Snapshot building
recalculates; preserve canonical export locks. The untracked three-file package
candidate at .tmp/project-package-draft-20260905 had 22 passing tests; inspect/reuse
compatible work without discarding it or requiring full ZIP infrastructure before UI.

Done: observed synthetic browser create/edit/validate/save/restart/reopen/download;
inspected stable IDs/revision/hash, explicit Draft/provenance/uncertainty, valid graph;
auth/CSRF/object-access, invalid-input, stale-save and safe-download tests; no automatic
AI/matching/pricing/canonical promotion/locks/release. Use shared services and explicit
Draft access policy. Fix supported-path defects; defer broad formats/polish/edge cases.

Run new service/UI tests and affected regressions including human_session_security,
physical_api_boundary, initial_canonicalisation_boundary and snapshot; Ruff after
formatting, Mypy, Bandit, Alembic heads, diff checks and full required CI. Use worktree
PYTHONPATH and disposable synthetic DB/storage/port; inspect settings before startup.
Update docs; continue autonomously through implementation, validation, classification,
explicit commit, normal push, PR and merge when checks/reviews pass; verify merge/CI.
No real customer/provider run, protected canonical write, lock, deployment, release or
OpenClaw retirement. No repeat approval request for ADR0002. Raise only genuinely new
material policy blockers; full package/import/other capabilities are later slices.
~~~

## Session evidence and local classification

This documentation session verified main `3b437da`, successful exact main CI,
PR #187's proposal head/CI, open legacy draft PRs #9-#13 and issues #42/#43. It
reviewed code, architecture/roadmap and local work; no runtime, provider, database,
new prototype tests or browser run occurred. Documentation checks and revised PR
CI/publication are reported separately; source presence is not prototype proof.

- Current branch: `docs/four-capability-architecture-review-20260905`, worktree
  `C:\CLASSIFIRE\.tmp\four-capability-architecture-review-20260905`. PR #187 is
  being updated from proposed ADR to accepted architecture plus prototype roadmap.
  Verify actual current commit/merge rather than treating this text as publication.
- Protected root: branch `gpt/phase8-linked-original-images`, HEAD `de0cc5a`,
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`; four linked-visual
  service/test conflicts and other staged/unstaged/untracked legacy work. Untouched.
- Package candidate: three untracked files in its own worktree; untouched.
- New tracked root AGENTS.md/GOAL.md are maintained project instructions/outcome,
  not edits to the protected root copy or external attachment/goal state.

Related: [State](./PROJECT_STATE.md), [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Goal](../GOAL.md).
