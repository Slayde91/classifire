# PROMPTS.md — CLASSIFIRE Technical System

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Opening Search

```text
Perform opening-specific technical search for locked Opening `{opening_id}`.

Use the active CLASSIFIRE Technical Authority Registry. Package 15/17 currently supplies FIREFLY candidates only.

For every candidate, assess:
service configuration, material, quantity, size, substrate, orientation, opening geometry, FRL, annular gap, insulation, supports, fixing, and source status.

Return explicit MATCH/MISMATCH/UNKNOWN findings. Select no system unless one complete authorised variant is supported.
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
