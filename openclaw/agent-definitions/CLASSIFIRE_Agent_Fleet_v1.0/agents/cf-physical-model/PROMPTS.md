# PROMPTS.md — CLASSIFIRE Physical Model

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Topology

```text
Build a draft physical topology for CLASSIFIRE defect `{defect_id}` using the attached actual images and retained evidence.

Mandatory order:
1. Reconcile views.
2. Identify barrier planes.
3. Identify physical Openings within each barrier.
4. Identify Services or homogeneous Service groups.
5. Assign Services to Openings.

Rules:
- One Opening may contain zero, one, or many Services.
- Different Service types do not create separate Openings.
- A blank core has no placeholder Service.
- Opposite faces and different angles usually remain one Opening.
- Separate unlike Services; group only homogeneous Services with the same physical/technical treatment.
- Record assumptions and confidence.
- Do not select a technical system or price.
```
## Canonical Write

```text
Write the validator-approved physical model for estimate `{estimate_id}`.

Preconditions:
- the draft topology receipt exists;
- the independent visual validator verdict is APPROVED;
- all rejected findings are resolved or explicitly Blocked;
- no active conflicting Physical Model Lock exists.

Use only controlled physical-write tools. Return canonical IDs, counts, links, assumptions, lock ID, content hash, and critical unknowns.
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
