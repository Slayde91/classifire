# CLASSIFIRE Session Handoff

**Verified:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `73c428ea450d9bd17c51031187608c205e200ffd` (PR #185)
**Latest executable-change baseline:** 73c428e (PR #185)

All four maintained documents live under `docs/`. Repository evidence outranks
this snapshot; inspect newer source and publication before resuming.

## Start Here / Next Session

**Single first task:** review, finish and publish the existing ProjectPackage v1
Draft contract/exporter candidate. Do not start another implementation from scratch.

**Why next:** the optional journal/transport lifecycle is already merged. A Draft
package can work without AI and without pretending unresolved stages are approved.
This is the next bounded foundation for creating, editing and downloading whole
projects through shared ChatGPT and standalone application services.

**Prerequisites:** read applicable AGENTS.md, these four documents and
[Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md). Inspect
current HEAD, upstream, changes/conflicts, remote main, PRs and CI before editing.
Find the candidate with `git worktree list --porcelain`; verify it has not since
been superseded. Preserve the conflicted root and all unrelated local changes.

**Existing work:** branch `feat/project-package-draft-20260905`, worktree
`C:\CLASSIFIRE\.tmp\project-package-draft-20260905`, based on `73c428e`.
Three untracked files were verified:

- `docs/PROJECT_PACKAGE_V1_CONTRACT.md`;
- `src/classifire/services/project_package.py`;
- `tests/test_project_package.py`.

Its 22 existing synthetic tests passed in this documentation session. Static
checks, full regression, completeness review and publication remain unverified.
This candidate is not in shared main and was not edited in this session.

**Relevant shared components:** `src/classifire/models.py`,
`physical_models.py`, `services/project_evidence.py`, `services/snapshot.py`,
`services/proposal_review_package.py`, `services/technical_release_publication.py`,
`security.py`, `api/router.py` and related tests. Abbreviated paths are relative
to `src/classifire/`. The snapshot builder calls `recalculate_estimate`; do not
use it as an unexamined read-only extractor. Preserve exact clean-byte ownership
and the separate canonical-output/lock gates.

**Definition of done:**

1. Review the candidate against existing records and Decision 0001. Define exact
   declared membership, schema version, revision/parent identity, hashes,
   uncertainty, stage blockers and historical-only authority.
2. Prove deterministic archive bytes and semantic identity using a synthetic
   multi-estimate project with shared evidence and multiple openings/services.
   Inspect the manifest and members. Reject invalid schema/relationships,
   missing or altered bytes, unsafe/duplicate paths and prohibited contents.
3. Prove authorization refusal and exact content binding, including mutation
   after authorization. No permissive default, invented export rights, secrets,
   implicit restricted-library redistribution or canonical mutation.
4. State clearly that caller inventory is not database completeness proof and
   that an authorization callback is not an implemented permission policy.
   Complete source mapping/redaction and governed projection remain prerequisites
   to a real whole-project export. Do not claim download/import/UI completion.
5. Run focused and warranted regression/static checks, align all four docs,
   classify changes, commit explicit paths, push normally, open a PR, and merge
   only after passing CI and required reviews. Verify merge and post-merge CI.

**Blockers and dependencies:** membership completeness, export policy/redaction,
predecessor integrity and actual database extraction still need explicit proof.
Resolve routine choices from existing rules; surface a material permission or
product-policy decision that those rules cannot resolve. Storage/download,
quarantined import and shared clients follow this bounded contract slice.
Actual AI producer assurance is independently blocked; no package task permits
provider wiring, OpenClaw retirement, live canonical writes, locks or release.

### Validation commands

From the verified candidate worktree, use its source and disposable test storage:

~~~powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = ''
$packagePython = 'C:\CLASSIFIRE\.venv\Scripts\python.exe'
$packageTemp = Join-Path $env:TEMP ('classifire-package-' + [guid]::NewGuid().ToString('N'))
& $packagePython -m pytest -o addopts= -q -p no:cacheprovider --basetemp $packageTemp tests/test_project_package.py tests/test_snapshot.py
& $packagePython -m ruff check . --no-cache
& $packagePython -m mypy src
& $packagePython -m bandit -q -r src
& $packagePython -m alembic heads
git diff --check
~~~

Check each exit code before publication. Add evidence/permission/authority tests
matching the final changed callers; do not substitute this short baseline for
required coverage. Run Ruff after any formatting. Install declared development
dependencies in an isolated environment if required. Full hosted CI includes
PostgreSQL containment tests, Ruff, Mypy, Bandit and one Alembic head. Never point
destructive PostgreSQL fixtures at a project/UAT/production database.

## Recommended Prompt for New Session

~~~text
Continue CLASSIFIRE at C:\CLASSIFIRE (github.com/Slayde91/classifire). Before editing,
read AGENTS.md, the four maintained docs under docs/ and Architecture Decision 0001.
Inspect Git/worktrees, HEAD/upstream/conflicts/local changes; fetch and reconcile
main, PRs and CI. Verified baseline was 73c428e (PR #185), main CI 33941884582 passed
974 tests. Preserve the conflicted root and all unrelated work; use an isolated tree.

Single task: finish and publish the existing ProjectPackage v1 Draft contract/exporter.
Verify feat/project-package-draft-20260905 at C:\CLASSIFIRE\.tmp\project-package-draft-20260905.
It had three untracked files: docs/PROJECT_PACKAGE_V1_CONTRACT.md,
src/classifire/services/project_package.py and tests/test_project_package.py;
22 synthetic tests passed, but full qualification/publication was unfinished.
Reuse valid work; do not duplicate anything now merged. This is next because Draft
portability advances the product independently of optional AI and Human Release.

Inspect models.py, physical_models.py, services/project_evidence.py, snapshot.py,
proposal_review_package.py, technical_release_publication.py, security.py and
api/router.py under src/classifire/, plus relevant tests. Preserve domain stages,
uncertainty, provenance, ownership and authority. Snapshot building recalculates;
do not use it as a read-only extractor. Review membership, export rights/redaction,
revision lineage and schema before extending the candidate. Caller inventory does
not prove database completeness; a callback does not establish permission policy.

Done: inspected deterministic multi-estimate archive, exact semantic/byte hashes,
shared evidence and opening/service relationships, explicit unresolved stages,
refusal of invalid schema/ownership/paths/bytes/rights and post-authorization mutation,
no canonical mutation, aligned docs and passing required CI. Database projection,
storage/download, import and clients remain later slices; do not claim them done.
Surface only material policy decisions unresolved by existing rules; avoid speculation.

Run new package tests, tests/test_snapshot.py and affected evidence/authority tests,
Ruff after formatting, Mypy, Bandit, Alembic heads and diff checks with worktree-local
PYTHONPATH and unique temporary storage; full hosted CI must pass. Continue
autonomously through implementation, validation, classification, explicit commit,
normal push, PR and merge where safe after checks/reviews; verify merge/main CI.
No customer/provider run, live canonical write, lock, deployment, release or
OpenClaw retirement. Keep AI optional and all existing protections intact.
~~~

## Verified project and publication context

PR #185 merged optional begin/complete/abort journal hooks into both transports.
[Exact main CI](https://github.com/Slayde91/classifire/actions/runs/33941884582)
passed 974 tests with 141 warnings. The existing completion consumer, execution
journal, deterministic domain services and governance remain. Managed AI still
lacks authenticated production capture assurance; generic worker handling and
recovery are incomplete. No full fleet replacement or production readiness is proven.

This session changed documentation only on `docs/package-target-handoff-20260905`
in `C:\CLASSIFIRE\.tmp\docs-package-target-handoff-20260905`, based on `73c428e`.
Publication of this documentation must be checked in Git/PR history; it is not
proof of publication of the separate package implementation.

- Protected root: branch `gpt/phase8-linked-original-images`, HEAD `de0cc5a`,
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`. Four conflicts:
  phase8_linked_visual_run and phase8_visual_evidence services and their tests.
  Staged additions, unstaged changes and untracked legacy material are unrelated
  recovery evidence. Protected pytest directories limit untracked enumeration.
  Never reset, clean, bulk-copy or publish this root.
- Package worktree: three untracked implementation files, unfinished and separate.
- Documentation worktree: only the four requested maintained documents changed.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw development dependency
  advisories) remain open. PRs #9-#13 remain legacy draft feature-to-feature work;
  do not bulk-merge them. No other open PR was returned at verification.
- Historical UAT failure and absence of a replacement lock were not rechecked
  against live records. Phase 8 evidence/authority gates and downstream phases
  remain; database/storage are live truth and packages convey no new authority.

Related: [Project State](./PROJECT_STATE.md),
[Architecture](./CLASSIFIRE_ARCHITECTURE.md), [Roadmap](./CLASSIFIRE_ROADMAP.md).
