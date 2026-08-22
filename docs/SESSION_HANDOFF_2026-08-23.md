# CLASSIFIRE Session Handoff - 2026-08-23

This handoff supersedes `SESSION_HANDOFF_2026-08-22.md` for current project
position. Repository code, tests, Git history, and runtime receipts remain the
source of truth.

## Latest verified state

- Shared-main code baseline is `0e590469d5b101bad43b38c47a4a19bce9b84df8`,
  merge commit for Phase 8 PR #53.
- Gates A-F remain locally deployment-validated. The real UAT estimate remains
  unchanged: no admission has been signed or registered, no canonical physical
  model has been submitted, and no Physical Model Lock exists.
- Current main now contains the bounded correction guard, blind inventory and
  reconciliation, deterministic proposal-only controller, retained-evidence
  adapter, deterministic prompt/profile bindings, and guarded OpenResponses
  transport.
- The transport permits only literal loopback endpoints, revalidates retained
  image bytes immediately before upload, sends no client tools, requires an
  empty effective server-tool attestation for the exact session, audits every
  attempted turn, and accepts exactly one strict JSON assistant payload.
- The transport has not yet made a configured live Gateway/model request. Its
  current evidence is synthetic HTTP, guard, and controller integration testing.

## Verification completed

- 18 no-tool transport tests pass.
- 113 combined transport, controller, retained-evidence, blind-inventory, and
  visual-validation tests pass.
- The full repository suite passes 218 tests when
  `CLASSIFIRE_ADJUDICATED_INITIAL_SUBMISSION_ENABLED=false`, which restores the
  repository default for tests instead of inheriting the configured live value.
- Ruff, targeted mypy, Bandit, `git diff --check`, TypeScript compilation, and
  the Phase 8 plugin-profile verifier pass.
- Exact-main ignored plugin artifact SHA-256 remains
  `38812E99DC138A198EE58BF6E00E9B34E081502CB43C39089418BC53E3C2AEE4`.
- Exact-main Gate A candidate fingerprint is
  `90ABCFF7CFDDBB16ECEE22EE5CC34DD2C09610A4041BA4455410655B7BA8A370`.
  The audit records `deployment_authorised=false` and
  `live_change_performed=false`.

## Unresolved work

1. Wire the guarded transport to an approved Gateway RPC, token provider, and
   HTTP client boundary; define dedicated zero-tool Physical and Validator
   profiles; then prove one controlled synthetic live run without any canonical
   write capability.
2. Reconcile the validation-only human comparator from the legacy Phase 8 stack
   without allowing reference answers into inference.
3. Reconcile the linked-original resolver against current retained-evidence
   abstractions and multiple report formats.
4. Design, persist, and enforce a canonical visual-validation receipt before a
   future Physical Model Lock can become eligible.
5. Reconcile a tracked `docs/CLASSIFIRE_ARCHITECTURE.md`. The existing copy is
   confined to the legacy branch and contains stale branch-specific claims.

## Next valid task

Implement and test the runtime composition boundary for the new guarded
transport. Use only synthetic retained images for live proof, keep both visual
agents on dedicated profiles with zero effective server tools, and stop before
any real-report inference, admission, canonical write, or lock. If exact
server-tool attestation cannot be proven before the provider request, fail
closed and do not send images.
