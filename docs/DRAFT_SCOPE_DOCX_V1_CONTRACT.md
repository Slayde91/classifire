# Draft Word evidence and Scope review contract

Retained inspection merged in PR #252 (c5d4774). The current review candidate adds
explicit Word-to-Scope review and portable originals. Existing Scope v1-v6 readers
and saved bytes remain supported; new Word claims use Scope v7.

## User interaction and authority

An owned Draft exposes `/scopes/{draft_id}/word`: upload a `.docx`, explicitly scan
and prepare it, inspect body paragraphs/table cells and static pictures, reopen,
and download the exact original. Upload and scan require current project-write
rights and CSRF checks. Viewing and original/picture downloads require current
project-read rights and ownership. A current clean scan, exact retained file binding,
document integrity and quarantine checks gate all prepared content access.

The shared `DraftSourceIntake` owns retention/scanning; its Word policy uses
`DraftScopeDocxSource`, `draft_scope_docx` storage purpose and the existing disposable
worker. No provider, new runtime dependency, external retrieval or autonomous agent
is involved. Inspection does not write Scope. A separate explicit review can append
a Draft Scope revision; it grants no canonical physical-model, technical, commercial
or release authority. Source statements and picture placement have no approval authority.

## Exact document contract

`CLASSIFIRE-DRAFT-SCOPE-DOCX-v1` contains:

- `manifest`: original `source_sha256` and `source_size_bytes`.
- `blocks`: ordered structural `locator`, exact normalized `text`, `text_sha256`
  and ordered picture occurrence IDs. Body positions are `body-N`; table paragraphs
  add `/row-N/cell-N/p-N`. These are not rendered Word page numbers.
- `pictures`: occurrence `id`, block `locator`, archive `member`, original `sha256`,
  `size_bytes`, `media_type`, pixel `width`/`height`, and sanitized `preview_sha256`.

The retained original preserves source bytes, formatting and original image bytes.
The preview is not a page-layout renderer: it shows normalized body text and full
source-image content, not Word crop/rotation/overlay effects. Table cells retain their
positions but are shown as individual text blocks. No image-to-entity association
is inferred from placement. The UI states these limitations before interpretation.

## Bounded profile and rejection

Input is limited to 10 MiB, 2,000 ZIP entries, 32 MiB expanded total, 8 MiB per entry,
1,000 text blocks, 16,000 characters per block, 40 picture occurrences and 2 MiB
of document metadata. Pictures use the existing sanitizer: PNG/JPEG only, at most
2 MiB and 2,000,000 pixels each; preview dimensions are bounded and metadata removed.
The worker retains its timeout, limited environment and platform resource controls.

The legacy canonical Word archive profile still rejects media by default. Only this
Draft profile opts into static pictures with additional DrawingML and binding checks.
Unsupported content is rejected, not skipped: external relationships, macros,
embedded objects, charts/diagrams, headers/footers/notes/comments, tracked changes,
fields/explicit hidden-text elements, text boxes, merged/nested tables and orphaned/unrepresented media.
Encrypted, duplicate/unsafe-path or oversized archives also fail closed. XML uses
the existing defused parser. Document contents are never executed as instructions.

Scan/processing failure keeps original retention evidence but does not expose a
prepared document. Historical source hashes do not override current quarantine or
expired scan checks. Source filenames are escaped for display; the original download
uses a fixed safe attachment name.

## Explicit graph review and Scope v7

The existing graph editor lets users create/edit distinct defects, openings and
services, including shared or blank openings and unknown dimensions/quantities.
Each selected target binds one structural text locator and zero or more explicitly
selected picture IDs. Any retained picture can support a selected text/target link;
its original placement is preserved, not treated as semantic ownership.

`draft_scope_docx_review.preview_review` validates the complete graph and selections
without writes. `CLASSIFIRE-DRAFT-DOCX-SCOPE-REVIEW-v1` binds actor, Draft, exact base
revision/hash, source bytes/name, document hash, scan hash, normalized payload,
selected text blocks and picture descriptors. The preview is signed for the same
user/browser session for 15 minutes. Confirmation repeats current access, ownership,
clean-scan/quarantine, document and exact-preview checks, then delegates one append
to the existing guarded Draft revision writer. A stale or altered preview cannot save.

`CLASSIFIRE-DRAFT-SCOPE-v7` extends the shared `evidence_refs` union. A Word claim has
`source_kind: docx`, `target_kind`, `target_id`, `target_sha256`, source identity/size/
filename/document/scan hashes, `block: {locator,text,text_sha256}`, `images` containing
exact selected native picture descriptors, `reviewed_by`, UTC `reviewed_at`,
`method: human_docx_entity_review` and `origin`. It has no invented page number.
The existing 100-reference/serialized-artifact bounds apply to the combined history.

V7 retains PDF, Excel and original AI suggestion claims through subsequent reviews
and manual edits. Changed/deleted items retain old evidence and are visibly stale.
Imported claims become `imported_unverified`; a scan never turns them into local
review or approval. New Scope report renderer versions are 9/10; Estimate/complete
versions are 10/11. Old report versions and bytes remain unchanged. All four profiles
show text/picture provenance, treating source content as literal text in PDF/XLSX.

## Portable original files

Optional `Selection.docx_sources` includes up to four reviewed Word originals in
ProjectPackage v5 as `evidence/<source-id>.docx`. Empty selection keeps legacy package
serialization. Inclusion requires owned, locally reviewed, currently clean and
intact source bytes and document identity. Import verifies exact member inventory,
reference kind and hashes, then reuses imported-source retention with the native
Word evidence parser. A fresh local scan/format check is required before download or
re-export. All retained ancestors retain permission and quarantine checks. See the
ProjectPackage contract; no separate storage or migration is added for review.

## Migration and pending work

Forward-only migration `0047_draft_scope_docx_sources` creates one Draft source table
with owner/Draft links, exact StoredFile byte foreign key, unique stored-file binding,
size constraint and Draft index. It preserves existing artifacts and history; its
downgrade refuses deletion of retained evidence. Deployment lineage recognizes the
previous quantity-basis head as requiring migration. No live activation is implied.

Still required: thin ChatGPT Word tools, formatted-page reconstruction, broader
layouts and representative report validation. The current review/package candidate
is not deployed; publication and CI must be checked against current GitHub state.
This bounded screen is not completion of the full Word ingestion or production goal.
