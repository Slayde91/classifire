# CLASSIFIRE Agent Fleet v1.0

This package contains complete OpenClaw/Mission Control markdown definitions for all nine CLASSIFIRE agents.

## Included agents

- `cf-orchestrator` — CLASSIFIRE Orchestrator
- `cf-intake-evidence` — CLASSIFIRE Intake and Evidence
- `cf-physical-model` — CLASSIFIRE Physical Model
- `cf-technical-system` — CLASSIFIRE Technical System
- `cf-commercial-engine` — CLASSIFIRE Commercial Engine
- `cf-validator` — CLASSIFIRE Validator
- `cf-output` — CLASSIFIRE Output
- `cf-library-governance` — CLASSIFIRE Library Governance
- `cf-platform-governance` — CLASSIFIRE Platform Governance

## Per-agent files

Each agent directory contains:

- `IDENTITY.md` — canonical identity, role, authority, status vocabulary.
- `SOUL.md` — personality, expertise, decision posture, constraints.
- `AGENTS.md` — complete operational system prompt.
- `TOOLS.md` — current and required tools plus invocation rules.
- `TASK_BOUNDARIES.md` — owned, refused, incoming, completion, and handoff rules.
- `WORKFLOWS.md` — detailed workflow, retries, Mission Control lifecycle, output envelope.
- `PROMPTS.md` — reusable task prompts.

## Current visual workflow

The existing fleet is retained. No new permanent agents are required.

```text
cf-orchestrator
  → cf-intake-evidence: direct-image observation and multi-view reconciliation
  → cf-physical-model: barrier-first draft topology
  → cf-validator: independent adversarial visual review using the same actual images
  → cf-physical-model: controlled canonical write and Physical Model Lock
  → cf-technical-system: opening-specific technical search
```

## Important security rule

Markdown describes behaviour but does not grant access. Actual permissions must remain enforced by OpenClaw tool grants, CLASSIFIRE plugin allow-lists, service-token scopes, and API role checks.

See:
- `OPENCLAW_UPDATE.md`
- `MISSION_CONTROL_UPDATE.md`
- `TOOL_GRANT_MATRIX.md`
