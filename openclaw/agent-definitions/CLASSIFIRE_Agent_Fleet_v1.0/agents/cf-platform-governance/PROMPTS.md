# PROMPTS.md — CLASSIFIRE Platform Governance

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Integration Change

```text
Implement controlled platform change `{change_id}`.

Requirements:
- identify the failure layer and root cause;
- preserve canonical domain boundaries;
- make the smallest version-controlled change;
- add regression and role-boundary tests;
- validate OpenClaw configuration and Mission Control sync;
- verify secrets are not exposed;
- document rollback.

Do not alter estimate facts to make the integration pass.
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
