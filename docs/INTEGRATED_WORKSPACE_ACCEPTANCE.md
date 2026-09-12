# Integrated workspace design and acceptance

Checkpoint: 2026-09-13. This is a bounded implementation and verification record for
`feat/integrated-project-workspace-20260913`, based on 7dbc59b. The complete redesign
request is not accepted as finished, deployed or merged by this document.

## Design and compatibility

The existing FastAPI/Jinja UI, versioned Draft Scope graph and separate matching,
estimate, report and package services remain authoritative. The change consolidates
navigation and adds a register projection/editor over those same records. This reduces
navigation while preserving existing services, IDs, URLs, ownership and history.

No model, database schema, migration, dependency, canonical writer or production gate
is changed. No duplicate pricing store or direct Service-to-Defect relationship is added.
A Service's displayed Defect is derived through its Opening. Existing many-opening or
missing-parent Draft history is retained in a relationship review queue; it is not
silently split, normalized, deleted or reinterpreted as a completed physical model.

The user's blank-opening clarification applies: an explicitly blank Opening may have
zero Services. Do not invent a placeholder Service. Working rows show linked Services
or blank Openings; unresolved relationships require review. Bulk edits protect identities
and relationships, validate the affected graph and use the existing explicit revision save.
Legacy readers/imports retain their existing contract, including historical unresolved data.

## Implemented interaction

- **Projects & estimates:** one primary directory for permitted projects, Draft Scopes,
  saved Draft Estimates and existing estimates. The old `/projects` and `/scopes` URLs
  share the workspace. Another owner's Draft-only project names are not exposed.
- **Libraries:** one primary section with internal navigation to Technical Evidence
  Library, Technical System Library, Item Price Library, Pricelist Library, Labour
  Library and Markup Library. Existing library routes and data remain in use.
- **Register:** cell/range, row and column selection; drag/keyboard navigation; TSV
  copy/paste; bulk fill/clear where editable; sorting/search/filtering; column sizing
  and ordering; frozen IDs; validation and unsaved-grid undo/redo. Selection is one
  contiguous rectangular range. Column preferences are not persisted, and detailed-editor
  changes reset grid undo history. Read-only users can inspect/select/copy. Detailed
  record editing remains available in the same workspace.
- **Systems and prices:** explicit saved Match/Estimate selections project into Proposed
  Technical System and Price columns, with exact revision links, warnings and staleness.
  One saved Match and one saved Estimate can be selected at a time. The subsequent
  [native row-authoring increment](./REGISTER_ROW_AUTHORING.md) adds explicit candidate
  review and manual estimate editing beside the selected row through these same services.
  Opening-qualified recommendations only appear on their matching Opening. Saved prices
  remain independent of that display filter. Reading the register does not run matching,
  create an estimate, recalculate a price or rewrite any saved artifact.
- **Evidence/history:** selected historical Scope and artifact revisions are honoured.
  Source changes remain visible as stale claims. Conflict/error paths retain submitted
  edits; unavailable optional artifacts do not discard the Scope or grant authority.
- **Guidance and layout:** concise section bullets, compact navigation/tables/forms,
  existing CLASSIFIRE logo/palette, active/focus states and responsive table scrolling.
- **Workspace advice:** a collapsible panel previews selected saved Scope records,
  required ancestors and source-reference claims before any optional request. Permission,
  selection/revision and consent checks bound access. Advice cannot write Scope, match,
  price or approval state; the ordinary manual path remains usable when disabled.

The advice panel is a separate optional API-backed interface. It does not embed the
user's authenticated external ChatGPT session or reuse that session's MCP transport.
No existing client plugin, OAuth identity mapping or human-confirmation contract is rebuilt.
Context does not automatically include raw source images, library bodies, pricing or
full estimates. Unsaved browser edits are not silently sent as saved truth. Conversation
is page-local and clears when context changes; no durable conversation history is added.

## Acceptance evidence

Private receipts/screenshots are retained outside Git. No customer document, extracted
customer facts, credentials, operational URL or private approval receipt belongs here.

| Check | Actual result | Evidence and limit |
| --- | --- | --- |
| Affected regression | 157 unique cases passed across 12 files, no remaining failure/skip | `workspace-regression-20260913/validation-receipt.json`; checkout-specific PYTHONPATH, fresh basetemps, disposable PostgreSQL 15433 only |
| Final static/focused checks | Full Ruff, Mypy (233 source files), Bandit and one Alembic head passed; 12 template/history and nine navigation checks passed | Mypy caught a SQL expression typing mismatch; using SQLAlchemy false() corrected it without changing query semantics |
| First hosted CI | 1 failed, 1,993 passed, 337 warnings; fail-fast stopped remaining cases | Run 34703458472 exposed a standalone template render without a permission helper. Reproduced locally; navigation now hides permission-dependent links when the helper is absent. Original assertions retained and a missing-context regression added; 11 focused checks passed. A new source revision requires fresh CI |
| Failure correction | Initial run: 33 passed, one missing-register template failure; subsequent runs: 117 and 7 passed | All original assertions retained; empty optional register context now fails closed. Earlier failure log remains preserved |
| Projects/Libraries browser | Existing synthetic IDs and exact saved estimate links visible; no page errors or mobile document overflow | `workspace-navigation-browser-20260913/receipt.json`; Edge routed through isolated ASGI/SQLite fixtures, not the operational runtime |
| Actual register browser | Column bulk edit, undo/redo, save/reopen and exact older revision succeeded; Scope 3 has five source references; null quantities retained | `integrated-workspace-uat-20260913/grid-browser-receipt.json`; isolated app and synthetic data, no general accuracy measurement |
| Chat browser | Saved revision 3 context preview succeeded; Send disabled and no provider call | Same grid receipt; live provider quality/availability and authenticated ChatGPT integration are unproven |
| Package browser | Preview and explicit automated save/download produced a 12,706-byte ZIP with exact Scope 3 and original DOCX | `package-browser-receipt.json`; exactly manifest, Scope and selected original; automated isolated UAT, not human production approval |
| Isolated process restart | Scope 3 and the original-bearing ZIP remained byte-exact after restarting only app 8840 | `restart-browser-receipt.json`; disposable database 15433, same ZIP digest, no diagnostic/live runtime activation |
| Layout | Grid receipt records no JavaScript errors and no mobile document overflow; desktop/mobile screenshots retained | Bounded Edge viewport checks, not a full accessibility, browser compatibility or large-project performance certification |

Package ZIP SHA-256 for this synthetic run:
`79cd529dc37640593eb33d53ee86f28ceab7aa60b9867f86560366dfd113bf3f`.
The earlier human-confirmed Word package is a separate artifact and is not replaced.

## Incomplete criteria and next acceptance

- **Accurate multimodal analysis:** retained text/picture upload and human review are
  implemented, but this run does not prove accurate automatic analysis of arbitrary
  reports or calibrated service/substrate/quantity extraction. A real report was supplied
  for assessment and its separately approved linked originals were inspected privately;
  the user has now confirmed the findings and unknowns as a private Draft reference.
  This assistant review is not an automatic
  CLASSIFIRE analysis run. No customer details or unsupported accuracy percentage are recorded here.
- **Broader system/pricing work:** selected-row manual authoring now reuses the existing
  explicit workflows in a native panel; its separate evidence is linked above. Scope edits
  still mark results stale. Automatic matching/rate derivation, project-wide result
  selection and broader applicability/pricing assurance remain in the roadmap.
- **Embedded live AI:** provider settings default disabled; verified UAT kept them disabled.
  No live response, multimodal provider analysis, pricing/library context or authenticated
  external ChatGPT session is proven. Any provider activation requires its explicit approval.
- **Complete UX acceptance:** bounded working screens were inspected, but exhaustive
  screen-reader/contrast/browser testing, large-report capacity and customer usability
  acceptance remain. Grid selection is contiguous; no persistent column preferences or
  undo across detailed-editor changes are claimed. The whole product is not certified
  production-ready.
- **Publication/activation:** record actual commit, exact-head CI, required reviews and
  merge separately. The workspace candidate has not been activated by these checks.
  Preserve the diagnostic trial and obtain explicit approval before any activation,
  OAuth/tunnel or host-policy change.

PR #260 merged as `3eabb23` after source `6bc9e96` passed run 34704939887
(2,113 tests plus full static and migration-head checks). No required reviews were
configured. Post-merge run 34706301132 subsequently passed all 2,113 tests and checks.
The workspace remains isolated on 8840; no workspace activation is claimed.

The privately confirmed Draft reference retains unknowns and cannot be coerced into
fixed topology for the older comparator. [Reference readiness](./PHYSICAL_REFERENCE_READINESS.md)
records the permitted preparation and unresolved contract, rights and roadmap gates.
No measured application accuracy or Phase 8C execution is claimed.

## Separate diagnostic runtime checkpoint

PR #259 diagnostic source e2e8292 was separately approved and activated. Its private
fresh restore manifest verified 69 tables, five Scope revisions, two packages and two
originals; retained data/files and reparsed schema were exact. Activation preserved
Scope/package/original history and schema; login activity affected users/audit only.
The saved package route worked; an expired one-time review link correctly returned 403.

A connected upload retry still returned `CLIENT_FILE_UNAPPROVED_HOST`, with no retained
file or changes to all 69 table inventories/files/schema. The rejected host is now
identified in the private diagnostic receipt. No allowlist or OAuth/tunnel policy changed.
This runtime checkpoint does not activate or prove the workspace redesign.
