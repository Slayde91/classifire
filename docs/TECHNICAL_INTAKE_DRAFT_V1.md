# Technical intake Draft authoring contract v1

Status: **pilot authoring envelope; not the frozen multi-report intake template**

## Purpose and authority boundary

`technical-intake-draft-v1` lets an authorised user save and resume field-level
transcription work against one retained PDF. It is deliberately separate from a
`TechnicalVariant`.

Saving this Draft:

- does not approve the source document;
- does not create or revise a `TechnicalVariant`;
- does not record a technical-review decision;
- does not add anything to a `LibraryRelease`; and
- does not make anything searchable or runtime-eligible.

The source PDF remains the evidence. The Draft is an owner-bound, versioned
working record whose source document ID, stored-file ID, SHA-256 digest, and byte
size cannot change.

This first contract proves safe field authoring, exact locators, save/resume,
optimistic concurrency, and audit history. It does not yet model the roadmap's
full repeatable configuration families, construction layers, service groups,
components, performance outcomes, relationships, or reviewer decisions. Those
structures must be designed from the complete representative report set before
the canonical intake template is frozen.

## Stored envelope

The database row uses schema `technical-intake-draft-v1`. Its payload uses schema
`technical-intake-payload-v1` and contains exactly four top-level members:

| Member | Meaning |
| --- | --- |
| `schema` | Exact payload schema identifier. |
| `fields` | Material facts transcribed or normalised by the author. |
| `locators` | Exact places in the source PDF that support or qualify facts. |
| `links` | Many-to-many relationships between fields and locators. |

Every row has a stable canonical UUIDv4. Saving canonicalises row order and JSON
member order, then stores a SHA-256 digest of the canonical payload. A save must
provide the version the editor loaded. A stale save is rejected unless it is an
exact replay of bytes already accepted.

## Field row

| Member | Meaning |
| --- | --- |
| `row_id` | Stable canonical UUIDv4 for this fact. |
| `ordinal` | Unique positive display order within the Draft. |
| `field_key` | One allow-listed technical field name. |
| `raw_value` | The source wording, retained exactly as entered. |
| `normalized_value` | Optional controlled interpretation; stored as text in this pilot. |
| `unit` | Optional unit applying to the normalised value. |
| `semantics` | Whether the value is exact, a limit, range, set, nominal size, outside diameter, wall thickness, or nominal bore. |
| `fact_state` | `Inferred`, `Provisional`, or `Unresolved` during authoring. `Confirmed` is reserved for a later independent review boundary. |
| `material` | Whether the fact can materially affect selection or applicability. |
| `limitation` | Required for an `Unresolved` fact and available for other qualifications. |

`raw_value` and an excerpt in a locator are source transcription fields. The
validator checks them but does not trim or rewrite their contents. Normalised and
explanatory text may be whitespace-normalised.

The pilot field allow-list follows the current scalar `TechnicalVariant` surface.
It includes identity, manufacturer/product, substrate, opening, service,
dimensions, FRL, installation, support, spacing, dependencies, exclusions,
jurisdiction, and validity dates. This allow-list is not evidence that the full
roadmap template has been completed.

## Locator row

Each locator repeats the Draft's exact `technical_document_id`, `source_sha256`,
and `source_size_bytes`. It also records a physical PDF page and at least one
finer locator:

- printed page;
- section or clause;
- table, row, column, or footnote;
- figure or drawing;
- specimen, option, or callout;
- bounded excerpt; or
- normalised page region (`x0`, `y0`, `x1`, `y1`, each from 0 to 1).

`visual_verification` is `required` when the claim depends on visually inspecting
a table, drawing, image, symbol, geometry, or layout; otherwise it is
`not_required`. The authoring state does not claim that independent review has
occurred.

## Evidence link row

Each link identifies one field, one locator, and an evidence role:

- `direct`
- `comparison`
- `derived_reasoning`
- `conclusion`
- `governing`
- `conflicting`
- `superseded`

A fact may have several locators and one locator may support several facts. Every
field and locator must participate in at least one link. A fact that is not
`Unresolved` needs at least one supporting role. A `conflicting` link is permitted
only for an `Unresolved` fact.

## Worked synthetic example

The following example is synthetic. It does not reproduce or assert a fact from a
supplier report.

```json
{
  "schema": "technical-intake-payload-v1",
  "fields": [
    {
      "fact_state": "Provisional",
      "field_key": "maximum_service_size_mm",
      "limitation": "Pending independent technical review.",
      "material": true,
      "normalized_value": "110",
      "ordinal": 1,
      "raw_value": "<= 110 mm outside diameter",
      "row_id": "22222222-2222-4222-8222-222222222222",
      "semantics": "maximum",
      "unit": "mm"
    }
  ],
  "locators": [
    {
      "callout": null,
      "clause": null,
      "column": "Maximum outside diameter",
      "drawing": null,
      "excerpt": "Synthetic source wording for contract demonstration only.",
      "figure": null,
      "footnote": null,
      "option": null,
      "physical_page": 37,
      "printed_page": "31",
      "region": null,
      "row": "Service row 4",
      "row_id": "33333333-3333-4333-8333-333333333333",
      "section": "6.2",
      "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "source_size_bytes": 123456,
      "specimen": "Specimen A",
      "table": "Table 7",
      "technical_document_id": "11111111-1111-4111-8111-111111111111",
      "visual_verification": "not_required"
    }
  ],
  "links": [
    {
      "evidence_role": "direct",
      "field_row_id": "22222222-2222-4222-8222-222222222222",
      "locator_row_id": "33333333-3333-4333-8333-333333333333",
      "row_id": "44444444-4444-4444-8444-444444444444"
    }
  ]
}
```

In a real Draft, the document ID, source digest, and byte size are supplied by
CLASSIFIRE from the verified retained PDF. The browser must not invent or let the
author replace them.

## Validation and audit rules

- JSON is UTF-8, duplicate-key-free, finite, bounded to 1 MiB, and limited to
  500 fields, 500 locators, and 5,000 links.
- Unknown members, field keys, semantics, fact states, evidence roles, and visual
  states fail closed.
- The retained source must still be a clean, immutable, verified PDF at start and
  save time.
- Only the Draft owner can read or mutate it through this authoring workflow.
- The author supplies a non-blank reason for each material save.
- Audit events retain the reason, old and new payload digests, and stable IDs of
  changed field, locator, and link rows. They do not copy confidential report
  wording into the general audit log.
- Re-opening the workspace revalidates the persisted payload and digest before it
  is shown.
- The Draft editor and rejected-save recovery page are private, non-cacheable,
  and use a no-referrer policy because they can contain confidential source
  wording.
- A rejected payload is reflected only after owner validation, only when its
  strict UTF-8 encoding is within the 1 MiB limit, and only through autoescaped
  readonly text. Oversized or unencodable input is never echoed.
- A stale changed payload is returned for recovery with HTTP 409 and cannot
  overwrite the current persisted Draft; an exact replay remains idempotent.
- A coarse variant created through the legacy UI cannot enter technical review.
  Genuine legacy and administrator-imported variants without that UI marker
  remain compatible with the existing governed review path.

## Deliberately deferred boundaries

Before this can become the roadmap's canonical multi-report template, later work
must add and prove:

1. repeatable configuration-family and atomic-variant structures;
2. structured construction, service, component, performance, applicability, and
   document-lineage data;
3. a separate reviewer-owned intake-record revision and decision workflow;
4. controlled materialisation into a `TechnicalVariant` candidate;
5. Excel and JSONL exchange using the same frozen schema;
6. coverage and exceptions evidence across the full representative report set,
   including a retained primary test and a scanned/image-only source; and
7. independent release publication and pinned-runtime eligibility UAT.
