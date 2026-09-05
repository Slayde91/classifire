# CLASSIFIRE - Engineering instructions

These instructions apply to Codex and other engineering agents in this repository.
CLASSIFIRE is a proprietary passive-fire evidence, scope, technical decision-support,
estimating and reporting platform developed for Ceasefire PFP.

## Approved direction and delivery priority

Read [GOAL.md](./GOAL.md), [the roadmap](./docs/CLASSIFIRE_ROADMAP.md),
[the architecture](./docs/CLASSIFIRE_ARCHITECTURE.md), and the accepted decisions:
[ADR 0001](./docs/ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md) and
[ADR 0002](./docs/ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md).

Build the existing modular application into four independently callable
capabilities: scope analysis, system matching, estimating and reporting. Reuse
CLASSIFIRE's domain services across the standalone UI and future ChatGPT integration.
Keep AI optional. Four capabilities do not require four agents or four services.

Prioritize a working, testable UI prototype. Deliver one complete user interaction
with the minimum supporting contract, persistence and validation in the same slice.
Use GOAL.md and the verified project state to select the next visible increment;
do not rebuild the completed manual Draft Scope workbench.
Do not substitute a schema, backend helper or collection of tests for the user-visible
milestone. Do not make a complete ProjectPackage ZIP, all four capability schemas,
production AI, OpenClaw replacement or every edge case a prerequisite to that demo.

Defer polish, broad optimization and nonessential edge cases until users can try the
prototype. Retain security, data integrity, explicit uncertainty and applicable
permission checks from the start. Record remaining gaps honestly. A usable prototype
is not a completed production phase or permission to weaken release gates.

## Inspect before editing

Current evidence outranks prior conversations and documentation. Inspect, in order:

1. Current source, branch, Git status/diff and relevant tests.
2. Available current runtime and retained execution evidence, where authorized.
3. `docs/PROJECT_STATE.md`, the relevant roadmap section and architecture decisions.
4. `docs/SESSION_HANDOFF.md` and older summaries as navigation, not proof.

Identify unrelated local changes and define the task's demonstrable completion
criteria before editing. Reconcile local work with current shared GitHub state;
never overwrite newer local work simply because it differs from main. Extend
existing abstractions before introducing another framework, database or pipeline.

Preserve the conflicted legacy `C:\CLASSIFIRE` checkout as recovery evidence while
its conflicts remain. Resolve worktrees through `git worktree list --porcelain` and
use an isolated worktree for new changes. Never copy or broadly stage the legacy
root. Reverify its state rather than assuming an old branch or commit is current.

## Domain reasoning and capability independence

Preserve the reasoning and authority chain:

**Evidence -> Defects -> Services/Assets -> Openings -> Substrate Planes -> Physical
Model -> Repair Components -> Technical System Search -> Compatibility Validation ->
Commercial Applicability -> Quantity/Labour -> Reconciliation -> Validation ->
Snapshot -> Estimate/Scope/Close-out Outputs -> Human Release.**

This is a rule about required information and authority, not a requirement to run
all capabilities in one session. Saved artifacts or validated manual inputs can
supply a capability's prerequisites. Completing a capability must not silently
invoke the next one. Reporting must use selected saved revisions and must not
recalculate or rerun matching merely to render an output.

- A defect can contain multiple services, openings, planes and repair components.
  Never assume one defect means one penetration, one service or quantity one.
- Opening, Service and their relationships are distinct. Preserve many-to-many
  relationships and shared openings; do not conflate legacy primary references
  with complete physical topology.
- Preserve source evidence, page/image context, locators, contradictory observations
  and provenance. Prefer better source images without losing distinct context.
- Represent **Confirmed / Inferred / Provisional / Unresolved** explicitly.
  Missing evidence remains missing; do not invent physical or technical facts.
- Technical compatibility requires authorized test/assessment evidence and the
  applicable review. AI extraction and manually selected systems are unapproved
  inputs until governed acceptance; price is never technical proof.
- Commercial calculations follow physical and technical requirements. Recover work
  once, preserve rate inclusions and the recovery ledger, and expose unsupported
  quantities, provisional methods and overrides with their provenance.

Use CLASSIFIRE for new user-facing material. Do not rename legacy QUANTIFIRE/PFEOS
identifiers without checking migrations, stored data, APIs, scripts and lineage.

## Draft, canonical state and human authority

The governed database and retained storage hold live canonical state. Agent memory,
chat, prompts, task text and UI state do not. Versioned capability artifacts and
ProjectPackage exports are portable representations of explicit revisions; imported
claims, signatures or foreign approval history never activate local authority.

A Draft Scope prototype may persist, reopen, validate and export clearly labeled
Draft data without satisfying production Phase 8-14 exits. Persisting an authorized
Draft is distinct from admitting a canonical physical model or granting approval.
Implement this separation through explicit Draft state and narrowly scoped services
within the existing persistence architecture. Existing guarded physical-model UI
writers are not a shortcut for Draft edits. Preserve canonical records and locks.

Do not weaken role separation, ownership checks, protected-state guards, admissions,
validation, lock requirements, verification/signatures or human-only release gates.
Analysis or export code gains no canonical-write authority by running in the same
process. Fail closed where authority, integrity or required evidence is missing.
Never modify a guard merely to let a demo, test or UAT continue.

Store exact artifact/dependency identities. Preserve prior revisions and review
history. Upstream changes make dependent results visibly stale; they must not
silently rewrite downstream quantities, totals or approval facts. A structurally
valid Draft is not proof of complete evidence, compatibility or release readiness.

## OpenClaw, AI and security

Keep deterministic CLASSIFIRE logic inside CLASSIFIRE. OpenClaw and Mission Control
are controlled orchestration components, not canonical state or domain authority.
Retire OpenClaw only after its required protections have verified replacements
under ADR 0001. An unavailable provider must not block the manual Draft prototype.
AI outputs remain bounded proposals; autonomous inference is never implicit approval.

Never commit or expose credentials, `.env` contents, tokens, private signing keys,
customer evidence, temporary signed URLs, proprietary pricing or confidential
technical material. Package 14 commercial and Package 15/17 technical-source
information retains its confidentiality and governance boundaries. Do not copy
restricted content into prompts, logs, fixtures, exports or documentation for
convenience. Export rights and project ownership require explicit enforcement;
an archive hash does not prove either. Use synthetic fixtures by default.

Do not introduce infrastructure or dependencies casually. First reuse the existing
FastAPI, `ui.py`, SQLAlchemy, validation and service patterns. Justify necessary new
dependencies, constrain versions, check maintenance/licensing and validate installation.

## Change, Git and authorization discipline

Use **inspect -> implement -> validate -> classify -> commit -> push -> PR -> merge**
for authorized engineering work. For a documentation-only request, change only the
approved documentation; updating a roadmap does not authorize its implementation.

Make the smallest coherent change that delivers the requested behavior. Inspect
callers and downstream dependencies first. Material architecture changes must
explain current architecture, proposed change, reason, consequences and migration.
Do not silently alter canonical models, authority, technical or pricing rules,
release semantics, evidence lineage, migrations or integration contracts.

A user-authorized named scope includes normal non-destructive Git publication and
merge after required checks pass. Continue autonomously within that scope. Before
publishing, verify branch/upstream, explicit diff, commit range, PR base/head,
current-head CI and review state. Do not bypass failures or required review.
Verify the resulting merge and commit rather than assuming the command succeeded.

Separate authorization is required for destructive Git operations, overwriting
work, deleting branches, force-pushing, protection/access changes, unrelated work,
deployment, release, canonical operations/locks, customer evidence and real
provider/report workflows. Synthetic isolated development tests may exercise those
boundaries without touching customer or operational state.

Never reset, clean, force checkout, destructively rebase or broadly stage unrelated
work. Stage explicit paths and classify what remains local. Preserve branches unless
safe deletion is specifically authorized or required by applicable repository policy.

## Verification and migration safety

Use targeted tests first, then the broader checks justified by the change and CI.
Standard tools are `python -m pytest`, `python -m ruff check .`,
`python -m mypy src`, `python -m bandit -r src` and `classifire doctor`.
Run only authorized runtime checks; do not read or mutate a customer database to
prove a prototype. Keep disposable database tests distinct from operational UAT.

In isolated worktrees, set `PYTHONPATH` explicitly to that worktree's `src` so tests
do not accidentally import the legacy root. Use a unique pytest temporary directory
and disable its cache provider when protecting the checkout. Check actual test
configuration and dependencies before quoting or running old handoff commands.

For a UI milestone, run the app and inspect the complete interaction: create/edit,
save, reopen, validate and inspect the downloaded artifact. Verify persistence after
restart and that applicable forbidden writes remain forbidden. If browser or runtime
verification is unavailable, report the limitation; do not mark the demo verified.
Schemas and unit tests alone do not establish a working UI.

Do not weaken tests to make failures disappear. Diagnose implementation, fixture,
contract and environment before changing assertions. Failures block dependent steps;
warnings and inspection limitations must be reported accurately. Avoid unnecessary
repetition of expensive UAT or broader checks after relevant checks already pass.

Migration history is durable. Prefer a new migration for deployed schemas; never
rewrite history for convenience. Check compatibility, migration order, constraints,
indexes, rollback behavior, auditability and canonical integrity. Prototype priority
does not justify destroying existing data or skipping required migrations.

## Documentation, done and reporting

Keep documentation aligned without making each file repeat the others:

- `GOAL.md`: ultimate product outcome and the immediate demonstrable priority.
- `docs/PROJECT_STATE.md`: verified implementation, gaps, health and next actions.
- `docs/CLASSIFIRE_ARCHITECTURE.md`: implemented versus planned design and decisions.
- `docs/CLASSIFIRE_ROADMAP.md`: delivery order, dependencies, gates and status.
- `docs/SESSION_HANDOFF.md`: verified branch/local context and a self-contained next task.

Do not mark roadmap phases complete from source presence or a Draft demo. Preserve
production exit criteria while developing independent Draft workflows in parallel.
Update completion and test claims only from current evidence.

Before finishing, inspect outputs and the full intended diff, check for secrets and
unrelated changes, run appropriate validation and reconcile documentation. Report in
plain English what changed, what was actually verified, Git/PR/CI/merge results,
remaining local changes, real limitations and the single most useful next action.
Never claim working behavior, test success, publication, deployment or production
readiness without direct evidence.
