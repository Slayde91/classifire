# PROMPTS.md — CLASSIFIRE Orchestrator

These prompts are task templates. Mission Control should insert exact IDs, file references, and required receipt paths. They do not expand the agent's authority.

## Stage Route

```text
Task: Coordinate the next CLASSIFIRE action for estimate `{estimate_id}`.

1. Read the canonical workflow status.
2. State the current stage and exact blockers.
3. Identify the single owning role for the next action.
4. Create or recommend one bounded Mission Control task.
5. Do not perform the specialist work yourself.
6. Return a handoff using the fleet handoff contract.
```
## Visual Pipeline

```text
Coordinate the visual physical-model pipeline for defect `{defect_id}`.

Required sequence:
1. `cf-intake-evidence`: direct-image observations and multi-view reconciliation.
2. `cf-physical-model`: barrier-first topology proposal using the actual images.
3. `cf-validator`: independent adversarial visual review using the same actual images.
4. `cf-physical-model`: canonical write only after validator approval.
5. Physical Model Lock.

Block progression on missing images, unresolved barrier topology, or validator rejection.
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
