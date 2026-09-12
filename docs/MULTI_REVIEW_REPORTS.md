# Reports from multiple saved row reviews

These increments extend the existing scope-and-system and Complete profiles. A user
selects exact saved reviews for distinct Opening/Service rows or blank Openings, previews the
combined content, then separately creates one frozen PDF/XLSX pair. Report creation
does not run matching, estimating, inference, technical approval or release.

## Architecture and compatibility

Previously the report service retained one review even when a register/package held
several. The same service, table, renderers, browser routes and typed client command
now accept an explicit collection. This closes the register-to-report gap without
adding a fifth report profile, database model, migration or dependency. The subsequent
Complete extension reuses the Estimate report service and its immutable Estimate
basis; it does not widen the Estimate's technical or commercial inputs.

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

## Complete profile over an unchanged Estimate

The [Complete report contract](./DRAFT_COMPLETE_REPORT_CONTRACT.md) adds optional
`matches` to the existing Estimate `preview_report`/`create_report` boundary. Only
profile `complete` accepts a nonempty collection. Its snapshot is
`CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v3`, render version 12, with exact sorted full
`system_matches` envelopes and the original unchanged Estimate. One to thirty
reviews must have distinct row targets and the Estimate's exact embedded Scope.
If that Estimate embeds a review, its exact revision must be explicitly included;
neither automatic union nor a newer substitute is allowed. Missing dependencies fail.

The Estimate report route takes its exact `revision`, `profile=complete` and repeated
`matches=UUID:revision`; Scope is fixed by the Estimate revision. GET does not write,
POST with CSRF separately saves, and selected old reviews survive the recent-twenty
picker. Additional reviews are visibly report-only context, with no effect on
original rates, overrides, partial amounts, unknowns, quantities or recovery.
An Estimate with no embedded review keeps that absence when additional context
is selected.
Legacy empty/absent collections and supported single-review target types keep the
previous schemas and behavior. Typed client confirmation applies the same selection,
local permissions and separate client technical/Estimate/export grants.

## Package and import dependencies

ProjectPackage v6 can include either saved pair only when all its exact review
dependencies are selected; Complete also requires the exact saved Estimate. Extra
selected reviews remain independent and never become Estimate inputs. Import/re-export retains exact report and ancestor bytes.
Existing import mapping v4 is reused for both collection profiles. It records each
report's full `matches` binding list, including exact source ID/revision/hash and
available local bindings. It is required if a collection
report occurs anywhere in retained ancestry, even when the outer package has none.
Ancestor-only bindings can remain nonlocal. Imports confer no local approval.
Packages without collection reports retain mapping v1-v3 rules and shapes.

Older binaries cannot read newly saved v3 reports or mapping-v4 imports. A binary
that only understands Scope collection v3 also cannot read Complete collection v3,
even though the latter reuses the existing mapping-v4 schema. No live
activation is included. A future exact-version plan needs matched backup/storage,
disposable restore and approval; a binary downgrade after new writes is not a safe
transparent rollback. Preserve all later records and original files.

## Verification and limits

The earlier Scope-and-system isolated Edge journey selected three rows, previewed
without writes, separately saved the pair and separately saved a ZIP containing the exact pair. Reopening after
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

The separate Complete browser journey selected three reviews and Estimate revision 4,
then used separate report/package confirmations. The 21-page PDF, XLSX and ZIP kept
the exact pair, original rate 1.005, override 1.505, partial subtotal 3.01 and an
unknown second line. Its actual isolated port-8844 restart preserved exact
PDF/XLSX/ZIP/Scope bytes and all 66 checked domain-table hashes. A second restart
verified exact raw Estimate-revision-2/4 downloads after correcting a verifier's
pretty-printed-versus-compact JSON comparison; no application fix was needed and
the original failed check remains in the receipts. PDF overviews/readable pages 1
and 3 plus desktop/mobile views showed no observed clipping. Native Excel visual
inspection was not performed. PROJECT_STATE.md tracks current publication status.
