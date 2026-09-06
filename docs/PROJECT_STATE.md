# CLASSIFIRE Project State

## Evidence-based snapshot

Verified 2026-09-06 from isolated source, Git, synthetic tests and runtime. Shared
baseline is `d2640defd00c23892691da79990a510bee59b2a0`, merged Excel PR #210.
Its exact-head PR CI passed 1,672 tests; post-merge main run 34033021353 succeeded.
Current branch is `feat/draft-pdf-suggestions-20260906`. This document is a source
checkpoint before this increment's own publication; verify current PR/CI before reuse.

ADRs 0001/0002 remain accepted: one modular deterministic core, independent Scope,
System Match, Estimate and Reporting capabilities, portable revisions and optional
bounded AI. OpenClaw remains; this Draft adapter does not establish retirement parity.

| Capability | Implemented and usable within the declared Draft scope | Remaining breadth |
| --- | --- | --- |
| Scope | Manual graph, retained PDF page/entity review, Excel row/cell/image mapping; current optional one-page suggestion review | Live AI accuracy, bulk/cross-page reconciliation, broader formats, richer service-instance/plane models |
| System Match | Saved candidates/notes, partial thickness/gap/service-size checks and client commands | Full authorized applicability, corpus extraction and multi-source field claims |
| Estimate | Manual/history, retained pricing-row application and separately confirmed client proposals | Explicit A/B profiles, reviewed mappings/recipes and calibrated estimates |
| Reporting | Four independent PDF/XLSX profiles over saved snapshots; v6 retains original suggestion claims | Production acceptance and governed close-out/release |
| Packages | Selected ZIP export, new-project import and retained-origin re-export; v6 refs carried intact | Source-body/history breadth, existing-project merge and production retention |
| ChatGPT boundary | Optional MCP identity mapping and independent client reads/proposals | Real linking/HTTPS operations; report intake and suggestion UI commands lack client parity |

## Current optional PDF suggestion interaction

The source page offers a separately confirmed request for its text and rendered PNG.
A configured OpenAI adapter exists but is disabled by default. The isolated demo uses
an explicitly labelled scripted port that refuses any other page text/image. No live
provider call, customer evidence, measured AI accuracy or production readiness is claimed.

The provider cannot access the saved graph, tools, pricebook or canonical records.
Strict bounded output supplies local keys, proposed defects/openings/services and
observations, text quotes and image/text bases. CLASSIFIRE assigns Draft IDs and uses
the existing graph editor. Proposed dimensions/quantities stay unknown; the user
supplies corrections and verifies shared-opening relationships. Visible circles,
defects or proposed records never imply billable quantity one.

Generation retains a separate proposal and audit event, without saving Scope. Users
inspect originals, edit/delete suggestions, explicitly select every retained proposed
item for page review, preview without writes, then separately confirm one atomic
Scope revision. Rejecting a batch preserves its original bytes and saves no Scope.
Current rights, source/scan/byte identities and revision are rechecked, including after
rendering and inference. Stale, foreign, quarantined, corrupted or replayed inputs fail.

Scope v6 adds strict nested suggestion provenance in the existing evidence_refs union.
Original proposed values remain separate from final whole-item hashes and human review.
Manual edits/deletion/re-review/import preserve history; imported claims remain unverified.
Existing v1-v5 formats and bytes are preserved. V6 alone selects report versions
7/8/8/9. The existing package inventory retains refs without silently bundling source
or raw provider response bodies. Migration 0039 adds only DraftPdfSuggestion retention;
its downgrade refuses data destruction. See the [contract](./DRAFT_PDF_SUGGESTIONS_V1_CONTRACT.md).

## Verification checkpoint

- Integrated service/boundary/HTTP and existing PDF review: 61 distinct cases passed.
  The first run passed 58 with three test-only failures: read-only pages correctly
  retained the global logout form. Assertions now allow exactly that form and no
  edit/save form; all five HTTP tests passed on rerun. No application behavior was
  changed to satisfy those assertions.
- Contract/transport: 72 pure tests passed, including mocked real HTTP protocol,
  refusal/tool output, exact quotes, byte limits and raw-chunk timeout checks.
- V6 provenance/report/package/budget compatibility: 59 passed.
- Migration/lineage/packaging: 30 passed; one existing Alembic deprecation warning.
- Suggestion/manual PDF/Excel form regression: 36 passed; JavaScript syntax passed.
- Full Ruff and Bandit passed. Full Mypy passed on 204 source files using existing
  isolated reportlab/yaml stub packages. Alembic reports exactly one head, 0039.
- Actual Chrome: upload, real ClamAV scan, rendered source, explicitly scripted
  suggestions, edit/preview/edit-back/confirm, reject, history and downloads passed.
  No browser errors. Saved r2 contains one defect, one shared opening, two services,
  one unresolved observation and five source/suggestion refs. Quantities remain null.
- Scope-only, Estimate-only and Complete PDF/XLSX plus ZIP were generated/downloaded.
  Output inspection verified literal cells, no formulas/hyperlinks and exact nested
  Scope JSON. Scope+System is covered by pure tests; the PG demo has no technical release.
  Representative UI/PDF views and native read-only Excel range inspection passed.
  The separate artifact-tool renderer failed to load skia.node; no dependency changed.
  A real process restart/fresh Chrome login preserved all Scope/PNG/report/ZIP hashes
  and applied/rejected history. Read-only demo counts: two Scope revisions, two
  suggestions (one applied/one rejected); all eight canonical model/lock counts zero.
- The UI serves the supplied logo, SHA-256
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.

Synthetic demo: `http://127.0.0.1:8818/scopes`; data under
`.tmp/draft-pdf-suggestions-demo-20260906`, database `classifire_draft_suggestions_demo`.
Receipts/downloads are under `.tmp/draft-pdf-suggestions-review-artifacts-20260906`.
Verify its marker, process and scanner before use. Existing 8817 Excel, 8816 PDF,
8815 pricing and earlier demos remain preserved.

## Known gaps and project health

The supported prototype is progressing with measured manual/assisted review and
historical-output coverage. Reviewed publication remains the gate for
this increment. The full production goal is incomplete. A successful scripted fixture
proves interaction and provenance, not that a model correctly interprets real reports.

A single rendered page can miss fine detail, opposite faces, hidden materials and
cross-page relationships. Broader OCR, image calibration, real model latency/cost,
provider-policy approval, production job/cancellation and evidence-format breadth
remain unverified. The transport's per-I/O timeouts and sampled elapsed budget are
not a hard whole-call deadline. No general OpenClaw replacement is claimed.

The approved corpus/dual-pricing track still needs explicit A/B source identity,
commercial basis, reviewed mappings and immutable component/activity recipes before
costing. Legacy Package 14 defaults do not establish either dataset. Real workbook
semantics and price-prediction accuracy remain unverified. Full tenancy, operational
readiness, canonical Phase 8-14 acceptance and human release gates remain separate.

The preserved recovery root was reverified at `de0cc5a`, branch
`gpt/phase8-linked-original-images`: 46 unstaged tracked modifications, 14 staged
additions and four DU conflicts. Untracked/ignored recovery material is not fully
inventoried. This increment uses an isolated branch; no unrelated root changes were
adopted. Demo/runtime artifacts stay local under .tmp and are not source to commit.

## Recommended Next Actions

1. Finish this tested suggestion increment's required CI and reviewed publication.
   Once its merge/checks are verified, implement the **bounded A/B source-profile UI**:
   declare A/B, inspect supported worksheet/header/mapping and price-basis gaps, preview,
   explicitly save and reopen an unapproved version using existing pricing intake.
   This is the next distinct user interaction; do not rebuild PDF/Excel review or add
   bulk AI, inferred prices or library activation as prerequisites.
2. Follow T1-T14: reviewed technical/commercial mappings, recipes and lineage-aware
   holdouts precede costing/calibration. Real sources/providers require authorization.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) records the self-contained next task.
