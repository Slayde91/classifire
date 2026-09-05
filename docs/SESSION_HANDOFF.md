# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `4ab872334cad326fbd3cc6dad7106f3f448eae14` (PR #181)
**Latest executable-change baseline:** 4ab8723 (PR #181)

All four maintained documents are under `docs/`. Inspect current repository
evidence before editing; this handoff records a snapshot, not live authority.

## Start Here / Next Session

**First task:** review, validate and finish the existing uncommitted
execution-completion acceptance candidate. Do not create a duplicate implementation.

**Why next:** PR #181 already refuses continued/oversized audit pages, but shared
main still accepts an empty page without proof of durable execution coverage.
The existing candidate addresses that consumer gap. Its default managed runtime
will refuse inference until a trusted producer/verifier is wired. Confirm that
deliberate availability consequence and prove the boundary before publishing.
The consumer does not itself prove complete capture or retire OpenClaw.

**Prerequisites and working context:**

- Read applicable AGENTS.md, the four maintained documents, Decision 0001 and
  `docs/OPENCLAW_CONTRACT_CHARACTERISATION.md`. Fetch main; inspect branch,
  upstream, changes, open PRs and CI before deciding what remains.
- Candidate worktree:
  `C:\CLASSIFIRE\.tmp\phase8-completion-evidence-20260905`.
  Branch: `feat/phase8-completion-evidence-20260905`; HEAD/base: `4ab8723`;
  upstream at inspection: `origin/main`. Five tracked modifications plus one
  untracked contract document; no candidate commit or open PR was found.
- Preserve that candidate and the conflicted legacy root. Use the isolated
  candidate worktree only after classifying its current contents. Reconcile
  newer main non-destructively; retain updated documentation when combining work.
- A trusted production evidence producer is absent. This blocks production
  wiring, not synthetic consumer validation. No live-provider/customer,
  canonical-write, lock, deployment or release authority is granted here.

**Relevant files:**

- `src/classifire/services/phase8_openresponses_transport.py`
- `src/classifire/services/phase8_report_openresponses_transport.py`
- `src/classifire/services/phase8_visual_runtime.py` (managed composition/callers)
- `tests/test_phase8_openresponses_transport.py`
- `tests/test_phase8_report_openresponses_transport.py`
- `tests/test_phase8_visual_runtime.py`
- `docs/EXECUTION_COMPLETION_CONTRACT.md` exists only in the candidate worktree.
- Controller/runner tests listed below; `src/classifire/models.py` and
  `src/classifire/worker.py` are later producer/recovery extension points.

**Definition of done:**

1. Review current-to-proposed behavior, trusted verifier authority, exact
   request/response/session/agent/attestation binding and receipt migration.
   Typed fields/hashes are not producer authentication.
2. Verify missing verifier prevents inference token/HTTP use; malformed,
   stale, mismatched, incomplete, disabled/lossy or untrusted evidence refuses
   acceptance. Test both transports, safe error handling and replay binding.
3. Preserve independent no-tool checks, proposal-only authority, historical
   receipt verification and all canonical/lock/release gates. Explicitly test
   the managed runtime's deliberate refusal. Never add a permissive fake
   production verifier to make tests or real runs proceed.
4. Focused and warranted caller regressions, static/migration checks, full hosted
   CI and documentation alignment pass. Report remaining producer limitations.
5. Classify and commit only reviewed scope, push normally, open/update the PR,
   merge after required CI/review passes where safe, then verify actual merge
   and post-merge CI. Do not report production readiness.

**Subsequent gate, not part of this consumer slice:** durable authenticated
completion production with capture-before-dispatch, persisted terminal ordering,
loss detection, invocation ownership and crash/replay recovery. Extend existing
job abstractions where suitable. Broader adapters, packages and UI follow their
own contracts; OpenClaw stays until proven protection and recovery parity.

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
  tests/test_phase8_openresponses_transport.py `
  tests/test_phase8_report_openresponses_transport.py `
  tests/test_phase8_visual_runtime.py `
  tests/test_phase8_report_assessment_controller.py `
  tests/test_phase8_report_assessment_runner.py `
  tests/test_openclaw_admission_writer_manifest.py `
  tests/test_phase8_admission_only_profile.py `
  tests/test_agent_security_boundary.py
& $contractPython -m ruff check . --no-cache
& $contractPython -m mypy src
& $contractPython -m bandit -q -r src
& $contractPython -m alembic heads
git diff --check
~~~

Check each command's exit code before continuing. Include newly added tests.
Hosted `.github/workflows/pull-request-validation.yml` runs full pytest, Ruff,
Mypy, Bandit and one Alembic-head validation with disposable PostgreSQL.
Run broader local regression when changed shared behaviour warrants it.
Never point destructive PostgreSQL tests at project/UAT/production databases.
Do not run `classifire doctor` against a real configured environment merely
for this synthetic task.

## Recommended Prompt for New Session

~~~text
Continue CLASSIFIRE at C:\CLASSIFIRE (https://github.com/Slayde91/classifire).
Before editing, read applicable AGENTS.md and the four docs under docs/, Decision
0001 and OPENCLAW_CONTRACT_CHARACTERISATION.md. Inspect HEAD/upstream/conflicts/
local changes; fetch main and check PRs/CI. Verified baseline: 4ab8723, PR #181;
main CI 33936917822 passed. Preserve the dirty legacy root and unrelated work.

Single task: review, validate and finish the existing completion-evidence
acceptance candidate in C:\CLASSIFIRE\.tmp\phase8-completion-evidence-20260905,
branch feat/phase8-completion-evidence-20260905. At handoff it was uncommitted on
4ab8723: two transports, three tests and untracked
docs/EXECUTION_COMPLETION_CONTRACT.md. Inspect the actual diff and newer main;
do not recreate completed work or overwrite newer documentation.

Why next: merged audit-page refusal does not prove durable execution coverage.
Review phase8_openresponses_transport.py, phase8_report_openresponses_transport.py,
phase8_visual_runtime.py under src/classifire/services/, their tests and the
local contract. The candidate requires trusted completion evidence and version-2
receipt binding; managed inference deliberately stops before inference token/
HTTP because no production verifier exists. Review and test that consequence.
A typed result/hash is not authentication; a trusted producer remains a later
gate. Do not fabricate provider fields or use empty audit polling as proof.

Done: justified consumer contract and migration; synthetic tests for absent,
stale, mismatched, incomplete, untrusted and replayed evidence in both transports;
safe errors; managed refusal; retained no-tool and historical receipt behavior;
aligned four docs and passing validation. Run the handoff eight-file suite plus
warranted caller regressions, Ruff, Mypy, Bandit, Alembic heads and diff checks
with worktree PYTHONPATH and unique temporary storage. Use only synthetic ports
and disposable test databases. No real provider/customer operation, canonical
write, lock, deployment, release, OpenClaw removal or speculative framework.

Continue autonomously through implementation as needed, validation,
classification, explicit commit, normal push, PR and merge where safe after
CI/reviews pass; verify merge and post-merge CI. Preserve unrelated changes.
If newer work already finishes this slice, report that evidence and follow the
next documented dependency rather than duplicating it.
~~~

## Verified project context

PR #181 is merged at `4ab872334cad326fbd3cc6dad7106f3f448eae14`.
[PR CI](https://github.com/Slayde91/classifire/actions/runs/33936702941) and
[exact main CI](https://github.com/Slayde91/classifire/actions/runs/33936917822)
were rechecked successfully. PR #181 records 114 contract/security plus 17 caller
tests; these are historical local results, not fresh completion-candidate tests.
This documentation task inspected source/diffs and publication evidence; it did
not execute or publish the candidate. Its validation must be re-established.

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
- The six-file completion candidate is separate uncommitted implementation work.
  Preserve it. Its contract file is not available on shared main at this snapshot.
- Documentation branch: `docs/verified-hybrid-handoff-20260905` in
  `C:\CLASSIFIRE\.tmp\docs-verified-hybrid-handoff-20260905`, based on `4ab8723`.
  Scope is exactly PROJECT_STATE, CLASSIFIRE_ARCHITECTURE, CLASSIFIRE_ROADMAP and
  SESSION_HANDOFF under `docs/`. Initial upstream is `origin/main`; check GitHub
  for the eventual documentation commit, PR and merge rather than assuming them.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw development dependency
  advisories) remain open. Draft PRs #9-#13 remain legacy feature-to-feature work;
  no completion-candidate PR was present. Do not bulk-merge that stack.
- Check current repository review/protection requirements before publication.
  Never bypass failed CI or required review. No runtime operation is authorised
  merely by this handoff.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Project State](./PROJECT_STATE.md).
