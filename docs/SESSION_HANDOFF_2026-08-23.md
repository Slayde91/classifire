# CLASSIFIRE Session Handoff - 2026-08-23

This handoff supersedes `SESSION_HANDOFF_2026-08-22.md` for current project
position. Repository code, tests, Git history, and runtime receipts remain the
source of truth.

## Latest verified state

- Shared-main code baseline is `7f7a06206eb52ea294c6dd6e44e2920b5546ab58`,
  merge commit for Phase 8 comparator PR #63.
- Gates A-F remain locally deployment-validated. The real UAT estimate remains
  unchanged: no admission has been signed or registered, no canonical physical
  model has been submitted, and no Physical Model Lock exists.
- Current main contains the bounded correction guard, blind inventory and
  reconciliation, deterministic proposal-only controller, retained-evidence
  adapter, deterministic prompt/profile bindings, guarded OpenResponses
  transport, managed local runtime composition, mandatory logical-role runtime
  identity bindings, pinned zero-tool v2 profiles, and fail-closed provisioning.
- The transport permits only literal loopback endpoints, revalidates retained
  image bytes immediately before upload, sends no client tools, requires an
  empty effective server-tool attestation for the exact session, audits every
  attempted turn, and accepts exactly one strict JSON assistant payload.
- `cf-phase8-visual-physical` and `cf-phase8-visual-validator` are installed
  under separate dedicated identities. Both resolve `openai/gpt-5.6`, use
  Docker sandboxing with no workspace access or elevation, deny all agent tools,
  explicitly disable the sandbox allow gate, and have independently verified
  empty live effective tool inventories. Normal OpenClaw agents were unchanged.
- One configured synthetic retained-image inference completed through the
  Validator identity on exact main. Its strict payload validated with one stage,
  no tool calls, no human-reference visibility, no canonical-state connection,
  no canonical write, and no lock.
- Current main has a post-inference, validation-only human-reference comparator.
  It binds the proposal, strict controller receipt, and reference by path and
  SHA-256, verifies the proposal's canonical JSON hash, and detects
  topology/substrate swaps. It imports no database or inference interface.

## Verification completed

- 31 focused transport/runtime tests pass.
- 8 comparator tests and 89 related Phase 8 tests pass.
- The full repository suite passes 239 tests when
  `CLASSIFIRE_ADJUDICATED_INITIAL_SUBMISSION_ENABLED=false`, which restores the
  repository default for tests instead of inheriting the configured live value.
- Targeted Ruff and mypy, `git diff --check`, TypeScript compilation, and the
  Phase 8 plugin-profile verifier pass.
- Exact-main ignored plugin artifact SHA-256 remains
  `38812E99DC138A198EE58BF6E00E9B34E081502CB43C39089418BC53E3C2AEE4`.
- Exact-main Gate A candidate fingerprint is
  `86FCF6000C450D77019F1FAD4F3434F44445AA1FDC091370A22B703A3F619557`.
  The audit records `deployment_authorised=false` and
  `live_change_performed=false`.
- The synthetic live-proof receipt is
  `C:\CLASSIFIRE\.tmp\phase8-synthetic-live-proof-027cf4b-20260823-07\synthetic-live-proof-receipt.json`
  with SHA-256
  `F256E6D9ED28904A1B009617B55D677A32AF0F2E8AF5ADAD1A690CD3ED4DD4C4`.
  Its transport receipt hash is
  `991A11A2A8EAEA181A4A05F44D63BC28CBE22C789EA7F41D9EA1AAA1CECE459A`.

## Unresolved work

1. Reconcile the linked-original resolver against current retained-evidence
   abstractions and multiple report formats.
2. Design, persist, and enforce a canonical visual-validation receipt before a
   future Physical Model Lock can become eligible.
3. Reconcile a tracked `docs/CLASSIFIRE_ARCHITECTURE.md`. The existing copy is
   confined to the legacy branch and contains stale branch-specific claims.

## Next valid task

Reconcile the standalone linked-image retrieval/materialisation service and its
security tests from legacy commit `ba1b6bd` without importing the obsolete
real-UAT runners. Then separately bridge verified linked originals into the
current retained-evidence boundary while preserving thumbnail and page context.
Keep live network retrieval out of the source reconciliation tests.
