# CLASSIFIRE Project State

**Verified snapshot:** 2026-09-05 (AEST).
**Product health:** working manual Draft Scope UI and saved-JSON exchange;
pre-production, with broader capability and evidence-intake gaps.
**Verified shared-main baseline before P1a:**
`96d686952021828ef1fb28b53f4d6eea566376aa` (PR #188).
**Current increment:** `feat/draft-scope-import-20260905`; verify its current
PR/merge before equating local demonstration with shared publication.

## Approved direction and current work

The owner approved [ADR 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md)
and prototype-first delivery, refining accepted hybrid
[ADR 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md). Keep four
independently callable capabilities over shared deterministic services, optional
bounded AI and explicit versioned artifacts. This direction is already approved.

**P0 is merged; P1a is implemented and locally demonstrated.** The `/scopes` UI
creates and edits manual Drafts, validates relationships, saves/reopens and downloads
exact revisions. It now accepts a supported saved JSON file, previews its complete
content without writes, and requires explicit confirmation before replacing local
content as a new revision. Old revisions remain unchanged.

Import checks version, schema, relationships, normalized content, checksum and
bounded input. The 15-minute preview binds exact bytes, destination/revision and
session. Imported v2 history survives manual edits and reimport; source identities
and authors remain unverified claims. Local ownership/author/time are assigned by
CLASSIFIRE, with Draft/unreviewed status and no canonical promotion.

**Next: P4a, scope-only Draft PDF/XLSX reports**, after P1a publication. This early
profile is already permitted by the roadmap and adds another useful independent
capability over proven saved data. P1b evidence intake remains required, with scan,
verified storage and retention prerequisites recorded below.

## Implemented foundations and remaining gaps

| Area | Verified implementation | Remaining product gap |
| --- | --- | --- |
| UI/API | Existing FastAPI/Jinja shell plus manual Draft editor and import/preview/confirmation/download routes | Other independent capability screens and ChatGPT adapter remain incomplete. |
| Draft Scope | Strict v1 manual/v2 imported contracts, ownership, revisions, graph and integrity checks, stale-save refusal, exact JSON downloads | Full evidence locators, service instances, independent planes/treatments, structured contradictions and downstream freshness remain unfinished. |
| Source intake | Exact-byte ownership and bounded PDF/XLSX/DOCX adapters; existing proposal runners and review lifecycle | No demonstrated user-facing evidence-to-Scope path. Uploads remain pending/not_configured without a verified clean-scan producer; locked clean reads require PostgreSQL. |
| Physical authority | Separate canonical Defect/Opening/Service/links, admissions, guarded writes, amendments and locks | Draft edits/imports do not satisfy physical admission or Phase 8-14 exits. Historical real-UAT acceptance was not refreshed. |
| Technical | Source-bound Draft/review/revision, eligibility, immutable releases and authority checks | Independent System Match workspace and complete applicability coverage remain unfinished. |
| Estimating | Decimal calculations, rates/rules, desk-quote proposals, snapshot integrity and renderers | Independent Estimate artifacts, pricing-workbook methods/overrides and full recovery coverage remain incomplete. |
| Reporting | Canonical/desk-quote output foundations; ReportLab and XlsxWriter already declared | Scope-only Draft profile and retained snapshot/output binding are next. Never call the recalculating estimate snapshot builder for it. |
| Orchestration | PRs #183-#185 acceptance/journal/transport foundations; manual Draft operations run without AI/OpenClaw | Producer assurance, general recovery and retirement parity remain incomplete. |
| Packages | Saved v1/v2 Scope JSON can be downloaded and imported; old local revisions retained | No complete ProjectPackage ZIP, rights/membership projection, raw imported-source attachment store or full foreign revision history. |

Abbreviated source paths are under `src/classifire/`. Manual/imported Confirmed
values remain unreviewed assertions. No partial prototype proves full Scope Analysis,
four-capability completion, production tenancy or authoritative release readiness.

## Project health and verification

- Shared P0 main [CI 33947498324](https://github.com/Slayde91/classifire/actions/runs/33947498324)
  passed on `96d6869`: 1,020 tests, plus static and migration-head checks.
- P1a service regression: 54 passed, one PostgreSQL concurrency test skipped locally.
  Import HTTP suite: 21 passed; the two cases with final additional assertions also
  passed. The final combined Draft/import/UI/migration/authority regression passed
  **118 tests**, with one local PostgreSQL skip and one existing Starlette warning.
- Full source Mypy passed (146 files); full Ruff, Bandit, JavaScript syntax and
  whitespace checks passed. Required exact-head hosted CI must verify the full
  suite and PostgreSQL race; a local skip is not a PostgreSQL pass.
- Actual Chrome file selection/preview/confirmation/import/manual-edit/reimport
  passed, with old v1 bytes unchanged and altered-source refusal. Screenshots were
  visually inspected. Actual server restart preserved v2 content, both source
  records and exact downloaded bytes; no browser page errors were recorded.
- Final, post-refusal and post-restart file SHA-256:
  `ef77991ef46955ae917e0a252ff19651ee8a3251f2d018c66fff6f759f437442`.
  Embedded envelope hash:
  `dd930c4e1ab0861fce9551c556f1ccc4bc076dce598ac1e541eb1359017f840e`.
- The isolated import demo has one Draft and five revisions, and zero canonical
  defects, openings, services, links, estimates or Physical Model Locks. No customer
  evidence, provider execution, operational canonical write, deployment or release ran.
- Migration head remains `0027_draft_scope_revisions`; P1a uses existing revision
  JSON storage and adds no migration or dependency. Bounds are 288 KiB per source
  artifact and 16 imported-source records; excess history is refused, not truncated.
- Draft content is owner/admin restricted. Existing `/projects` names/references
  remain shared for project readers; full tenant privacy is not established.

## Known dependencies and technical debt

P1b can reuse DOCX paragraph/simple-table extraction and retained-evidence services,
but must demonstrate actual scanning before parsing, PostgreSQL locked clean-byte
access and source-retention policy. `save_upload` has a same-filename temporary-path
concurrency concern to resolve before general intake exposure. Scanner and disposable
PostgreSQL availability were not verified here. Do not invent a clean attestation.

P4a can proceed with saved manual/imported scopes using existing output libraries.
It needs one frozen snapshot containing the Scope revision, project labels and
profile/render version, with retained PDF/XLSX bindings. Preserve missing quantities
and unverified history; canonical estimate exports keep their existing lock gates.

## Local change classification

- Protected root `C:\CLASSIFIRE`: `gpt/phase8-linked-original-images`, HEAD
  `de0cc5a`, CHERRY_PICK_HEAD `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`.
  Four linked-visual conflicts and staged/unstaged/untracked recovery work remain
  untouched. Do not reset, clean, resolve, broadly stage or publish from this root.
- Active worktree `.tmp/draft-scope-import-20260905`, branch
  `feat/draft-scope-import-20260905`, based on `96d6869`: shared import service,
  browser boundary/templates/script, regressions and aligned docs only.
- P0 worktree `.tmp/draft-scope-ui-20260905` retains merged PR #188 and its demo.
- `.tmp/project-package-draft-20260905` retains three unrelated untracked candidate
  files: contract, `services/project_package.py` and tests. Its previous 22 synthetic
  tests are historical evidence; this increment neither edits nor requalifies it.
- Import demo data and browser tools/receipts/screenshots/downloads remain under
  `.tmp/draft-scope-import-demo-20260905`, `.tmp/scope-browser-test-tools` and
  `.tmp/draft-scope-import-artifacts`. They are synthetic local artifacts, not PR files.

## Historical operational evidence

The documented 2026-09-01 proposal-only UAT failed at blind inventory with
`VISUAL_PROPOSAL_FAILED` / `INFERENCE_PORT_FAILED`; human comparison was NOT_RUN.
Its historical receipt was
`F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.
The recorded outcome was rollback-only with no canonical writes or Physical Model
Lock. The receipt/database were not reopened. This does not authorize a rerun.

## Recommended Next Actions

1. **Deliver P4a: scope-only Draft PDF/XLSX reports** after verifying P1a publication.
   Use one explicitly selected saved revision and retained snapshot/output binding;
   inspect the browser, PDF page images and workbook contents. Follow the handoff.
2. Complete a real evidence-intake slice with its scanner, storage and retention
   prerequisites, then independent matching/estimating and further report profiles.
3. Complete project-wide portability and shared ChatGPT access; broaden accuracy,
   formats and production operations from measured needs. Retire OpenClaw only
   after its required protections have proven replacements.

Related: [Goal](../GOAL.md), [Architecture](./CLASSIFIRE_ARCHITECTURE.md),
[Roadmap](./CLASSIFIRE_ROADMAP.md), [Handoff](./SESSION_HANDOFF.md),
[Demo](./DRAFT_SCOPE_DEMO.md).
