# CLASSIFIRE Project State

Verified snapshot: 2026-09-06 AEST. Health: working bounded Draft UI prototype;
full product and production readiness remain incomplete. ADRs 0001/0002 retain
independent capabilities, shared deterministic services, optional AI and UI-first
delivery. OpenClaw retirement still requires proven replacement protections.

Shared baseline: `d2709d84c70d7295624cb090ce1d6f6190dab5f1`, merged
[PR #201](https://github.com/Slayde91/classifire/pull/201); exact-head CI 33999996200
passed 1,456 tests on rerun and main CI succeeded. The first run crossed midnight
and exposed an existing collection-time date fixture; assertions were not weakened.
PR #200 already merged selected package download at `541c107`.

Current branch: `feat/draft-package-import-v1-20260906`, worktree
`C:\CLASSIFIRE\.tmp\draft-package-import-v1-20260906`. This is an implementation
checkpoint; verify live PR/head CI before claiming publication.

## Implementation snapshot

| Capability | Implemented bounded behavior | Remaining gap |
| --- | --- | --- |
| Scope | Manual editing, saved JSON import/export, graph checks, PDF page observations | Broader evidence formats/analysis, richer physical entities and contradictions |
| Technical | Source-bound candidates, decision history, partial thickness/gap/service-size checks | Full authorized applicability, materials/FRL/insulation/configuration coverage |
| Estimate | Provisional manual rates, source-cell XLSX selection, original/override history | Governed defaults/inference, broader components and recovery |
| Reports | Four retained Draft PDF/XLSX profiles | Professional/production acceptance and release gates |
| Packages | Merged configuration/save/history/download; current no-write ZIP semantic preview | Transactional new-project import, local identity mapping, safe binary retention, editable re-export; full-project/history/source coverage |
| Interfaces | Shared FastAPI/Jinja use cases; exact supplied logo | ChatGPT adapter, complete tenant/operational assurance |
| Authority | Governed persistence, admissions/locks and human release remain separate | Production Phase 8-14 exits and OpenClaw replacement parity |

## Current import work and known gaps

The new upload screen checks a complete selected package before any local import.
Strict manifest and capability schemas, source pointers, exact selected membership,
report profiles and embedded dependency equality are validated through existing
services. Rehashed inconsistent content is refused. All four report profiles and
original Estimate override history are preserved in inspection. Project/technical/
Estimate/pricing-library permissions follow included content; CSRF and bounded forms
apply. Project labels are escaped and never select a local project by foreign ID.

PDF/XLSX members are only inventoried with size/header/hash checks. They are not
opened, scanned, rendered, retained or downloaded. This neither proves safe binaries
nor correct report contents. Imported technical/library/approval claims remain foreign
and unverified. No project, canonical record or audit event is created by preview.

**Import remains active and incomplete.** The next change must create a new owned
Draft project transactionally while preserving all selected capability records,
original bytes, history and identity mapping. Existing Match records require a local
LibraryRelease; importing must not fabricate one or activate foreign authority.
Scope-only substitution or silently dropping review/Estimate/report members is not done.

## Verification and project health

- New service tests: 3 passed, including all four report profiles, original history,
  permissions, no writes and 20 rehashed invalid-content scenarios.
- New HTTP tests: 2 passed, one existing Starlette warning; upload, CSRF, body/file
  bounds, duplicate files, permission denial, text escaping and no record creation.
- Affected package/PDF/pricing HTTP regression: 14 passed, 5 PostgreSQL-dependent
  cases skipped locally, two warnings. Hosted CI must cover those cases before merge.
- Full Mypy passed for 181 source files; Ruff and Bandit passed. No migration or
  dependency added. Shared source inventory preserves the existing ZIP format.
- Three previous synthetic exported ZIPs passed independent semantic inspection.
  Real Chrome uploaded Scope-only and populated packages, displayed inventory and
  unverified claims, and refused an invalid ZIP without page errors. The exact
  supplied logo remained byte-identical. The screenshot was visually inspected.
- A fresh marked synthetic SQLite demo contains zero Projects, Draft Scopes, package
  records, canonical Estimates/lines, Openings, Services or Physical Model Locks
  after inspection. No operational/customer data or real provider was used.

## Local changes and active work

Current files: semantic import inspection service, package UI/template and Scope link,
shared bounded upload helper/PDF adapter, reused source inventory, service/HTTP and
pricing-permission tests, and aligned docs. AGENTS.md and ADRs already align.

Preserve the legacy root (four DU conflicts, 46 unstaged modifications, 14 staged
additions) and older untracked generic package experiment. Never stage local-only
synthetic data, screenshots or receipts. Current demo is port 8810 at
`.tmp/draft-import-preview-demo-20260906`; the previous package demo on 8809 is untouched.

## Recommended Next Actions

1. Complete safe new-project package import using the current semantic preview:
   explicit identity/origin contracts, clean/quarantined original-byte retention,
   transactional local Draft records, reopen/edit and traceable full selected re-export.
2. Expose proven shared commands through ChatGPT, then broaden evidence analysis,
   actual applicability, governed estimating and full project/production coverage.
