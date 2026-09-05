# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST).
**Product health:** shared main supports manual Draft Scope editing/import,
scope-only PDF/XLSX reporting and saved technical-candidate review. The manual
Draft Estimate UI is implemented locally with passing HTTP/backend checks and a
successful real-browser interaction and actual server restart. Local checks passed;
publication remains pending at this checkpoint. Full applicability,
governed estimating coverage and production readiness remain incomplete.
**Verified shared-main baseline:** `02dc20022b87b532c3d860d4c12527bdfb60dd05`,
merged [PR #191](https://github.com/Slayde91/classifire/pull/191), from feature commit
`21b53363b3e5037b7ad3496c002d0cd84c47fe21`.
**Current increment:** `feat/draft-estimate-ui-20260905` (P3a), based on that main.
P3a changes are currently local and uncommitted. Do not infer a P3a commit, PR,
merge or production release from this checkpoint.

## Approved direction and active work

Accepted [ADR 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md) and approved
[ADR 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md) establish four
independently callable capabilities over shared deterministic services and optional
bounded AI. Prototype-first delivery is approved. No new agent fleet or framework
is needed for the demonstrated workflows; OpenClaw retirement remains conditional.

**P0, P1a and P4a are merged.** `/scopes` supports manual editing, validation,
revision persistence, exact JSON download, bounded import preview/confirmation and
v2 unverified source lineage. Reporting freezes one selected Scope/project snapshot
and retains the exact PDF/XLSX pair; later upstream edits flag it as stale.

**P2a is merged and was demonstrated:** select a saved Scope revision,
explicit technical release and one opening/service target; inspect candidates,
references and missing criteria; keep/reject with notes; save, reopen and download
exact historical JSON. The backend validates release/source dependencies and
preserves them across review revisions. Later upstream changes show stale reasons.
Each artifact declares selected-target coverage and other unassessed items. Search
is text retrieval; keeping a candidate is never technical approval or applicability.

**P3a is implemented locally:** `/scopes/{draft_id}/estimates` creates an independent
Draft from an exact saved Scope, optionally retaining a matching candidate-review
revision. Users add service-specific or blank-opening work, enter provisional AUD
unit sell rates, save reasoned quantity/rate overrides, omit/restore the same line,
reopen history and download exact JSON. Unknown quantity/rate remains unpriced;
zero stays explicit. Totals are always labelled partial and exclude tax, which is
not calculated. Nonblank-opening work remains explicitly unassessed.

The shared contract/service owns arithmetic, recovery identity, original values,
change history and authority. This slice creates no canonical Estimate/physical
model or lock and requires no pricing library, AI or OpenClaw. Browser/restart and
combined local checks passed; review and publication remain at this checkpoint.
After those gates, the next implementation is P4b: estimate-only Draft PDF/XLSX
reports from an exact saved Estimate, with no upstream recalculation.

## Implemented foundations and remaining gaps

| Area | Verified implementation | Remaining product gap |
| --- | --- | --- |
| UI/API | FastAPI/Jinja Scope/import/report/candidate routes; local independent Draft Estimate adapter and original supplied UI logo | Estimate publication remains pending at this checkpoint. ChatGPT adapter is unfinished. |
| Draft Scope | Strict manual v1/imported v2, graph validation, owner/admin access, CAS/history/hash checks, exact JSON exchange | Full evidence locators, service instances, independent planes/treatments, structured contradictions and technical criteria remain incomplete. |
| Source intake | Exact-byte ownership, bounded PDF/XLSX/DOCX adapters, governed technical review/release services | No demonstrated evidence-to-Scope UI or working scan producer/retention workflow. Source-file viewing is not added by P2a. |
| Physical authority | Separate Defect/Opening/Service/link records, admissions, guards, amendments and locks | Draft operations do not satisfy authoritative Phase 8-14 exits; historical real UAT was not refreshed. |
| Technical | Source-bound governance/releases plus independent P2a revision persistence, retrieval, keep/reject notes and stale status | No complete applicability assessment. Scope lacks material/size/FRL/insulation and other required fields. Text scores are not compatibility. |
| Estimating | Existing canonical calculations/desk quotes plus local P3a manual Draft artifact, exact Decimal subtotals, attributed overrides and omission/restoration | Governed/default/inferred rates, pricing workbook provenance, tax, multi-component work and complete shared-work recovery remain unfinished. |
| Reporting | Shared scope-only snapshot/renderers, exact PDF/XLSX retention, ownership and stale indication | Other profiles, complete report integration and measured production retention remain future work. |
| Orchestration | Existing transport/acceptance/journal foundations; all new Draft interactions run without AI/OpenClaw | Producer assurance, general recovery and retirement protection parity remain incomplete. |
| Packages | Scope v1/v2 JSON exchange, candidate-review JSON and local exact Draft Estimate JSON download | Full ProjectPackage archive, export rights/membership projection, candidate/estimate import and complete evidence/history portability remain unfinished. |

All Draft facts, including Confirmed labels and imported claims, remain unreviewed.
The database/retained storage hold governed live state; artifacts pin explicit
revisions for interoperability. Neither chat context nor package hashes confer
approval, physical admission, technical authority or human release.

## Project health and measured verification

- P2a [PR CI 33955043986](https://github.com/Slayde91/classifire/actions/runs/33955043986)
  and [main CI 33955401203](https://github.com/Slayde91/classifire/actions/runs/33955401203)
  both succeeded with **1,191 tests and 141 warnings**. These establish the merged
  `02dc200` baseline, not the uncommitted P3a increment.
- P3a HTTP tests: **40 passed** using real session login, file-backed synthetic
  SQLite and the real routes/templates. After tightening the request-limit test
  to 64 KiB + 1, its **three affected cases passed** again. These are overlapping
  runs, not 43 different tests. One existing Starlette/httpx warning remains.
- P3a backend verification: **53 passed in 71.45 seconds**. Migration verification:
  **27 passed**, followed by **20 readiness/preflight/legacy checks passed** after
  correcting the missing-table test fixture that caused the original run to fail.
  All 47 checks are now verified; the earlier fixture failure is resolved.
- Combined 15-file regression: **328 passed, one dedicated PostgreSQL concurrency
  test skipped**, one existing warning, in 1,173.05 seconds. Full Ruff, Mypy
  (157 source files), Bandit and `git diff --check` passed. Hosted CI remains to
  verify the skipped database case and full-suite result. Independent local code
  review found no remaining supported-path correctness or security blocker.
- HTTP verification covers direct six-decimal rates, rounded-line sums, null versus
  zero, original/override history, omitted-target duplicate refusal/restoration,
  optional review binding, stale dependencies, old-tab conflicts, permission
  revocation/CSRF, safe rendering and retained-amount corruption refusal. A fresh
  client after disposing database connections returned unchanged historical bytes.
- Review caught two real form issues before browser UAT: an unselected optional
  review initially supplied revision 1, and status buttons initially submitted
  pricing fields. Defaults now leave both attachment fields blank, and separate
  update/status forms pass actual rendered-field submission tests.
- Current schema head is **0030_draft_estimates**, after the merged 0029 candidate
  review migration. New parent/revision tables bind exact saved Scope and optional
  review revisions; destructive downgrade is refused. Limits are 100 lines,
  100 history events per line, 2 MiB JSON, 64 KiB browser forms and newest 20
  accessible estimates. No new dependency, provider, database or scheduler.
- The UI serves the supplied original PNG at `static/brand/classifire-logo.png`.
  Its verified SHA-256 is
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.
  CSS frames its original pixels on white. The existing report master/logo and
  report renderers are unchanged; the current logo change is scoped to the UI.
- **P3a real Chrome interaction passed:** create/import/edit Scope through four
  revisions; retain eight Estimate revisions over two service targets and one blank
  opening; preserve an unknown rate; price 1000 mm at 0.001234 to obtain 1.23;
  override values with originals/history retained; omit and restore; display the
  partial **AUD 441.23 subtotal with tax not calculated**. A later Scope edit flagged
  staleness while saved Estimate revision 2 and revision 8 bytes stayed unchanged.
  Sign-in, sidebar and Estimate screenshots were inspected with the correct
  original supplied logo. **Actual server restart passed** after HTTP readiness, with both historical
  revision 2 and latest revision 8 bytes unchanged. The first harness navigation
  raced startup; the ready-server rerun passed without a product change.
- Historical P2a browser/restart evidence remains in the preserved final demo:
  review revision 2 file SHA-256
  `2f808517d29c32b6afde4f2f378d22aaebcfc3570aa1038a7bad07547fe90590`;
  revision 1 file SHA-256
  `a54eea645fe4c5fdcb7a347e8a6f9ed0c3c31e67ddd736403287971336a666c8`.
  The recorded Scope import/review/stale/restart workflow retained unchanged
  downloads and no canonical physical records, Estimates or locks. Those demo
  receipts were not reopened for this documentation edit.
- No customer evidence, real provider call, operational canonical write/lock,
  deployment or release is part of P3a validation. Optional technical-library
  approval/clean states are explicitly seeded synthetic fixtures, not a scanner
  result or an operational technical verdict.

## Dependencies and technical debt

P1b needs an actual scanner producer, retained source policy, safe concurrent upload
and verified storage. `save_upload` records pending/not_configured; `worker.py` has
no registered processing handler. Optional `clamd` alone is not a working scan path.
PostgreSQL provides existing locked clean-byte reads; SQLite demonstration does not
prove production quarantine serialization. Do not weaken these guards for intake.

P2a freezes allowlisted library fields because current release manifests do not
freeze every matching field. Legacy unbound sources remain visibly unresolved. Live
source/release changes flag staleness without erasing historical metadata. Unapproved
notes may be appended on a stale basis; only an explicit new retrieval refreshes
candidates. Current source links show metadata, not retained-file viewing. Full
applicability requires sufficient input/evidence contracts and actual criteria checks.

P3a deliberately uses the existing `money` helper on quantity multiplied by a
six-decimal unit sell rate, then sums the rounded lines. It does not call `D(None)`
or `calculate_line`, which would erase missing values or round a unit rate to cents
before multiplication. Canonical Estimate creation, locked line mutation and the
recalculating snapshot builder retain their existing gates. The separate manual
contract is [DRAFT_ESTIMATE_V1_CONTRACT.md](./DRAFT_ESTIMATE_V1_CONTRACT.md).

Supported recovery is narrow: one service-specific line across all its opening
links, excluding shared-opening work, or one blank-opening closure line. Duplicate
targets are refused even when omitted; restore the existing line. Quantity/rate
changes need a local author/time and reason, while original values and prior events
remain. Service units are fixed to Scope (`each`, `m`, `mm`); each is integral.
Blank openings accept explicit manual `each` or `m2` quantities. There is no unit
conversion, inferred quantity, library/default price, tax calculation or full
rate-inclusion ledger. P3b and other report profiles remain separate work.

Existing project names/references remain shared for project readers even though Draft
content is owner/admin restricted. Full tenant privacy is not established. Bounded
in-database reports/reviews keep writes atomic; measure growth before adding storage
infrastructure. Existing canonical export/lock/human-release gates remain intact.

## Local change classification

- Protected root `C:\CLASSIFIRE` remains recovery evidence. Its last documented
  checkpoint was branch `gpt/phase8-linked-original-images`, HEAD `de0cc5a`,
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`, staged/unstaged work,
  four DU conflicts and unrelated untracked material. This documentation edit did
  not re-audit that checkout; do not resolve, clean or publish it implicitly.
- Active `.tmp/draft-estimate-ui-20260905`: P3a service/contract/models, 0030 migration
  and current-head fixtures, routes/templates/tests, the supplied UI logo and
  related presentation, plus aligned documentation. These local changes are
  uncommitted at this checkpoint; the root session owns final classification.
- P2a is merged through PR #191. Its `.tmp/system-match-review-20260905` worktree,
  earlier P0/P1a/P4a worktrees and demos remain preserved historical checkpoints.
- `.tmp/project-package-draft-20260905` retains the unrelated contract/service/test
  candidate. Historical 22-test evidence is not current qualification; do not
  silently ship it or substitute schema work for the visible prototype.
- Historical P2a demo uses `.tmp/system-match-review-final-demo-20260905`; receipts,
  downloads and screenshots are in `.tmp/system-match-review-final-artifacts`.
  Its prior port 8800 assignment is not a claim that a server remains running.
  Synthetic databases, source PDFs, JSON, cookies and browser tools stay outside
  the PR. P3a artifacts are retained in `.tmp/draft-estimate-artifacts`, with data in
  `.tmp/draft-estimate-demo-20260905`. Read-only counts found one Scope/four
  revisions and one Draft Estimate/eight revisions; zero library releases or
  canonical Estimate/line/physical/lock rows. See DRAFT_SCOPE_DEMO.md for hashes.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Historical receipt:
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The reported rollback-only result created no canonical write or Physical Model Lock.
The receipt/database were not reopened. This does not authorize a real rerun.

## Recommended Next Actions

Complete P3a's remaining review and publication
checks first; verify the actual merge and main CI before treating it as shared main.

1. **Next implementation: P4b estimate-only Draft PDF/XLSX reports.** Select one
   saved Estimate revision, preview its partial/unpriced/omitted work, freeze the
   exact Estimate and project labels once, and retain/download both output formats.
   Reuse `services/draft_scope_reports.py`, `outputs/draft_scope.py` and existing
   report UI/security patterns with an explicit Estimate profile and dependency
   binding. Do not refresh saved quantities/prices, run retrieval/AI or call the
   canonical snapshot builder.
2. Verify PDF/XLSX amounts, units, originals/overrides, missing-work qualifications,
   permissions, integrity refusal and staleness warnings and unchanged downloads after edits
   and restart. Preserve old scope-only profiles and migration history.
3. Retain P1b intake, P2b applicability, P3b governed/default/inferred pricing,
   additional report profiles and ProjectPackage/ChatGPT access as required work.
   The manual worksheet and its future reports do not complete production
   estimating, full recovery or authoritative Phase 10-14/human-release gates.
