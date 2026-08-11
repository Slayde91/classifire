# CLASSIFIRE Tool Grant Matrix

| Agent | Read/media tools | Controlled write/action tools |
|---|---|---|
| cf-orchestrator | classifire_health, classifire_workflow_status | none |
| cf-intake-evidence | classifire_health, classifire_workflow_status, classifire_evidence_read, pdf, image | classifire_register_evidence_observations |
| cf-physical-model | classifire_health, classifire_workflow_status, classifire_evidence_read, classifire_physical_model_read, pdf, image | classifire_submit_initial_physical_model, classifire_lock_physical_model, classifire_derive_quantity_labour |
| cf-technical-system | classifire_health, classifire_workflow_status, classifire_technical_search | classifire_select_repair_strategy, classifire_lock_repair_strategy |
| cf-commercial-engine | classifire_health, classifire_workflow_status, classifire_package14_recommendation | classifire_required_components, classifire_derive_commercial |
| cf-validator | classifire_health, classifire_workflow_status, **classifire_evidence_read, classifire_physical_model_read, pdf, image** | classifire_run_validation |
| cf-output | classifire_health, classifire_workflow_status | classifire_lock_snapshot, classifire_render_output |
| cf-library-governance | classifire_health, classifire_workflow_status, classifire_library_releases | none until separate human-governed release endpoints are approved |
| cf-platform-governance | classifire_health, classifire_workflow_status | none |

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
