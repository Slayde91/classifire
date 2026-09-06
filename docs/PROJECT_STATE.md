# CLASSIFIRE Project State

Verified snapshot: 2026-09-06 AEST. Health: working bounded Draft UI prototype;
full product and production readiness remain incomplete. Accepted ADRs 0001/0002
retain independent capabilities, a shared deterministic core, optional AI and
prototype-first delivery. OpenClaw retirement requires proven replacement protections.

Shared baseline: `13a5b34ebb08eb287aebf02ed218c78ff539f1d5`, merged
[PR #202](https://github.com/Slayde91/classifire/pull/202). Exact-head CI 34002073595
and main CI 34002483886 succeeded. Selected package download was merged in PR #200.

Current branch: `feat/draft-package-materialization-20260906`, worktree
`C:\CLASSIFIRE\.tmp\draft-package-materialization-20260906`. This is an implementation
checkpoint; inspect live PR/head CI before claiming publication or merge.

## Implementation snapshot

| Capability | Implemented bounded behavior | Remaining gap |
| --- | --- | --- |
| Scope | Manual editing, saved import/export, graph checks, PDF page observations | Broader formats/analysis, richer physical entities and contradictions |
| Technical | Source-bound candidates, review history, partial thickness/gap/service-size checks; editable foreign-origin review | Full authorized applicability; imported source claims stay unverified |
| Estimate | Provisional manual rates, source-cell XLSX selection, original/override history; editable imported values | Governed defaults/inference, broader components and recovery |
| Reports | Four retained Draft PDF/XLSX profiles; original imported reports retained behind scan/format checks | Professional/production acceptance, complete source correctness and release gates |
| Packages | Selected configuration/save/history/download; new-project import, identity mapping, original history retention and v2 re-export | Full-project/history/source coverage, existing-project merges and operating limits |
| Interfaces | Shared FastAPI/Jinja use cases; exact supplied logo | Authenticated ChatGPT adapter, full client parity and tenant assurance |
| Authority | Governed persistence, admissions/locks and human release remain separate | Production Phase 8-14 exits and OpenClaw replacement parity |

## Current import work

`draft_package_materialization.create_import` uses one transaction for a new owned
Project/Draft, existing Scope import, explicit imported Match/Estimate identities,
original ZIP retention and hashed identity mapping. It preserves original values,
summary, source claims and history without automatic recalculation. Users may edit
Scope, review preferences/notes and Estimate values independently. Imported approvals
never create local LibraryRelease eligibility or canonical physical authority.

Migration 0035 adds original/archive mapping and report-source tables, imported-origin
columns and native-versus-foreign Match/file-binding constraints. Native bytes and
historical migrations remain intact. Match v4 and Estimate v3 wrap their existing
native contracts; v2 project exports retain current selections and exact original
ZIP ancestry. The retained mapping binds initial local revisions.

Original report snapshots/PDF/XLSX remain foreign attachments. Report-bearing import
requires PostgreSQL and existing shared retention/scan/quarantine controls. Scanner
failure, expired verdicts, changed bytes, active content or lost rights block binary
and original-ZIP downloads/re-export, including already saved packages. Scope/review/
Estimate-only import also works on SQLite. No new dependency or provider run.

## Verification and health

- Core/HTTP/readiness checks: 23 passed, including confirmation, wrong file, CSRF,
  replay refusal, new ownership, edit/re-export/re-import and reopened records.
- Six migration checks passed, including actual 0034 -> 0035 retention of native
  Match/Estimate/revision/package bytes, relationship constraints and refused downgrade.
- PostgreSQL report lifecycle checks passed for original-byte retention, new owner
  bindings, nested re-import, scanner absence, rollback and shared sticky quarantine.
- The browser found a PostgreSQL ordering bug when importing Match plus Estimate;
  an explicit Match-revision flush fixes it and a populated PostgreSQL regression
  passed. No constraint was weakened. Affected regression: 506 passed, three warnings.
- Real Chrome completed Scope-only and populated upload/confirmation, report scan,
  Scope save, review-note and Estimate price edits, and new ZIP downloads. Independent
  inspection verified unchanged original ZIP/PDF/XLSX, preserved history and the
  edited price. Final restart/re-import verification passed, including a further Scope edit.
- Mypy passed for 186 source files. Ruff and Bandit passed; the final focused run passed 10 tests, including full PostgreSQL import, local
  workbook edits and migration. Exact-head hosted CI remains a publication prerequisite.
- The supplied logo is byte-identical to the served asset (SHA-256
  `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`).
  Chrome verified exact bytes and the rendered logo was visually inspected.

Evidence is synthetic. No customer evidence, real provider, operational database,
governed physical/Estimate submission or lock, deployment or human release was
authorized or executed. The demo contains zero canonical Estimates/lines, Openings,
Services and Physical Model Locks; new Project and Draft rows are expected.
A passing Draft workflow does not complete the product's technical or commercial rules.

## Known gaps and local context

The package is a selected workspace, not a complete database/evidence backup.
Restricted source bodies stay external/withheld. Size/depth limits, retention/quotas,
redistribution, existing-project conflict resolution and production parser sandboxing
need further work. Imported reports are not proof of technical truth or source/snapshot
agreement. ChatGPT, broader evidence/applicability/pricing and production gates remain
unfinished. Do not make all that breadth a prerequisite to trying this prototype.

All current branch changes belong to editable package import, its UI, tests,
migration/contract documentation and a separately marked synthetic import demo.
The legacy root remains untouched: 46 unstaged modifications, 14 staged additions,
four DU conflicts and unrelated untracked work. Some old pytest directories cannot
be enumerated, so the untracked inventory is not guaranteed complete. Preserve older
worktrees and the three untracked generic-package experiments.

## Recommended Next Actions

1. Publish the locally verified import milestone through normal exact-head CI/PR
   review and merge. Regression and restart/re-import checks have passed. Do not substitute more preview polish or a Scope-only result.
2. Then implement the first thin authenticated ChatGPT-facing Draft interaction using
   the shared create/read/edit/download commands. Prove ownership, explicit mutation
   confirmation and local synthetic parity before credentials or external deployment.
3. Gather user-trial feedback; fix supported-path failures before broad polish. Extend
   evidence formats, full authorized applicability and governed pricing in bounded
   visible increments. Preserve production gates and OpenClaw protection parity.

The runnable demo, exact next-session prompt and validation commands are in
[SESSION_HANDOFF.md](./SESSION_HANDOFF.md).
