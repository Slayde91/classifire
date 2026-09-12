# CLASSIFIRE Session Handoff

Reconciled 2026-09-13. Current source, Git/CI and runtime evidence override this checkpoint.
Read [PROJECT_STATE.md](./PROJECT_STATE.md), [architecture](./CLASSIFIRE_ARCHITECTURE.md),
[roadmap](./CLASSIFIRE_ROADMAP.md) and root GOAL.md. The four independent capabilities
and full production objective remain unchanged and incomplete.

## Verified publication and runtime

- Workspace PR #260 merged as `3eabb23`; exact-head and post-merge CI passed 2,113 tests
  and all remaining checks. Comparison PR #261 merged as `095ee3d`; exact-head run
  34707202158 and post-merge run 34708282314 each passed 2,127 tests and remaining checks.
- Row-authoring PR #262 merged source `6c30361` as
  `48b4b111f6c8f539a9aa7d8211be5fcb2e61db52`. Exact-head run 34709110199 passed 2,134
  tests and remaining checks. The merged tree equals the tested source. No required
  reviews were configured; no human GitHub review is claimed. Post-merge run
  34710331473 is still running at this checkpoint; poll the same job.
- Current checkout: `C:/CLASSIFIRE/.tmp/multi-review-package-20260913`, branch
  `feat/multi-review-package-20260913`, based on merged `48b4b11`. The coherent change
  is locally validated but not yet committed or published at this source checkpoint.
- Live port 8820 remains the separately approved diagnostic source `e2e8292`.
  Its activation receipt verified fresh backup/restore, all 69 tables, five Scope
  revisions, two packages and two originals. No newer workspace deployment is implied.
- Connected upload remains refused by CLIENT_FILE_UNAPPROVED_HOST. No allowlist,
  OAuth/tunnel, client grant or provider configuration change is part of this increment.
- Separate synthetic demos: 8840 integrated workspace, 8841 pinned row authoring,
  8842 current multi-review candidate. Only 8842 was restarted in this increment.
  PostgreSQL tests used disposable 15433, never live 15432. The 8842 demo uses SQLite.
- The separate row-authoring rehearsal restored an existing synthetic clone on 15433;
  all 69 tables/schema/rows and retained artifacts verified. It is not a fresh live backup.
  The prepared 6c30361 activation plan is unapproved and excludes the newer v6 change.

## Current implementation

[The multi-review contract](./MULTI_REVIEW_PROJECT_PACKAGES.md) describes the exact
format, dependency and authority rules. Existing services and tables are extended:

- Several Opening/Service rows and blank Openings retain explicit saved review choices.
  Updating one row preserves the others. Repeated URL references represent working
  choices; a separate package preview/save is the durable checkpoint.
- Forward ProjectPackage v6 holds exact reviews, an optional existing Estimate and
  selected individual reports/originals. Extra reviews never become Estimate inputs.
- Import mapping v3 binds every source review to its exact new local identity. Original
  archives, report bytes and evidence remain retained; foreign claims stay unverified.
- Saved/imported workspace links reopen exact selected revisions, including historical
  items outside the recent picker window. Invalid selections fail visibly.
- Technical client grants apply to every selected review in preparation, confirmation
  and downloads. A separate same-user browser confirmation still authorizes Draft writes.
- No new model, table, migration, dependency, provider or canonical writer is added.
  Blank openings remain valid with zero Services; unresolved relationships stay in review.

Older binaries cannot read newly written v6 packages or mapping-v3 imports. A future
activation plan must cover this forward-format recovery boundary; a simple binary
rollback after new writes is not a transparent downgrade. Preserve user records.

## Validation

109 unique affected tests passed with the selected checkout's PYTHONPATH, disabled
pytest cache and fresh basetemps. The inventory includes 65 new cases across register,
package, import, client authorization, UI and original-bearing Word coverage. Full Ruff,
Mypy (233 source files), Bandit, both JavaScript syntax checks and diff whitespace checks
passed. Alembic remains at the single 0047_draft_scope_docx_sources head.

Actual isolated Edge UAT saved reviews for two Services and a blank Opening, updated
one, separately saved v6 and reopened the same set. After saving a newer first review,
restart preserved the package's 2/1/1 selection, exact Scope/ZIP and all review versions.
All non-login SQLite tables were unchanged by restart verification; canonical counts
remained zero. Actual ZIP upload, separate import confirmation, exact mapped workspace
reopening and separate re-export preserved the original archive byte for byte. No page
errors or mobile document overflow were observed. Desktop/mobile and import screenshots
and ZIP contents were inspected. These were synthetic automated confirmations.

The separate disposable PostgreSQL regression retained the exact DOCX, five Word
references, one picture reference, three reviews and nested origins through import and
re-export. Shared quarantine correctly blocked all copies of the same source. It also
preserved earlier v5 bytes. The browser package fixture itself contained JSON, not DOCX;
the Word regression is separate evidence, not a claimed browser Word upload.

Private evidence under C:/CLASSIFIRE/.tmp/:

- `multi-review-package-validation-20260913/unique-test-inventory.json` and test logs.
- `multi-review-package-uat-20260913/`: browser, restart and import-browser receipts,
  package/re-export ZIPs, screenshots and synthetic SQLite data.
- `multi-review-package-ui-20260913/`: historical picker and imported landing checks.
- `multi-review-word-package-tests-20260913-b/`: original-bearing ZIP regression outputs.

Do not rerun the completed browser creation scripts; their saved Drafts and receipts
already exist. Login-related table changes are expected only where explicitly recorded.

## Classification, limitations and next work

The current diff consists of shared package/import/register services, client grant
checks, UI/JavaScript/templates, six synthetic regression files and documentation.
Private logs, sources, SQLite data and generated outputs remain outside Git. Preserve
the conflicted root at de0cc5a with CHERRY_PICK_HEAD c3e4c810, all unrelated modifications
and four DU conflicts, and the older workspace's two untracked browser artifacts.

1. Finish explicit-file commit/push/PR publication and observe exact-head CI and required
   reviews before merging. Record the actual commit and merge result in private receipts.
   Poll existing jobs; an observation timeout is not a reason to restart them.
2. Prepare a fresh exact-candidate activation/recovery plan before requesting deployment
   approval. No activation, provider enablement or host/OAuth/tunnel change is authorized here.
3. Preserve the confirmed private Draft reference and unknowns. Follow
   [reference readiness](./PHYSICAL_REFERENCE_READINESS.md) before any real evaluation;
   no application accuracy score or blind independent benchmark is established.

The complete redesign and production exits remain open: general multimodal accuracy,
full technical applicability, calibrated automatic pricing, combined multi-review
reporting, full project history, representative scale/accessibility and operational
assurance. One Estimate and existing individual report formats remain selected at a time.
Do not rebuild completed Word/client/confirmation work or promote synthetic Draft checks
to technical approval, canonical admission, a Physical Model Lock or production release.
