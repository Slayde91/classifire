# Draft pricing workbook selection

## Relationship to the planned two-source libraries

This document describes the implemented generic Draft row-selection contract. It is
not a dedicated importer for `pricelist.xlsx` (general products/materials/labour/services)
or `pricing_library.xlsx` (Firefly system prices). Their separately versioned source
identities, price-basis review, system mappings, bulk capacity and estimated-price
workflow are planned in the [integrated design](./TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md).
The 1,000-row limit below includes the header; it cannot accommodate a single sheet
with 1,000 price rows plus a header. Preserve this contract while adding bounded bulk
processing and versioned compatibility explicitly; do not silently lift safety limits.

Defect-report spreadsheets now have a separate active Scope mapping increment; see
[the Excel Scope contract](./DRAFT_SCOPE_XLSX_V1_CONTRACT.md). It reuses the bounded
worker with explicit Scope/image modes, a separate DraftScopeXlsxSource binding and
`draft_scope_xlsx` purpose. It does not apply rates or need pricing-library authority.
This pricing UI still does not extract defects/openings/services and still refuses
embedded images. Same-byte cross-purpose adoption remains refused. PDF graph review
is merged; Excel Scope proof is active, then optional bounded PDF suggestions. A/B
profiles remain the first slice within the separate corpus/pricing track.

## Implemented boundary

P3b's first bounded interaction uploads a synthetic/authorized XLSX, explicitly
scans it, previews retained cells, maps columns, then applies one selected row to
one existing Draft Estimate line. It never activates a PricingLibraryRecord,
LibraryRelease, technical approval, canonical Estimate, physical model or release.
The existing CSV importer remains separate and is not called by this UI.

`draft_source_intake.py` extracts the proven PDF retention/scanning boundary for
reuse by both formats. PDF public entry points remain compatible. The merged
`DraftPricingSource` model and additive migration 0033 bind the Draft, StoredFile,
exact source SHA-256/size, scan receipt and parsed-document SHA-256. PostgreSQL's
shared quarantine locks remain required for uploaded sources; manual estimating
still works without PostgreSQL, ClamAV, AI or OpenClaw.

## Supported workbook and explicit mapping

At most 10 MiB compressed, 2,000 unique archive members, 32 MiB uncompressed,
8 MiB per member, 10 visible sheets, 1,000 rows and 50 columns per sheet,
20,000 grid cells overall, 4,000 characters per cell and 2 MiB parsed metadata.
Existing safe OOXML validation rejects macros, external relationships and embedded
media; hidden sheets, merged cells, hyperlinks and comments are unsupported.
The fixed disposable parser has a 30-second parent timeout; Linux also bounds CPU,
address space and file writes. Windows byte/time limits are not a complete sandbox.
Production parser/container isolation and scanner operations remain open work.

Choose the worksheet and header row, then map eleven separate columns: reference,
description, unit, rate, currency, tax basis, date, labour, materials, inclusions,
exclusions. The first six require mapping; optional unmapped/blank cells stay
unknown. Every retained value includes its cell address, coordinates and kind.
Dates, labour/material breakdowns and inclusions are source claims, not approved
commercial rules. Formulas are preserved as formula text, never calculated or used
as selectable prices. Missing prices never become zero.

This slice accepts existing units each/m/mm/m2, AUD and explicitly excluded tax
(`excluded` or `GST Exclusive`). Prices use the existing strict Decimal contract;
no guessed unit conversion, currency conversion, rounding or tax calculation.
An incompatible unit, unsupported row, stale revision/hash or missing recovery
explanation refuses application. Selection preserves quantity and the initial rate;
existing reasoned override history records author, time, old rate and new rate.
The recovery explanation is an unapproved human claim. Full recovery assessment,
inferred/default/mapped/component pricing and all supplier layouts remain future work.

## Revision and download contract

Existing Estimate v1 bytes and report bytes remain unchanged. A workbook selection
appends Estimate `CLASSIFIRE-DRAFT-ESTIMATE-v2`, with provenance
`manual_and_workbook_unit_sell` and a bounded `pricing_sources` list. Each selection
binds line/event IDs, source identity/name/size, document and scan hashes, sheet,
header/mapping, row and exact cells, recomputable row SHA-256, recovery explanation,
method `exact_library_rate` and approval status `unreviewed`. The method means an
exact value copied from the selected workbook, not an approved canonical library.
Validation recomputes values/hashes and binds the row to its rate-override event.
Later manual overrides retain this historical source entry without claiming it is
the current rate. Unknown and omitted work retain existing Estimate semantics.

Estimate JSON includes frozen provenance. Explicit Estimate reporting renders both
PDF and XLSX from the same selected revision. Estimate-only render version 2 carries
pricing provenance for older Scope inputs (v1 for manual-only); Scope v4 selects
version 4 and the active v5 selects 6, preserving every historical version. The PDF
includes workbook selections and XLSX adds a Pricing sources sheet with literal safe strings. Historical downloads
remain exact after further edits/restart. Reads/exports containing pricing-source claims
additionally require `library:read`; project ownership and estimate/export permissions
still apply.
Live source quarantine, stale scan or changed bindings make dependent Estimates/reports
visibly stale. Downloading a retained snapshot does not reapply a price or approve it.
Full retained-workbook download remains separate work. Selected ProjectPackage
projection/import/re-export follows [its contract](./DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md),
retains declared pricing claims and keeps source bodies external/withheld. Scope-only
worksheet claims do not silently acquire the pricing permission requirements.

## UI, service and validation

Routes live under `/scopes/{draft}/estimates/{estimate}/pricing`; upload, scan,
preview and apply are explicit actions with bounded forms, CSRF and ownership checks.
Core commands are `draft_pricing_intake.preview` and `apply_rate`; another interface
must call these same services. No new framework, provider or dependency was added.

Targeted tests: `test_draft_pricing.py`, `test_draft_pricing_ui.py`,
`test_migrations_draft_pricing_sources.py`, plus affected PDF, Estimate/report,
Scope UI, deployment and migration regressions. Migration 0033 retains old report
bytes and refuses destructive downgrade. The active Excel Scope migration advances
the application head from 0037 to 0038; it does not rewrite this pricing schema/data
or relax the original worker mode.

Historical synthetic Chrome demo for the pricing milestone: `http://127.0.0.1:8805/scopes`, separate marked database
`classifire_draft_pricing_demo` and `.tmp/draft-pricing-demo-20260906` storage.
The real ClamD/browser journey selected Rates!D5 = AUD 120.25, retained original
AUD 100, then saved a reasoned AUD 125 override. Revisions 2/3/4 and PDF/XLSX
remained byte-identical after an actual server restart. No browser page errors.
The supplied logo is exact on sign-in/sidebar and the report. Browser/output receipts
are local under `.tmp/pricing-artifacts`; do not commit synthetic runtime databases.
See PROJECT_STATE.md for current validation and publication status.
