# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-08 from shared main
`58ff6fdb308b4c4b9c9ed5215b9e938c43c4b5d4`, merge commit for PR #220.
Exact PR head `f29110339359f74ea85460ee58a40117be9df12d` passed workflow
34127607174 with 1,868 tests. Post-merge main workflow 34127945847 also
passed. Both completed the full Ruff, Mypy, Bandit and one-head Alembic workflow.

ADRs 0001/0002 remain accepted. CLASSIFIRE is one modular deterministic
application with independently callable Scope, System Match, Estimate and
Reporting capabilities, portable artifacts and optional bounded AI. OpenClaw
remains transitional. The latest pricing changes use no agent or provider and
grant no canonical, technical, commercial, deployment or release authority.

This handoff update is prepared on `docs/pr220-final-state-20260907` in the
isolated worktree `C:\CLASSIFIRE\.tmp\pr220-final-state-20260907`. Reconcile
the final documentation PR and current `origin/main` before new work.

## Relevant local changes and open issues

PR #220 extends the existing Draft pricing path:

- migration 0043 adds append-only `draft_pricing_system_mappings` and is
  the single migration head;
- a current approved `firefly_system_prices` row can be previewed and then
  saved as mapped, ambiguous or unmatched;
- mapped requires one exact eligible variant from an active technical release;
  ambiguous requires at least two candidates; unmatched retains none;
- price, currency and unit cannot be used as technical identity evidence;
- the immutable envelope binds the exact Draft, dataset/version, source bytes,
  profile/decision, worksheet row/cells, technical release, variants and source
  evidence, with reviewer, uncertainty, reason, canonical bytes and hashes;
- save locks and rechecks dependencies; stale, changed, replayed, foreign,
  corrupt, unusable, formula and price-only inputs fail closed;
- reopen and exact JSON download verify stored bytes and duplicated bindings;
- every technical approval, library activation, applicability, System Match,
  price inference, Estimate, holdout, deployment and release effect is false.

Measured PR #220 evidence:

- the full Draft Pricing regression group passed;
- all modified migration and deployment-lineage consumers passed;
- the final service/UI/migration group passed 37 tests with three
  environment-specific skips;
- repository-wide Ruff and Bandit passed;
- targeted Mypy passed on all six changed production files;
- `git diff --check` and the one-head Alembic check passed;
- TestClient covered permission denial, no-write preview, explicit save,
  reopen and exact download through rendered HTTP routes;
- PR workflow 34127607174 passed 1,868 tests and all gates; post-merge main
  workflow 34127945847 passed the same validation workflow.

A separate real-browser and process-restart journey has not been run for the
Dataset B mapping UI. Treat the TestClient evidence as functional HTTP proof,
not visual-layout or restart proof.

Actual Dataset A/B layouts, ownership, redistribution rights, price meaning,
tax/date/unit/inclusion semantics and representative record counts remain
unverified. The current parser cap is 1,000 rows including the header, so it
does not prove support for a claimed 1,000-plus data-row B source.

The recovery root `C:\CLASSIFIRE` remains on
`gpt/phase8-linked-original-images` at `de0cc5a`, with 46 unstaged
tracked changes, 14 staged additions and four DU conflicts at last inspection.
It also contains untracked recovery material. Do not reset, clean, resolve,
broadly stage or publish from it. Preserve unrelated worktrees and changes.

## Start Here / Next Session

**First task:** persist the first governed T13 pricing-evaluation lineage roster
from current reviewed mapped Dataset B records.

**Why this is next:** PR #216 already defines the deterministic manifest,
connected-group and leakage rules. PR #220 now supplies governed B mappings to
exact technical identity. Persisting the roster before model or feature work
protects validation and holdout membership from target leakage.

**Prerequisites and dependencies:**

- inspect `AGENTS.md`, Git/worktrees, current `origin/main`, latest CI and
  the state/architecture/roadmap/handoff documents before editing;
- work from a clean current-main isolated worktree and preserve the recovery root;
- reuse `DraftPricingSystemMapping`, its current-dependency integrity checks
  and `draft_pricing_evaluation_contract.py`;
- only current `mapped` B records may be eligible; exclude ambiguous,
  unmatched and stale mappings with explicit reasons;
- derive stable system, alias, near-duplicate configuration, source-derivation
  and workbook-version lineage from frozen identity/provenance fields;
- assign connected groups deterministically without reading the target price;
- require at least three independent connected groups and all training,
  validation and holdout splits, or return explicit insufficient evidence;
- define scoped pricing/technical read authority without broad project visibility.

**Relevant files/components:**

- `src/classifire/models.py`;
- `src/classifire/services/draft_pricing_intake.py`;
- `src/classifire/services/draft_pricing_contract.py`;
- `src/classifire/services/draft_pricing_evaluation_contract.py`;
- `src/classifire/draft_pricing_ui.py` and Draft pricing templates;
- migration 0043 and `src/classifire/deployment_lineage.py`;
- `tests/test_draft_pricing_system_mappings.py`;
- `tests/test_draft_pricing_evaluation_contract.py`;
- `tests/test_draft_pricing_ui.py`;
- pricing migration/deployment-lineage tests and roadmap T13.

**Definition of done:** an authorised user can preview the exact eligible and
excluded B mappings, see connected groups and deterministic proposed splits,
and explicitly save an immutable roster revision only when all three splits are
valid. The user can reopen it after a separate process restart and download
identical canonical JSON. The saved record binds its exact mapping dependencies,
cutoff/policy version, groups, split membership, exclusions, parent revision,
actor/time and hash. Its member data carries only the target hash and
availability metadata, never the target price.

Stale, replayed, foreign, changed or corrupt inputs must fail closed. Rebuilding
from identical eligible inputs must be deterministic. Insufficient independent
groups must produce a visible no-save result. Add an additive migration, keep
one Alembic head and preserve historical bytes. Do not train or run a model,
compute metrics, reveal validation/holdout targets, activate a commercial
library, change an Estimate, approve technical applicability, deploy or release.

**Validation commands:** resolve paths first and use the disposable PostgreSQL
database.

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t13-roster-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp <targeted tests>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads

**Blockers requiring validation:** real B schema and data rights; stable alias,
near-duplicate configuration, source-derivation and workbook-version lineage
policy; the parser capacity limit; and the current administrator-only practical
review path. Synthetic records may prove the mechanism but not real-data
coverage, pricing accuracy or production readiness.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect
> AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, architecture, roadmap, handoff,
> current Git/worktrees, origin/main and GitHub CI. Preserve the conflicted
> C:\CLASSIFIRE recovery root and unrelated local changes; use a clean
> current-main worktree. Implement the single highest-value next task: persist a
> governed T13 lineage roster from current reviewed `mapped` Dataset B records.
> Reuse DraftPricingSystemMapping and
> draft_pricing_evaluation_contract.py. Exclude ambiguous, unmatched and stale
> mappings with reasons. Build connected lineage and deterministic train,
> validation and holdout assignment without reading target prices; require
> independent groups in all three splits or show insufficient evidence and do
> not save. Provide scoped preview, explicit immutable save, reopen-after-restart
> and exact JSON download with dependency, policy, revision and hash checks.
> Reject stale, changed, replayed, foreign and corrupt inputs. Store target
> hashes only; do not train/run a model, reveal holdout targets, activate pricing,
> change an Estimate, approve technical applicability, deploy or release. Add
> focused service/UI/migration/determinism/leakage/no-side-effect tests, then run
> relevant regression tests, Ruff, Mypy, Bandit, one Alembic-head check and
> browser/restart proof where available. Inspect and classify the final diff,
> preserve unrelated work, then autonomously commit, push, open/update a PR and
> merge only when checks and repository rules allow. Update documentation from
> measured evidence and avoid speculative work.
