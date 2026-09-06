# CLASSIFIRE Project State

## Evidence-based snapshot

Verified 2026-09-06 from the isolated source, Git, tests and synthetic runtime.
Shared baseline is `96680f4ce1b26da5da599bd5cb7894af8d3b28de`: PR #209 merged
PDF-to-Draft graph review. Required feature CI passed 1,564 tests plus static checks;
main run 34027941914 is confirmed successful. Earlier PDF browser/restart proof and
264 local regressions remain baseline evidence, not this Excel increment's results.

Current branch: `feat/defect-xlsx-mapping-20260906` in
`C:\CLASSIFIRE\.tmp\defect-xlsx-mapping-20260906`. It extends the same Draft workflow
with bounded Excel defect-report mapping. This checkpoint describes source and
measured validation; inspect current head/upstream, PR/CI and merge evidence before
calling it shared-main capability. No deployment or production release is claimed.

ADRs 0001/0002 remain accepted: four independent capabilities, deterministic modular
services, optional bounded AI and portable explicit revisions. Database and retained
storage govern live state. OpenClaw retirement still needs proven replacement
protections. A Draft save does not satisfy canonical Phase 8-14 exit gates.

| Capability | Implemented bounded behavior | Remaining product gap |
| --- | --- | --- |
| Scope | Manual editor/import and client commands; merged PDF page-to-graph review; active Excel upload, typed-cell mapping, explicit row/image-to-item review | Optional OCR/AI proposals, broader source formats, field-level interpretation and complete physical scope |
| System matching | Saved candidates/notes, partial thickness/gap/service-size review and client commands | Full authorized applicability, corpus extraction, stable technical identity and multi-source field claims |
| Estimating | Manual/history, retained pricing workbook row selection and separately confirmed client proposals | Dedicated A/B source pipelines, reviewed mappings/recipes, coverage and calibrated estimates |
| Reporting | Four independent saved PDF/XLSX profiles; active v5 renderers display mixed PDF and workbook claims | Production acceptance, refinement and governed close-out/release |
| Portability | Selected ZIP export, editable new-project import and retained-origin re-export; shared inventory accepts v5 claims | Complete source/history coverage, source-body export, existing-project merge and production retention |
| ChatGPT-facing boundary | Optional MCP identity mapping and independent client proposals/reads | Real account linking, HTTPS deployment, in-chat files and operations; PDF/Excel graph UI commands do not yet have client parity |

## Active Excel workflow

Users choose **Excel defect report** in a saved Draft, or the Excel upload choice
when creating one. The existing retained-source boundary stores and scans the XLSX
before the isolated parser reads supported visible sheets. Users choose a worksheet,
header, columns, up to 25 rows, and which kinds of item to draft from each row.
Pagination makes later rows reachable without silently dropping them.

The same graph editor accepts the proposed defects, openings and services. Matching
labels never create relationships automatically. A person can join two services to
one opening, keep a separate blank opening, add/remove items and choose any selected
row as a source for an item. Selected embedded PNG/JPEG occurrences are linked only
by explicit choice; workbook placement is context, not proof of a physical relationship.
The mapper retains raw typed cell values and does not evaluate formulas or reproduce
Excel's visual number formatting. Missing, invalid or ambiguous values stay unknown
with visible reasons. Zero stays distinct from an unknown quantity.

Preview makes no writes. Separate signed, same-session confirmation rechecks actor,
Draft ownership, current revision, exact graph, mapping, selected rows/images and
source/document/scan hashes. One atomic shared save appends Scope v5; no canonical
Opening/Service/Estimate, lock, technical approval or AI/provider call is involved.
The existing artifact budget remains 288 KiB; large selections must use smaller batches.

Scope v5 adds exact workbook row/cell/image claims to the existing evidence_refs
union. It retains prior PDF observation/entity claims. Manual edits expose stale
whole-item review hashes; deletion retains historical entity claims; re-review only
replaces matching claims in a new revision. Imports mark every claim unverified and
grant no local source access. Packages inventory the claims; original workbook/image
bytes remain external rather than being silently bundled. Earlier revisions and
report/package bytes remain exact. The new renderer versions apply only to v5.

Migration `0038_draft_scope_xlsx_sources` adds the Draft-owned source binding while
reusing StoredFile retention, scanner containment and shared intake. It does not
change canonical physical tables or the pricing-source contract. Downgrade refuses
to destroy retained source history. Manual SQLite Draft behavior remains supported;
retained evidence requires the existing PostgreSQL/storage/scanner setup.

## Verification checkpoint

- Parser: **49 passed**, including actual pricing, Scope metadata and image CLI modes.
- Migration/lineage/packaging: **30 passed**, including prior artifact-byte preservation,
  constraints and refused downgrade; one existing Alembic deprecation warning.
- UI/template checks: **19 passed**, including the existing PDF preview templates;
  both JavaScript syntax checks and the new router's Ruff/Mypy/Bandit checks passed.
- Mixed workbook/PDF output regression: **20 passed** across all four report profiles
  and older renderer/schema paths. Pure artifact-budget regression: **3 passed**,
  including exact-limit re-review and refusal before confirmation.
- Full Ruff and Bandit passed; Mypy passed on **199 source files**, using the existing
  isolated reportlab/yaml stubs. Alembic reports exactly one head, 0038.
- Real Chrome passed **11 checkpoints**, with no page errors. After loading final code,
  a fresh review saved r5. A second actual process restart/fresh login preserved r2/r5
  JSON, both PNG occurrences, all three real PDF/XLSX report pairs and ZIP hashes.
  Scope+System is covered by pure output tests; the guarded PostgreSQL demo has no
  technical release and its SQLite-only synthetic seed guard was preserved.
- All real workbook cells were checked for formulas/hyperlinks; source formula text
  stayed literal. All three report covers, representative Scope/Estimate/Complete
  reference pages and two worksheet ranges were inspected with no clipping/overlap. The separate worksheet rendering
  utility returned an unexplained nonzero exit after producing both inspectable PNGs;
  source workbook hashes remained unchanged. This is an inspection-tool limitation,
  not a claimed clean renderer command. The app's own output generation succeeded.
- Read-only demo counts: canonical Estimate, EstimateLine, Defect, Opening, Service,
  EvidenceSource, ServiceOpeningLink and PhysicalModelLock were all zero. The served
  logo SHA-256 equals the supplied PNG: fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a.
- All **30 new PostgreSQL service/HTTP cases passed** across the focused runs. Two
  new test expectations needed correction: scope the injected audit failure to saving,
  and count the two legitimate download audits alongside the one save. Rollback,
  no-write and exact audit-event assertions remain intact; application behavior was
  not changed for either correction. The final remaining-workflow/legacy Scope/import/
  PDF UI group passed **110 tests** in 310.35 seconds. Combined independent focused
  groups total **254 passed**, no skips and one existing Alembic deprecation warning.
  Independent code/document reviews found no blockers. Required PR CI and verified
  merge remain publication checks; this document does not claim its own future merge.

The live synthetic demo is `http://127.0.0.1:8817/scopes`; read
[DRAFT_SCOPE_XLSX_DEMO.md](./DRAFT_SCOPE_XLSX_DEMO.md). Receipts and exact local outputs
are in `.tmp/defect-xlsx-review-artifacts-20260906`. Verify availability/scanner freshness
before use. Existing PDF 8816 and pricing 8815 demos remain preserved.

## Known gaps and active work

This is human-selected mapping and review, not automatic image/text interpretation.
It does not infer service count, scale, hidden substrates, FRL, technical compatibility
or repair quantities from a photograph. The supported workbook subset is deliberately
bounded: 10 visible sheets, 1,000 rows including headers, 50 columns, 20,000 grid cells,
50 supported picture occurrences and a 10 MiB source limit. Unsupported layout,
active content, external links, hidden/merged content and oversized inputs are refused;
see [the contract](./DRAFT_SCOPE_XLSX_V1_CONTRACT.md) for precise restrictions.
Real report layouts and authorized user acceptance have not been verified.

The separate [corpus/dual-pricing design](./TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md)
and T1-T14 roadmap remain required. A/B source identity, price basis, reviewed mappings
and immutable component/activity recipes precede costing. Technical release v3 does
not freeze the complete recipe. Legacy Package 14 defaults do not become trusted A/B
intake. The original named workbooks were absent from the prior scoped inspection;
real semantics and prediction accuracy remain unverified.

Broader gaps include multi-report deduplication, service-instance/plane modelling,
field-level provenance, source-inclusive exchange, full tenancy and production
operations. Optional AI and OpenClaw migration retain their own proof and authority
requirements. No current test count proves the full production goal complete.

## Project health and local changes

PDF report review is merged and demonstrated. The Excel extension has meaningful
parser/migration/UI/browser/restart and automated regression evidence; publication
is the remaining gate for this bounded increment. The full goal is
incomplete. Only this isolated implementation branch is in scope for publication.

The recovery root remains on `gpt/phase8-linked-original-images` at `de0cc5a`, with
46 unstaged tracked modifications, 14 staged additions and four DU conflicts at the
verified task start. Untracked/ignored recovery material was not fully enumerated.
Preserve it, unrelated worktrees/demos/scanners/receipts and the supplied logo. New
runtime fixtures, screenshots and demo data under `.tmp` are synthetic local evidence,
not files to commit. No unrelated root changes have been adopted into this branch.

## Recommended Next Actions

1. After verifying this tested Excel increment's required CI and merge, add one
   **optional source-bound PDF text/image
   suggestion interaction** feeding the same editor and human review boundary. Reuse
   compatible inference protections in a small Draft-specific adapter; begin with synthetic evidence
   and a controlled adapter. Preserve unknowns and require explicit review/save.
   Existing Phase8 runners require canonical estimate/defect manifests and cannot
   consume Draft identities directly; never spoof them or weaken validators. Real
   provider/customer workflows need their own authorization and evidence.
2. Deliver A/B profiles, reviewed technical mappings and pricing coverage according
   to T1-T14 dependencies; establish recipes and benchmarks before model/cost tuning.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) records the next-session entry point.
