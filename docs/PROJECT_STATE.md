# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST).
**Product health:** usable manual Draft Scope editing/import, scope-only PDF/XLSX
reporting and a locally demonstrated saved technical-candidate review UI. Full
applicability, independent estimating and production readiness remain incomplete.
**Verified shared-main baseline:** `18f5177f55458a5a1eb36b8117aea112d7a82f33`,
merged [PR #190](https://github.com/Slayde91/classifire/pull/190).
**Current increment:** `feat/system-match-review-20260905` (P2a).
This checkpoint precedes publication. Verify its final commit/PR/checks/merge from
Git and GitHub; local evidence is not a claim that the increment has merged.

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

**P2a is implemented locally and demonstrated:** select a saved Scope revision,
explicit technical release and one opening/service target; inspect candidates,
references and missing criteria; keep/reject with notes; save, reopen and download
exact historical JSON. The backend validates release/source dependencies and
preserves them across review revisions. Later upstream changes show stale reasons.
Each artifact declares selected-target coverage and other unassessed items. Search
is text retrieval; keeping a candidate is never technical approval or applicability.

**Next after P2a publication: P3a, a manual Draft Estimate UI.** Explicit supported
unit sell rates, attributed overrides, unknowns and partial totals can bring the
fourth capability into a usable prototype. P2b applicability, P3b governed/default/
inferred pricing, evidence intake and full portability remain required work.

## Implemented foundations and remaining gaps

| Area | Verified implementation | Remaining product gap |
| --- | --- | --- |
| UI/API | FastAPI/Jinja shell, Draft Scope editor/import/report routes; new saved candidate-review adapter | Independent Draft Estimate interaction and ChatGPT adapter remain unfinished. |
| Draft Scope | Strict manual v1/imported v2, graph validation, owner/admin access, CAS/history/hash checks, exact JSON exchange | Full evidence locators, service instances, independent planes/treatments, structured contradictions and technical criteria remain incomplete. |
| Source intake | Exact-byte ownership, bounded PDF/XLSX/DOCX adapters, governed technical review/release services | No demonstrated evidence-to-Scope UI or working scan producer/retention workflow. Source-file viewing is not added by P2a. |
| Physical authority | Separate Defect/Opening/Service/link records, admissions, guards, amendments and locks | Draft operations do not satisfy authoritative Phase 8-14 exits; historical real UAT was not refreshed. |
| Technical | Source-bound governance/releases plus independent P2a revision persistence, retrieval, keep/reject notes and stale status | No complete applicability assessment. Scope lacks material/size/FRL/insulation and other required fields. Text scores are not compatibility. |
| Estimating | Decimal helpers, canonical rates/rules/calculation, desk-quote proposals and snapshots | Independent Draft artifacts/UI, broad price methods and overrides, workbook provenance and full recovery coverage remain incomplete. |
| Reporting | Shared scope-only snapshot/renderers, exact PDF/XLSX retention, ownership and stale indication | Other profiles, complete report integration and measured production retention remain future work. |
| Orchestration | Existing transport/acceptance/journal foundations; all new Draft interactions run without AI/OpenClaw | Producer assurance, general recovery and retirement protection parity remain incomplete. |
| Packages | Scope v1/v2 JSON exchange and candidate-review JSON download | Full ProjectPackage archive, export rights/membership projection, candidate import and complete evidence/history portability remain unfinished. |

All Draft facts, including Confirmed labels and imported claims, remain unreviewed.
The database/retained storage hold governed live state; artifacts pin explicit
revisions for interoperability. Neither chat context nor package hashes confer
approval, physical admission, technical authority or human release.

## Project health and measured verification

- Shared-main [CI 33952553673](https://github.com/Slayde91/classifire/actions/runs/33952553673)
  passed on `18f5177`: **1,124 tests, 141 warnings**, plus static checks.
- Final P2a backend and existing technical-governance/publication regressions:
  **78 passed**. Migration/deployment/preflight/legacy checks: **45 passed**.
  These include preserving existing 0028 Scope/report bytes through forward 0029,
  source-revision foreign keys and refusal of destructive downgrade.
- Integrated candidate UI, Draft/import/report and authority regression: **193 passed,
  one local PostgreSQL test skipped**, one existing Starlette warning. All 26 candidate
  HTTP tests are included. These collections overlap; do not add their totals.
- Ruff passed repository-wide. Full Mypy passed 153 source files; final changed
  backend/model/migration/lineage files also passed targeted Mypy. Full Bandit
  checks passed. Existing Starlette/Alembic warnings remain; exact-head hosted CI
  is a separate publication gate, including PostgreSQL checks skipped locally.
- Independent code review identified missed legacy-source staleness and the need
  to recheck write authority after source reads. Both fixes and refusal regressions
  passed. Read/history integrity remains separate from current source eligibility.
- Final actual Chrome workflow passed: import v2 Scope, explicitly enter synthetic
  pipe input, select Scope revision 3/release/linked target, inspect current source
  metadata, keep/reject two candidates, save review revision 2, and download it.
  A later Scope revision 4 showed Out of date; old review bytes stayed unchanged.
- Actual server restart and fresh login passed. Both latest and historical review
  downloads remained identical; no browser page errors. Final review file SHA-256:
  `2f808517d29c32b6afde4f2f378d22aaebcfc3570aa1038a7bad07547fe90590`.
  Historical revision 1 SHA-256:
  `a54eea645fe4c5fdcb7a347e8a6f9ed0c3c31e67ddd736403287971336a666c8`.
  The saved Scope retains three unverified import records, three openings, two
  services and their shared links. Screenshots and downloaded JSON were inspected.
- Final isolated demo database: one Draft, four Scope revisions, one review/two
  review revisions and one explicitly seeded synthetic library release; **zero**
  canonical defects, openings, services, links, estimates or Physical Model Locks.
  The real one-page synthetic PDF hash is
  `1810bb49485e4781ba94baac3140d18fb7b5988a702604996c23ec1ad5cf587d`.
  Seeded approved/clean metadata is fixture setup, not a scanner or technical verdict.
- Candidate head is `0029_draft_system_matches`, following 0028. Limits are 20
  candidates, 1 MiB review JSON, 64 MiB aggregate deduplicated verified source reads
  and newest 20 reviews. No new dependency, provider, database or scheduler.
- No customer evidence, real provider call, operational canonical write/lock,
  deployment or release occurred. Synthetic fixture publication is explicitly
  distinguished from operational technical-library publication.

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

For P3a, inspect pure Decimal helpers first: `D(None)` becomes zero and `calculate_line`
rounds unit sell before multiplication. Existing Estimate creation pins six releases,
line editing requires a Physical Model Lock, and snapshot creation recalculates.
Do not reuse those mutating/gated paths as independent Draft projections. Define
explicit provisional arithmetic, units, original/override provenance and missing-work
presentation without changing canonical technical/commercial rules.

Existing project names/references remain shared for project readers even though Draft
content is owner/admin restricted. Full tenant privacy is not established. Bounded
in-database reports/reviews keep writes atomic; measure growth before adding storage
infrastructure. Existing canonical export/lock/human-release gates remain intact.

## Local change classification

- Protected root `C:\CLASSIFIRE`: branch `gpt/phase8-linked-original-images`, HEAD
  `de0cc5a`, CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
  Verified 46 unstaged modifications, 14 staged additions, four DU conflicts and
  unrelated untracked recovery material. No root changes were made.
- Active `.tmp/system-match-review-20260905`: only this P2a service/contract/model,
  migration/current-head fixtures, UI, synthetic demo/tests and aligned docs.
  Verify final commit/upstream/PR/merge before calling it shared-main capability.
- Prior P0/P1a/P4a worktrees and demos are preserved. The P4a branch was verified
  clean and synced at `d72134a`; its merge is `18f5177`.
- `.tmp/project-package-draft-20260905` retains three unrelated untracked candidate
  files: contract, service and test. Historical 22-test evidence is not current
  qualification; do not silently ship them or replace a working UI with schema work.
- Final synthetic demo uses `.tmp/system-match-review-final-demo-20260905` on port
  8800. Receipts/downloads/screenshots are in `.tmp/system-match-review-final-artifacts`.
  Intermediate 8799 data is preserved as prepublication evidence. None of these
  databases, PDFs, generated JSON, cookies or browser tools belongs in the PR.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Historical receipt:
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The reported rollback-only result created no canonical write or Physical Model Lock.
The receipt/database were not reopened. This does not authorize a real rerun.

## Recommended Next Actions

1. Finish P2a publication after final combined checks, exact-head CI and review;
   verify actual merge and main CI. Do not abandon the implemented UI.
2. **Deliver P3a: independent manual Draft Estimate workspace.** Follow the concrete
   handoff: explicit saved inputs, unit sell rates, unknowns/partial totals, reasoned
   overrides, safe recovery, save/reopen/restart/download and meaningful tests.
3. Retain P1b source intake, P2b applicability, P3b governed/default/inferred pricing,
   further report profiles and full ProjectPackage/ChatGPT access as required work.
   Advance authoritative gates only with their separate evidence and authority.
