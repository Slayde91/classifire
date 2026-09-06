# CLASSIFIRE Project State

Verified snapshot: 2026-09-06 AEST. Health: working bounded Draft UI prototype;
full product and production readiness remain incomplete. Accepted ADRs 0001/0002
retain independent capabilities, shared deterministic services and optional AI.
OpenClaw retirement still requires proven replacement protections.

Shared baseline: `541c107b9b3552e572d9933b86140b4d6f750120`,
[merged PR #200](https://github.com/Slayde91/classifire/pull/200).
[Exact-head CI 33998891633](https://github.com/Slayde91/classifire/actions/runs/33998891633)
and [main CI 33999342298](https://github.com/Slayde91/classifire/actions/runs/33999342298)
succeeded, rechecked 2026-09-06. All four Draft report choices, selected package
download and the supplied logo are merged. Safe new-project ZIP import is not implemented.

## Implementation snapshot

| Capability | Verified implementation | Remaining gap |
| --- | --- | --- |
| Scope | Manual editing, exact JSON import/export, graph checks, PDF page-linked observations | Broader formats/analysis, richer instances/planes/treatments and contradictions |
| Technical | Source-bound candidates, saved decisions/history, partial thickness/gap/service-size checks | Full authorized applicability, coverage, materials/FRL/insulation/configuration |
| Estimate | Provisional manual rates, exact-cell XLSX selection, original/override history, missing/omitted work | Governed defaults/inference, broader components and recovery |
| Reports | Scope-only, scope-and-system, estimate-only and complete retained PDF/XLSX | Professional/production acceptance and release gates remain separate |
| Packages | Current selected Draft configuration, preview, save, history and ZIP download | Safe imports, source-body/full-project/history coverage |
| Interfaces | Shared FastAPI/Jinja use cases; supplied logo exact in UI and outputs | ChatGPT adapter and full tenant/operational assurance |
| Authority | Existing governed persistence, admissions/locks and human release boundaries | Production Phase 8-14 exits and OpenClaw replacement parity unproven |

## Merged package increment

Users choose one Scope revision, optional coherent review/Estimate revisions and
selected existing report pairs. Preview performs no database writes. Explicit save
creates an immutable package revision; changed membership creates another revision.
Downloads retain exact original bytes. Mismatched inputs, changed previews, stale
package save versions, invalid archives and revoked content permissions are refused.
Source/dependency changes are shown without rewriting history.

Migration 0034 adds DraftProjectPackage in the existing database, with parent/revision,
manifest/archive hashes and creator/time. Existing artifact readers and report
integrity/permissions are reused; no provider, new dependency or canonical writer.
Source bodies remain external/withheld with provenance pointers. This packages
selected workspace revisions, not every project record or original source file.
The older untracked generic archive candidate remains unshipped. See
[contract](./DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md).

## Verification and health

- 43 focused package, HTTP, migration, lineage, packaging and preflight tests passed
  in 65.43 seconds. Warnings: existing Starlette/Alembic deprecations and an intentional
  malformed ZIP duplicate-name fixture. The broader affected migration/report/package
  regression also passed: **98 tests**, three warnings, 389.05 seconds.
- Initial import, fixture and template-context wiring errors were diagnosed and fixed.
  Audit assertions now explicitly allow the three expected create/download events;
  canonical/source counts remain unchanged. No failing production assertion was hidden.
- Mypy passed for 179 source files; Ruff, Bandit and one Alembic head (0034) passed.
  Hosted PR and main CI have now succeeded, including PostgreSQL validation.
- Real Chrome configured Scope-only, combined and reconfigured package revisions.
  Downloaded three ZIPs; all remained exact after a real process restart. No page errors.
  UI screenshot inspected; exact supplied logo verified by bytes.
- Independent ZIP inspection checked every member size/hash, exact Scope/review/
  Estimate dependencies, retained AUD 440.00 subtotal and original report PDF/XLSX
  bytes. The combined archive has seven entries including its manifest.
- Synthetic fixture is a marked copy of the previous report demo, with only local
  storage paths relocated. Three package revisions exist; canonical Estimates,
  lines, Openings, Services and Physical Model Locks all remain zero. No customer
  evidence, operational database, provider, deployment or release was used.

Package publication is complete; no concrete blocker is currently known. The full
platform goal remains active. The running synthetic UI on port 8809 returned the
supplied logo with SHA-256 `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`;
its login page references that same asset. No replacement image was generated.

## Local changes and active work

Merged PR #200 files: package service/UI/template, model/migration, router and Scope link,
readiness head, focused tests, pricing permission regression, current-head migration
expectations and aligned docs. Existing migration histories remain unchanged;
the prior pricing migration test is pinned to 0033 so it still checks its own downgrade.
AGENTS.md and accepted ADRs already match the approved direction and remain unchanged.

The conflicted legacy root and unrelated older package candidate files are preserved.
Local-only demo, browser harnesses, ZIPs and receipts are under
`.tmp/draft-package-demo-20260906`, `.tmp/package-artifacts` and
`.tmp/scope-browser-test-tools`. Do not stage them. Demo URL: port 8809.

## Recommended Next Actions

1. Deliver safe new-project package import with full selected membership, explicit
   local identity mapping, retained foreign provenance and unresolved external sources.
   Include review/Estimate contracts; do not silently discard unsupported artifacts.
2. Share proven commands through ChatGPT. Broader evidence analysis, actual applicability,
   governed estimating and full package/production coverage remain required.
