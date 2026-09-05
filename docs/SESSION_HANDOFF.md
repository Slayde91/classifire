# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `d03753f94634860ed3381825f4c5d2f514e6523d` (PR #183)
**Latest executable-change baseline:** d03753f (PR #183)

All four maintained documents are under `docs/`. Inspect current repository
evidence before editing; this handoff records a snapshot, not live authority.

## Start Here / Next Session

**First task:** after verifying journal publication, integrate its lifecycle
with Phase 8's pre-dispatch and post-response boundaries. Use injected trusted
capture/verification ports and prove the path end to end with synthetic transport.

**Why next:** the consumer is merged and the journal candidate can durably seal
a trusted producer's outcome, but managed transports are not wired to it.
A naive wrapper is circular: transport waits for verification while the journal
waits for transport return. Split or adapt the existing lifecycle deliberately;
persist capture before dispatch and completion before returning a proposal.

**Prerequisites:** inspect applicable AGENTS.md, root/worktree status, branch/
upstream/HEAD, main, open PRs and CI before editing. Read the four docs, Decision
0001, completion contract and OpenClaw inventory. Verify the actual journal
commit/PR/merge from `feat/execution-journal-20260905` in
`C:\CLASSIFIRE\.tmp\execution-journal-20260905`, based on `d03753f`.
Preserve unrelated/root work and use an isolated current-main tree.

**Files/components:** `src/classifire/services/execution_journal.py`;
`phase8_openresponses_transport.py`, `phase8_report_openresponses_transport.py`,
`phase8_visual_runtime.py` in that service directory; `src/classifire/models.py`
and `worker.py` for state compatibility; completion contract; journal and existing
transport/controller/caller tests listed below.

**Definition of done:**

1. Record the exact lifecycle change and trust/availability impact before editing.
   Reuse the journal and existing transport checks; do not duplicate domain logic.
2. Commit capture identity before inference dispatch; let post-response verification
   authenticate producer evidence, commit a terminal journal and reload it before
   proposal acceptance. Bind the same session/request/response/attestation/context.
3. Prove positive visual/report execution with synthetic capture/HTTP, absence and
   loss refusal, safe failures, interruption/late completion, concurrent/repeated
   calls and historical receipts. A verifier must never require transport return
   before it can complete that same transport.
4. Preserve no-tool enforcement, exact evidence, owner/producer boundaries and all
   canonical/lock/release controls. An authenticated application supplies owner IDs;
   accepting an arbitrary owner string is not user authorization.
5. Keep managed real-provider wiring disabled until actual capture/terminal
   assurance is proven. Empty remote pages and locally sealed assertions cannot
   establish that assurance. No real provider/customer/canonical operation.
6. Run focused integration/journal and warranted caller tests, full static checks,
   migration heads, guarded disposable PostgreSQL concurrency and hosted CI.
   Inspect synthetic records/receipts; align docs; classify, commit, push, PR and
   merge where safe after CI/reviews. Verify merge and post-merge CI.

**Remaining limits:** journal HMAC is integrity protection inside the trusted
application/storage boundary, not provider authentication or malicious-database
anti-rollback. Production key custody/rotation, retention, actual capture and
remote cancellation remain unproven. The generic worker still has no handlers;
journal operations use explicit non-queued states. No new migration is needed
for the current journal. Do not expand the next slice into a general agent
framework, packages or UI.

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
Before editing read AGENTS.md, the four docs under docs/, Decision 0001,
EXECUTION_COMPLETION_CONTRACT.md and OPENCLAW_CONTRACT_CHARACTERISATION.md.
Inspect branch/upstream/HEAD/conflicts/local changes; fetch main and check PRs/CI.
Verified main was d03753f (PR #183), CI 33939296281 passed. Verify publication
of feat/execution-journal-20260905 in
C:\CLASSIFIRE\.tmp\execution-journal-20260905 and reconcile newer source.
Preserve the conflicted root and unrelated work; use an isolated current-main tree.

Single next task: connect the execution journal to Phase 8's pre-dispatch and
post-response lifecycle with injected trusted capture/verification ports.
The consumer is merged; the journal candidate persists sealed outcomes on
BackgroundJob, but managed inference is still unwired. Avoid a circular wrapper:
the verifier cannot wait for the transport return that it is itself blocking.

Inspect src/classifire/services/execution_journal.py, both phase8_*openresponses
transports, phase8_visual_runtime.py, their tests, models.py, worker.py and the
completion contract. Record lifecycle/trust impact first. Persist capture before
HTTP, authenticate exact producer evidence after response, commit/reload terminal
evidence before proposal acceptance. Reuse no-tool/context/receipt checks and
journal state transitions. Owner identity comes from authenticated composition.

Done: synthetic visual/report end-to-end execution; missing/lost evidence,
identity mismatch, interruption/late completion, duplicate/concurrent invocation
and safe-error tests; preserved historical receipts and authority gates; aligned
docs and passing checks. Run new integration tests, handoff journal/transport/
caller suite, Ruff, Mypy, Bandit, Alembic heads, guarded disposable PostgreSQL
concurrency and diff checks with worktree PYTHONPATH and unique temporary storage.

Keep actual provider wiring disabled until authenticated capture/terminal proof
exists. A journal HMAC or empty audit page does not prove remote activity.
No real provider/customer operation, canonical write, lock, deployment, release
or OpenClaw retirement. Continue autonomously through implementation, validation,
classification, explicit commit, normal push, PR and merge where safe after
CI/reviews pass. Verify actual merge/post-merge CI and disclose remaining
production assurance. Do not duplicate newer completed work.
~~~

## Verified project context

PR #183 merged at d03753f with
[successful exact main CI](https://github.com/Slayde91/classifire/actions/runs/33939296281).
The journal candidate adds durable capture/terminal ordering and authenticated
record verification on BackgroundJob, with owner/producer/context binding,
completed replay and interruption without redispatch. It does not supply a
production capture producer or wire the managed transports.

Local validation: 27 journal tests and 171 existing transport/security/caller
tests passed. Three disposable PostgreSQL cases are included for hosted CI and
skipped locally. Ruff, Bandit, Mypy (143 files) and one Alembic head passed.
Eight existing Pillow warnings remain. No real provider/customer/canonical
database was used. Verify journal publication/CI separately.

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
- Current journal candidate: `feat/execution-journal-20260905` in
  `C:\CLASSIFIRE\.tmp\execution-journal-20260905`, based on `d03753f`.
  Scope: one journal service, two test files, completion contract, inventory and
  four continuity documents. Verify actual commit/upstream/PR/merge before reuse.
- PRs #182 and #183 are merged. Their clean retained worktrees are separate.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw development dependency
  advisories) remain open. Draft PRs #9-#13 remain legacy feature-to-feature work;
  verify current journal-candidate publication separately. Do not bulk-merge that stack.
- Check current repository review/protection requirements before publication.
  Never bypass failed CI or required review. No runtime operation is authorised
  merely by this handoff.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Project State](./PROJECT_STATE.md).
