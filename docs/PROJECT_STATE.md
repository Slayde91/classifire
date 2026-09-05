# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-06 (AEST).
**Product health:** usable manual Draft Scope/import, candidate review, manual
estimating and Scope reports on shared main. The first estimate-only report
increment is locally implemented with passing browser, restart and focused checks.
Evidence-to-Scope intake, full applicability, governed pricing, complete portability
and production readiness remain unfinished.
**Verified shared-main baseline:** `24ee6e35f181ed544ae82cdc3bc429ce70f49c3b`, merged
[PR #192](https://github.com/Slayde91/classifire/pull/192), feature `8c0da21476e66dac0e1e003b086271d6118c78b2`.
**Current increment:** `feat/draft-estimate-reports-20260905`, based on that main.
This is a prepublication checkpoint. Verify current Git/PR/CI before treating the
report increment as merged or repeating it. Full product completion is not claimed.

## Approved direction and implementation

Approved ADRs 0001/0002 establish four independently callable capabilities over
shared deterministic services, with optional bounded AI. Deliver interactive slices
before broad polish. OpenClaw retirement remains conditional on protection parity.
Database/retained storage hold governed live state; versioned packages carry explicit
revisions. Imported claims, chat and hashes never grant approval or release authority.

| Area | Verified implementation | Remaining gap |
| --- | --- | --- |
| Scope (P0/P1a, merged) | Owner/admin manual editor, graph validation, immutable revisions, exact JSON download, bounded import preview/confirmation with unverified v2 lineage | Evidence-backed intake UI, service instances, full plane/treatment/criteria and contradiction coverage |
| Technical (P2a, merged) | Explicit saved Scope/release/target, source-bound retrieval, keep/reject notes, history/export and stale checks | Retrieval is not applicability; P2b needs sufficient physical criteria and authorised technical constraints |
| Estimating (P3a, merged PR #192) | Manual service/blank-opening lines, exact Decimal amounts, original values, attributed overrides, omit/restore, partial AUD subtotal and exact JSON | Pricing XLSX provenance, governed/default/inferred methods, tax, broader components and complete recovery |
| Reporting (P4a merged; first P4b local) | Separate Scope-only and estimate-only frozen snapshots, paired PDF/XLSX retention, exact downloads and stale warnings | Technical/combined profiles, complete integration and measured production retention |
| UI/API | FastAPI/Jinja shared services; supplied original PNG on login/sidebar; estimate-report routes locally demonstrated | Shared ChatGPT adapter and full tenant privacy remain unproven |
| Source intake | Existing retained-byte checks, PDF/XLSX/DOCX adapters and technical governance | save_upload records pending/not_configured; worker has no registered scan/processing handler; no demonstrated source-to-Scope UI |
| Packages | Scope v1/v2 exchange, candidate/Estimate JSON, retained report outputs | Complete ProjectPackage ZIP, rights/membership projection, candidate/estimate import and evidence/history portability |
| Authority/operations | Guarded canonical models, admissions/locks, release and transport/journal foundations remain intact | Production Phase 8-14 exits, real provider assurance and OpenClaw protection parity are not proven by Draft demos |

## Current report increment

One explicitly selected saved Estimate revision is frozen with its full validated
Scope/optional review context, project labels, author/time and render version.
`draft_estimate_reports.py` retains both outputs atomically; migration
`0031_draft_estimate_reports` adds a separate table with exact Estimate revision
binding. Historical migrations and existing Scope-only reports remain unchanged.
Read/download verifies snapshot/input/byte hashes and current authority; never
regenerates output or reruns calculation, matching, canonical writers or locks.

The real UI previews, creates, lists and downloads reports. Later Estimate, Scope,
optional review/source and project changes flag stale inputs without rewriting
files. Both formats show partial coverage, unknown/unpriced/omitted work, original
values and change history. Exact decimal text preserves values beyond spreadsheet
precision; optional numeric subtotals use a tested safe-precision policy. Tax is
not calculated, technical status is unapproved. See
[DRAFT_ESTIMATE_REPORT_V1_CONTRACT.md](./DRAFT_ESTIMATE_REPORT_V1_CONTRACT.md).

## Project health and measured verification

- P3a [PR CI 33967557386](https://github.com/Slayde91/classifire/actions/runs/33967557386)
  and [main CI 33968038437](https://github.com/Slayde91/classifire/actions/runs/33968038437)
  succeeded: **1,286 tests, 141 warnings**, full Ruff/Mypy/Bandit and one migration head.
  This proves the shared baseline, not publication of the current report changes.
- Current report backend/renderer tests: **21 passed**. Report HTTP, forward migration
  and deployment lineage: **17 passed**, one existing Starlette/httpx warning.
- Combined 12-file regression: **233 passed**, one existing warning, in 313.11 seconds.
  It covers report/Estimate/Scope services and UI, candidate dependencies, existing
  reports, snapshots, desk quotes and physical/admission boundaries. Runs overlap;
  these counts must not be added as unique coverage.
- Additional historical migration/packaging/preflight/legacy checks: **15 passed**,
  one existing Alembic path_separator warning, in 82.39 seconds.
- Full Ruff, Mypy (**160 source files**), Bandit and diff whitespace checks passed.
  Full hosted CI and PostgreSQL coverage remain publication gates at this checkpoint.
- Real Chrome creation/download, later Estimate edit and an **actual server restart**
  passed. Exact PDF/XLSX bytes remained unchanged; stale reasons remained visible.
  Five PDF pages and representative ranges from all six workbook sheets were
  visually inspected. Cell types, filters, exact decimals, no formulas/URLs and
  embedded original logo were checked. The artifact-tool preview had a Windows
  native-module error; read-only Excel/PyMuPDF previews supplied visual verification.
- Tests cover unknown/zero/omitted values, large decimals, long/hostile text, source
  staleness, integrity corruption, atomic renderer failure/mutation, ownership,
  export/technical permissions, revocation and CSRF. No customer/provider UAT ran.
- Read-only synthetic counts after restart: one Scope/four revisions, one Estimate/
  nine revisions and one report; zero canonical Estimate/line, Defect/Opening/Service,
  Physical Model Lock or library-release rows. The demo uses create_all and has no
  alembic_version table; the separate migration test proves 0030-to-0031 upgrade.
- Original supplied logo bytes match the packaged PNG SHA-256
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.
  Existing report outputs were not rewritten. See DRAFT_SCOPE_DEMO.md for receipts.

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

- Active isolated `.tmp/draft-estimate-reports-20260905`: estimate-report model/
  service/renderer/UI, forward migration, tests/current-head fixtures and aligned
  docs. All are part of this increment; publication pending at this checkpoint.
- Protected root remains recovery evidence at `de0cc5a` on
  `gpt/phase8-linked-original-images`, with CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
  Its reverified 46 unstaged modifications, 14 staged additions and four
  DU conflicts are unrelated. Recheck before any recovery; never bulk-stage it.
- Prior P0/P1a/P4a/P2a/P3a branches and demos are preserved. P3a is merged, not work
  to rebuild. The separate ProjectPackage candidate remains three untracked files;
  its historical 22-test result is not current qualification.
- Current synthetic data: `.tmp/draft-estimate-report-demo-20260906`; outputs,
  screenshots and receipts: `.tmp/draft-estimate-report-artifacts`. Browser harnesses
  and synthetic databases/cookies remain outside this feature diff.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Historical receipt:
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The reported rollback-only result created no canonical write or Physical Model Lock.
The receipt/database were not reopened. This does not authorize a real rerun.

## Recommended Next Actions

1. Finish current report publication after exact-head checks/review; verify merge
   and main CI. Do not redo it if current Git shows it has already merged.
2. **Next implementation: P1b, one PDF evidence intake UI path.** Reuse storage and
   report evidence services; deliver real scanning, retained identity, safe viewing
   and explicit reviewed observations into Draft Scope together. Pending/error/
   infected/unconfigured inputs remain blocked. Preserve manual operation and
   demonstrate with synthetic evidence before expanding formats or AI.
3. Continue P2b actual applicability, P3b governed pricing, remaining report profiles
   and full ProjectPackage/ChatGPT access. None is completed by the manual worksheet
   or its reports. Authoritative Phase 8-14 and Human Release gates remain separate.
