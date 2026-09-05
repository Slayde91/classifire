# Draft service-size review

Status: implemented local P2b increment under accepted ADRs 0001/0002. Consult
PROJECT_STATE.md and live Git/CI for publication. This is a partial measured-range
comparison, not a technically applicable system or approval.

## User interaction and meaning

The existing measured-limit screen now records smallest/largest measured service
sizes in millimetres plus two explicit meanings: what the observations measure and
what the selected source's limits mean. For one observation, enter the same size
twice. No quantity, instance count, shape or diameter is inferred from a label.
The range describes recorded observations only; complete instance coverage remains
unassessed. Record the observed instances, measurement method and relevant source
page/definition in the existing required measurement evidence note.

Both meanings default to unknown. Supported enum values are `unknown`,
`outside_diameter`, `nominal_diameter`, `rectangular_dimensions`, `bundle_envelope`.
Only two explicitly recorded `outside_diameter` meanings permit the numeric size
comparison. These are unapproved human interpretations of retained evidence; the
library's generic min/max fields do not establish the dimension meaning themselves.
Nominal sizes, bundles, rectangular dimensions, missing or differing meanings remain
unresolved. No conversion or automatic promotion of source interpretation occurs.

Positive decimal millimetres retain the existing strict syntax: no exponent,
nonfinite value, locale separator, implicit coercion or more than four decimal
places. A reversed measured range is refused. A missing endpoint remains unknown.
With a valid selected opening/nonblank service and hash-bound published source,
recorded diameters are compared against `minimum_service_size_mm` and
`maximum_service_size_mm`. Bounds are inclusive. A known exceeded bound is outside;
a range cannot be within limits unless both source bounds are valid and present.
Malformed source values stay unavailable; reversed complete bounds, unpinned
releases and invalid targets remain unresolved. Source staleness blocks new measured reviews through the existing guard.

## Additive contract and shared services

`CLASSIFIRE-DRAFT-SYSTEM-MATCH-v3` preserves the existing envelope and adds these
fields inside `constraint_review.inputs` alongside the original thickness/gaps/note:

| Field | Type |
| --- | --- |
| `service_size_min_mm`, `service_size_max_mm` | Strict positive decimal strings or null |
| `service_size_basis`, `source_size_basis` | Explicit enum strings above |

The existing check list gains `measured_service_outside_diameter_range`; status is
within_limits/outside_limits/unresolved with saved bounds and reason. Review remains
`partial_unapproved`; source-meaning authorization, service instances/coverage and
all remaining technical conditions stay explicitly unassessed. Review actor/time,
source fields/hash, exact Scope/target and revision/parent hash remain retained.

`save_constraint_review(..., service_size=True)` opts into v3. The old default still
accepts the exact v2 input shape. V2 validation never accepts v3 fields. Once a review
is v3, an older client cannot drop size evidence by submitting the v2 form: the
service refuses with `MATCH_MEASUREMENT_VERSION_REQUIRED`. Keep/reject edits preserve
the complete prior review/version. Old v1/v2 JSON and report downloads are unchanged.
No table, database migration, new dependency or agent is added.

The existing form endpoint accepts complete old or new forms, never a partial mix;
active-human ownership, project write, technical read, CSRF, bounded input, stale
basis and concurrent revision checks still apply. Shared pure presentation includes
the range, recorded meanings and numeric check in scope-and-system PDF/XLSX. Explicit
Estimate creation retains the exact v3 review without reinterpreting or applying it.
Estimate-only reports remain an estimating profile; complete combined reporting is
still planned. No next capability, quantity calculation, canonical write or approval
is automatically invoked by saving measurements.

## Synthetic demonstration and checks

Use a fresh marked SQLite demo with `--seed-service-size-library`. The separately
versioned `SYNTHETIC-P2B-SIZE-001` source explicitly defines individual round-service
outside diameter of 10 to 90 mm, plus prior synthetic thickness/gap limits. It is
not real test evidence or a malware-scan/approval result. Existing P2a/P2b demos and
source bytes remain unchanged; the launcher refuses to adopt the wrong fixture.

Run `tests/test_draft_service_size_review.py`, `tests/test_draft_service_size_ui.py`
and affected constraint/match/Estimate/report regressions. Demonstrate explicit
within/outside/unknown states, escaping, permission/CSRF rejection, exact history,
actual restart, readable PDF/XLSX and unchanged canonical counts. PROJECT_STATE.md
records actual results and preview-tool limits. Full applicability and production
readiness are not claimed by these checks.
