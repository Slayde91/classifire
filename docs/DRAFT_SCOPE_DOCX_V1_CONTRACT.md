# Draft Word evidence inspection v1

This candidate is retained evidence inspection, not source-linked Scope review.
The existing PDF/XLSX review contracts and Scope v1-v6 remain unchanged.

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
is involved. No defect, opening, service, quantity, technical approval or price is
created. Source statements and image placement have no approval authority.

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

## Migration and pending work

Forward-only migration `0047_draft_scope_docx_sources` creates one Draft source table
with owner/Draft links, exact StoredFile byte foreign key, unique stored-file binding,
size constraint and Draft index. It preserves existing artifacts and history; its
downgrade refuses deletion of retained evidence. Deployment lineage recognizes the
previous quantity-basis head as requiring migration. No live activation is implied.

Still required: explicitly reviewed Word-to-Scope graph proposals, versioned Word
evidence references, portable original-bearing package import/export, ChatGPT tools,
formatted-page reconstruction, broader layouts and representative report validation.
This bounded screen is not completion of the full Word ingestion or production goal.
