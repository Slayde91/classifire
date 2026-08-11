# PROMPTS.md — CLASSIFIRE Intake and Evidence

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Photo Observation

```text
Review the attached actual photograph for CLASSIFIRE defect `{defect_id}`.

Observe only what is visible. Report:
- barrier/substrate clues;
- visible physical apertures and their boundaries;
- visible Services or homogeneous Service groups;
- colours, fittings, dimensions or size bands that are defensibly inferable;
- viewpoint and barrier face;
- landmarks for matching other views;
- whether native detail is adequate or zoom is required;
- uncertainty.

Do not decide the final Opening count, technical system, or price.
```
## View Reconciliation

```text
Reconcile all attached actual photographs for defect `{defect_id}`.

Determine:
- which photos show the same physical area;
- which show opposite faces or different angles of the same barrier;
- which show physically distinct barrier planes;
- which Services are the same physical Service across views;
- which distinct Services share one physical aperture;
- which photos are exact duplicates or non-scope.

Photograph count is not quantity. Return structured groups, counting instructions, and unresolved contradictions.
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
