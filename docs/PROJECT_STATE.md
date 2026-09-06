# CLASSIFIRE Project State

## Evidence-based snapshot

Verified 2026-09-06 AEST from current source, Git/GitHub, tests and synthetic runtime.
Shared baseline: `2f79e490049d23a9dc8e34e3aa54fb8d232a960d`, merged PR #203.
Its exact-head CI 34007195747 passed 1,470 tests; main CI 34007644149 succeeded.
Current worktree: `C:\CLASSIFIRE\.tmp\chatgpt-draft-client-20260906`, branch
`feat/chatgpt-draft-client-20260906`. Publication of this branch must be checked live.

Accepted architecture: ADR 0001 hybrid modular core and ADR 0002 independent
capabilities. Deterministic services, optional AI and portable explicit revisions
remain the target. No OpenClaw retirement, customer operation or production release.

| Capability | Verified bounded implementation | Remaining product gap |
| --- | --- | --- |
| Scope | Manual Draft editor, revisions/import, retained PDF page workflow | Broader Word/XLSX/image/drawing analysis and full governed interpretation |
| System matching | Saved candidate review and selected measured-constraint checks | Full authorized applicability and evidence coverage |
| Estimating | Independent Draft estimates, preserved overrides and workbook rate selection | Validated provisional/default pricing breadth and full recovery chain |
| Reporting | Four independent Draft PDF/XLSX profiles from saved snapshots | Professional/production acceptance and governed close-out/release |
| Portability | Selected v1 ZIP creation/download; editable new-project import and v2 retained-origin re-export | Complete project/source/history coverage, existing-project merge and production retention |
| ChatGPT-facing client | Optional MCP Scope/create/edit/package tools, identity mapping, browser confirmation and shared exact downloads on current branch | Real OAuth/account linking, remaining capability tools and production deployment |

## Active work and measured verification

The client branch adds `draft_client.py`, `draft_client_auth.py`, a retained request
service/table and migration 0036. Existing Draft services remain the only business
logic. Tools can propose writes; the same human must confirm through the existing
browser session. Owner/role checks, stale revisions, CSRF, explicit selection,
foreign-origin restrictions and retained-byte checks remain enforced.

Executed checks (overlapping suites, not additive coverage claims):

- First official MCP HTTP/service journey and token boundaries: 10 passed.
- Expanded client, new migration and readiness checks: 38 passed.
- PostgreSQL two-confirmation race plus preflight/legacy lineages: 11 passed.
- Affected client/auth/Scope/package UI/readiness/packaging regression: 74 passed,
  one PostgreSQL test skipped in that run; its separate PostgreSQL run passed.
- Full Mypy: 190 source files passed. Ruff and Bandit passed before the final
  presentation/documentation reconciliation; recheck final source and exact-head CI.
- Official SDK client + Chrome: propose/confirm/create/edit/package/download passed;
  browser and client ZIP bytes matched, quantity remained unknown, no page errors.
- Actual process restart: saved bytes and SDK reads remained exact; sign-in returned
  to the pending review and rejection persisted. The supplied logo matched exact bytes.
- Synthetic database receipt: one Draft workspace/package, five client requests;
  canonical estimates/lines/openings/services/physical locks all zero at that checkpoint.

The PostgreSQL fixture was initially rejected by automatic approval review because
it uses table cleanup. Read-only inspection then proved its dedicated loopback
`classifire_containment_test` database had no tables or other sessions; the bounded
synthetic run was approved and passed. No customer/demo database was reset.

## Project health, gaps and local context

The interactive Draft prototype is usable for the demonstrated synthetic paths.
That is not complete scope analysis, technical suitability, production estimating or
release readiness. Preserve production Phase 8-14 gates and explicit uncertainty.
A real ChatGPT session has not been connected. OAuth authorization-server selection,
compatible tokens, callback/PKCE/consent, HTTPS deployment and account-specific access
remain to be established with separate operational authority. Local key/revocation
policy is implemented; issuer-side revocation/rotation operations remain unproven.
Read [the client contract](./DRAFT_CLIENT_V1_CONTRACT.md) for precise limits.

This branch's local changes belong to the client adapter, human review, optional
dependencies, migration/readiness, tests, synthetic launcher and aligned docs.
The legacy root remains recovery material on `gpt/phase8-linked-original-images`:
prior verified inventory had four DU conflicts, 46 unstaged modifications and 14
staged additions; inspect afresh before any recovery. It was not edited for this task.
Old worktrees, source evidence, demos and generic archive experiments remain preserved.

## Recommended Next Actions

1. Finish exact-head CI/PR publication; recheck
   current Git state before assuming this checkpoint's work is merged.
2. Extend this same authenticated adapter to existing independent System Match,
   Estimate and report use cases. Reuse human confirmation/shared commands and prove
   client/UI saved-artifact parity with synthetic data; no implicit capability chaining.
3. Configure and test a real OAuth/HTTPS ChatGPT link when account/deployment authority
   is available. Gather user feedback and extend missing domain coverage in visible
   increments. Do not claim production readiness or retire OpenClaw from prototype tests.

[SESSION_HANDOFF.md](./SESSION_HANDOFF.md) carries exact context, checks and next prompt.


## Final local validation checkpoint

Final client/auth/readable-Scope regression: 64 passed, one PostgreSQL test skipped
in that run (the separate PostgreSQL confirmation test passed). Full Ruff, Mypy
(190 files), Bandit and the single 0036 migration head passed. Final Chrome inspection
confirmed readable proposed physical content, the exact supplied logo, login return,
persisted rejection and byte-identical downloads after process restart. Documentation
links and diff whitespace checks passed. Git publication/full exact-head CI still
must be checked live; these local results do not establish external ChatGPT linking.
