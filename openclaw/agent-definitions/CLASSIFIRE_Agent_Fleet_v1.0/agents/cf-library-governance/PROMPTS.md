# PROMPTS.md — CLASSIFIRE Library Governance

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Release Review

```text
Review proposed library change `{change_id}`.

Classify affected records, provenance, release lineage, duplicate/collision risk, schema impact, regression impact, required human approver, and estimate-pinning consequences. Prepare a draft revision only; do not activate or overwrite a release.
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
