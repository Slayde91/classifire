# CLASSIFIRE Session Handoff

## Verified branch and project context

2026-09-06. Documentation worktree:
`C:\CLASSIFIRE\.tmp\technical-corpus-dual-pricing-20260906`;
branch `docs/technical-corpus-dual-pricing-20260906`.
Shared baseline is `a22a02769d3b842d5d0129dbd09273759ae583c1`, merged PR #207.
Its feature `75f3a8e004269f7e790b76818d89bfc770ab0465` passed CI 34019881433:
1,522 tests, 141 warnings, Ruff/Bandit and Mypy (193 files). Main CI 34020498735
succeeded, with identical feature/merge trees. No deployment or release occurred.

This is a documentation checkpoint for the requested technical-corpus and dual-pricing
amendment. Inspect live head/upstream, PR/CI and merge state before starting implementation;
this file cannot contain its own final commit hash. ADRs 0001/0002 remain accepted.
The full production goal is active and incomplete.

## Current changes, verification and open issues

Changed documentation: GOAL.md, AGENTS.md, docs/CLASSIFIRE_ARCHITECTURE.md (5.21),
CLASSIFIRE_ROADMAP.md, PROJECT_STATE.md, SESSION_HANDOFF.md and DRAFT_PRICING_XLSX.md;
new TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md. The integrated design follows the
requested 16-section order; roadmap T1-T14 records dependencies and acceptance.
There is no runtime implementation, migration, import, provider execution, pricing
rule change, canonical write or operational-state change in this amendment.

Verified foundations: technical source/variant review and release controls; bounded
retained PDF/XLSX intake; Product/Labour/PricingLibraryRecord and Decimal calculations;
four independent Draft capabilities; exact reports/packages and human-confirmed client
proposals. PR #207 additionally passed 187 focused local tests plus official SDK,
Chrome, real scan, actual restart and exact PDF/XLSX checks. Those are prior milestone
evidence; new corpus/dual-source estimation functionality has not been tested or built.

New dependencies/gaps: distinct A/B source identity and explicit cost/sell/unit/basis;
reviewed system/configuration mappings; immutable component/activity recipe publication;
full coverage/recovery; lineage-aware holdouts and calibration. Existing technical
release v3 lacks complete BOM/labour snapshots. Generic XLSX row limits include the
header (maximum 1,000); UI/search caps and job lifecycle do not meet corpus scale.
Legacy Package 14 CSV defaults, derived Product lineage and raw-file release manifests
must not be silently reused as trusted new A/B ingestion or independent test evidence.

Neither named workbook was located in inspected tracked/root-level/data/docs locations;
no workbook cells were read. Actual layout, dates, currency/tax, cost/sell meaning,
1,000-plus row count and source rights need verification from authorized originals.
This blocks real-data acceptance, not a synthetic source-profile UI implementation.
Review thresholds, recipe/productivity authority and broader operating limits remain
open; do not invent them to make an estimate look complete.

## Preserved local context

The conflicted root `C:\CLASSIFIRE` remains on `gpt/phase8-linked-original-images`
with four DU conflicts and pre-existing staged/unstaged/untracked work. Preserve it
as recovery evidence; never reset, clean, resolve, broad-stage or publish there.
The prior `client-workbook-pricing-20260906` worktree is unrelated merged work.
Earlier worktrees/demos/receipts/scanners remain preserved. The approved logo at
`src/classifire/static/brand/classifire-logo.png` matches the supplied root PNG:
SHA-256 `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.

Prior synthetic runtime receipts under `C:\CLASSIFIRE\.tmp` include
`client-pricing-publication.json`, `client-pricing-browser-receipt.json`,
`client-pricing-restart-receipt.json` and `client-pricing-output-inspection.json`,
plus PDF/XLSX/screenshots. Verify live GitHub state over an older receipt.
The prior demo directory is `client-pricing-demo-20260906`, URL
`http://127.0.0.1:8815/scopes`, with separate PostgreSQL database
`classifire_draft_client_pricing_demo` on loopback 15432. Do not assume it is still
running or reuse its data as a destructive test fixture. Read local launcher setup
without copying credentials or bearer tokens into docs, logs or prompts.

The separate guarded test database has been `classifire_containment_test`. Verify
its ownership, isolation and idle state before any cleanup opt-in. Scanner 13311 was
a native disposable ClamAV setup; 13310 is an older preserved scanner. Prior scan
freshness is not current scan authority. Inspect current scanner definitions and
exact process command lines before operating only owned demos. Background helpers
must launch hidden. No runtime service was changed for this documentation task.

## Start Here / Next Session

**First task:** implement one bounded, user-visible **dual-source intake/profile
preview**. A is `pricelist.xlsx` (general products/materials/labour/services); B is
`pricing_library.xlsx` (Firefly system prices). Explicit source selection, original
hash/version, sheet/header/count preview and unknown unit/price-basis diagnostics
must be visible. Save and reopen a Draft profile without publishing prices, mapping
systems automatically or running estimation. This is the thin T1+T5+T7 slice.

**Why next:** current workbook selection works but has no semantic A/B source identity
or trustworthy source profile for later mappings and estimates. Actual workbook layouts
are unknown. A working profile UI exposes those gaps early and supports later decisions;
a complete corpus schema or AI model is not a prerequisite. The retained-PDF structured
Draft task remains upcoming but reordered by the owner's latest architecture request.

**Files/components:** inspect `models.py`, `services/draft_source_intake.py`,
`services/draft_pricing_intake.py`, `draft_pricing_worker.py`, `draft_pricing_contract.py`,
`draft_pricing_ui.py`, `templates/draft_pricing.html`, existing storage/source guards,
client source preview and migrations. Read docs/DRAFT_PRICING_XLSX.md and the integrated
design before deciding the smallest SourceDataset/DatasetVersion/profile contract.
Do not call the legacy CSV importer or activate LibraryRelease/PricingLibraryRecord.

**Prerequisites/dependencies/blockers:** inspect current main/PR and preserve unrelated
changes; use an isolated worktree. Verify local development dependencies and current
fixtures. Use synthetic A/B workbooks, marked storage, disposable PostgreSQL and genuine
current scanner definitions for source-containment/browser proof. Missing originals
block real-layout acceptance only. Missing isolation/scanning blocks that runtime proof;
never weaken guards or substitute customer data. No real OAuth, provider, deployment,
pricing coefficients or complete technical-system schema is required for this slice.

**Definition of done:** users explicitly select A/B and retain the source/version;
inspect supported sheets/headers/physical-row counts, cell kinds and clear basis/unit
unknowns; save/reopen the profile after restart. Unsupported/capacity-limited content
must be explicit, never silently truncated or reported fully processed. Preserve
existing 1,000-including-header parser safety unless a separately bounded/versioned
change is proven necessary. Keep raw bytes and prior profiles; replay cannot conflate
A with B, overwrite an existing version or create duplicate authority. Recheck rights,
source/scan/hash freshness and expected revision. No rate application, system match,
canonical write or approval occurs. Inspect the actual UI and retained profile; align
docs, classify changes and complete safe Git publication. Broader bulk capacity and
estimation are later T stages, not hidden additions to this slice.

**Validation:** add focused source-kind/profile/replay/version tests and relevant UI
checks; run existing retained-pricing and client regression. Verify test filenames,
fixture configuration and explicit PostgreSQL isolation before executing:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$profileTestTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('source-profile-tests-' + [guid]::NewGuid())
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp $profileTestTemp tests/test_draft_pricing.py tests/test_draft_pricing_ui.py tests/test_draft_client_pricing.py tests/test_migrations_draft_pricing_sources.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Run destructive-fixture PostgreSQL suites serially only against the verified disposable
test database with its documented cleanup opt-in. Report skips and environment limits.
Demonstrate actual browser upload/scan/profile/save/restart/reopen and inspect output;
exercise missing/invalid/zero/formula values and clear over-limit refusal. Add migration
checks if the minimal contract requires a forward migration. Full PR CI has no docs
path exemption: `.github/workflows/pull-request-validation.yml` runs the required suite.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, inspect AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md,
> docs/CLASSIFIRE_ROADMAP.md, docs/SESSION_HANDOFF.md and
> docs/TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md; reconcile branch/worktrees, main,
> current PR/CI and local changes. Preserve the conflicted root, unrelated work,
> receipts and approved logo; work in an isolated current-main checkout. Implement
> only the next thin T1+T5+T7 interaction: a visible A/B source intake/profile preview.
> A pricelist.xlsx means general products/materials/labour/services; B pricing_library.xlsx
> means Firefly system prices. This is next because current generic workbook selection
> lacks distinct dataset identity and verified source semantics needed by later mapping
> and estimation. Reuse draft_source_intake, draft_pricing_intake/worker/contract/UI,
> storage guards, models and templates; read DRAFT_PRICING_XLSX.md. Add only the minimal
> source/version/profile contract. Users must choose A/B, retain exact bytes/hash,
> inspect supported sheets/headers/counts and unit/price-basis gaps, then save/reopen
> after restart. Preserve unknowns, prior versions and existing parser limits; show
> unsupported content explicitly. Verify rights, scan/hash freshness, replay and stale
> revision behavior. No automatic match, rate application, publication or canonical
> approval. Use synthetic workbooks, marked storage, verified disposable PostgreSQL and
> current scanner definitions; originals were not located, so real-layout acceptance
> awaits authorized files, while synthetic development can proceed. Run focused new
> profile tests plus pricing/UI/client/migration regression, actual browser/restart
> checks, Ruff/Mypy/Bandit/migration checks and required CI. Align docs, classify local
> changes and continue autonomously through explicit-path commit, normal push, PR and
> merge after required checks/reviews pass; verify the merge. Avoid speculative bulk
> infrastructure/model work, preserve human gates, and do not deploy or release.
