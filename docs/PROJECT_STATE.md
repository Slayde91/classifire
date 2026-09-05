# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-06 (AEST).
**Product health:** usable manual Draft Scope/import, candidate review, manual
estimating and independent Scope/Estimate reports. The first PDF evidence review
path now has local real-scanner browser and restart evidence. Full Scope analysis,
actual applicability, governed pricing, complete portability and production readiness
remain unfinished; no full product or production-phase completion is claimed.
**Verified shared-main baseline:** `45c0fdd389b066589881531778e6b7a8b898d754`,
[merged PR #193](https://github.com/Slayde91/classifire/pull/193), feature
`acc2f458fa11a4604d617a990eba6a7de99f0842`.
**Current increment:** `feat/draft-pdf-intake-20260906` in
`C:\CLASSIFIRE\.tmp\draft-pdf-intake-20260906`, based on that main.
This is a prepublication checkpoint. Verify current Git/PR/CI before treating the
PDF changes as merged or repeating work already published.

## Approved direction and implementation

Approved ADRs 0001/0002 establish four independently callable capabilities over
shared deterministic services, with optional bounded AI. Deliver interactive slices
before broad polish. OpenClaw retirement remains conditional on protection parity.
Database/retained storage hold governed live state; versioned packages carry explicit
revisions. Imported claims, chat and hashes never grant approval or release authority.

| Area | Verified implementation | Remaining gap |
| --- | --- | --- |
| Scope (P0/P1a merged; first P1b local) | Owner/admin editor, graph validation, immutable JSON revisions/import; PDF upload/scan/page review appends v3 evidence-linked observations | Automatic analysis, other formats, service instances, full planes/treatments/criteria and contradiction coverage |
| Technical (P2a merged) | Saved Scope/release/target, source-bound retrieval, keep/reject notes, history/export and stale checks | P2b actual applicability needs sufficient physical inputs and authorized structured constraints; text retrieval is not compatibility |
| Estimating (P3a merged) | Manual service/blank-opening lines, Decimal amounts, originals and reasoned overrides, omit/restore, partial AUD subtotal and exact JSON | Pricing XLSX provenance, governed/default/inferred methods, broader components and complete recovery |
| Reporting (P4a and estimate-only P4b merged) | Independent frozen snapshots, paired PDF/XLSX, exact historical downloads and stale warnings; local v3 page claims flow into outputs | Technical/combined profiles, production retention and full package export |
| UI/API | Shared FastAPI/Jinja use cases; supplied logo on sign-in/sidebar; local PDF evidence routes | Shared ChatGPT adapter and full tenant privacy remain unproven |
| Source intake (first P1b local) | Exact-byte ClamD adapter, unique atomic upload, PostgreSQL quarantine coordination, bounded parser child, authorized PNG pages and unreviewed text | OCR/other formats, hosted parser isolation, quotas/retention/monitoring and a general durable queue |
| Packages | Scope v1/v2 exchange plus local v3 page claims, candidate/Estimate JSON and retained reports | Complete ProjectPackage ZIP, exact rights/membership projection, source bytes/history portability and other artifact imports |
| Authority/operations | Existing canonical guards, admissions/locks, human release and transport/journal foundations | Production Phase 8-14 exits, real provider assurance and OpenClaw protection parity are not proven by Draft demos |

## Current PDF increment

`draft_pdf_ui.py` calls `services/draft_pdf_intake.py` for explicit upload, scan,
page viewing and reviewed observation saves. `malware_scan.py` talks to real ClamD;
`draft_pdf_worker.py` reuses the report normalizer in a bounded child process.
Migration `0032_draft_pdf_sources` adds exact Draft/StoredFile byte bindings and
scan/document metadata. Supported PDFs: 10 MiB, 50 pages, 20 per Draft. Missing,
failed, stale, infected or unsupported input cannot become viewable evidence.

A v3 Scope reference pins the observation hash, source/hash/size, page locator/text
hash, normalized document and scan hashes, reviewer/time. A manual edit keeps the
old review claim visibly stale; imported claims become imported_unverified. Earlier
v1/v2/v3 downloads and generated reports are not rewritten. Source changes propagate
stale status to dependent reports/estimates. Saving review creates no canonical
physical rows, technical approval, price, lock or release. See the
[contract](./DRAFT_PDF_EVIDENCE_V1_CONTRACT.md) and [demo](./DRAFT_PDF_DEMO.md).

## Project health and measured verification

- Shared PR #193 [PR CI 33974663186](https://github.com/Slayde91/classifire/actions/runs/33974663186)
  and [main CI 33975108129](https://github.com/Slayde91/classifire/actions/runs/33975108129)
  succeeded: **1,315 tests, 141 warnings**, Ruff/Mypy/Bandit and one migration head.
  Initial PR CI had caught lost 0029 upgrade recognition; the corrected service
  preserves recognized lineages. The original failing assertion remains intact.
- Current final focused PDF/HTTP/parser/scanner/storage/migration/readiness set:
  **67 passed, 2 skipped, 2 warnings** (156.20 seconds). Both skips require Windows
  symlink privileges; full Linux CI must cover them. Warnings are existing
  Starlette/httpx and Alembic path_separator deprecations.
- Earlier combined Draft/Estimate/report/candidate/storage regression:
  **238 passed, 1 skipped, 1 warning** (410.92 seconds). Runs overlap; do not sum
  counts. New migration proves 0031 -> 0032 preserves existing Estimate JSON and
  PDF/XLSX bytes and enforces exact source binding; historical 0031 test stays pinned.
- Real Chrome upload -> pending -> real clean scan -> retained raster page ->
  explicit observation -> saved v3 download passed. An actual process restart
  preserved page access and exact revision-2 bytes. Manual edit to revision 3
  exposed the changed-review warning without changing revision 2.
- Real scanner: isolated loopback ClamAV 1.5.4, signature database 28108, published
  2026-08-30. The actual scan metadata is retained in the synthetic source; the
  seven-day freshness rule can block it later and must not be bypassed. Tests use
  controlled verdict fixtures for failures; those are not real malware-scanning proof.
- Synthetic demo counts after restart/edit: one PDF source, three Scope revisions;
  zero canonical Estimate, Opening, Service or Physical Model Lock rows. Demo
  create_all is distinct from the passing forward-migration test.
- Served logo bytes match the owner's original PNG SHA-256
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.
  Sign-in/sidebar were visually inspected; existing report outputs were not rewritten.
- Full hosted current-head CI/review remains a publication gate at this checkpoint.
  No customer evidence, real provider, operational database, deployment or release ran.

## Dependencies and technical debt

PDF review requires PostgreSQL and a trusted reachable ClamD with a fresh signature
database. SQLite manual entry is unaffected. The configured daemon must use UTC;
its unauthenticated TCP endpoint requires trusted private access. This bounded
synchronous command is not a general durable worker. Linux adds parser resource
limits; Windows process/timeout/data bounds are not a complete OS sandbox.

Supported retention is append-only with no source-delete UI or automatic cleanup.
An aborted DB publication may leave unreferenced exact-byte storage; never blindly
delete it. Global quotas, orphan reconciliation, retention duration/legal holds,
scanner update monitoring, hosted isolation and measured concurrent capacity remain
pre-customer deployment requirements. Existing storage ACLs are trusted. Uploaded
PDFs are not yet included in a portable archive; source metadata imports confer no
local viewing or approval rights. These gaps do not justify fake clean flags.

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

- Active isolated PDF worktree: bounded scan/parser/intake services, v3 evidence
  extension, model/additive migration, UI/CSS, shared upload correction, downstream
  provenance/staleness, tests/current-head fixtures and aligned documentation.
  These are the selected P1b increment; publication is pending at this checkpoint.
- Protected root stays at `de0cc5a` on `gpt/phase8-linked-original-images`, with
  CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`. Its 46 unstaged
  modifications, 14 staged additions and four DU conflicts are unrelated recovery
  evidence. Recheck read-only; never bulk-stage, reset, resolve or publish it implicitly.
- Prior P0/P1a/P4a/P2a/P3a/P4b branches, demos and the original logo remain preserved.
  The separate ProjectPackage candidate remains three untracked files; its historical
  22-test result is not current qualification.
- Synthetic PDF data: `.tmp/draft-pdf-demo-20260906`; screenshots, source and receipts:
  `.tmp/draft-pdf-artifacts`; browser harnesses: `.tmp/scope-browser-test-tools`.
  Dedicated loopback containers `classifire-pdf-intake-20260906-pg` and
  `classifire-pdf-intake-20260906-av` have no customer host mounts. Demo/test databases
  are separate. No synthetic data, session marker, cookies or QA outputs enter Git.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Historical receipt:
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The reported rollback-only result created no canonical write or Physical Model Lock.
The receipt/database were not reopened. This does not authorize a real rerun.

## Recommended Next Actions

1. Finish current PDF publication after exact-head CI/review; verify merge and main
   CI. Do not redo it if current Git shows it already merged.
2. **Next implementation: P2b's first bounded applicability review UI.** Current
   retrieval uses service type/substrate while physical material/size/orientation/FRL
   and installation criteria are missing. Capture explicit target inputs and compare
   only authorized structured constraints, saving reasons and unresolved findings.
   Reuse existing Scope/match/technical services; never promote text similarity or a
   synthetic fixture into technical authority. Deliver one visible interaction with
   its minimum compatible contract, tests, reopen/download and stale dependencies.
3. Continue governed pricing, remaining reports, full ProjectPackage/ChatGPT access
   and broader Scope analysis. Authoritative Phase 8-14 and Human Release are separate
   gates; this PDF milestone does not complete the full product goal.

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
