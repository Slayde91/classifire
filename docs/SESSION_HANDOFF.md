# CLASSIFIRE Session Handoff

**Verified:** 2026-09-06 AEST. Approved ADRs 0001/0002; prototype-first delivery.
**Shared baseline:** `45c0fdd389b066589881531778e6b7a8b898d754`, merged PR #193,
feature `acc2f458fa11a4604d617a990eba6a7de99f0842`. PR CI 33974663186 and
main CI 33975108129 succeeded with 1,315 tests, 141 warnings. Do not redo P0/P1a/
P4a/P2a/P3a or the estimate-only P4b profile. The supplied logo is already on main.
**Current branch:** `feat/draft-pdf-intake-20260906`, upstream origin/main, worktree
`C:\CLASSIFIRE\.tmp\draft-pdf-intake-20260906`. This is a prepublication checkpoint
for the first P1b PDF increment; inspect live Git/PR/CI to determine later publication.
No production phase or full product goal is complete merely because this slice works.

## Start Here / Next Session

First finish PDF publication only if still outstanding: classify/review the exact
diff, commit/push/PR, require exact-head checks/review, merge and verify main CI.
Then the single highest-value implementation task is **P2b's first bounded
applicability review UI**, with explicit physical target inputs and authorized
structured constraint comparisons, saved reasons and unresolved findings.

Why next: source-to-Scope page review now has real-scanner/browser/restart evidence;
manual Scope, candidate review, costing and two report profiles are already usable.
`draft_system_matches._retrieval` supplies only service_type/substrate and explicitly
leaves material, size, orientation, FRL and installation criteria missing.
`technical._compare` is text retrieval, not an applicability engine. More ranking or
report polish would not close that gap. Deliver one visible supported configuration
with the minimum compatible criteria/constraint contract; do not claim complete P2b.

### Inspect before editing

Read AGENTS.md, GOAL.md, canonical docs under docs/, accepted ADRs and Draft contracts.
Inspect branch/HEAD/upstream/status/diff/worktrees, remote main and current PR/CI;
source evidence outranks this checkpoint. Preserve all unrelated work. Use the
existing isolated branch for its outstanding PDF work; use a clean main-based
worktree after merge for the next increment. No root-level architecture/roadmap/
handoff copies exist here; do not create competing documentation.

### Files, prerequisites and blockers

- Reuse `src/classifire/services/draft_scope.py` (the content/envelope contract is
  in this file; there is no draft_scope_contract.py), draft_scope_evidence.py,
  draft_system_matches.py, draft_system_match_contract.py, technical.py and
  technical_validity.py, models, existing Scope/candidate UI/templates and tests.
- DraftOpening currently has plane/substrate/width/height; DraftService has free-text
  service_type and quantity/unit. Add only explicit supported inputs needed for the
  chosen criteria comparison; retain old v1/v2/v3 bytes and imported authority rules.
- Structured technical constraints must come from authorized source/release records,
  not inferred labels. Use a clearly synthetic, isolated source-bound fixture for
  development. If an actual technical rule or source contract is ambiguous, keep
  it unresolved and identify the precise blocker; do not invent compatibility.
- PDF prerequisites: loopback PostgreSQL and ClamD with fresh UTC signature data.
  See DRAFT_PDF_DEMO.md. Current migration is 0032_draft_pdf_sources; preserve older
  migration history and recognized 0029/0030/0031 upgrade lineages.
- No customer/provider runs, operational DB, canonical records/locks, deployment,
  release or protection changes are authorized by this handoff. Do not bypass
  missing evidence, source eligibility, authority or failing CI for a demo.

### Completion criteria and validation

For the next bounded P2b increment, a real UI user supplies explicit supported
criteria for one saved/manual target, inspects evidence-bound comparison reasons
and missing inputs, saves/reopens/downloads an unapproved revision and stops without
pricing. Unsupported criteria/configurations remain unresolved. Input/source changes
show stale status without rewriting older Scope/match/Estimate/report bytes.

Run focused contract/service/HTTP tests and existing Draft/import/PDF/candidate/
Estimate/report regressions. Cover unknowns, boundary/unit values, incompatible
configurations, source/release drift, ownership/revocation, stale save and old-artifact
compatibility. Inspect the rendered interaction and downloaded artifact after restart.
Use only synthetic data. Run full Ruff, Mypy, Bandit, one Alembic head and required CI.
For isolated local tests:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider `
  --basetemp <new-unique-temp-directory> <verified-relevant-test-paths>
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

PDF/quarantine tests need the existing guarded destructive-test URL and explicit
opt-in from test_shared_file_containment.py. Use classifire_containment_test on
loopback 15432, never the separate classifire_draft_pdf_demo or an operational DB.
Do not run concurrent test processes that both reset the same disposable DB.
Local Mypy may require the previously installed lifecycle-stubs directory on
PYTHONPATH; inspect dependency state rather than bypassing type checking. CI installs
.[dev,postgres] and runs the full suite on Linux with PostgreSQL.

## Current changes and measured evidence

PDF service/parser/scanner/UI, v3 refs, StoredFile upload correction, migration 0032,
model, downstream provenance/staleness, CSS and tests/docs are this increment.
No new dependency or agent platform was added. AGENTS.md already embodies the
approved architecture and prototype priority; it required no instruction rewrite.

Final focused set: 67 passed, 2 Windows symlink-permission skips, 2 existing warnings.
Earlier broad Draft/Estimate/report/candidate/storage set: 238 passed, 1 skip,
1 warning. Counts overlap. Migration 0031 -> 0032 and historical 0031 checks passed.
Real ClamD/Chrome upload, page view, explicit save, exact v3 download, restart and
manual-edit review warning passed. Logo exact-byte and visual checks passed.
Read PROJECT_STATE.md and PR for final static/hosted checks; do not infer publication.

Synthetic demo: port 8803, marked data `.tmp/draft-pdf-demo-20260906`, screenshots/
receipts/source/artifacts `.tmp/draft-pdf-artifacts`, harnesses
`.tmp/scope-browser-test-tools`. Real scanner database 28108 dates from 2026-08-30;
freshness can expire and must be refreshed, never forced clean. Dedicated loopback
PostgreSQL/ClamD containers are named classifire-pdf-intake-20260906-pg / -av.
Synthetic counts after restart/edit: one PDF, three Scope revisions, zero canonical
Estimate/Opening/Service/PhysicalModelLock. Draft report QA may add Draft reports only.

Protected root: de0cc5a on gpt/phase8-linked-original-images, CHERRY_PICK_HEAD
c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7; 46 unstaged modifications, 14 staged
additions and four DU conflicts remain unrelated recovery evidence. Recheck read-only.
Never reset/clean/resolve/bulk-stage/publish it implicitly. Preserve the original logo,
prior worktrees/demos and three untracked ProjectPackage candidate files. Synthetic
DBs, session markers, cookies, logs, screenshots and browser tools stay outside Git.

## Recommended Prompt for New Session

```text
Continue CLASSIFIRE from verified repository state. Read AGENTS.md, GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md, docs/CLASSIFIRE_ARCHITECTURE.md, docs/SESSION_HANDOFF.md, ADRs 0001/0002 and relevant Draft contracts. Inspect branch/HEAD/upstream/status/diffs/worktrees, remote main and current PR/CI before editing. Preserve the conflicted C:\CLASSIFIRE root, unrelated local changes, prior demos and ProjectPackage candidate. Finish feat/draft-pdf-intake-20260906 publication only if still outstanding, then use an isolated current-main worktree. Do not redo merged manual Scope/import, candidate review, estimating, Scope/Estimate reports or demonstrated PDF intake.

Deliver one next task: P2b's first bounded applicability review UI. Current draft_system_matches._retrieval only supplies service_type/substrate; material, size, orientation, FRL and installation criteria remain missing, and technical._compare is text retrieval. Capture explicit target criteria and compare only authorized structured constraints for one supported configuration, showing reasons and unresolved inputs in a saved unapproved revision. Reuse services/draft_scope.py (contract is in this file), draft_scope_evidence.py, draft_system_matches.py, draft_system_match_contract.py, technical.py, technical_validity.py, models and existing UI/templates/tests. Preserve v1/v2/v3 bytes, source/release authority and stale dependencies. Never invent technical rules or convert similarity into applicability; ambiguous source/rule semantics are a concrete blocker. Use only synthetic fixtures; no customer/provider, operational DB, canonical writes/locks, deployment or release.

Done means the real UI can enter criteria, inspect results, save, reopen after restart and download exact history without pricing or approval. Cover unknowns, limits/units, incompatibility, source/release drift, permissions, stale saves and old-artifact compatibility; run relevant Draft/PDF/import/candidate/Estimate/report regressions, Ruff, Mypy, Bandit, one Alembic head and full required CI. PDF tests require fresh ClamD and isolated PostgreSQL; destructive test DB and browser demo DB are distinct. Inspect outputs, reconcile docs and classify the diff. Continue autonomously through implementation, validation, commit, normal push, PR and merge after exact-head checks/reviews pass; verify merge/main CI. Preserve unrelated work, avoid speculative expansion and stop only for a concrete blocker. The full product goal remains active after this bounded milestone.
```

## Final local verification checkpoint

Full Ruff, Mypy (167 source files), Bandit and one Alembic head (0032) passed;
Git whitespace and relative documentation-link checks passed. Report-specific tests
had 43 passes and two header-position failures; the original C1 placement was restored
and both unchanged assertions passed on rerun. No tests were weakened.
New Draft Scope and Estimate outputs share the supplied original PNG renderer;
Chrome verified new PDF/XLSX creation and unchanged historical downloads. Both PDF
pages and workbook cell types/source references were inspected. Final browser console
had no errors. Existing canonical/legacy output rendering was not migrated.
Full hosted current-head CI/review remains the publication gate at this checkpoint.
