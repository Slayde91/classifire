# Draft pricing workbook selection

## Relationship to the planned two-source libraries

This document describes the implemented generic Draft row-selection contract and the
active bounded A/B source-profile extension. It is not a reviewed row importer for
`pricelist.xlsx` (general products/materials/labour/services) or
`pricing_library.xlsx` (Firefly system prices). Their explicit source identities and
unapproved sheet/mapping/price-meaning profiles now exist; human review, normalized
observations, system/component mappings, bulk capacity and estimated-price workflow
remain planned in the [integrated design](./TECHNICAL_CORPUS_AND_DUAL_PRICING_DESIGN.md).
The 1,000-row limit below includes the header; it cannot accommodate a single sheet
with 1,000 price rows plus a header. Preserve this contract while adding bounded bulk
processing and versioned compatibility explicitly; do not silently lift safety limits.

Defect-report spreadsheets now have a separate active Scope mapping increment; see
[the Excel Scope contract](./DRAFT_SCOPE_XLSX_V1_CONTRACT.md). It reuses the bounded
worker with explicit Scope/image modes, a separate DraftScopeXlsxSource binding and
`draft_scope_xlsx` purpose. It does not apply rates or need pricing-library authority.
This pricing UI still does not extract defects/openings/services and still refuses
embedded images. Same-byte cross-purpose adoption remains refused. PDF graph review
and Excel review plus optional bounded PDF suggestions are merged. The minimum A/B
profile interaction is the current first slice within the separate corpus/pricing track.

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

## Explicit A/B source profile lifecycle

Before upload, the pricing screen requires one human declaration:
`general_pricelist` (A) or `firefly_system_prices` (B). The source filename is never
used to infer this identity. The same exact bytes and same kind return the existing
source; attempting to relabel those bytes as the other kind fails. New bytes for the
same Draft/kind reuse a stable dataset ID and increment the source version. A and B
have separate stable IDs/version sequences.

After clean scanning, the user chooses the supported sheet/header/column mapping and
one explicit price meaning: unknown, buy cost, list price, sell price, quoted price or
actual price. Preview performs no write. It shows data/usable/unresolved row counts,
row problems, mapped/unmapped fields and current structural/commercial gaps. The A
profile explicitly lacks a mapped item kind; B explicitly lacks manufacturer and system
configuration mapping. Unknown price meaning remains a visible gap.

An explicit save appends `CLASSIFIRE-DRAFT-PRICING-SOURCE-PROFILE-v1`. The envelope
binds the Draft, stable dataset ID/kind/version, exact source and parsed-document hashes,
source size/name, sheet/header, exact header cells, mapping, price meaning and diagnostics.
It records creator/time, revision, definition hash and parent-profile hash. Saves re-read
the exact clean source and compare the submitted source, preview and current profile
revision. Stale, changed, replayed, foreign or corrupt values fail closed. At most 20
profile revisions are listed/retained through this bounded UI.

Every profile is `unapproved`. Its contract states that library activation, Estimate
change, system matching and price inference are false. Saved profiles can be reopened
and downloaded as exact JSON. The existing `apply_rate` action is separate and remains
the only action on this screen that explicitly changes an Estimate line.

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
profile preview/save/reopen/download and row apply are explicit actions with bounded
forms, CSRF and ownership checks. Core commands include `retain_source`,
`preview_profile`, `save_profile`, `read_profile`, `profile_bytes`, `preview` and
`apply_rate`; another interface must call these same services. No new framework,
provider or dependency was added.

Profile tests are `test_draft_pricing_profiles.py`, `test_draft_pricing_ui.py` and
`test_migrations_draft_pricing_source_profiles.py`, with existing pricing/client,
deployment, packaging and migration regressions. Migration 0033 retains the original
pricing source/Estimate history. Forward migration 0040 adds nullable dataset identity
and the separate profile table, preserves historical unclassified rows and refuses
destructive downgrade. The single application head is 0040.

Historical synthetic Chrome demo for the pricing milestone: `http://127.0.0.1:8805/scopes`, separate marked database
`classifire_draft_pricing_demo` and `.tmp/draft-pricing-demo-20260906` storage.
The real ClamD/browser journey selected Rates!D5 = AUD 120.25, retained original
AUD 100, then saved a reasoned AUD 125 override. Revisions 2/3/4 and PDF/XLSX
remained byte-identical after an actual server restart. No browser page errors.
The supplied logo is exact on sign-in/sidebar and the report. Browser/output receipts
are local under `.tmp/pricing-artifacts`; do not commit synthetic runtime databases.
See PROJECT_STATE.md for current validation and publication status.

Current synthetic profile proof uses `http://127.0.0.1:8819`, marked storage
`.tmp/pricing-source-profiles-demo-20260907`, database
`classifire_draft_pricing_profiles_demo`, and real local ClamAV. Both A and B profile
JSON hashes survived a process restart; A source version 2 reopened and profile saves
did not advance the Estimate. Native visual inspection was blocked by the browser
sandbox helper, so repeat layout inspection when available. No real workbook meaning,
source rights, production scale or price accuracy is claimed.
