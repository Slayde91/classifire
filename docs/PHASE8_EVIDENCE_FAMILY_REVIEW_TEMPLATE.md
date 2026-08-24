# Phase 8 Evidence-Family Relationship Review Template

Use this local review record only after a retained evidence-family inventory has
been produced. It records a human reviewer's specific declaration about a pair
of evidence IDs. It must not be treated as an automatic regrouping rule or an
authority to infer, write, lock, submit, or release a physical model.

The record must bind the exact canonical SHA-256 of the inventory. The allowed
relationship types are `REENCODE_OF`, `CROP_OF`, `ANNOTATION_OF`,
`ALTERNATE_ANGLE_OF`, and `DISTINCT_IMAGE`. For the first three, `subject` is
the derived image and `related` is the source image. The last two are symmetric.
`DISTINCT_IMAGE` cannot be combined with any other declared relationship for the
same pair.

```json
{
  "schema": "CLASSIFIRE-PHASE8-EVIDENCE-FAMILY-REVIEW-v1",
  "status": "HUMAN_DECLARATIONS_RECORDED",
  "scope": "DECLARATIONS_ONLY_NO_AUTOMATIC_MERGE",
  "source_inventory": {
    "schema": "CLASSIFIRE-PHASE8-EVIDENCE-FAMILY-INVENTORY-v1",
    "inventory_sha256": "REPLACE_WITH_CANONICAL_INVENTORY_SHA256"
  },
  "reviewer": {
    "name": "REPLACE_WITH_REVIEWER_NAME",
    "competency_reference": "REPLACE_WITH_COMPETENCY_OR_AUTHORITY_REFERENCE",
    "reviewed_at": "YYYY-MM-DD",
    "review_method": "Visual evidence review",
    "site_visit_performed": false
  },
  "relationship_declarations": [
    {
      "declaration_id": "EFR-001",
      "relationship_type": "REENCODE_OF",
      "subject_evidence_id": "DERIVED_EVIDENCE_ID",
      "related_evidence_id": "SOURCE_EVIDENCE_ID",
      "outcome": "CONFIRMED",
      "evidence_basis": "State the visual basis and any limitation."
    }
  ],
  "unreviewed_relationships_may_remain": true,
  "report_or_image_retrieval_performed": false,
  "runtime_inference_performed": false,
  "database_write_performed": false,
  "canonical_write_performed": false,
  "physical_model_lock_created": false,
  "automatic_family_merge_performed": false,
  "release_performed": false
}
```

Validate a completed record locally:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts\validate_phase8_evidence_family_review.py `
  --inventory C:\path\to\evidence-family-inventory.json `
  --review C:\path\to\evidence-family-review.json
```

`PASS` only confirms that the record is structurally valid and bound to the
provided inventory. It does not prove reviewer competence, confirm an
unreviewed image relationship, merge evidence families, or authorize any
downstream CLASSIFIRE action.

## Proposal-context overlay

A downstream proposal component must not use the raw review record as an
automatic regrouping instruction. It may build a content-free, read-only
overlay only with `build_phase8_evidence_family_review_overlay`, retain the
bound inventory and review record, and validate a reloaded overlay with
`validate_phase8_evidence_family_review_overlay` before consuming it. The
overlay binds both canonical SHA-256 values and exposes only declaration IDs,
relationship types, and the two evidence IDs. It neither changes the automatic
inventory nor permits inference, canonical writes, locking, release, or an
automatic family merge.
