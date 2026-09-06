# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06 source checkpoint. Worktree:
`C:\CLASSIFIRE\.tmp\draft-pdf-suggestions-20260906`; branch
`feat/draft-pdf-suggestions-20260906`, initially tracking origin/main. Base/HEAD at
implementation start: `d2640defd00c23892691da79990a510bee59b2a0` (Excel PR #210).
Required PR CI passed 1,672 tests; main CI 34033021353 succeeded. This document
precedes the suggestion increment's own commit/PR/merge; inspect live Git/CI and the
local publication receipt before treating it as shared main.

ADRs 0001/0002 remain accepted. The deterministic modular core and optional bounded
AI are retained. The active slice is one-page PDF suggestions through a Draft-specific
port, retained generation and explicit human graph review. No canonical Phase8 IDs,
OpenClaw retirement, technical approval, pricing activation or deployment are involved.
A working scripted browser demo is not live AI accuracy or production acceptance.

## Local changes and evidence

Current relevant changes: optional suggestion contract/OpenAI transport/settings;
DraftPdfSuggestion model and forward 0039; source-bound preparation/read/reject/preview/
confirmation service; UI and shared editor observation controls; Scope v6 provenance,
conditional report versions and history/import handling; migration/current-head tests;
guarded exact synthetic demo fixture; aligned documentation. PROJECT_STATE.md records
actual checks and remaining proof. Do not copy its prior test counts as current proof.

The supplied logo is preserved and verified in the UI. The legacy root is untouched:
`gpt/phase8-linked-original-images`, HEAD `de0cc5a`, 46 unstaged tracked modifications,
14 staged additions and four DU conflicts. Do not clean/reset/resolve/stage or publish
from it. Preserve unrelated worktrees, older demos, source evidence and local receipts.

Demo `http://127.0.0.1:8818/scopes` uses separately marked directory
`C:\CLASSIFIRE\.tmp\draft-pdf-suggestions-demo-20260906` and PostgreSQL database
`classifire_draft_suggestions_demo` on loopback15432, scanner13311. It has an exact
scripted fixture and no live provider. Verify command lines before stopping its
launcher; start background helpers hidden. Receipts/downloads/screenshots are under
`C:\CLASSIFIRE\.tmp\draft-pdf-suggestions-review-artifacts-20260906`; keep these
synthetic runtime files local. Older 8817/8816/8815 demos are unrelated and preserved.

## Start Here / Next Session

**First task:** after verifying the suggestion increment's final checks and merge,
implement the bounded **A/B pricing-source profile UI**. It is next because PDF/Excel
human review and the optional interpretation interaction now form a usable Scope
prototype, while generic pricing workbook transport/row selection still cannot declare
or preserve the semantic identity and commercial basis of datasets A and B.

**Prerequisites:** inspect AGENTS.md, GOAL.md, PROJECT_STATE.md, architecture, roadmap,
ADRs and `TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md` T1/T5/T7. Inspect live branch/diff,
main and current PR/CI first; finish genuine outstanding suggestion proof/publication
before new edits. Use an isolated current-main worktree and preserve unrelated changes.
No dependency on live AI or the dirty recovery checkout is acceptable.

**Files/components:** existing `draft_pricing_intake.py`, `draft_pricing_contract.py`,
`draft_pricing_worker.py`, `draft_source_intake.py`, pricing UI/templates and retained
Draft models; inspect actual paths/callers/tests. Read DRAFT_PRICING_XLSX.md
and existing source/permission/scan, preview-confirm, revision and audit boundaries.
Extend these components rather than making a second importer or parallel database.

**Definition of done:** a user can explicitly choose general source A or Firefly
system-price source B, retain/scan a supported synthetic workbook, inspect a selected
sheet/header and bounded mapping, see unit/cost-sell/tax/currency/date/inclusion gaps,
preview without writes, explicitly save an unapproved versioned profile and reopen
it after restart. Preserve exact source bytes/cell references, previous profile
versions and missing-versus-zero distinctions. A filename is never proof of source
identity or price basis. Do not automatically activate a library, infer prices, match
systems or change an Estimate. No broad corpus extraction/recipe/calibration work in
this first profile slice. Update contracts/continuity docs from measured evidence.

**Validation:** targeted profile/permission/source/stale/basis/atomic-history tests;
existing pricing-row and client-proposal regressions; actual browser/restart and
inspected saved profile/export. Run Ruff, Mypy, Bandit and a single-head Alembic check.
Force isolated source imports. PostgreSQL tests must run serially only after verifying
the exact idle disposable `classifire_containment_test` loopback15432 database and
its explicit cleanup opt-in; never use a demo/customer database. Example setup:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('profile-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Verify test names and local dev/stub setup before using commands. Run meaningful
profile tests added by the task as well. Required full workflow is
`.github/workflows/pull-request-validation.yml`; never bypass failures or review.

**Blockers/decisions:** authorized real A/B sources and their commercial semantics
remain unverified; synthetic fixtures allow implementation now. Credentials, real
provider/customer workflows, deployment and canonical operations require separate
authorization. No known blocker prevents the synthetic source-profile interaction.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect
> AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/CLASSIFIRE_ROADMAP.md, docs/SESSION_HANDOFF.md, accepted ADRs and
> docs/TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md. Check branch/worktrees, diff,
> current main and PR/CI; finish any genuine remaining PDF-suggestion validation or
> publication prerequisite. Preserve the conflicted C:\CLASSIFIRE root, unrelated
> changes and demos; use an isolated current-main worktree. Next implement one bounded
> A/B source-profile UI by extending draft_pricing_intake/contract/worker,
> draft_source_intake and existing pricing UI, models and tests. This is next because
> report review now works but generic pricing rows lack explicit dataset identity and
> commercial basis. Done means choose A/B, retain/scan a supported synthetic workbook,
> inspect sheet/header/mapping and unit/price-basis gaps, preview, explicitly save an
> unapproved version and reopen after restart with exact evidence/history. Filenames
> confer no identity or approval. Do not activate prices, infer rates, run matching or
> reprice estimates. Follow minimal T1/T5/T7 dependencies; avoid speculative bulk AI,
> recipes/calibration or a second importer. Real sources/semantics remain unverified;
> do not use customer evidence, live providers, deploy or create canonical state
> without authorization. Validate new profile and pricing/client regressions, source/
> permission/stale/atomic refusal, browser/restart and saved outputs; run Ruff, Mypy,
> Bandit and single-head Alembic with isolated imports and guarded serial disposable
> PostgreSQL tests. Reconcile docs from evidence, classify the complete diff, preserve
> unrelated work, commit explicit reviewed paths, push normally, create/update the PR
> and merge after required CI/reviews pass; verify the resulting merge. Continue
> autonomously through that workflow when safe, reporting concrete blockers only.
