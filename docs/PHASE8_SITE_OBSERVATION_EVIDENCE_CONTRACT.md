# Phase 8 Site-Observation Evidence Contract

**Status:** Controlled evidence-intake contract; non-canonical and non-authorising.

## Purpose

This contract records newly governed field evidence for one Defect without
changing a Physical Model. It supports the current Phase 8 evidence gap:
opening dimensions, depth/boundaries, substrate, service identification/material,
and opposite-face continuity.

It does not approve a proposal, create a canonical Opening or Service, sign an
admission, create a Physical Model Lock, select a system, price work, or release
an estimate.

## Registration boundary

Use `POST /api/v1/estimates/{estimate_id}/evidence-sources` with:

- `evidence_type`: `site_observation` (hyphen/space aliases normalise to this);
- one `defect_id` belonging to that estimate;
- `evidence_class`: `observed`;
- an immutable, malware-admissible StoredFile whose purpose is
  `technical_evidence`; and
- the strict `source_json` payload below.

The existing evidence-mutation guard still applies. Evidence cannot be added
through this endpoint after the existing physical-state guard blocks mutation.
For `site_observation`, the audit event records the immutable file hash and a
canonical `source_json_sha256`; it does not duplicate the payload body.

## Required provenance payload

```json
{
  "schema_version": "CLASSIFIRE_SITE_OBSERVATION_EVIDENCE_V1",
  "captured_at": "2026-08-25T11:00:00+10:00",
  "collected_by": "qualified-inspector-reference",
  "collection_method": "site_visit",
  "governance_reference": "SITE-VISIT-REFERENCE",
  "location_reference": "Level and location reference",
  "observations": [
    {
      "observation_id": "SITE-O-001",
      "subject_kind": "opening",
      "subject_reference": "The locally identifiable subject",
      "evidence_locator": "The exact page, image region, or sheet area",
      "fact_type": "opening_dimensions",
      "status": "confirmed",
      "value": "120 x 80",
      "unit": "mm"
    }
  ]
}
```

`captured_at` must include a timezone. Allowed `collection_method` values are
`site_visit`, `remote_supervised_inspection`, and `documentary_follow_up`.
Observation IDs must be unique within the payload. Every observation must
include an `evidence_locator` that identifies its page, image region, or sheet
area within the retained file. Extra fields fail closed.

## Fact and uncertainty rules

Allowed `fact_type` values are:

- `opening_dimensions`;
- `opening_depth_or_boundary`;
- `substrate`;
- `service_identification`;
- `service_material`; and
- `opposite_face_continuity`.

Allowed statuses are `confirmed`, `inferred`, `provisional`, `unresolved`, and
`contradicted`.

A non-unresolved fact needs a value. An `unresolved` fact must have no value and
must record a `limitation`, such as inaccessible opposite face or obscured
boundary. The contract intentionally preserves uncertainty instead of treating
an unverified field observation as a fact.

A `contradicted` fact must also record a `limitation` explaining the conflict;
it is not a resolved site fact.

## Operational use

Retain the original field photograph, drawing, measurement sheet, or supporting
document as the immutable StoredFile first. Register only observations that the
retained file and the named collection event support. Do not use this contract to
repeat the unchanged visual inference run or to construct a canonical 5/6/6
model. A new proposal-only validation run remains conditional on materially new,
governed evidence and separate run authority.
