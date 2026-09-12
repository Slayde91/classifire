# Reports from multiple saved row reviews

This increment extends the existing scope-and-system profile. A user selects exact
saved reviews for distinct Opening/Service rows or blank Openings, previews the
combined content, then separately creates one frozen PDF/XLSX pair. Report creation
does not run matching, estimating, inference, technical approval or release.

## Architecture and compatibility

Previously the report service retained one review even when a register/package held
several. The same service, table, renderers, browser routes and typed client command
now accept an explicit collection. This closes the register-to-report gap without
adding a fifth report profile, database model, migration or dependency.

`preview_report` reads without allocating report identities, rendering or writing.
`create_report(..., matches=[{match_id, match_revision}, ...])` retains the exact Scope
and selected reviews. One to thirty references are canonicalized by review ID;
duplicate IDs, competing reviews for one row, mismatched Scope or incomplete row
identity fail. A shared Service may occur at different Openings; blank Openings have
no Service. Review count never becomes quantity. Legacy singular arguments and empty
collections preserve previous snapshot/command shapes and supported target types.

The collection snapshot is `CLASSIFIRE-DRAFT-SCOPE-REPORT-v3`, render version 11,
profile `scope-and-system`. `system_matches` holds full exact review envelopes and
replaces the singular field only in v3. Mixed, empty or malformed v3 snapshots fail.
Scope, review, project and output identities/hashes are retained. Every dependency
is checked on creation and read; later changes mark reports stale without rewriting
old bytes. PDF and XLSX are saved together or neither is saved.

The JSON limit is the existing Scope limit plus thirty existing review-envelope
limits plus 8 KiB. Legacy per-profile bounds remain. Each output remains capped at
8 MiB; package limits remain 32 members and 128 MiB. Oversized combinations fail
rather than dropping reviews, originals or provenance to fit.

## Interfaces and authority

The register's Scope reports link carries its explicit saved choices. No choice
opens scope-only reporting; a single choice retains the legacy single-review route.
Several choices open `/scopes/{id}/reports?revision=N&matches=UUID:revision` with
repeated `matches` parameters. The picker retains explicitly selected older reviews
outside the recent twenty. GET previews do not save; POST with CSRF separately saves
the displayed revisions. An invalid register selection has no active report link.

The typed `scope_report` client command accepts `matches` with the same exact pairs.
Technical client grants and local technical-read permissions apply to preparation,
review, execution, lists and both downloads. The existing separate same-user browser
confirmation remains required. Legacy pending-command serialization and five-field
input hashes are unchanged. Repeated review panels have distinct accessible IDs.
Word v7 references use their Word locators and the shared provenance presentation.

## Package and import dependencies

ProjectPackage v6 can include this saved pair only when all its exact review
dependencies are selected. Extra selected reviews remain independent and never
become Estimate inputs. Import/re-export retains exact report and ancestor bytes.
Import mapping v4 records each report's full `matches` binding list, including exact
source ID/revision/hash and available local bindings. It is required if a collection
report occurs anywhere in retained ancestry, even when the outer package has none.
Ancestor-only bindings can remain nonlocal. Imports confer no local approval.
Packages without collection reports retain mapping v1-v3 rules and shapes.

Older binaries cannot read newly saved v3 reports or mapping-v4 imports. No live
activation is included. A future exact-version plan needs matched backup/storage,
disposable restore and approval; a binary downgrade after new writes is not a safe
transparent rollback. Preserve all later records and original files.

## Verification and limits

The isolated Edge journey selected three rows, previewed without writes, separately
saved the pair and separately saved a ZIP containing the exact pair. Reopening after
an actual process restart preserved Scope, PDF, XLSX, ZIP and all 66 checked domain
tables. The 19-page PDF was inspected in rendered overviews and at readable size;
desktop/mobile screens showed no clipping, overflow or page errors. The XLSX was
read back for identities, unknowns and literal cells; native Excel visual inspection
was not performed. The detailed provenance appendix remains lengthy.

Synthetic PostgreSQL tests exercise import, binary inspection, complete mappings,
ancestor re-export and exact original report bytes on disposable port 15433. This
is not a browser import proof or live 15432 rehearsal. Word v7 output tests separately
cover retained locators and claims. No customer inference or accuracy score is claimed.
Current test and publication facts are recorded in PROJECT_STATE.md and private
validation receipts; production phase exits remain incomplete.
