# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-06 (AEST). **Health:** usable bounded Draft prototype,
not a production-ready platform. Approved ADRs 0001/0002 remain the target:
independent capabilities, shared deterministic services, optional AI, and conditional
OpenClaw retirement after protection parity. Database/retained storage govern live
state; portable revisions and imports never confer approval or release authority.

**Verified shared main:** `25510565aac69ce7d0b6402423caac251a266236`,
[merged PR #194](https://github.com/Slayde91/classifire/pull/194).
Its feature was `91b9a0be82c5790a7d608da03832c8de2fdfbf86`; PR CI 33981999121
and [main CI 33982467430](https://github.com/Slayde91/classifire/actions/runs/33982467430)
succeeded (1,354 tests, 141 warnings; static checks and one migration head).
**Current increment:** `feat/draft-applicability-review-20260906`, isolated worktree
`C:\CLASSIFIRE\.tmp\draft-applicability-review-20260906`, based on that main.
This document is a prepublication checkpoint for measured-limit review. Check the
branch's PR/current Git evidence before treating this increment as merged or repeating it.

## Evidence-based implementation snapshot

| Area | Implemented and evidenced | Remaining gap |
| --- | --- | --- |
| Scope | Merged manual editor, immutable JSON/import, graph validation, v3 PDF page-linked observations; real-scanner/browser/restart evidence in PR #194 | Automatic analysis, Word/XLSX/images/drawings intake UI, instances, full planes/treatments and contradictions |
| Technical | Merged source-bound candidate retrieval/keep/reject/history. Current local UI checks substrate thickness and measured gap range for one candidate against published limits, saving a v2 review | These are partial numeric checks, not compatibility. Material/size/FRL/insulation/seal depth/configuration/exclusions and complete applicability remain unassessed |
| Estimating | Merged manual AUD unit sell rates, unknown quantities, original values/reasoned overrides, omit/restore, partial subtotals and exact history | Pricing XLSX with cell provenance, governed defaults/inference, broader components and complete recovery |
| Reporting | Merged independent Scope/Estimate PDF+XLSX from frozen snapshots, retained downloads, source claims and stale warnings | Technical/combined profiles and full package export |
| UI/integration | FastAPI/Jinja over shared commands; correct supplied logo served on sign-in/sidebar and new Draft reports | ChatGPT adapter, full tenant/privacy and hosted operational assurance |
| Packages | Scope v1/v2/v3 exchange, match/Estimate JSON, retained reports | Complete ProjectPackage ZIP, membership/export rights, source/history portability and other imports |
| Operations | Canonical authority guards, admissions/locks, human release, exact-byte storage and transport/journal foundations | Production Phase 8-14 exits and OpenClaw protection parity are unproven |

## Current measured-limit increment

New technical publications use manifest v3 and freeze the explicit public field
snapshot. Previously numeric limits were only captured from live variant rows at
retrieval time. Existing release bytes remain unchanged; v1/v2 releases remain
retrievable but cannot claim pinned-limit checks. No database migration is needed.

`draft_constraint_review.py` checks inclusive numeric ranges using Decimal. Explicit
opening selection is required; gap checks additionally require a selected linked
service. A missing measurement, source range/binding or old publication leaves the
check unresolved. Unsupported conditions remain listed; no Applicable or technical
approval verdict is produced. Manual measurements require an evidence/method note
and remain unapproved claims, separate from the saved Scope.

`save_constraint_review` uses existing ownership/permissions, locked dependencies,
source integrity/staleness checks and revision compare-and-swap. It appends match v2;
v1/history bytes survive. Keep/reject notes preserve the measurement review. A later
match revision makes an attached Estimate stale without changing its saved bytes.
No AI, pricing, canonical physical rows, lock or release is invoked by the review.
See [the contract and demo](./DRAFT_CONSTRAINT_REVIEW.md).

## Verification and project health

- Existing candidate/UI/publication regression: **76 passed, 1 existing warning**
  (139.62 seconds), before the final fixture/measurement additions.
- Latest new measurement/service/HTTP/Estimate dependency set: **24 passed, 1 existing
  Starlette/httpx warning** (14.06 seconds). Covers limits, unknowns, invalid numbers,
  source drift, old releases/history, CSRF, stale revisions and ownership.
- Real Chrome: imported synthetic Scope, explicit target/candidate, within-limit r2,
  outside-limit r3, unknown r4, unchanged r1/r2 downloads. Actual server restart
  retained exact r1/r2/r4 downloads. No browser page errors.
- Served logo bytes match `classifire logo.png` exactly (SHA-256
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`).
  The rendered screen was inspected. Source PNG and historical reports were preserved.
- Ruff and Mypy (169 source files) passed. Bandit found one type-narrowing assertion;
  it was replaced with explicit control flow. Final static/broader checks passed as recorded below; exact-head hosted CI remains
  required before publication.
- Source numeric field names do not define service-size measurement semantics. This
  increment deliberately leaves service size and full applicability unresolved.
- No operational/customer database, real provider or production readiness audit ran.
  PDF hosted parser isolation, scanner refresh, quotas, retention and monitoring remain
  open. Manual prototype entry is available without AI or the scanner.

## Local changes and blockers

The current branch contains only the measured-limit service/UI, shared release
snapshot, synthetic demo/tests and aligned documentation. The protected legacy root
remains at `de0cc5a`, branch `gpt/phase8-linked-original-images`, with 46 unstaged
modifications, 14 staged additions, four DU conflicts and CHERRY_PICK_HEAD `c3e4c810`.
Those are unrelated recovery evidence. Three untracked ProjectPackage candidate files
remain in `.tmp/project-package-draft-20260905`; do not publish or delete them implicitly.
Prior demos, source evidence and the original logo are preserved. Synthetic data/logs/
browser artifacts are excluded from Git. No concrete blocker to this branch's normal
validation/publication is known at this checkpoint.

## Recommended Next Actions

1. Finish the current measured-limit increment's validation/publication if outstanding.
2. Deliver **P3b's first pricing-XLSX preview and explicit Draft-rate selection UI**.
   The verified pricing importer currently consumes CSV and can write active library
   rows; it is not a safe browser XLSX intake command. The Draft Estimate still uses
   manual `unit_sell_rate` plus free-text `source_note`, without retained sheet/cell
   lineage. Reuse existing storage/scanner, workbook readers and estimate revisions;
   retain source bytes and explicit mapping/units before applying one unapproved rate.
   Preserve original rates and overrides. This independent pricing slice does not need
   full technical compatibility and must not imply it. See the handoff for boundaries.
3. Continue full applicability and Scope coverage, additional report profiles,
   ProjectPackage exchange and ChatGPT access after their supporting commands are proven.
   These are required product work, not completed phases or reasons to postpone user trials.


## Final local verification checkpoint

Broader measurement/candidate/publication/Estimate/report regression: **241 passed,
1 existing Starlette/httpx warning** (364.94 seconds). Counts overlap earlier runs;
do not sum them. Final Ruff, Mypy (169 source files), Bandit and one Alembic head
(0032) passed. No migration or new dependency. Browser/restart and exact historical
JSON/served-logo checks passed. Final documentation-link/whitespace/diff classification
precedes publication. Exact-head hosted CI and merge/main CI remain to be verified
from the branch PR; this checkpoint does not preclaim their result.
