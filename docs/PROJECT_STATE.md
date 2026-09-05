# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST).
**Product health:** a working manual Draft Scope UI prototype; pre-production.
**Verified shared-main baseline before this increment:**
`803da1bfee1724a9f1bd86f58b6130782dfdb8c3` (PR #187).
**Implementation increment:** P0 on `feat/draft-scope-ui-20260905`; verify its
current PR/merge state before treating local evidence as shared publication.

## Approved direction and current work

The owner approved [ADR 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md)
and prototype-first delivery. It refines accepted hybrid
[ADR 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md): four independently
callable capabilities, a shared deterministic core, optional bounded AI, versioned
artifacts and user-controlled continuation. This direction needs no further approval.

**P0 is implemented and locally demonstrated.** The authenticated `/scopes`
workspace creates a new project and manual Draft, supports distinct defects,
openings and services, validates relationships, saves successive revisions, reopens
after a server restart and downloads the exact saved JSON. Validation and unknown
facts remain separate from approval. See [the runnable demo](./DRAFT_SCOPE_DEMO.md).

**Next engineering task: P1a, safe Draft Scope JSON import/replacement in that UI.**
Complete P0 publication checks first. Keep import preview, explicit confirmation,
revision conflict checks and imported provenance together in one usable increment.
Do not expand this task to report extraction, whole-project ZIP or another capability.

## Implemented foundations and remaining gaps

| Area | Verified implementation | Remaining product gap |
| --- | --- | --- |
| UI/API | FastAPI/Jinja login/CSRF and existing screens; new `/scopes` create/editor/validation/download routes call shared Draft services | Only manual Scope is demonstrated. Four-capability UI, source upload and ChatGPT adapter are incomplete. |
| Draft Scope | `services/draft_scope.py`, strict v1 schema, owner/admin access, database revisions, hash/parent checks, conditional stale-save refusal and exact JSON download | No import, full Scope provenance/contradiction structures, service instances, independent planes/treatments or downstream freshness tracking. Manual Confirmed remains unreviewed. |
| Scope/evidence | Retained-byte ownership, bounded PDF/XLSX/DOCX locators, approved scopes/families, proposal runners and review lifecycle | Full user-facing report analysis is absent; report runners remain service-only. Broad formats/visual interpretation remain limited. |
| Physical authority | Distinct canonical Defect/Opening/Service/links, admissions, guarded writes, amendments and replacement locks | The new Draft tables intentionally confer no physical admission, lock or release. Historical real-UAT acceptance was not refreshed. |
| Technical | Source-bound Draft/review/revision, eligibility, immutable releases and authority checks | No independent System Match workspace over saved/manual Scope with complete applicability results. |
| Estimating | Decimal calculations, basic rates/rules, desk-quote proposals, snapshot integrity and PDF/XLSX renderers | Independent Estimate artifacts, workbook/rate-method/override workflow and complete recovery coverage remain unfinished. |
| Reporting | Canonical export uses active lock and retained snapshot; snapshot building recalculates | Independent partial Draft reports must consume explicit saved revisions without invoking estimation. |
| Orchestration | PRs #183-#185 completion acceptance, journal and optional transport lifecycle hooks | Producer assurance, general recovery and retirement parity remain unfinished. The manual Draft UI runs without OpenClaw or AI. |
| Packages | Versioned Draft Scope JSON plus existing narrow proposal/estimate exports | No complete ProjectPackage workflow. Whole-project projection, rights, archive/import and client parity remain incomplete. |

Paths abbreviated above are under `src/classifire/`. Implementation and tests
outrank this document. A manual Scope increment does not complete Scope Analysis
or any authoritative Phase 8-14 exit.

## Project health and verification

- Baseline main [CI 33945228889](https://github.com/Slayde91/classifire/actions/runs/33945228889)
  succeeded on `803da1b`. P0 publication requires its own exact-head CI and review.
- The initial combined local service/HTTP/migration/authority regression run passed
  **69 tests**, with **one PostgreSQL concurrency test skipped** locally and two
  existing dependency warnings. Subsequent focused checks are recorded in the
  handoff. Final HTTP checks passed 20 tests; the complete migration collection
  plus deployment/preflight/legacy regressions passed 41 tests. Do not infer hosted
  PostgreSQL success from a local skip.
- Full source Mypy passed (146 files), full Ruff and Bandit passed during the
  implementation review. The JavaScript syntax and template checks passed.
  Recheck final changed files and required CI before merging.
- Actual Chrome automation created, edited, validated, saved, reopened and
  downloaded a synthetic scope. The server was restarted; the reopened revision
  and downloaded bytes were unchanged. Screenshots were visually inspected and
  no browser page errors were recorded. This was a browser test, not a user trial.
- The sample has one defect, three openings, two services and one Unresolved
  observation, including a blank opening, shared links and a null quantity.
  Both downloaded file hashes are
  `551221821649d33a78b0a2e8a8fa427a0b7e60819b8c0199605351c2edc04f4e`.
- Isolated demo database inspection found zero canonical defects, openings,
  services, service links, estimates and Physical Model Locks. Retry runs left
  five synthetic Drafts and seven revisions; these are not customer records.
- Additive migration `0027_draft_scope_revisions` introduces two Draft tables.
  Deployment readiness now requires that head and both Draft tables, and rejects
  missing tables or the previous revision. Downgrade refuses retained history.
  It does not rewrite deployed migrations;
  production migration/readiness is not established by the SQLite demo.
- Draft content is owner/admin restricted. Existing project names/references are
  still shared through `/projects` for `project:read` users. Full tenancy, customer
  privacy, real report accuracy, deployment/recovery and human release are unproven.

## Local change classification

- Protected root `C:\CLASSIFIRE`: branch `gpt/phase8-linked-original-images`,
  HEAD `de0cc5a`, CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
  Four linked-visual conflicts plus staged, unstaged and untracked material remain
  recovery evidence. Do not resolve, copy, broadly stage or publish from this root.
- P0 worktree: `.tmp/draft-scope-ui-20260905`, branch
  `feat/draft-scope-ui-20260905`, based on `803da1b`. Relevant changes comprise the
  Draft service/schema, models/migration, UI, synthetic launcher, tests and docs.
  Determine final publication from current Git/GitHub rather than this snapshot.
- Earlier documentation worktree `.tmp/four-capability-architecture-review-20260905`
  carried merged PR #187. Its accepted direction remains the target.
- `.tmp/project-package-draft-20260905` retains three unrelated untracked candidate
  files: `docs/PROJECT_PACKAGE_V1_CONTRACT.md`, `services/project_package.py` under
  `src/classifire/`, and `tests/test_project_package.py`. Prior review passed 22
  synthetic tests; this increment neither edits nor requalifies that candidate.
- Demo data, browser tools, screenshots, receipts and synthetic browser sessions
  remain under `.tmp/`; they are local verification artifacts, not repository files.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Its historical receipt was
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The recorded outcome was rollback-only, without controller/runner canonical
writes or a Physical Model Lock. The receipt/database were not reopened here.
This history neither authorizes a rerun nor blocks synthetic Draft UI development.

## Recommended Next Actions

1. **Deliver P1a: safe import/replacement of saved Draft Scope JSON in the working
   UI**, after verifying P0 publication. Validate and preview before persistence,
   preserve source lineage separately from local authority, and append a revision
   only on explicit confirmation. Follow the [handoff](./SESSION_HANDOFF.md).
2. Use the demonstrated screen and user feedback to add one supported evidence
   intake path, independent matching/estimating and partial PDF/XLSX reporting.
   Build each contract with its usable interaction; keep missing information visible.
3. Complete whole-project portability and a thin ChatGPT client over proven shared
   commands. Broaden accuracy and production operations from measured needs, with
   OpenClaw retirement on its separate protection-parity track.

Related: [Goal](../GOAL.md), [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md).
