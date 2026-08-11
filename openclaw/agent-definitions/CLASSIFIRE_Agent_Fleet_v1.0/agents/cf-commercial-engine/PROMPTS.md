# PROMPTS.md — CLASSIFIRE Commercial Engine

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Commercial Recovery

```text
Derive commercial recovery for estimate `{estimate_id}` after Repair Strategy Lock.

For each required component:
1. identify the exact technical requirement;
2. retrieve its governed quantity and labour activities;
3. test exact Package 14 applicability;
4. use component build when exact applicability is absent;
5. retain Not Priced or Expert Estimate status where required;
6. reconcile every requirement and prevent duplicate/shared-work recovery.

Do not alter technical scope.
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
