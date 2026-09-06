# CLASSIFIRE Project State

## Evidence-based snapshot

Verified 2026-09-06 against the isolated source, Git and synthetic tests/runtime.
Shared baseline is `080845e2681e292cabb6f201f373a696d1fc40c1`, merged PR #208
(the technical-corpus/dual-pricing design). Its exact feature-head CI passed
1,522 tests, Ruff/Bandit and Mypy on 193 files. That is baseline evidence, not the
validation count for the implementation below.

Current branch: `feat/defect-report-review-20260906` in
`C:\CLASSIFIRE\.tmp\defect-report-review-20260906`. This branch implements the
source-linked PDF graph review described below. Check the live PR/head/CI for its
publication state; this checkpoint does not claim its own merge or deployment.

ADRs 0001/0002 remain accepted: deterministic modular services, four independently
callable capabilities, optional bounded AI and portable explicit revisions. The
database and retained storage govern live state. OpenClaw retirement requires proven
replacement protections. Production Phase 8-14 exits remain separate.

| Capability | Implemented bounded behavior | Remaining product gap |
| --- | --- | --- |
| Scope | Manual editor/import and client create/read/edit; PDF upload, retained page observations and new page-linked Defect/Opening/Service graph review | Excel defect-register mapping, optional OCR/AI proposals and complete evidence interpretation |
| System matching | Saved candidates/notes, partial thickness/gap/service-size reviews and client commands | Full authorized applicability, corpus extraction, stable technical identity and multi-source field claims |
| Estimating | Manual/history, retained pricing workbook row selection, client preview and separate human confirmation | Dedicated A/B source pipelines, reviewed mappings/recipes, coverage and comparable estimates |
| Reporting | Four independent saved Draft PDF/XLSX profiles; all support v4 entity/page references | Production acceptance, refinement and governed close-out/release |
| Portability | Selected ZIP export, editable new-project import and retained-origin re-export | Complete source/history coverage, existing-project merge and production retention |
| ChatGPT-facing boundary | Optional MCP identity mapping and independent client proposals/reads | Real OAuth/account linking, HTTPS deployment, in-chat files and operations; new PDF graph UI has no client command yet |

## New PDF workflow and implementation evidence

Users can choose **Upload defect report** when creating a project or from a saved
Draft. PostgreSQL evidence mode retains and scans the PDF, then shows a raster page
beside the existing graph editor. A person creates/edits defects, shared or blank
openings and services, explicitly selects the items linked to that page, previews
the full graph and separately confirms saving one Draft revision. Existing page
observations remain separately available. Text extraction is unreviewed; this is
human interpretation, not automatic OCR/AI extraction.

The existing `evidence_refs` array now has an explicit Scope v4 union for observation
and whole-item references. A link binds source bytes, document/scan/page/text hashes,
reviewer, item ID and item hash. It records human page review, not proof that every
field is confirmed. Changed/removed items retain a visible review warning; old
revisions stay exact. Re-review updates only the new revision. Import retains claims
as unverified and grants no source access. Selected packages inventory these same
references; they do not automatically embed the source PDF or the whole project.

Preview writes nothing. Confirmation rechecks permission, ownership, source integrity,
scan freshness, revision and exact edited graph/selection. A signed 15-minute token
also binds the browser session. Saving uses the existing atomic revision mechanism;
there is no new dependency, database migration or canonical physical writer. Report
render versions change only for Scope v4; historical outputs remain byte-for-byte.

Real Chrome with a real fresh scanner passed 11 checkpoints: upload, scan, existing
observation, shared opening/two services, preview/edit-back/confirm, separate blank
opening, saved JSON, three PDF/XLSX profiles and selected package download. Later
item edits/deletion preserved links and earlier downloads. Actual restart with fresh
login preserved current/historical JSON, both page PNGs, all six report files and ZIP
hashes. Browser errors: zero. Canonical Estimate, EstimateLine, Opening, Service
and PhysicalModelLock counts in this synthetic database were all zero. Scope+System was covered by synthetic output tests;
this browser demo had no technical release and did not fabricate one. Report images
and workbook cells were inspected; no material rendering issue was identified.

Final focused PDF/Scope/report/package/client regression: **264 passed**, no skips,
one intentional malformed-ZIP warning, in 1,308.86 seconds on disposable PostgreSQL.
An earlier run had 24 passes and two PDF-fixture preparation errors; both passed
unchanged on rerun and in this complete final regression. No parser/scan limit or
assertion was weakened. Full required PR CI and merge must still be verified.
Ruff and Bandit passed; Mypy passed on 193 source files with the existing isolated
reportlab/yaml stubs. Migration head remains `0037_draft_client_capabilities`.

Local receipts are under `.tmp/defect-report-review-artifacts-20260906`, including
`browser-receipt.json`, `restart-receipt.json`, exact downloads and screenshots.
The synthetic demo is `http://127.0.0.1:8816/scopes`; setup/limits are documented in
[DRAFT_PDF_DEMO.md](./DRAFT_PDF_DEMO.md). Verify availability and current scanner
freshness before use. The approved logo is unchanged and was visible in the review.

## Known gaps and active work

The immediate priority has been reordered around the user's missing defect-report
interaction: finish this PDF slice, then Excel defect mapping, then bounded optional
interpretation. Excel pricing selection already exists inside an Estimate; it is not
a defect-report importer. A/B source profile remains the first slice of the separate
corpus/pricing track, not a prerequisite to trying report-to-Scope interaction.

The [corpus/dual-pricing design](./TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md) and
roadmap T1-T14 remain planned. Key dependencies remain explicit source/basis identity,
reviewed mappings and immutable component/activity recipes before costing. Technical
release v3 does not freeze the complete recipe. Existing XLSX limits include headers
(maximum 1,000 rows); listing/retrieval and job lifecycle do not meet corpus scale.
Legacy Package 14 defaults/identity/release semantics must not become trusted A/B
intake silently. Neither named original workbook was found in the scoped prior
audit; real layouts, rights, semantics and prediction accuracy remain unverified.

This PDF slice does not solve field-level evidence claims, multi-report deduplication,
image-to-service measurement, FRL/technical confirmation, unattended extraction,
source-inclusive export, real tenancy or production operations. Canonical Phase 8
review/admission/lock and downstream gates are not satisfied by a saved Draft.

## Project health and local changes

The synthetic Draft workflow is now visibly usable from PDF to reviewed graph and
portable output. The full product goal remains incomplete. Real-evidence acceptance,
full technical suitability, estimating breadth and Human Release remain unproven.

Only the isolated implementation branch is in scope. The recovery root remains on
`gpt/phase8-linked-original-images`, with 46 unstaged tracked changes, 14 staged
additions and four DU conflicts at task start; unrelated untracked/ignored material
was not enumerated. Preserve it, earlier worktrees/demos/scanners/receipts and the
supplied logo. Runtime artifacts and demo data under `.tmp` are local synthetic
verification evidence, not source changes to publish.

## Recommended Next Actions

1. After this slice passes required CI/review and merges, implement **bounded Excel
   defect-report mapping into the same Draft graph**. Retain/scan a synthetic XLSX,
   show sheets/headers/rows, let the user map defect/location/service/opening columns
   and inspect editable proposed items, then explicitly confirm one revision. Keep
   spreadsheet cell provenance, blanks/unknowns and shared-opening decisions visible.
   Do not route this through the pricing importer or infer quantity from defect count.
2. Add optional bounded text/image interpretation only after the manual mapping path
   is usable: propose source-linked facts and unresolved questions, require review,
   and reuse the same deterministic validation/save boundary. It must remain optional.
3. Deliver the retained A/B profile, technical mapping and coverage slices according
   to T1-T14 dependencies; establish versioned recipes and benchmark policy before
   costing/model tuning. OpenClaw retirement retains its separate protection gates.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) contains the next-session task.
