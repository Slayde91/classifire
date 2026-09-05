# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `bdd67198728e2da18171cdc4a3bea143328254ef` (PR #184)
**Latest executable-change baseline:** bdd6719 (PR #184)

All four maintained documents are under `docs/`. Inspect current repository
evidence before editing; this handoff records a snapshot, not live authority.

## Start Here / Next Session

**First task:** after verifying lifecycle publication, implement ProjectPackage v1
membership/schema validation and deterministic Draft export. This is shared
domain/service work, independent of AI, UI and ChatGPT transport.

**Why next:** synthetic journal/transport integration is proven in the candidate;
actual provider assurance remains unresolved. Decision 0001 section 2.5 permits
Draft exports that preserve unresolved stages and confer no authority. Current
code has Project/Estimate/evidence and estimate/proposal exports, but no complete
portable ProjectPackage contract. This slice advances the intended product without
making package access depend on optional AI.

**Prerequisites:** read applicable AGENTS.md, four docs, Decision 0001 and
completion contract; inspect branch/upstream/HEAD/conflicts, fetch main and check
PRs/CI before editing. Verify publication of `feat/phase8-journal-lifecycle-20260905`
in `C:\CLASSIFIRE\.tmp\phase8-journal-lifecycle-20260905`, based on `bdd6719`.
Preserve unrelated/root work and use an isolated current-main tree.

**Relevant components:** `src/classifire/models.py` (Project, Estimate, StoredFile,
ProjectEvidence and related records), physical models, `services/project_evidence.py`,
`services/snapshot.py`, `services/proposal_review_package.py`,
`services/technical_release_publication.py`, existing export routes in
`api/router.py`, storage/security/permission conventions, and their tests.
These paths are relative to `src/classifire/`. Extend existing abstractions before
adding a new database, orchestration framework or parallel business logic.

**Definition of done:**

1. Inventory complete project membership and map each item to source-of-truth
   records, exact evidence identity, lifecycle, ownership and export rights.
   Distinguish included bytes, authorized references and explicit withheld items.
   Do not silently omit data and call a narrow review/estimate export complete.
2. Define versioned manifest/schema, semantic validation and immutable revision/
   parent identity. Preserve physical/technical/commercial separation, provenance,
   unresolved evidence, review state and blockers. Imported authority is historical
   evidence only. Unknown schema/invalid relationships/conflicting hashes fail closed.
3. Implement deterministic Draft archive generation from validated, explicitly
   authorized inputs using shared services. Stable semantic content produces stable
   archive bytes/hash; volatile transport metadata cannot change semantic identity.
   Reject unsafe paths, duplicate archive members and missing/altered required bytes.
4. Preserve confidentiality: no credentials, raw secrets or automatic export of
   restricted technical/commercial libraries. Record material unresolved export-
   policy decisions explicitly; do not silently grant redistribution authority.
5. Test a synthetic project with multiple estimates/services/openings/relationships,
   retained evidence and unresolved stages. Inspect archive members and manifest,
   verify deterministic output, exact hashes, policy refusal and no canonical
   mutation. An empty/incomplete package fixture alone is insufficient proof.
6. Run new/focused package and warranted evidence/snapshot/authority regressions,
   Ruff/Mypy/Bandit, one Alembic head and full hosted CI. Align docs; classify,
   commit, push, PR and merge where safe after checks/reviews; verify actual merge
   and post-merge CI. Storage/download, import and shared interfaces remain later
   bounded slices unless already covered by the verified current implementation.

**Blockers/limits:** full package membership/export rights are not yet defined.
Resolve within existing authority; surface any material policy decision that
cannot be inferred. No real customer/provider/canonical write, lock, deployment
or release is authorized. Actual producer assurance and managed AI wiring remain
blocked independently; do not weaken their controls to make package tests pass.

### Validation commands

Run from the clean worktree with its own `src` first. The interpreter below
was verified locally; use a clean equivalent if unavailable. No credentials
are needed for this synthetic baseline.

~~~powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$contractPython = 'C:\CLASSIFIRE\.venv\Scripts\python.exe'
$contractTemp = Join-Path $env:TEMP ('classifire-contract-' + [guid]::NewGuid().ToString('N'))
& $contractPython -m pytest -o addopts= -q -p no:cacheprovider --basetemp $contractTemp `
  tests/test_phase8_journal_lifecycle.py `
  tests/test_phase8_journal_lifecycle_postgresql.py `
  tests/test_execution_journal.py `
  tests/test_execution_journal_postgresql.py `
  tests/test_phase8_openresponses_transport.py `
  tests/test_phase8_report_openresponses_transport.py `
  tests/test_phase8_visual_runtime.py `
  tests/test_phase8_report_assessment_controller.py `
  tests/test_phase8_report_assessment_runner.py `
  tests/test_openclaw_admission_writer_manifest.py `
  tests/test_phase8_admission_only_profile.py `
  tests/test_agent_security_boundary.py `
  tests/test_phase8_report_runtime_input.py `
  tests/test_phase8_report_assessment_prompts.py `
  tests/test_phase8_representative_run.py `
  tests/test_run_phase8_representative_package.py
& $contractPython -m ruff check . --no-cache
& $contractPython -m mypy src
& $contractPython -m bandit -q -r src
& $contractPython -m alembic heads
git diff --check
~~~

This is the verified orchestration regression baseline, not the only package
validation. Select new package and relevant evidence/snapshot/authority tests
from current source. Check each command's exit code before continuing.
Hosted `.github/workflows/pull-request-validation.yml` runs full pytest, Ruff,
Mypy, Bandit and one Alembic-head validation with disposable PostgreSQL.
Run broader local regression when changed shared behaviour warrants it.
Never point destructive PostgreSQL tests at project/UAT/production databases.
Do not run `classifire doctor` against a real configured environment merely
for this synthetic task.

## Recommended Prompt for New Session

~~~text
Continue CLASSIFIRE at C:\CLASSIFIRE (https://github.com/Slayde91/classifire).
Before editing read AGENTS.md, four docs under docs/ and Decision 0001. Inspect
HEAD/upstream/conflicts/local changes; fetch main and check PRs/CI. Verified main
was bdd6719 (PR #184), CI 33940542172 passed. Verify actual publication of
feat/phase8-journal-lifecycle-20260905 in
C:\CLASSIFIRE\.tmp\phase8-journal-lifecycle-20260905 and reconcile newer source.
Preserve the conflicted root and unrelated work; use an isolated current-main tree.

Single next task: ProjectPackage v1 membership/schema validation and deterministic
Draft export. Decision 0001 permits Draft exports without completed AI or Human
Release. Existing estimate/proposal exports are not the complete project contract.
Inspect models.py, physical_models.py, project_evidence.py, snapshot.py,
proposal_review_package.py, technical_release_publication.py, api/router.py and
their storage/permission tests under src/classifire/ and tests/.

Inventory complete project membership, ownership and export rights before coding.
Define versioned manifest, semantic validation, immutable revisions/parent hashes,
exact evidence membership and deterministic archive generation from authorized
inputs. Preserve unresolved stages, provenance and review/authority status.
No silent omissions or implied technical/commercial redistribution rights.
Imported approvals/locks remain historical, never active local authority.
Extend existing services; avoid a new database or parallel business pipeline.

Done: synthetic multi-estimate/project export with multiple services/openings,
evidence and unresolved stages; inspected manifest/archive; deterministic bytes/
hashes; refusal of wrong ownership, unsafe/duplicate paths, altered/missing
evidence, invalid relationships/schema and prohibited members; no canonical
mutation; aligned docs. Clarify any material export-policy choice that existing
authority cannot resolve, while completing independent safe work.

Run new package and relevant evidence/snapshot/authority regressions, warranted
handoff baseline tests, Ruff/Mypy/Bandit, Alembic heads and diff checks with
worktree PYTHONPATH and unique temporary storage. Full hosted CI must pass.
No real customer/provider operation, canonical write, lock, deployment, release
or OpenClaw retirement. Managed AI remains gated on actual producer assurance.
Continue autonomously through implementation, validation, classification, explicit
commit, normal push, PR and merge where safe after CI/reviews; verify merge and
post-merge CI. Do not duplicate newer completed work.
~~~

## Verified project context

PR #184 merged at bdd6719 with
[successful exact main CI](https://github.com/Slayde91/classifire/actions/runs/33940542172).
The lifecycle candidate adds optional shared visual/report pre-dispatch capture
and post-response durable completion. Begin/complete/abort reuse the journal and
retain producer-owned execute. Verifier-only injection remains compatible;
conflicting configuration is refused. Managed factories are not wired.

Local validation: 222 tests passed; seven guarded disposable PostgreSQL cases
were skipped locally for hosted CI. Ruff, Bandit, Mypy (143 files) and one
Alembic head passed. Eight existing Pillow warnings remain. Tests inspect database
state during HTTP and before successful return, plus cleanup, duplicates and
interruption. No real provider/customer/canonical database was used.

Implemented foundations include evidence ownership/locators, proposal controllers
and review packages, signed physical amendments and separate replacement locks,
technical-library publication, snapshot integrity and basic estimate outputs.
The worker has no handlers and does not honour run_after. Durable hybrid
execution, full ProjectPackage portability and production ChatGPT/standalone
package flows remain planned. The database/storage remain live truth; exported
packages will be immutable interchange revisions, not imported authority.

Historical UAT failure/rollback and absence of an accepted replacement lock were
not rechecked against live records. Phase 8 authority/evidence/semantic gates and
downstream Phases 9-14 remain. See [Project State](./PROJECT_STATE.md).

## Local changes, open issues and publication context

- Protected root: `gpt/phase8-linked-original-images`, HEAD `de0cc5a`,
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`. Four unresolved
  paths are the phase8_linked_visual_run and phase8_visual_evidence services
  and their two tests. Other staged/unstaged/untracked legacy work is unrelated;
  protected pytest directories prevent complete untracked enumeration.
  Never reset, clean, bulk-copy or publish from this root.
- Current lifecycle candidate: `feat/phase8-journal-lifecycle-20260905` in
  `C:\CLASSIFIRE\.tmp\phase8-journal-lifecycle-20260905`, based on `bdd6719`.
  Scope: three services, four test files, completion contract, inventory and four
  continuity documents. Verify actual commit/upstream/PR/merge before reuse.
- PRs #182-#184 are merged. Their clean retained worktrees are separate.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw development dependency
  advisories) remain open. Draft PRs #9-#13 remain legacy feature-to-feature work;
  verify current lifecycle-candidate publication separately. Do not bulk-merge that stack.
- Check current repository review/protection requirements before publication.
  Never bypass failed CI or required review. No runtime operation is authorised
  merely by this handoff.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Project State](./PROJECT_STATE.md).
