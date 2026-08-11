# PROMPTS.md — CLASSIFIRE Output

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Render

```text
Render `{artifact_type}` for estimate `{estimate_id}` from the current immutable validated snapshot.

Do not recalculate any value. Verify snapshot ID, validation receipt, artifact hash, row counts, totals, assumptions, exclusions, and branding. Return only the controlled rendering receipt and artifact reference.
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
