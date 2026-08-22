# CLASSIFIRE Tool Grant Matrix

## Active Phase 8 admission-only profile

The active controlled-write deployment profile is
`phase8-admission-only`. Of the tools owned by the controlled-write plugin, it
registers only `classifire_submit_initial_physical_model`, and only for
`cf-physical-model`. Other plugin-owned tools below are source inventory, not
current authority.

| Agent | Read/media tools | Active controlled write/action tools |
|---|---|---|
| cf-orchestrator | classifire_health, classifire_workflow_status | none |
| cf-intake-evidence | classifire_health, classifire_workflow_status, classifire_evidence_read, pdf, image | none from the controlled-write plugin |
| cf-physical-model | classifire_health, classifire_workflow_status, classifire_evidence_read, classifire_physical_model_read, pdf, image | classifire_submit_initial_physical_model |
| cf-technical-system | classifire_health, classifire_workflow_status, classifire_technical_search | none from the controlled-write plugin |
| cf-commercial-engine | classifire_health, classifire_workflow_status, classifire_package14_recommendation | none from the controlled-write plugin |
| cf-validator | classifire_health, classifire_workflow_status, **classifire_evidence_read, classifire_physical_model_read, pdf, image** | classifire_run_validation |
| cf-output | classifire_health, classifire_workflow_status | classifire_lock_snapshot, classifire_render_output |
| cf-library-governance | classifire_health, classifire_workflow_status, classifire_library_releases | none until separate human-governed release endpoints are approved |
| cf-platform-governance | classifire_health, classifire_workflow_status | none |

## Retained inactive controlled-write source inventory

The explicit `full-controlled-write` profile retains these implementations for
later authorised phases. They are inactive under the Phase 8 profile:

- `classifire_register_evidence_observations` — `cf-intake-evidence`;
- `classifire_select_repair_strategy` and
  `classifire_lock_repair_strategy` — `cf-technical-system`;
- `classifire_derive_quantity_labour` — no active owning agent;
- `classifire_required_components` and `classifire_derive_commercial` —
  `cf-commercial-engine`.

The retired `classifire_lock_physical_model` tool is not part of either
controlled-write profile. A future Physical Model Lock requires its own
reviewed admission boundary and separate authority.

## Required delta

The current implementation must be amended so `cf-validator` can read canonical evidence, read the physical model, and inspect the actual PDF/images for pre-lock independent visual validation.

The validator remains read-only for physical scope. It must not receive:
- evidence write;
- physical write;
- Physical Model Lock;
- technical selection/lock;
- commercial derivation;
- snapshot lock;
- Human Release.

## Enforcement layers

1. OpenClaw `agents.list[*].tools.alsoAllow`.
2. CLASSIFIRE OpenClaw plugin `TOOL_AGENTS`.
3. Controlled-write plugin agent allow-list.
4. CLASSIFIRE service-principal scopes.
5. CLASSIFIRE API role and workflow guards.
6. Regression tests proving both authorised access and cross-role denial.
