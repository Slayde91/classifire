# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `51e7d601a756141dfbdef5d113e754a9b2833d34` (PR #182)
**Latest executable-change baseline:** 4ab8723 (PR #181)

All four maintained documents are under `docs/`. Inspect current repository
evidence before editing; this handoff records a snapshot, not live authority.

## Start Here / Next Session

**First task:** after verifying publication of the completion-consumer candidate,
implement the smallest durable execution journal and authenticated verifier path.
Extend CLASSIFIRE's existing BackgroundJob/worker/service abstractions where
suitable. Use a synthetic executor to prove the contract before production wiring.

**Why next:** the consumer now refuses inference without a configured verifier
and refuses proposals without valid bound completion evidence. Managed factories
have no verifier. A durable trusted producer is needed to restore governed
inference; empty OpenClaw audit pages cannot supply its guarantees.

**Prerequisites:**

- Inspect AGENTS.md, Git branch/upstream/HEAD/conflicts, current main and PR/CI.
  Read the four docs, Decision 0001, OPENCLAW_CONTRACT_CHARACTERISATION.md and
  EXECUTION_COMPLETION_CONTRACT.md. Do not repeat newly merged work.
- Candidate branch `feat/phase8-completion-evidence-20260905` in
  `C:\CLASSIFIRE\.tmp\phase8-completion-evidence-20260905` was advanced to
  `51e7d60` before validation. Verify its actual commit/PR/merge and current main.
  Preserve its changes and the unrelated conflicted root; use an isolated tree.
- Review capture lifecycle, durable authority, clock assumptions and retention
  requirements before implementation. The stock audit API does not certify
  persistence or loss. Do not manufacture a certificate from its responses.
- No live provider/customer, canonical-write, lock, deployment or release
  authority is granted. Synthetic/disposable database work is available.

**Files/components:** `src/classifire/models.py`, `worker.py`, `db.py`;
`services/phase8_openresponses_transport.py`,
`services/phase8_report_openresponses_transport.py` and
`services/phase8_visual_runtime.py` under `src/classifire/`; packaged migrations,
completion contract, relevant job/database tests and the transport/caller suite
below. Reuse receipt/transaction conventions without giving a job canonical authority.

**Definition of done:**

1. Record current-to-target design and justified schema/migration impact. Journal
   immutable invocation identity, owner, capture start, execution and terminal
   outcome; separate operational job state from canonical project truth.
2. Make capture-before-dispatch and durable terminal ordering explicit. Missing,
   disabled, pending, lost, corrupt or interrupted capture cannot verify success.
   Authenticate the producer record before returning typed completion evidence.
3. Prove exact request/response/session/agent/attestation binding, cross-invocation
   refusal, idempotent replay, concurrent ownership and crash/recovery behavior.
   Use synthetic executors; add only necessary forward migrations and disposable
   PostgreSQL tests where transaction semantics matter.
4. Preserve no-tool controls, historical receipt verification, safe diagnostics,
   deterministic services and all human/canonical/lock/release gates. Production
   wiring stays disabled unless the actual producer meets the complete contract.
5. Run focused/new job and transport regressions, static/migration checks and full
   hosted CI. Inspect stored synthetic records/receipts, align documentation,
   classify scope, commit, push, PR and merge after CI/reviews pass where safe.
   Verify merge/post-merge CI; report remaining real-provider parity honestly.

**Blockers/limits:** no trusted production producer exists; whether the current
OpenClaw integration can supply sufficient terminal/capture evidence remains
unproven. A local journal alone cannot attest events outside its enforcement
boundary. Complete the durable synthetic boundary without claiming provider parity,
then identify the exact remaining adapter requirement. Do not create a general
agent framework, new package/UI pipeline or permissive production verifier.

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
Inspect branch/upstream/HEAD/conflicts and local changes; fetch main and check
PRs/CI. Verified main was 51e7d60 (PR #182), CI 33938506042 passed. Verify actual
publication of feat/phase8-completion-evidence-20260905 in
C:\CLASSIFIRE\.tmp\phase8-completion-evidence-20260905 before proceeding.
Preserve the conflicted root and unrelated work; use an isolated current-main tree.

Single next task: implement the smallest durable execution journal and
authenticated completion verifier using existing BackgroundJob/worker/service
boundaries where suitable. The consumer candidate requires bound completion
evidence; managed inference intentionally refuses dispatch because no production
verifier exists. Empty audit pages cannot prove capture completeness. Do not
duplicate the consumer or invent provider certificates.

Inspect src/classifire/models.py, worker.py, db.py, the two phase8_*openresponses
transports, phase8_visual_runtime.py, their tests and packaged migrations.
Document design/migration impact first. Prove capture-before-dispatch, durable
terminal ordering, immutable invocation/owner binding, lost/disabled/pending
capture refusal, idempotent replay, concurrent ownership and crash recovery with
a synthetic executor. Authenticate journal evidence before returning typed proof;
hashes/booleans alone confer no authority. A local journal cannot attest remote
events outside its enforcement boundary. Keep production wiring disabled until
the actual producer satisfies the full contract.

Done: minimal durable producer/verifier boundary, inspected synthetic records and
receipts, positive/negative/recovery tests, justified forward migrations, aligned
docs and passing checks. Preserve no-tool, historical receipts and human/canonical/
lock/release gates. Run new job tests, handoff transport/caller suite, Ruff,
Mypy, Bandit, Alembic heads, warranted disposable PostgreSQL tests and diff checks.
Set worktree PYTHONPATH and unique temporary storage. No real provider/customer
operation, canonical write, lock, deployment, release or OpenClaw retirement.

Continue autonomously through implementation, validation, classification,
explicit commit, normal push, PR and merge where safe after CI/reviews pass.
Verify merge and post-merge CI. Reconcile newer completed work rather than
duplicating it; disclose the remaining real-provider boundary.
~~~

## Verified project context

Main PR #182 merged as 51e7d601a756141dfbdef5d113e754a9b2833d34, with
[successful exact CI](https://github.com/Slayde91/classifire/actions/runs/33938506042).
Its executable baseline remains PR #181. Current candidate validation passed
171 synthetic tests across the twelve files below, full Ruff/Bandit, and one
Alembic head. Full Mypy passed for 142 source files; hosted publication checks are verified
before merge. Eight existing Pillow deprecation warnings remain.
No real runtime/customer/canonical database was used.

The consumer binds exact encoded request/response bytes, invocation identity and
validated completion evidence into version-2 transport receipts. Legacy audit
observation hashes remain unchanged. Missing verifier prevents inference token
acquisition/HTTP; managed factories intentionally supply none. Production
producer/verifier implementation and OpenClaw retirement remain incomplete.

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
- Current completion candidate: `feat/phase8-completion-evidence-20260905`,
  `C:\CLASSIFIRE\.tmp\phase8-completion-evidence-20260905`, validated on `51e7d60`.
  Scope: two transports, three tests, completion contract, inventory and four
  continuity docs. Verify actual commit/upstream/PR/merge before the next task.
- Documentation-only PR #182 is merged; its retained worktree is separate and clean.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw development dependency
  advisories) remain open. Draft PRs #9-#13 remain legacy feature-to-feature work;
  verify current completion-candidate publication separately. Do not bulk-merge that stack.
- Check current repository review/protection requirements before publication.
  Never bypass failed CI or required review. No runtime operation is authorised
  merely by this handoff.

Related: [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Project State](./PROJECT_STATE.md).
