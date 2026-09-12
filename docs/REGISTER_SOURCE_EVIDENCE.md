# Register source evidence

The register's **View sources** action opens retained evidence beside an exact saved
Defect, Opening or Service row. The Evidence tab is read-only and works independently of
technical review, estimating, AI and package creation. The existing standalone
PDF, Word and Excel review screens remain the place to preview and confirm corrections.

## Selection and provenance

An explicit saved Scope revision and selected identity are required. Select either
one Defect alone or an Opening/Service row; mixed Defect and Opening/Service arguments
are refused. A selected Defect exposes only its own references, without implicitly
selecting linked descendants. A Defect with no linked Opening stays in the review
queue with an explicit unresolved-relationship warning; no placeholder Opening or
Service is created. Its own references are labelled Defect evidence claims.

For an Opening/Service selection, the selected Service must belong to that exact
Opening; shared legacy relationships are preserved. Blank openings need no Service.
An unlinked Service can be inspected from the relationship review queue while
technical/price authoring stays unavailable.
Defect and Opening references inherited by another selected row are clearly labelled
context, not proof of a Service's values. Defect-only inspection can also be requested
for a Defect that has linked Openings, but descendants are not included implicitly.

The shared `draft_register.evidence_context` service supplies the full-page and native
panel views. `evidence_image` rechecks the exact selection and current access before
and after the existing format-specific preview reader. No model, migration, artifact
schema, new parser, provider or canonical writer is added.

For local sources, the existing intake readers enforce current ownership, permission,
retained bytes, containment and scan status. The saved file size/hash, document hash,
scan hash, text/cell locator and selected picture descriptors must match. PDFs show
retained page text and page preview; Word shows the selected block and explicitly
linked pictures; Excel shows selected row mappings, original values and linked
pictures. Mapped empty cells and unmapped fields are different; zero is retained.
Picture placement does not establish physical ownership or quantity.

A stale target claim remains visibly stale while its intact original source stays
inspectable. Changed, quarantined or unavailable sources expose saved identity/review
metadata without source text or images. Imported IDs remain foreign, unverified
metadata; this endpoint never resolves them as local source authority. AI lineage
identifiers/hashes may remain metadata, but unavailable previews exclude source quotes
and proposed values. Source integrity is not technical or physical approval.

## Imported original navigation

An imported row may offer **Review retained imported original** when its exact saved
reference and import lineage identify one retained evidence member in the validated
ProjectPackage mapping. The link opens that member's existing review card in another
tab. Its anchor identifies the full retained archive path, including nested origins;
a reused local source row does not collapse distinct ancestor cards.

This is navigation, not inline preview or local approval. The row remains
`imported_unverified`, with no source text or images exposed. Opening Evidence does
not scan, download, interpret or adopt a foreign source ID. The existing imported
package page and subsequent explicit scan/download actions recheck current rights
and source safety. Missing, ambiguous or unavailable bindings offer no original link.
No model, migration, package format, parser or authority rule changes.

## Interface and authority

The browser binds a fragment to the exact Draft, revision and selected identity before
installing it. Opening Evidence with unsaved Scope edits explicitly shows the saved revision;
those edits are excluded and no save occurs. Evidence exposes no write form. Source
review links explicitly open the current Draft's review screen in another tab, where
existing preview and confirmation rules still apply. Scope, technical, price and
package confirmations remain separate.

Both GET routes reject duplicate, unknown or malformed query fields and recheck
project access. Images accept only a selected saved reference and its declared image
identity. Responses are not cached and vary on the session cookie; HTML also varies
on the native-panel header. Images carry `nosniff`. No raw source body is added to the
advisory assistant payload. Technical/price authoring retains its prior gates.

## Validation and limits

Current exact results and publication state are in [PROJECT_STATE](./PROJECT_STATE.md).
The new core and HTTP checks cover native PDF/Word/Excel bindings, quarantine and
source drift, permission revocation, imported metadata, historical/stale selections,
Defect-only and blank/unlinked/shared relationships, exact image selection, escaping,
unknown/zero values and absence of database writes. Browser acceptance uses a separate synthetic
PostgreSQL15433 database and real retained originals/ClamAV scans. It is not a customer
report accuracy evaluation, production approval or operational deployment.

Imported binary preview through this row panel, broad format/scale coverage and
general automated interpretation remain incomplete.
