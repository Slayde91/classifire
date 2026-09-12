# Register row authoring

The register now opens native technical-review and price forms beside a selected
linked Service or blank Opening. It uses the existing application handlers and
versioned domain services. It introduces no new model, schema, migration, pricing
engine, provider or canonical authority.

The subsequent [Evidence tab](./REGISTER_SOURCE_EVIDENCE.md) adds read-only source
inspection to this same panel, including unresolved rows. Its saved-revision view
can be opened with unsaved Scope edits; write-authoring restrictions below remain.

## User interaction

1. Open a saved Scope revision and choose a row's Proposed Technical System or Price
   cell. Enter or F2 also opens its action. Resolve missing or historical multiple-parent
   relationships before authoring from the linked working register.
2. Choose a technical release and explicitly find/save candidates. Review sources and
   existing measured-limit fields; save keep/reject preferences as a separate revision.
   A kept candidate remains an unapproved review preference.
3. In Price, explicitly create or select an estimate using the saved Scope and optional
   exact candidate review. Add a manual work description, rate, quantity and source note.
   Only the selected row's work line is editable in the panel; totals retain all lines.
4. Override a quantity/rate with a reason, or omit/restore a saved line. The existing
   service retains the original value, author/time/reason and prior revisions. Blank
   quantities remain unknown; no quantity one or subtotal is manufactured.
5. Saved artifact revisions update the register and its selected-revision URL. Reopen
   those exact saved selections later. Scope, review, estimate, reports and package
   confirmations remain independent actions.

Unsaved Scope edits must be saved before authoring. The panel and Scope controls are
inactive while a request is pending, so its result cannot replace newly typed entries.
Closing or changing an edited panel asks before discarding unsaved panel entries.
Stale-write errors retain attempted entries and require explicitly reopening a current
revision; they never overwrite the newer saved result. A displayed result for another
Scope revision or target remains read-only in the row panel. Normal standalone
historical workflows retain their existing rules.

## Implementation boundary

`X-Classifire-Workspace: register` changes only presentation of existing matching and
estimate picker/detail routes. Their normal full-page forms still work. Both modes
call the same ownership, permission, CSRF, bounded-input, dependency and optimistic
revision checks. Responses remain uncached and vary on the presentation header and
session cookie. No arbitrary return URL or new write endpoint is introduced.

The browser accepts only same-Draft capability paths for panel actions, imports native
HTML content without scripts, and refreshes saved projections through read-only Scope
GETs. Form action attributes are read explicitly: existing named `action` inputs must
not shadow the target URL. Price actions use the service recovery key even when
historical views repeat a service across openings; existing duplicate recovery guards
remain authoritative.

## Verified checkpoint

- 104 affected tests passed: 7 new native-fragment integrations, 66 existing matching/
  estimate UI cases and 31 Scope/register/history cases. Full Ruff, Mypy (233 source
  files), Bandit and JavaScript syntax checks passed. Tests used the selected checkout,
  fresh basetemps and isolated synthetic SQLite; no operational database was used.
- Actual Edge on a separate loopback demo exercised a linked service and blank opening:
  explicitly retrieve candidates, save review, create estimate, add manual rates,
  override, inspect exact downloads and reopen. Blank openings gained no dummy service.
- The synthetic service's original rate 12.5 remained retained after rate 15 and a
  concurrent rate 16. Quantities and subtotals remained null. A stale attempted rate 17
  returned 409, retained its reason and left the newer rate intact. Two distinct recovery
  lines existed; Scope revision 2 bytes remained unchanged throughout downstream work.
- Restart preserved Scope 2 and estimate 4/5 bytes exactly; estimate 3's content matched
  its retained decoded reference. The earlier reference file for estimate 3 was pretty
  printed, so no byte-for-byte pre-restart claim is made for that file.
- Desktop/mobile output was inspected, with no document overflow at 390px and no page
  script errors. Keyboard opening, focus return, unsaved-Scope refusal and hidden
  nonselected row edit forms were checked. Synthetic canonical estimate, opening,
  service, relationship and lock tables remained empty.

Private browser scripts, screenshots and receipts are retained under
`.tmp/register-row-authoring-uat-20260913`; they contain synthetic data only. They are
not a hosted CI result or deployment receipt. Publication and exact-head CI must be
observed separately. The operational 8820 app, OAuth/tunnel/host policy and provider
settings are unchanged. Only the separate 8841 synthetic SQLite demo was restarted.

## Remaining scope

This implements selected-row manual authoring, not automatic technical approval,
project-wide matching, library-derived automatic pricing or general report accuracy.
The initial checkpoint selects one saved Match and one saved Estimate at a time.
The subsequent [multi-review package increment](./MULTI_REVIEW_PROJECT_PACKAGES.md)
extends explicit row-review selection while retaining one Estimate. Source
review, broader applicability, governed rates/recovery, scaling and exhaustive
accessibility remain in the roadmap. The private human-reviewed Draft reference and
Phase 8/8C gates in [reference readiness](./PHYSICAL_REFERENCE_READINESS.md) are unchanged.
