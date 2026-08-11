# PROMPTS.md — CLASSIFIRE Validator

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Visual Review

```text
Independently validate the proposed physical topology for defect `{defect_id}` using the attached actual images.

Try to prove it wrong. Check for:
- MISSED_BARRIER
- WRONG_BARRIER_PLANE
- MISSED_OPENING
- DUPLICATED_OPENING
- OVER_SPLIT_OPENING
- OVER_MERGED_OPENING
- MISSED_SERVICE
- INVENTED_SERVICE
- WRONG_SERVICE_CLASS
- WRONG_SERVICE_QUANTITY
- WRONG_SERVICE_OPENING_LINK
- DUPLICATED_PHOTO_SUBJECT
- UNSUPPORTED_MATERIAL
- UNSUPPORTED_DIMENSION

Return exactly:
VERDICT: APPROVED | REJECTED | BLOCKED
ISSUES: structured issue list with image/evidence references
REQUIRED_ACTION: exact correction or evidence needed

Do not edit the model.
```
## Final Validation

```text
Run the controlled independent validator for estimate `{estimate_id}`.

Report:
- validator receipt ID and version;
- every gate result;
- exception count and issue codes;
- stale-state findings;
- reconciliation and anomaly results;
- whether snapshot creation is permitted.

Do not alter upstream records to make the validator pass.
```

## Standard handoff prompt

```text
Prepare a CLASSIFIRE handoff.

Include:
- estimate_id, run_id, task_id, and relevant record IDs;
- current canonical stage;
- exact evidence/files reviewed;
- confirmed, inferred, provisional, unknown, and blocked facts;
- controlled writes and receipts;
- exact unresolved issues;
- next owning role and one next controlled action;
- facts the receiving role must not infer.
```
