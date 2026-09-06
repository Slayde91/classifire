# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-07 in
`C:\CLASSIFIRE\.tmp\pricing-profile-review-20260907` on branch
`feat/pricing-profile-review-20260907`, based on `origin/main`
`205cf277ea86f6a47697e617465c8ab102ed8107`. PR #212 merged the A/B source-profile
interaction. PR #213 raised the validation timeout; exact shared-main run 34047634074
succeeded. The current branch adds the early-T12 exact-profile human review slice and
migration 0041. Treat it as candidate work until commit, push, PR, CI and merge are
verified from Git/GitHub.

ADRs 0001/0002 remain accepted. The deterministic modular core, independent capabilities
and optional bounded AI remain unchanged. This work uses no AI or OpenClaw and grants no
row-import, library, technical, Estimate, canonical, deployment or release authority.

## Relevant local changes and verified evidence

The candidate extends existing profile abstractions:

- `DraftPricingSourceProfileDecision` retains one immutable decision per exact profile,
  including profile revision/hash, approve/reject/request-revision, reason, reviewer,
  UTC time, exact JSON/hash and explicit false downstream effects.
- `draft_pricing_intake` requires `pricing:approve`, locks the retained source against a
  simultaneous profile save, rejects stale/changed/replayed/foreign/corrupt decisions,
  and preserves original profile/decision bytes.
- the pricing UI shows current/stale review status and history, presents the review form
  only to authorized users, and downloads exact decision JSON.
- migration `0041_draft_pricing_profile_decisions` is additive, becomes the single
  packaged head and refuses destructive downgrade.
- focused contract/service/browser/migration/lineage tests cover all three outcomes,
  permissions, stale/hash/replay/integrity refusal and no Estimate, LibraryRelease or
  TechnicalVariant side effects.

Current evidence: 33 migration/lineage tests and five focused service/browser tests pass;
changed-path Ruff and targeted Mypy pass. A full Mypy invocation using the system Python
cannot resolve the repository's optional `jwt`/`mcp` dependencies; rerun it in the project
environment used by CI. Full regression, Bandit, single-head, diff classification and
exact-head PR CI remain required before merge.

The recovery root `C:\CLASSIFIRE` remains at `de0cc5a` on
`gpt/phase8-linked-original-images`, with 46 unstaged tracked changes, 14 staged additions
and four DU conflicts at last inspection. Do not reset, clean, resolve, stage or publish
from it. Preserve unrelated worktrees and the running synthetic demo on port 8819.

## Start Here / Next Session

**First task:** after verifying that the T12 profile-review change is merged and green,
implement the smallest T13 pricing-evaluation lineage and holdout manifest boundary.

**Why this is next:** CLASSIFIRE can distinguish sources and retain a human decision, but
prediction work could still leak a target price or a related duplicate into training,
retrieval, prompts, caches or evaluation. Sealing lineage and split rules now protects the
validity of later bottom-up/comparable accuracy claims. Keep this prerequisite small so
the following slice can return immediately to a reviewed A-row or B-system mapping UI.

**Prerequisites and dependencies:** inspect current Git/GitHub/CI and repository docs
before editing. Confirm migration head 0041 and exact-profile review behavior are actually
merged. Read roadmap T1/T7/T10-T13 and the technical-corpus/dual-pricing design. Use a
clean isolated current-main worktree. Reuse canonical JSON/hash, append-only revision,
dataset/profile identity and download patterns. Use synthetic identifiers only. Do not
build prediction, vector retrieval, bulk ingestion or a second orchestration framework.

**Relevant files/components:** `services/draft_pricing_contract.py`,
`services/draft_pricing_intake.py`, pricing models/migrations, current A/B profile and
decision tests, `docs/TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md`, roadmap T13,
PROJECT_STATE, architecture, GOAL, AGENTS and this handoff.

**Definition of done:** a reviewed contract defines immutable dataset/source/profile
lineage, grouping keys for aliases/near-duplicate configurations/version copies,
train/validation/holdout assignment, creation actor/time and a sealed manifest hash.
The supported service can validate, save, reopen and exactly download a synthetic manifest
without assigning the same lineage group to more than one split. Replays, changed inputs,
duplicate group assignments, target-derived feature declarations and corrupt/foreign
manifests fail closed. Existing profiles and decisions remain unchanged. No price is
predicted, no row/library is activated and no accuracy claim is made. If repository
inspection proves persistence/UI premature because normalized rows do not exist, record
the enforceable contract and executable contamination tests only, then keep the first
reviewed-row UI as the next task rather than inventing placeholder records.

**Validation:** add meaningful contract/service/migration tests if persistence is added;
run pricing/profile/review, migration/lineage and compatibility regressions on the idle
disposable PostgreSQL database. Run full Ruff, Mypy, Bandit, `git diff --check`, one
Alembic head and required PR CI. Preserve unrelated changes. Do not use customer data,
live providers, deployment, canonical locks/writes or OpenClaw retirement work.

Useful setup after verifying local paths and database ownership:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
$env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
$taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-lineage-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTemp <targeted tests>
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

**Blockers/decisions needing validation:** actual A/B layouts, handling rights, commercial
semantics and related-row lineage are unknown, so only synthetic manifests are authorized.
The exact grouping keys must be sufficient to prevent connected Firefly aliases,
configuration duplicates and version copies crossing splits; do not guess real mappings.
Current reviewer access is effectively administrator-only because `pricing_manager` lacks
owned Draft project/Estimate read permissions. A future scoped reviewer assignment model
is needed before production multi-user review; do not broaden global project access in the
T13 slice.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. First inspect AGENTS.md, GOAL.md,
> docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md, docs/CLASSIFIRE_ROADMAP.md,
> docs/SESSION_HANDOFF.md, current Git/worktrees and GitHub PR/CI. Preserve the conflicted
> C:\CLASSIFIRE root and unrelated local work; use a clean current-main worktree. Verify
> the T12 exact-profile review and migration 0041 are merged and green; finish that
> publication first if required. Then implement the smallest enforceable T13 pricing
> lineage/holdout manifest: immutable exact dataset/source/profile lineage, grouped
> alias/duplicate/version assignments, sealed split/hash/actor/time, exact reopen/download,
> and fail-closed contamination/integrity/foreign/replay checks using synthetic data only.
> Reuse existing contracts, persistence and permissions. Do not predict prices, activate
> rows/libraries, use real sources/providers, deploy, weaken authority gates or build
> speculative infrastructure. If normalized rows are not ready for honest persisted
> assignments, implement the executable contract/tests and document that limit. Run
> relevant PostgreSQL regressions plus Ruff, Mypy, Bandit, diff and Alembic checks. Reconcile
> docs from evidence, classify and stage explicit paths, then autonomously commit, push,
> open/update a PR and merge only after required checks pass; verify the merge.
