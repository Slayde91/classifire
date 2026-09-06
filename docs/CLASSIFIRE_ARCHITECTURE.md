# CLASSIFIRE Architecture

**Document status:** Current pre-production architecture

**Architecture version:** 5.18 - independent Draft capability client commands.

**Verified shared baseline:** `bef06e2264944a34f85f72e7d0fb80c83e406997`, merged
PR #204; main CI 34010757579 succeeded. Current branch
`feat/client-independent-capabilities-20260906` extends the optional resource server
to independent Match, Estimate and report operations. PROJECT_STATE.md records
validation/publication. Local parity is not a real ChatGPT connection or production readiness.
Earlier milestone descriptions are historical checkpoints where a later amendment
supersedes their status. Current component/amendment sections distinguish remaining coverage.

**Accepted target architecture:** Hybrid deterministic core with bounded,
optional AI adapters; see
[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md),
refined by approved [Decision 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md).

This document separates the architecture that is implemented now from the
adopted target architecture and known gaps. Read it with [PROJECT_STATE.md](./PROJECT_STATE.md)
and [CLASSIFIRE_ROADMAP.md](./CLASSIFIRE_ROADMAP.md). Source, tests, migrations,
Git state, and retained runtime receipts determine factual implementation state.

## Implemented execution boundary and planned package boundary

PR #185 is merged at `73c428e`; optional journal lifecycle hooks now span both
visual and report transports. Capture begins before inference dispatch;
completion is durably reloaded and validated before proposal acceptance.
Duplicate begin, abort and conflicting verifier configuration fail closed.
The journal is a bounded foundation, not a complete workflow scheduler or proof
of remote capture. Managed factories remain unwired pending producer assurance.
[Exact main CI](https://github.com/Slayde91/classifire/actions/runs/33941884582)
passed 974 tests. No OpenClaw retirement or operational migration occurred.

A local, untracked Draft ProjectPackage schema/archive candidate exists in
`.tmp/project-package-draft-20260905`; 22 synthetic tests passed on review.
It is not shared-main architecture. It accepts an explicit snapshot/inventory
and authorization callback, validates the declared graph and hashes, and writes
or validates deterministic archives. A supplied inventory cannot prove database
completeness, and a callback interface cannot establish an export policy.
That candidate remains unshipped. The current Draft-specific implementation below
adds selected artifact projection, rights, immutable persistence and download; full
project coverage and source-body export remain unfinished; the import amendment
below implements selected-workspace exchange.

Do not reuse `services/snapshot.py:build_estimate_snapshot` as a read-only package
extractor: it calls `recalculate_estimate`. Future projection must preserve a
consistent authorized revision and reuse exact clean-byte evidence reads without
recalculating, changing records or bypassing canonical output gates.

## Approved capability composition and first prototype

**Accepted target; manual Scope/Estimate, candidate review and independent Draft reports have browser evidence:** one modular CLASSIFIRE application exposes
Scope, System Matching, Estimating and Reporting through independent use cases.
Each accepts explicit validated saved/manual inputs, produces a versioned artifact
and stops unless the user requests another capability. Stable IDs, evidence,
validation, storage and permissions are shared across clients.

```mermaid
flowchart TD
    UI[Existing standalone UI / CLI] --> API[Authenticated application use cases]
    CHAT[Optional MCP client; external ChatGPT linking pending] --> API
    API --> S[Scope]
    API --> T[System matching]
    API --> E[Estimating]
    API --> R[Reporting]
    S --> A[Versioned artifacts and exact dependencies]
    T --> A
    E --> A
    A --> R
    R --> O[Same snapshot: PDF and XLSX]
    A --> DB[Governed database and retained evidence storage]
    A --> P[Artifact / ProjectPackage validation and download]
    AI[Optional bounded AI proposals] -.-> S
    AI -.-> T
```

The arrows show available data paths, not automatic execution. Reporting reads
selected available artifacts; it does not call the other three capabilities.
Technical suitability and pricing remain separate, and source/library eligibility
still applies. Model output is proposed evidence, never authority.

| Component | Implemented starting point | Accepted prototype/target work |
| --- | --- | --- |
| Interfaces/API | FastAPI/Jinja Scope/import/report/candidate/Estimate routes; local PDF upload/scan/page-review routes | PDF, workbook pricing and partial measured checks are implemented. Service-size review and complete reporting are merged. Selected ProjectPackage download is merged in PR #200; selected-workspace import is implemented on the current branch; ChatGPT remains planned. |
| Optional external client | `draft_client.py`, `draft_client_auth.py`, `draft_client_requests` and shared Draft services | OAuth resource server only; client proposals require a separate same-user browser confirmation. External linking and the other capability tools remain incomplete. |
| Orchestration | Deterministic controllers and bounded inference journal; generic worker incomplete | Ordinary synchronous bounded manual commands for P0. Add durable jobs only when a selected long-running workflow needs them. |
| Domain services | Physical/evidence guards, technical governance, calculations, snapshot/renderers | Reuse rules behind independently validated capability contracts; do not duplicate business logic in UI or adapters. |
| Draft persistence | Separate Scope/report/candidate tables plus merged Estimate/report retention and DraftPdfSource and DraftPricingSource bindings; owner/admin checks, exact dependencies, hash/parent validation and conditional saves | Preserve imported-source lineage and separate retention; full archive exchange and operating limits need further work. |
| Canonical physical writes | Existing opening/service UI writes guarded canonical rows | Keep these routes and admission/lock protections intact. Draft Scope saving cannot promote data into them. |
| Packages | Scope v1/v2 exchange plus v3 page-reference claims, candidate JSON and exact manual Estimate JSON download | Current selected Draft archive projection and download reuse these readers; whole-project coverage and source-body membership remain planned; imported-origin capability wrappers are implemented below. |
| Reporting | Scope-only, estimate-only and scope-and-system Draft snapshots plus merged complete profile; paired PDF/XLSX retention; upstream edits flag stale reports. Canonical export retains its lock gates. | Add other profiles only when independently versioned inputs exist; do not use the recalculating estimate builder for rendering. |
| Security | Session/CSRF, active human permissions, Draft owner/admin access, bounded forms/JSON and safe download names | Preserve these checks on import. Existing shared project metadata means full tenant/project privacy is still unproven. |

### Implemented manual Draft Scope slice (P0)

The existing UI now creates a new project and owner-scoped manual Draft, edits
separate defects/openings/services/observations, validates, saves successive
revisions and downloads exact saved JSON. The browser demonstration included shared
links, a blank opening and unknown quantity; data and bytes survived a server restart.
See [the contract](./DRAFT_SCOPE_V1_CONTRACT.md) and [demo](./DRAFT_SCOPE_DEMO.md).

```mermaid
flowchart LR
    UI[Authenticated Draft Scope UI] --> HTTP[Bounded forms and CSRF]
    HTTP --> S[Shared draft_scope use cases]
    S --> V[Strict schema and graph validation]
    S --> DB[Draft ownership and revision tables]
    DB --> H[Hash and parent integrity checks]
    H --> D[Exact saved JSON download]
    S --> A[Metadata-only audit events]
```

`draft_scope_ui.py` adapts browser requests; `services/draft_scope.py` owns the
independently callable validation, ownership, save/read and export rules. No new
framework, agent, database or scheduler is required. Each save uses the expected
revision and a conditional update so simultaneous writers cannot silently overwrite.
The service flushes in a caller-owned transaction; failed requests roll back.

Migration `0027_draft_scope_revisions` adds two tables. Revision envelopes preserve
stable IDs, server-assigned author/time, Draft/manual/unreviewed status, parent and
content hashes. Historical bytes remain stable. Read/download validates retained
bindings; checksums are integrity checks, not signatures or approval. Downgrade
refuses destruction of retained revisions. The standalone synthetic launcher uses
separate local SQLite storage; it does not establish production migration readiness.

Draft content requires an active human with the relevant project permission and
ownership or administrator status. Existing project names/references remain visible
through shared `/projects` behavior; this is not tenant isolation. Bounded input,
CSRF, escaped rendering, safe download names and metadata-only audit, excluding scope text, preserve the exposed
boundary. Import preview/confirmation is implemented as described below. Saving or validating creates no
canonical Defect/Opening/Service, technical match, estimate, lock or release and
invokes no AI provider. Manual Confirmed is still an unreviewed assertion.

**Remaining Scope gaps:** report/source intake, verified evidence locators, richer
plane/service-instance/treatment and contradiction models, verified evidence provenance
and cross-capability dependency tracking. These are subsequent visible increments;
P0 does not claim the complete Scope Package contract or full Scope Analysis.

### Implemented Draft Scope exchange (P1a)

`preview_import` and `apply_import` extend the existing shared Draft service. The
browser uploads exact bytes as bounded base64 form data; the server validates the
version, strict envelope fields, UUID/time/hash claims, graph, normalized values and
checksum before displaying a no-write preview. Duplicate JSON keys, nonfinite
values, malformed UTF-8 and unsupported authority fields fail closed. The artifact
limit is 288 KiB and the separate encoded form limit is 1.2 MB.

Confirmation requires an explicit replacement choice plus a purpose-specific,
15-minute signed preview binding the actor, session, destination, saved revision/
hash and exact file hash. Current ownership/permissions and target integrity are
rechecked, then the existing conditional revision update arbitrates concurrent
writers. Replay or stale confirmation cannot silently create another revision.
Preview emits no audit/persistence changes; successful apply records metadata only.

Existing v1 manual revision bytes remain unchanged. Imported revisions use
`CLASSIFIRE-DRAFT-SCOPE-v2`, `provenance: imported` and up to 16 source metadata
records. Later manual edits retain that history with `provenance: manual_edit`;
reimport retains declared ancestry and appends the newly observed source identity
and file hash. All foreign identities/history remain unverified claims. Local
revision/actor/time/ownership come from the current application; status remains
Draft/unreviewed. No approval, canonical model, estimate or provider is invoked.

This evolution uses existing revision JSON storage and needs no database migration
or new dependency. Reaching the supported lineage limit is an explicit refusal,
not silent truncation. Raw source attachments and complete foreign revision history
are not stored by this narrow import; the complete ProjectPackage/evidence-retention
boundary remains separate. See the [v1/v2 contract](./DRAFT_SCOPE_V1_CONTRACT.md).

**Implemented for Draft artifacts, reports and selected packages:** pin input/release
revisions and hashes. Broader canonical package coverage remains planned.
Upstream edits mark affected downstream relationships stale without changing the
old artifact's content or approval history. The user chooses to compare or rerun.
A report snapshot captures selected revisions and freshness so PDF and XLSX agree.

**Scope of independence:** saved/manual input can replace a prior session's
execution, but cannot replace required evidence or approval. Partial Draft
artifacts/reports may be valid with explicit missing information. Structural
validity, completeness, technical authority and Human Release are separate facts.


### Implemented independent Draft Scope reporting (P4a)

`services/draft_scope_reports.py` exposes create/list/read/download/freshness use
cases independently of an Estimate, canonical physical model or provider.
`draft_scope_ui.py` provides saved-revision selection, full content preview,
explicit creation and retained PDF/XLSX links. No upstream capability runs.
See the [report contract](./DRAFT_SCOPE_REPORT_V1_CONTRACT.md).

The frozen `CLASSIFIRE-DRAFT-SCOPE-REPORT-v1` snapshot includes the entire verified
Scope v1/v2 envelope, project identity/name/reference, local actor/time, report ID,
Draft/unreviewed status, profile/render version and canonical JSON checksum.
Both renderers consume detached copies of that snapshot. One new report row retains
both output byte strings, separate byte hashes and the source revision binding.
A renderer failure saves neither report nor create audit; a later download never
regenerates the files. Each output is limited to 8 MiB in service and database.

```mermaid
flowchart LR
    UI[Select saved Scope revision in UI] --> S[Report application use case]
    S --> V[Owner, schema and source integrity checks]
    V --> F[Freeze Scope and project labels]
    F --> PDF[ReportLab PDF]
    F --> XLSX[XlsxWriter workbook]
    PDF --> DB[Atomic report snapshot and exact output pair]
    XLSX --> DB
    DB --> D[Authorized hash-checked downloads]
    DB --> ST[Compare current dependencies: stale status]
```

Forward migration `0028_draft_scope_reports` adds the report table and a composite
foreign key to the retained Draft/Scope revision. Existing migration history is
unchanged. Deployment-lineage/current-head checks advance explicitly. Generated
outputs are held within the existing database transaction; they are not uploaded
source documents and acquire no fabricated clean-scan attestation. Downgrade refuses
to destroy retained reports. Append-only service behavior and checksums do not make
the database tamper-proof; operational database administrators remain trusted.

Creation requires an active human with project write permission and Draft ownership
or administrator access. Reads require the corresponding read permission and the
same ownership boundary. Browser mutations require CSRF. Reads verify snapshot,
source and both output hashes; stale-but-valid files remain downloadable. Metadata-only
audit excludes Scope text. Later Scope revisions or project label changes flag the
report as stale without modifying its snapshot or downloads.

PDF includes complete flowing content and provenance. XLSX has typed known quantities,
explicit unknowns, stable IDs, separate many-to-many links, filters and frozen headers.
Imported claims remain unverified; missing technical/pricing sections remain unavailable.
Escaped PDF text and literal Excel strings prevent markup/formula/URL interpretation.
Unsupported PDF glyphs and unsafe control characters are visibly represented as code
points; exact original text remains in the saved Scope artifact. No new dependency.

**Bounded prototype trade-offs:** synchronous rendering, maximum 8 MiB per format,
and a newest-20 report list. Older report IDs remain valid; pagination and moving
large outputs to object storage can follow measured need. The dedicated PDF is the
print layout; wide Excel sheets are intended for filtering and horizontal navigation.
Only this Scope profile is implemented, not complete reporting or ProjectPackage export.

### Implemented saved technical-candidate review (P2a)

`draft_system_match_ui.py` is a thin FastAPI/Jinja adapter over independently callable
`services/draft_system_matches.py`. Users explicitly select a saved Scope revision,
a technical release and one opening, service or valid linked pair. Retrieval does
not create canonical Openings or an Estimate and does not invoke AI. The full saved
Scope remains context; `coverage: selected_target_only` identifies unassessed items.
An opening-only review does not imply every linked service has been assessed.

The existing `technical.search_variants` supplies text retrieval with stable ordering.
It does not test complete applicability. Missing material, size, FRL, insulation and
installation criteria remain visible; plane is not substituted for orientation.
The UI exposes captured constraints/references, not an Applicable control. Keeping
or rejecting a candidate is an unapproved preference, not library approval.

```mermaid
flowchart LR
    UI[Select Scope, release and explicit target] --> S[Shared candidate-review use cases]
    S --> V[Owner, technical permission, release and source checks]
    V --> T[Bounded deterministic text retrieval]
    T --> F[Freeze Scope, candidates, references and missing criteria]
    F --> DB[Draft match and append-only review revisions]
    DB --> R[Inspect, keep or reject with notes]
    R --> DB
    DB --> D[Exact saved JSON download]
    DB --> ST[Check current dependencies; display stale reasons]
```

The [v1 candidate contract](./DRAFT_SYSTEM_MATCH_V1_CONTRACT.md) stores the complete
Scope envelope, release ID/hash, explicit target, allowlisted technical fields,
source locators/bindings, retrieval findings and decisions. It omits raw source JSON,
storage paths, source bytes and arbitrary metadata. New retrieval validates release
membership, published fields, dates and source integrity. Legacy unbound records
remain unresolved. Source verification means retained-byte integrity, not a malware
scan or technical applicability decision.

Forward migration `0029_draft_system_matches` adds a parent and revision table after
0028. Review saves use expected-revision comparison and append rather than overwrite;
only decisions, author/time and revision lineage change. Downgrade refuses retained
data loss. All operations require an active persisted human, Draft owner/admin access
and technical read permission; writes additionally require project write and browser
CSRF. Metadata-only audit excludes source/Scope text and review notes.

Reads validate retained envelope/hash/chain and its local Scope binding separately
from live source eligibility. Changed Scope, library, candidate or source dependencies
produce stale reasons while preserving earlier unapproved metadata downloads. Users
may annotate an old basis; this neither refreshes it nor removes staleness. A newer
review revision blocks a stale save. Rerunning retrieval creates a separate artifact.

Bounded synchronous limits: 20 candidates, 1 MiB artifact, 64 MiB aggregate deduplicated
source reads and newest 20 saved reviews. PostgreSQL uses existing locked clean-byte
reads; SQLite supports the isolated demonstration without proving quarantine
serialization. Technical source links open current metadata, not a source-file viewer.
Complete applicability (P2b), full System Match import/export and general source intake
remain unfinished. No new framework, provider, database or scheduling dependency.

### Implemented: independent manual Draft Estimate (P3a)

This slice implements the separate estimating capability under ADR 0002. It uses
an exact saved Scope v1/v2 revision and optionally the complete saved candidate
review envelope for that same Scope. Matching and pricing-library publication are
not prerequisites. An attachment remains unapproved context; it never selects a
technical system or rate. Browser/restart and local verification passed; PR #192 is merged with successful main CI.

`draft_estimate_ui.py` adapts shared `services/draft_estimates.py` commands. Its
picker creates empty revision 1; users select one target, add a work line, change
quantity/rate with a reason, omit or restore a retained line, view history and
download exact JSON. The UI contains no parallel arithmetic or persistence logic.
The [v1 contract](./DRAFT_ESTIMATE_V1_CONTRACT.md) defines strict commands and the
`CLASSIFIRE-DRAFT-ESTIMATE-v1` envelope in `draft_estimate_contract.py`.

```mermaid
flowchart LR
    UI[Select saved Scope and optional review] --> CMD[Shared manual Estimate commands]
    CMD --> CHECK[Permissions, exact inputs, units and recovery identity]
    CHECK --> CALC[Decimal quantity times manual unit sell rate]
    CALC --> REV[Draft parent and retained revisions]
    REV --> EDIT[Inspect, override, omit or restore]
    EDIT --> CMD
    REV --> JSON[Exact saved JSON download]
    REV --> STALE[Compare dependencies without recalculating history]
```

**Bounded arithmetic and work:** rates are explicit user-defined unit sell prices
in AUD. Tax is excluded and not calculated. Quantities and rates accept bounded
nonnegative decimal strings with at most six decimal places; `each` quantities
must be whole numbers. Service units are fixed to the Scope (`each`, `m`, `mm`).
A blank opening accepts manual `each` or `m2` with a quantity reason. No conversion,
geometry-derived quantity, default rate, markup, waste or labour inference runs.
Each quantity times rate is rounded half up to cents using the existing `money`
helper; those rounded line amounts are summed. Thus 3 x 0.333333 produces 1.00,
and 1000 mm x 0.001234 produces 1.23. Missing quantity/rate yields no line amount;
explicit zero remains zero. Summary always declares a partial, unapproved subtotal.

A server-derived recovery key permits one service-specific line across all that
service's opening links, excluding shared-opening work, or one blank-opening
closure line. A duplicate target is refused even if its line is omitted; restoration
returns the same line. Nonblank-opening work, unrepresented targets, unpriced lines
and omitted work remain visible. This is not the complete recovery ledger.
Original Scope quantity, first entered rate, fixed target/unit/work basis and
original description/source note remain retained. Later changes add local actor,
UTC time, before/after values and a reason; they do not overwrite earlier events.

**Persistence and authority:** forward migration `0030_draft_estimates` adds
`DraftEstimate` and `DraftEstimateRevision` tables, unique revision identities and
foreign keys to exact Scope and optional review revisions. It preserves previous
migrations and refuses destructive downgrade. The shared Draft atomic wrapper,
expected-revision/hash comparison and metadata-only audit support caller-owned
transactions. All reads verify retained content, recomputed amounts, parent chain
and dependencies; download returns canonical retained bytes with a safe ID-based
name, `no-store` and `nosniff`. Current Scope/review/source changes flag staleness
without recalculating prior totals or replacing attachments.

Every operation requires an active persisted human, `project:read`, `estimate:read`
and Draft owner/admin access. Mutations additionally require `project:write` and
`estimate:write`; downloads require `estimate:export`. An attached review requires
`technical:read` on reads, edits and downloads, including history. Lists exclude
attached artifacts when that permission is absent. Browser mutations require CSRF;
services independently enforce object and role checks and recheck authority around
writes and attached-source freshness checks.

**Consequences and limits:** 100 retained lines, 100 events per line, 2 MiB JSON,
64 KiB form bodies and newest 20 accessible estimates keep this synchronous slice
bounded. No new dependency or infrastructure was added. `D(None)` and canonical
`calculate_line` are not used for this contract because they respectively collapse
unknowns and round unit rates before multiplication. Existing canonical Estimate
creation, locked line writers, recalculation, snapshots and human-release gates
are unchanged. P3b default/inferred methods and broader source coverage, full recovery, taxes,
Historical checkpoint: Estimate import and the additional PDF/XLSX profiles were
planned here; the later reporting and imported-origin amendments supersede this status.

The supplied original UI PNG is served at `static/brand/classifire-logo.png`
(SHA-256 `fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`).
Shared UI CSS frames its original pixels on white; the report master/logo remains
unchanged. Sign-in, sidebar and Estimate browser screenshots were inspected with
this exact logo during the successful local P3a workflow.

## 1. Governing reasoning chain

CLASSIFIRE preserves this order:

```text
Project Evidence
-> Defects
-> Services and Assets
-> Openings
-> Substrate Planes
-> Physical Model
-> Repair Components
-> Technical System Search
-> Compatibility Validation
-> Commercial Applicability
-> Quantity and Labour
-> Reconciliation
-> Estimate, Scope, and Close-out
-> Human Release
```

This chain governs defensibility and authority; it does not require every user
to run every capability in one session. Validated saved/manual inputs may enter
at a capability boundary, with unresolved facts and approvals explicit.

Physical reality comes before technical selection or pricing. A report label,
Defect, photograph, Opening, Service, Opening-Service link, repair component,
and commercial line are different records. One Defect does not imply one
Opening, one Service, or quantity one.

An assumption-led desk quote is a deliberately parallel proposal-only
commercial scenario. It may support early budgeting from bounded evidence and
assumptions, but it does not enter or bypass the canonical chain above.

## 2. Authority and sources of truth

The governed CLASSIFIRE database and content-addressed retained-file storage are
live canonical project state for an application instance. The planned versioned
`ProjectPackage` schema is the canonical interoperability contract; each valid
export is an immutable, hash-bound snapshot of one governed project version,
with independent Scope/System Match/Estimate artifacts and explicit partial
project exports supported in the target. Every import remains untrusted until quarantine, integrity, schema,
lineage, conflict, permission, and authority checks pass. The existing
`ProposalReviewPackage` is a narrower proposal-only review artifact, not that
complete portable project contract. OpenClaw sessions, Mission Control tasks,
prompts, model outputs, chat history, desk quotes, and temporary receipts remain
evidence or proposals, not live canonical truth.

Authority remains separate for:

1. evidence retention and review;
2. proposal-only inference;
3. human evidence adjudication;
4. canonical Physical Model submission;
5. Physical Model Lock creation;
6. technical-source and TechnicalVariant approval;
7. technical-release publication;
8. commercial approval;
9. deployment; and
10. Human Release.

Approval for one operation never grants a later authority.

### Repository tiers

| Tier | Meaning |
| --- | --- |
| **Shared main** | Reviewed source on the current GitHub `main` lineage. |
| **Isolated branch/worktree** | Candidate work based on current main; not shared implementation until reviewed and merged. |
| **Quarantined legacy root** | Historical and unfinished evidence in the conflicted `C:\CLASSIFIRE` checkout; never a bulk publication or deployment source. |
| **Local runtime evidence** | Receipts and disposable artifacts proving a particular bounded operation; never canonical state or source publication. |

## 3. Implemented application composition

| Layer | Current implementation | Main boundary |
| --- | --- | --- |
| Application | FastAPI, CLI, development HTML UI, worker shell, and audit services | Pre-production; not every merged service has an operator/UI flow |
| Persistence | SQLAlchemy with packaged Alembic migrations | Shared baseline is 0036_draft_client_requests; the current branch adds 0037_draft_client_capabilities without rewriting history |
| Evidence storage | Content-addressed `StoredFile`, Project/Estimate ownership, immutable metadata, verified reads, quarantine | Exact production use requires PostgreSQL transaction semantics |
| Physical model | Defect, EvidenceSource, Opening, Service, `ServiceOpeningLink`, locks, admissions, submission receipts, governed reopen/amendment execution, and atomic signed replacement-lock execution | Historical UAT records report no accepted replacement lock; live state was not rechecked; code capability does not authorise operation on real project data |
| Proposal-only inference | Blind inventory, Physical proposal, Validator, bounded correction, receipts | No canonical-write or lock capability |
| Report assessment | Shared components, expected-label admission, an approval-bound proposal-review controller, proposal-only single/family runners, retained single-report/family package lifecycle, and administrator-only immutable human-review annotations | The family runner validates every exact family member's approved source and V2 scope before it creates any injected no-tool port, then preserves separate member packages; no CLI, API, or UI invokes either runner and no real-provider run exists |
| Technical governance | Document review, clean source-byte checks, source-bound Draft materialisation/variants/revisions, hash-bound Draft source-document predecessor lineage, source locators, independent activation, pinned active releases, atomic governed publication, and read-only lineage | Extraction-assisted and manufacturer-neutral lineage plus production technical authority remain incomplete |
| Estimating/output | Canonical calculation/outputs/desk quotes plus local independent manual Draft Estimate contract, history, partial totals and JSON | All four independent Draft report profiles exist; full pricing, technical-to-component recovery and production release remain incomplete |
| Orchestration | OpenClaw boundary and Mission Control client/bootstrap | Transitional current implementation. The accepted target is a small CLASSIFIRE-owned deterministic job/run coordinator with bounded optional AI adapters; journal/lifecycle foundations are implemented, but full migration remains incomplete and OpenClaw stays until parity gates pass. Neither control plane owns canonical estimate state. |

Production startup validates configuration before storage work, never runs
`create_all()` or seeds a default administrator in production, and requires the
configured database to match the packaged migration head. Development retains
convenient schema creation/seeding. This is narrow hardening, not deployment
proof.

### Verified execution boundary and worker debt

Controllers determine stage order and correction bounds through injected
inference ports. Separate Physical/Validator contexts do not prove a deployed
autonomous fleet. OpenClaw transport lives under services; that placement does
not make it a provider-neutral domain layer.

BackgroundJob and worker.run_once() are existing extension points. The worker
claims a queued job with a row lock, marks it running, then fails it because no
handlers are registered. Its selector does not honour run_after. Durable stages,
lease expiry, cancellation and crash recovery remain gaps. Record them now;
PR #184's journal reuses this table in distinct non-queued states;
the generic worker still has no registered handlers.

The controlled-write plugin defaults to phase8-admission-only. Broader catalog
entries and Mission Control bootstrap code do not prove working API routes,
deployed tools or an operational fleet. Inventory callers/profiles/tests before
deciding what the replacement must preserve.

## 4. Domain model

The current physical graph is:

```text
Project
  -> Estimate
       -> Defect
            -> EvidenceSource
            -> one or more Openings
                 -> zero Services for an explicit blank opening/core hole
                 -> one or more Services through ServiceOpeningLink records
```

An Opening is the aperture or bounded penetration condition. A Service is a
physical item passing through it. Placeholder Services are prohibited.

### Pre-technical physical amendments

**Current architecture:** an active Physical Model Lock blocks evidence and
physical mutations. **Change:** the generic API now allows an `estimate:write`
human to reopen an active *unsigned* pre-technical lock with a nonblank reason.
**Reason:** a human-reviewed physical correction needs a governed way to proceed
without discarding retained evidence or topology. **Consequences:** reopening
invalidates the old lock, records the actor, reason, prior lock hashes, current
physical hash, and row counts in the existing audit record, then preserves every
Defect, EvidenceSource, Opening, Service, and link for amendment. It fails closed
when technical selection, estimate lines, rule evaluations, snapshots, approval,
or any signed lock is present. **Migration impact:** none; it uses the existing
lock invalidation and audit fields.

### Signed-lock amendment eligibility

**Current architecture:** a no-write P-256 verifier and transaction-ready
preflight bind an active signed lock, its current physical hash, a prospective
canonical payload, and an exact semantically approved visual-validation receipt.
**Change:** a separately additive immutable admission journal now records a
fresh verified manifest, canonical prospective payload, preflight receipt, and
attributed human-governance audit event. **Reason:** retain exact approval
lineage without letting a generic API, a receipt, or the journal itself become
lock-execution authority. **Consequences:** registration refuses unsigned,
stale, altered, expired, mismatched, visually withheld, conflicting-replay, or
corrupt retained candidates. Exact replays recheck every stored binding before
returning the existing admission. A separate no-write registered-admission preflight reloads the exact journal
record and reruns the locked signed preflight. The permission-gated execution
service consumes only that exact registered payload in the same caller-owned
transaction. It reconciles Openings, Services, and ServiceOpeningLinks, preserves
or records their logical row identities, invalidates only the signed target lock,
and retains exact canonical before/after payloads, hashes, an identity map, an
execution receipt, and an attributed audit event. Exact completed replays return
the intact retained outcome; corrupt outcomes fail closed. Any write or audit
failure rolls back the topology, invalidation, outcome, and audit together. A
disposable PostgreSQL two-session race test holds the first execution
uncommitted, proves the second session blocks, and then requires both callers to
resolve to the same single outcome and audit event.
Execution rejects a no-op and rechecks later technical, commercial, rule,
snapshot, or release dependencies. It creates no replacement lock and grants no
technical, commercial, snapshot, release, or other downstream authority. Lock
decimals remain semantically normalised before hashing so an unchanged model is
not made stale by database display scale. **Migration impact:** forward-only
migration `0022_signed_physical_model_lock_amendment_admissions` adds the journal;
`0023_signed_physical_model_lock_amendment_outcomes` adds the immutable execution
outcome. Neither alters the initial-submission admission table.

A separate signed replacement-lock contract now binds one short-lived P-256
approval to the exact immutable amendment outcome, invalidated signed-lock hash,
approved visual receipt, and unchanged amended physical-model hash. Its
transaction-ready preflight locks the Estimate and every current physical row,
rechecks scope-aware physical completeness, editable lifecycle state, and the absence of technical, commercial,
rule, snapshot, or release dependencies, then returns only a deterministic
no-write receipt. A separate human-attributed registration transaction reruns
that preflight and immutably journals the exact canonical signed envelope and
receipt. Exact replays are idempotent; conflicting or corrupted records fail
closed. A fresh separately signed approval can be registered if an earlier
short-lived approval expires unused; every record keeps a distinct exact identity.
Registration creates no Physical Model Lock and grants no downstream authority.
A separate active-human `estimate:write` transaction may consume one exact
registered admission only after rerunning its locked fresh preflight. It creates
the exact replacement Physical Model Lock over the unchanged approved snapshot,
retains the complete canonical signed envelope on that lock, and writes one
immutable outcome plus attributed audit event in the same transaction. Exact
completed replay returns the same intact outcome. Active-lock races, state drift,
corrupt replay, or a failed outcome/audit write fail closed or roll back together.
The writer performs no technical selection, pricing, deployment, or release and
grants no downstream authority. **Migration impact:** forward-only migration
`0024_signed_physical_model_lock_replacement_admissions` adds the journal;
`0025_signed_physical_model_lock_replacement_outcomes` adds the immutable
execution outcome.

The read-only lock-content snapshot API exposes the exact canonical JSON preimage
of the existing v1 lock hash. That payload includes the row identities and bound
fields for Defects, evidence, Openings, Services, and ServiceOpeningLinks. The
ordinary lock summary and persisted content hash are built through the same
snapshot path, preventing the inspection payload from silently diverging from
the lock identity. It performs no write and grants no amendment authority.

Barrier/substrate, plane, orientation, opening type and dimensions, FRL or
governed assumption, service identity/material/quantity, link provenance, and
limitations remain independently represented. Unknown or occluded facts must
not be invented to make a proposal complete.

Shared main also implements immutable admission registration and one-shot
initial physical submission. Registration is authority evidence, not a write.
Initial submission does not create a lock. A separate reviewed and signed lock
admission is required before a replacement active Physical Model Lock.

## 5. Evidence and storage architecture

### 5.1 Retained evidence

`StoredFile` retains immutable file metadata and content identity.
`ProjectEvidence` gives each binding exactly one direct owner: either a Project
or an Estimate, never both. Every Estimate is itself owned by a Project.
`EvidenceSource` binds a supported claim or observation to the estimate and
retained source.

For security-sensitive consumption, the PostgreSQL path locks every row sharing
the same SHA-256, requires every shared row to remain clean, opens the exact
retained path without following unsafe substitutions, verifies size and hash,
and holds the transaction through consumption. A malware verdict uses the same
row set and quarantines all matching-byte rows. Binding mismatches cannot roll
back confirmed shared-byte quarantine.

Metadata-only checks are not equivalent to this atomic clean-byte contract.

### 5.2 Report normalisation

The merged report adapter supports bounded PDF, XLSX, and DOCX normalisation:

- report/page metadata hashes;
- text blocks;
- strict explicitly numbered caption text blocks, with a fixed categorical caption
  kind and no raw caption text in the locator;
- tables;
- annotations;
- drawing locators/hashes;
- embedded-image locators/hashes;
- visible XLSX worksheet shape locators with no worksheet names;
- non-empty XLSX cell position/category/hash locators with no cell values;
- structural DOCX document locators, visible body paragraph locators, and simple body table locators, all with no document text or table values; and
- stable report/page/item identities and ordered Defect scopes.

Text, table, annotation, strict caption, selected XLSX cell, and selected DOCX paragraph/table items can provide
transient documentary content. Drawing, embedded-image, and XLSX worksheet items are
locator/hash evidence without raw documentary content. XLSX formula text is never
executed. The XLSX boundary rejects hidden sheets, macros, external links,
drawings/media/charts, comments, pivots, embedded objects, validation rules, and unsafe
archive or worksheet shapes. The DOCX boundary rejects encrypted or unsafe archives, macros, external relationships, embedded or hidden content, tracked changes, fields, hyperlinks, drawings, and unsupported body structures. Actual visual inference bytes come from a separately
governed retained visual packet. A caption is only an exact retained text block with an
explicit numbered category; it is not automatically associated with an image and cannot
establish a physical fact. General report formats remain planned. Explicit human-approved family admission, deterministic proposal-review aggregation, and service-only family execution are available. The family runner preflights every ordered member's exact retained source and V2 approved scope before it creates any no-tool port, then preserves separate inputs and packages; family records retain their approved member identities through the existing controlled-UAT reviewer lifecycle.

On shared main, cardinality is deterministic for the report scopes that already exist in the
database. An approved expected-label manifest record is source-bound to the
report bytes and estimate for runner completeness. New report scopes are admitted
only as one complete, exact label set matching that approval record, and every new
scope retains its approval-record ID. Bound packets emit V2 approval details.
Historical unbound scope packets remain verifiable as V1, but both the proposal
runner and the database-backed proposal-review controller reject them rather than
treating them as approved coverage or using them to assemble a new package.

### 5.3 Linked originals and visual evidence

Linked-original retrieval is limited by approved host/address/TLS/redirect,
path/query, MIME, byte, pixel, and runtime policies. A higher-resolution image
is retained only after binding to the report-provided parent. Lower-resolution
page context, annotations, crops, and alternate views remain relevant when they
contain different evidence.

Photograph count never becomes Opening, Service, or quantity count.

## 6. Proposal-only assessment architecture

The visual controller executes:

```text
Blind Validator inventory
-> Physical proposal
-> Conditioned Validator review
-> Optional bounded correction
-> Approved, Blocked, or Failed receipt
```

The blind inventory cannot see a Physical proposal or human answer. The Physical
role cannot see the blind inventory. Human-reference material is validation-only
and remains hidden from inference.

Schemas enforce separate Openings and Services, links, blank-opening semantics,
unique candidate IDs, uncertainty, evidence references, issue codes, and blind
reconciliation. Correction authority is field-specific. A quantity issue cannot
authorise an unrelated topology, substrate, material, or relationship change.

The report-specific services add:

```text
Owned clean report bytes
-> stable report locators and Defect scopes
-> transient documentary context + governed visual packet
-> v2 property assessment
-> proposal/Validator receipt
-> deterministic JSON + inert Markdown review
-> completion receipt over preceding artifacts
```

`execute_phase8_report_assessment_runner()` composes this sequence as a
proposal-only application service. It is not an operator surface: callers must
provide the transaction and no-tool port. The shared proposal-review lifecycle provides a scoped internal reviewer UI for registered package metadata, with explicit reader grants and administrator-only immutable review annotations. It does not wire that UI, an API, or a CLI to execute the runner. No real-provider run is implemented or authorised.

### Latest documented operational evidence

The following is retained historical evidence; the receipt and UAT database
were not reopened during the 2026-09-05 documentation reconciliation.

The authorised 2026-09-01 proposal-only attempt started inference and failed at
the first blind-inventory call. It safely returned
`VISUAL_PROPOSAL_FAILED`, did not compare a human reference, remained rollback-
only, exposed no write/lock capability, and performed no database write,
canonical submission, or lock creation.

`Phase8OpenResponsesTransportError` owns a stable code intended to exclude
secrets and response content. Historical receipts recorded only the exception
class under `INFERENCE_PORT_FAILED`, so they cannot identify the actual safe
transport reason. New proposal-only receipts retain only codes from the explicit
validated safe-code set; arbitrary exception text remains excluded.

## 7. Human review and canonicalisation

Human evidence review is a post-inference provenance record. It must bind exact
review/proposal lineage, account for every requested item, preserve unresolved
outcomes, and remain invisible to runtime inference. It is not a visual approval
receipt, canonical submission, lock, technical selection, price, or release.

The durable `VisualValidationReceipt` registry hash-binds the reviewed candidate,
controller receipt, evidence manifest, family/review records, policy versions,
and decision. Its verifier is a no-write eligibility check for a future lock
candidate. It neither writes a Physical Model nor creates lock authority.

Canonical submission, semantic acceptance, and Physical Model Lock remain
separate operations. The current estimate has no accepted replacement lock, so
downstream canonical technical and release phases remain blocked.

## 8. Technical authority

Technical selection must use authorised evidence and an immutable active
technical release; commercial pricing cannot prove compatibility.

Current shared-main safeguards include:

- independent technical-document submission and decision;
- clean, immutable, unchanged source-byte checks; an approved, unexpired source
  document with clean immutable `technical_evidence` metadata at bound-variant
  activation, search, snapshot, and pinned runtime use; and current
  technical-variant effective/expiry windows at
  activation, search, snapshot, and pinned runtime use;
- a retained source document on every Draft variant and preserved exact binding
  through a Draft revision;
- a nonblank source locator before technical review, clean hash-verified bytes
  before candidate extraction and Draft-only metadata refresh, and content-safe
  extraction failure diagnostics;
- independent TechnicalVariant activation from `in_review`;
- Draft-only new technical-library imports regardless of source-declared state;
- a new Draft technical document may record a hash-bound historical predecessor only when that predecessor is independently approved and its retained source bytes remain clean and unchanged; this does not approve the Draft, retire the predecessor, activate a variant, or create a release;
- runtime use only through an active immutable pinned technical release;
- technical publication only by an active `technical:approve` human; it locks
  the current active candidates, rejects any ineligible or duplicate logical
  variant instead of silently omitting it, rechecks exact bound source bytes,
  and atomically supersedes the prior active release while creating the new
  immutable manifest and audit event. Migration
  `0026_single_active_technical_release` adds a technical-only partial unique
  index so concurrent publication cannot leave two active technical releases;
- each newly published technical manifest fixes a safe source state: bound
  document/file identity, digest, and locator, or an explicit legacy-unbound
  state; pinned runtime rejects a later source-hash or source-binding mismatch; and
- rejection when any manifest TechnicalVariant is missing, inactive, or no
  longer current because its bound source is missing/ineligible or its own date
  window has expired; and
- the same eligibility check before refreshing an editable estimate's pins; and
- read-only current-authority displays on TechnicalVariant and TechnicalDocument
  detail screens, structured immutable source-lineage rows on TechnicalRelease
  detail screens, and each TechnicalVariant revision's existing retained document
  plus cited document/page/table/figure locator. An eligible bound record safely
  links to the existing current read-only TechnicalDocument record without
  changing its published binding. Those displays reuse metadata or existing
  persisted locator values only: they do not read source bytes or grant approval,
  activation, publication, or release authority.

Extraction-assisted and manufacturer-neutral source lineage, clean-machine
recovery, and production technical authority are not complete. Unsupported
compatibility remains unresolved.

## 9. Quantity, commercial recovery, snapshots, and outputs

The target canonical path is:

```text
Locked Physical Model
-> supported technical strategy
-> required repair components
-> deterministic quantities and labour
-> one commercial recovery per component
-> independent validation
-> reproducible immutable snapshot
-> rendered output
-> Human Release
```

Shared main has basic calculation, releases, estimate lines, PDF/XLSX rendering,
and snapshots. The merged P3a slice adds independent manual unit-sell Draft arithmetic
and exact revision downloads, as described above, without invoking this canonical
chain. It does not yet implement the complete system-derived component,
productivity, and rate-inclusion/recovery ledger. Estimate snapshot V2 keeps
`generated_utc` for audit display but excludes it from `snapshot_hash`; a
separate `snapshot_document_hash` still binds every displayed field, including
that timestamp. The output boundary accepts legacy V1 full-payload hashes and
fails closed for invalid V1/V2 or unsupported packets. This establishes snapshot
integrity foundations only; it does not prove the independent Phase 12 inputs or
Human Release.

### Desk-quote exception boundary

PR #75 added strict assumption-led desk-quote payloads, active pricing-release
bindings, tamper-checked receipt rendering, client qualifications, PDF/XLSX
outputs, and audit events. A desk quote cannot claim an observed site condition,
technical system, canonical model, lock, approved estimate, or release.

The current implementation requires an explicit Project and Estimate reference,
accepts only ProjectEvidence-owned, immutable `project_evidence` with a `clean`
scan state, and reads every retained source through the atomic PostgreSQL
clean-byte reader. It rejects missing, changed, outside-root, link/reparse,
quarantined, wrong-purpose, and cross-estimate evidence. A caller locator must
match a persisted EvidenceSource page/region value or ReportEvidenceLocator.

Both new and cached exports are atomically read and hash-checked before their
bytes are returned. The audit binds the artifact hash and size. An evidence or
cache mismatch fails before an output or audit event; the proposal-only endpoint
still cannot create canonical state, a lock, a technical decision, or a release.
Synthetic SQLite and PostgreSQL race tests cover this boundary. PR #103 review
and CI passed; operational approval remains necessary before use.

Desk quotes also do not complete the canonical rate-inclusion/recovery ledger
and do not mark Phase 11 or Phase 13 complete.

## 10. Hybrid orchestration, OpenClaw, Mission Control, and human authority

[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md)
accepts a hybrid target: deterministic CLASSIFIRE commands own durable workflow,
state, validation, packages, and authority-bearing transitions, while bounded
stateless AI calls are optional for evidence interpretation or independent
challenge where their benefit is measured. A persistent autonomous agent fleet
is not a required product foundation.

This is an accepted target with partial journal/lifecycle foundations, not a completed migration. OpenClaw remains the
current controlled execution adapter until CLASSIFIRE-owned replacements prove
equivalent no-tool isolation, context separation, input and version binding,
safe receipts, recovery, observability, and rollback. Removing or bypassing it
before those parity gates pass is not authorised by the decision.

OpenClaw provides controlled sessions, model routing, workspace/tool policy,
and audit evidence. Proposal roles must have empty effective tool inventories
and cannot submit canonical data, create a lock, approve technical/commercial
decisions, or release an estimate.

Mission Control is an operational task and visibility plane. It may mirror links
and summaries but must not become a second estimate database, technical library,
pricing authority, or release workflow.

The target ChatGPT integration and any standalone interface call the same
authenticated CLASSIFIRE application commands and queries. The governed
database and content-addressed storage remain live canonical state. A planned
`ProjectPackage` is a versioned interchange contract and immutable export; it
does not replace live canonical state or activate imported approvals, locks, or
release authority.

Competent humans own source approval, material evidence exceptions, technical
and commercial approvals where required, canonical/lock authorities, deployment,
and final Human Release. Decisions bind exact governed records, hashes, and
reasons.

## 11. Status vocabularies

Several bounded contracts intentionally use different vocabularies:

| Context | Terms |
| --- | --- |
| General governed evidence | Confirmed, Inferred, Provisional, Unresolved |
| Phase 8 v2 property assessment | Confirmed, Approximate, Inferred, Unknown |
| Desk-quote assumption | inferred, provisional, assumed, unresolved |

These terms are not interchangeable. No automatic translation may upgrade a
desk assumption or model estimate into a confirmed canonical fact.

## 12. Current architectural gaps and follow-up

### Accepted hybrid target (migration incomplete)

The hybrid decision merged in PR #175 at 9c0fc7d, with executable code
unchanged from the PR #174 baseline.
PR #177 completed the initial inventory and 13 synthetic contract cases.
PR #179 merged uncertain-creation refusal. Characterisation remains incomplete.
PR #180 merged deadline enforcement; PR #181 merged refusal of explicitly
incomplete/oversized audit pages. Stock pinned audit persistence is asynchronous
and can lose/disable new records without signaling this through audit.list.
A trusted completion/coverage evidence contract is therefore required before
claiming complete protection; legacy empty-list receipts remain observation-only.
This is a verified migration gap, not a new guarantee or permission to remove guards.
Complete remaining contract gates before production replacement wiring; extend the
existing journal/BackgroundJob boundary instead of inventing parallel run state.
Selected ProjectPackage exchange and the first optional MCP Draft adapter are
implemented as described in later amendments. Full project coverage, real ChatGPT
linking, production standalone packaging and OpenClaw retirement remain incomplete. No part
of this documentation decision grants canonical, technical, commercial, lock,
deployment, provider-run, or Human Release authority.

### Unresolved decisions, migrations and technical debt

**Implemented consumer (PR #183) and lifecycle integration (PR #185):** the completion-evidence boundary adds
a required application-injected verifier to both transports and binds validated
evidence into version-2 transport digests. Its context includes request/response
bytes, session, agent, audit and attestation receipts, and invocation times.
Missing evidence blocks inference dispatch; malformed, mismatched or incomplete
evidence blocks proposal acceptance. Independent no-tool checks remain.

**Reason and consequences:** shared-main audit pages cannot establish durable
completion. The consumer closes acceptance without pretending the missing
producer exists, but managed inference becomes unavailable until a trusted
producer/verifier is implemented and wired. Synthetic tests prove this availability
impact; no real provider was exercised. Typed callback data alone is not authentication.

**Migration and unresolved decisions:** verify historical version-1 receipts
separately from version-2 acceptance; never relabel old observations as complete
capture. The consumer adds no database migration or provider removal. Prove
producer identity, persistence ordering, capture health/loss detection, retention,
clock assumptions and crash/replay recovery before production wiring. The
[completion contract](./EXECUTION_COMPLETION_CONTRACT.md) records this boundary.

| Decision/gap | Constraint and next evidence |
| --- | --- |
| Durable execution | PR #184 journal is merged. PR #185 begin/complete/abort lifecycle integrates both transports without recursion; existing execute remains compatible. Generic coordination and real cancellation remain incomplete. No migration. |
| Inference replacement | Preserve ports, context isolation, evidence/version binding and receipts. Provider/endpoint, privacy, egress, retention/residency and secret policy need validation. |
| ProjectPackage v1 | Define project/estimate membership, rights/redaction, profiles, schema compatibility and signature trust. Database/storage remain live truth; imports never activate foreign authority. |
| Package integrity | Separate semantic and byte hashes; deterministic manifest entries, external final archive hash. Prove blank-instance import before existing-project conflict handling. |
| Interfaces/tenancy | MCP/standalone share application commands; prove identity mapping, tenant/project isolation and human review. Scoped reviewer grants are not full tenancy proof. |
| Offline use | Local backend/database and safe revision exchange need a separate decision. Do not assume SQLite reproduces PostgreSQL locking or permit automatic bidirectional merges. |
| Operations/cost | Clean-machine setup, backup/restore, safe traces, monitoring, rollback and accepted-result cost/latency remain unmeasured. Changing frameworks alone does not prove savings. |

**Migration impact:** P0 adds the Draft revision tables and minimal manual contract.
P1a adds explicit v2 import provenance in existing revision storage without reinterpreting v1 authority.
P4a adds a retained scope-only snapshot and exact PDF/XLSX pair in migration 0028.
P2a adds candidate-review revisions and explicit Scope/library dependencies in migration 0029.
P3a adds manual Draft Estimate parent/revisions and exact Scope/optional review foreign keys in migration 0030 (merged PR #192). P4b adds retained estimate-report snapshots and paired bytes in forward migration 0031; no historical migration is changed.
Capability/package/client increments follow the roadmap independently of the
replacement track. That track adds required run/adapter behavior and retires
OpenClaw only after Decision 0001 parity gates. Preserve historical migrations and receipt readers,
signed admissions and human authority. Do not create a general agent platform
or duplicate business rules in MCP/UI.

**Historical verification:** PR #175 was documentation-only; its 70 focused
contract/security tests and main CI 33899855871 describe that older baseline.
At that historical checkpoint, shared main was `24ee6e3`, including P3a through
PR #192, with main CI
33968038437 (1,286 tests, 141 warnings). P4b local verification includes 233 combined
regression passes, 17 report-HTTP/migration/readiness passes and 15 historical
migration/preflight checks. Browser creation, later edits and actual restart retained
identical PDF/XLSX bytes. See PROJECT_STATE.md for precise evidence and limitations.
None proves production or full recovery parity.

### Completed report-governance integration

PR #104 merged the expected-label manifest, atomic scope admission, V2 runner
preflight, migration-head readiness, and `main` push validation into
`b6409a5`. Pull-request validation passed on `0f6c252`, and the first observed
`main` validation passed on the merge commit (`33516292114`), including tests
and the one-head Alembic check. These are implementation and CI facts only: the
services remain proposal-only and no operator/UI surface or downstream authority
was added.

GitHub protection configuration is still unavailable to inspect on the current
private-repository plan. The standard merge and hosted validation were accepted;
that does not prove a configured required-review or required-check rule.

PRs #105-#118 then merged documentation reconciliation, semantic snapshot
identity, retained-source safeguards, source-bound Draft materialisation, and
contained type-safety hardening through `14ed594`. PR #119 reconciled the
preceding factual records; PR #120 moved PDF timestamps to an aware UTC clock;
PRs #121-#122 applied current CLASSIFIRE display branding; PR #123 reconciled
factual records; PR #124 added full hosted Mypy validation; PR #125 established
full hosted Ruff validation; and PR #126 added full hosted Bandit validation
and explicit Phase 8 fail-closed invariant errors. Their pull-request checks
and corresponding `main` validation runs passed; the latest post-merge run is
`33667477950` on `b33246a`. The technical changes require
retained source identity and locator, preserve exact Draft/revision source
binding, and derive candidate metadata only from clean hash-verified bytes with
content-safe extraction diagnostics. PR #113 makes admission rejection helpers explicitly
non-returning without altering their fail-closed safe-code behaviour. PR #114
makes rule and UI response types explicit, rejects non-text rule operators
deterministically, and proves existing library-page rendering. PR #116 preserves
release-administration guards while making their type boundaries explicit; PR
#117 clarifies XLSX row handling; and PR #118 rejects non-object task responses
from Mission Control. These safeguards do not approve a system, publish a
release, price work, create a lock, deploy, or release an estimate.

PRs #127-#142 then added verified-byte extraction, Draft refresh and
current-authority safeguards, reviewer visibility, immutable published source
lineage, factual reconciliations, and read-only source-document/locator
visibility for every TechnicalVariant revision. PR #142 validated successfully
on `cdf4236` (run `33695410954`) and after merge into `main` as `abe8bde`
(run `33695636744`). Those validations prove source/test/static/migration checks,
not technical, commercial, canonical, lock, deployment, or release authority.

### Proposal-review lifecycle and scoped-reader access on shared main

The adopted lifecycle policy names CLASSIFIRE as records owner and sets a five-year retention period from registration; an active legal hold prevents deletion beyond that period. PR #144 merged the narrow metadata and separate immutable-redaction records. PR #145 merged auditable active/revoked reader grants for one Project or one exact retained package. They retain only hash-bound identifiers, safe locators, safe outcome states, uncertainty, and receipt/source/approval bindings - never report bytes, image bytes, prompts, provider output, filesystem paths, signed URLs, credentials, or tokens.

Administrators can register a record, create a redaction, place or remove a legal hold, delete an expired non-held record, and manage reader grants. A non-administrator needs both the existing human read permission and an active matching grant before listing or reading a package. Every read verifies hashes and relational bindings; a mismatch is refused and produces a content-safe tamper audit event.

PR #145 passed pull-request run 33741309950 and post-merge main run 33741595397. The lifecycle does not execute the report runner or add canonical, technical, commercial, lock, deployment, or release authority.

### Approval-bound proposal-review assembly on shared main (PR #149)

The database-backed `assemble_phase8_report_review_package()` controller now
requires the exact human-approved expected-label manifest. Before it creates an
in-memory package, every selected packet must be V2 and retain the same manifest
ID, deterministic hash, and approval reference. Legacy/unbound packets and
packets tied to a different approval are refused before package assembly.
Historical V1 packet verification is retained without rewriting old records.

PR #149 passed pull-request validation run 33749820103 and post-merge main run
33750096567. The controller still cannot retrieve report bytes, invoke a
provider, materialise files, write canonical state, create a lock, or release
anything.

### Strict source-bound report captions on shared main (PR #151)

The PDF normaliser accepts only an explicit, bounded numbered caption prefix and
stores its category, position, size, sequence, and content hash—not its raw
wording. Before selected caption wording is exposed in transient documentary
context, the system normalises the exact verified PDF again and requires the
same locator and hash. Ambiguous prose, unknown categories, and locator fields
that attempt to persist raw caption wording fail closed. This is no image link,
no visual interpretation, and no physical, technical, commercial, canonical,
lock, deployment, or release authority. PR #151 pull-request run 33753130859
and post-merge main run 33753516838 passed.

### Source-bound XLSX report locators on shared main (PR #154)

PR #154 extends the existing exact-byte report boundary to retained `.xlsx` files.
It adds forward-only migration `0017_xlsx_report_evidence_locators`, accepts only
visible worksheet shape and non-empty cell position/category/hash locators, and
re-extracts a selected cell transiently only after exact-source verification. It stores
neither worksheet names nor cell values and never executes formulas. It adds no provider,
canonical, technical, commercial, lock, deployment, or release authority. Pull-request
run 33760112145 and post-merge main run 33760450512 passed.

### Source-bound DOCX report locators on shared main (PR #156)

PR #156 extends the existing exact-byte report boundary to retained `.docx` files.
It adds forward-only migration `0018_docx_report_evidence_locators`, accepts only
structural document, visible body paragraph, and simple body table locators, and
re-extracts a selected paragraph or table transiently only after exact-source
verification. It stores positions, counts, and hashes--never document text or table
values--and fails closed on encrypted or unsafe archives, macros, external
relationships, embedded or hidden content, tracked changes, fields, hyperlinks,
drawings, and unsupported body structures. It adds no provider, canonical, technical,
commercial, lock, deployment, or release authority. Pull-request run 33765731885 and
post-merge main run 33766069162 passed.

### Explicit human-approved report evidence families

Migration `0019_report_evidence_family_manifests` retains an immutable,
human-approved, ordered family of at least two already-retained reports for one Project
and Estimate. The approver supplies only each exact stored-file ID and source SHA; the
service rejects filenames, folders, timestamps, titles, and other inferred membership.
It rechecks the immutable clean source binding, ownership, source hash, and family hash
whenever the family is loaded, and rejects tampering or source drift.

Explicit family admission is now accompanied by a deterministic proposal-review
aggregate. It accepts exactly one already-valid single-report review package for each
approved member, in the approved order. Each inner package must retain a V2
human-approved expected-label manifest that is independently re-resolved against the
member's exact stored source and hash. The aggregate retains the separate scopes,
artifacts, and identical protected-state receipt binding; it rejects absent, extra,
swapped, legacy/unbound, drifted, or tampered components.

The proposal-review register now retains either a single-report package or an approved
report-family package. A family record binds the exact approved family-manifest ID,
hash, and human approval reference, then independently rechecks every member's exact
stored source, expected-label approval record, review-package manifest, and outcome
membership. It preserves member order and separate source identities; it never merges
reports or scopes. The same CLASSIFIRE-owned five-year retention, separate redaction,
legal hold, integrity refusal, and scoped internal reader grants apply. The internal `/proposal-reviews` pages identify a family and show each outcome's family
member and evidence identifier without exposing storage paths or creating an execution
route. Only an administrator may append an immutable, hash-bound human-review annotation
for the exact original or redacted view and a visible scope using an explicit finding state
and safe reason code. Other eligible readers can see annotations only in their exact view.
An annotation records an observation only; it is not a technical, commercial, lock, or
release approval.
This remains evidence admission and proposal-review assembly only. It does not change
PDF/XLSX/DOCX normalisation, merge or re-scope evidence/proposals, invoke the
single-report runner, call a provider, or grant canonical, technical, commercial, lock,
deployment, or release authority.

### Implemented and merged: estimate-only Draft reporting (first P4b increment)

`services/draft_estimate_reports.py` captures one explicitly selected saved Estimate
and its exact Scope/optional candidate-review envelope with project labels, author,
time and render version. `outputs/draft_estimate.py` renders that frozen snapshot
without calling upstream writers. Both outputs are retained atomically in
`DraftEstimateReport`, bound to the exact Estimate revision by migration 0031.
Read/download verifies the snapshot, saved input and both output hashes; it never
regenerates files. Separate scope-only contracts and older reports remain unchanged.
See [the report contract](./DRAFT_ESTIMATE_REPORT_V1_CONTRACT.md).

`draft_estimate_ui.py` and `draft_estimate_reports.html` provide selection, preview,
creation, saved-report listing and PDF/XLSX downloads. Active human owner/admin,
project/estimate read/write/export and optional technical permissions apply in the
shared service, with rechecks around rendering/byte work. CSRF protects creation.
Later Estimate, Scope, optional review/source or project changes show stale reasons
without rewriting historical files. Corruption and missing authority fail closed.

PDF and six-sheet XLSX show saved quantities, rates, partial AUD subtotal, originals,
change history, omissions, unknown/unassessed work and provenance. Exact decimal
text is authoritative; optional numeric line amounts appear only when safely
representable within 15 significant digits. No formulas, inferred URLs or tax
calculation. New outputs use the exact supplied PNG; existing outputs are untouched.

This is one estimate-only profile, not completion of P4b or production reporting.
Other technical/combined profiles, production retention limits and export projection
remain open. The first source-to-Scope interaction is merged in PR #194, described below.
P2b applicability, P3b governed pricing and full portability remain required work.

### Implemented and merged: retained PDF evidence review (first P1b increment)

Current architecture -> change: the shared upload service previously left files
pending/not_configured with no demonstrated Draft scanner consumer. A thin
`draft_pdf_ui.py` now calls CLASSIFIRE-owned `draft_pdf_intake.py` use cases for
upload, explicit scan, page viewing and explicit reviewed observations. No new
agent framework or orchestration server is introduced; OpenClaw is not called.

```mermaid
flowchart LR
    UI[Draft PDF upload and review UI] --> S[Authenticated shared intake commands]
    S --> B[Bounded immutable upload / StoredFile]
    B --> AV[Explicit exact-byte ClamD scan]
    AV --> G[PostgreSQL shared quarantine locks]
    G --> W[Disposable bounded PDF parser process]
    W --> N[Existing report normalizer / retained page metadata]
    N --> V[Authorized raster page and unreviewed text]
    V --> H[Human explicitly saves an observation]
    H --> D[New Draft Scope v3 revision with page references]
    D --> R[Independent downstream snapshots / stale checks]
```

Migration `0032_draft_pdf_sources` adds Draft ownership and an exact StoredFile
ID/hash/size foreign key, scanner metadata and normalized-document hash. It is
additive; older revisions and PDF/XLSX bytes remain intact. Downgrade refuses to
destroy retained evidence. Readiness advances to 0032 while preserving recognized
0029/0030/0031 upgrade lineages. SQLite manual workflows remain available; the new
PDF path requires PostgreSQL's existing serialized clean-byte boundary.

`malware_scan.py` streams bytes to configured ClamD using bounded INSTREAM, accepts
only explicit clean/infected verdicts and records engine/signature database/time.
Missing, stale, ambiguous, timed-out or changed-database responses never become clean.
A detected infection quarantines shared bytes, even if the scanning user's permission
was revoked during processing. The daemon endpoint is trusted infrastructure, not a
user-supplied URL; restrict its unauthenticated TCP service to trusted private access.

The parser uses the existing report evidence normalizer in a fixed child process,
with a 30-second timeout and no inherited application/provider/database credentials.
Source limits: 10 MiB, 50 pages, 20 sources per Draft; normalized metadata 2 MiB and
PNG preview 4 MiB. Encrypted/embedded-file/oversized PDFs fail closed. Extracted text
is unreviewed; image-only pages are available as raster previews without claiming OCR.
Linux adds CPU/address-space limits. Windows has process/timeout and data bounds,
not a complete OS sandbox. Hosted untrusted multi-user intake still needs deployment
isolation, concurrency/rate limits, scanner update monitoring and measured capacity.

Uploads use unique temporary files and atomic no-overwrite publication. Parent
links/reparse points are refused before child creation. Storage-root ACLs remain a
trusted operational boundary. A per-hash transaction lock prevents cross-Draft source
adoption; the supported policy binds each retained source to one Draft. There is no
source deletion UI or automatic garbage collection; quarantine retains bytes.
Global quotas, retention duration, orphan reconciliation, legal holds and complete
source export rights remain decisions before customer deployment, not implied by
this bounded synthetic prototype. Generic `worker.py` remains unwired; this explicit
synchronous scan command is a real working consumer, not a claim of a general queue.

Scope v3 pins observation content, source/hash/size, page locator/text hash, normalized
document hash, scan hash and reviewer/time. The full source hash binds page-image
context; a page text hash alone does not prove pixel identity. Manual edits keep the
old review hash and expose a stale-review warning; removal affects only the new
revision. Import always downgrades local source/review claims to imported_unverified,
without access to source bytes or local approval. Existing v1/v2 bytes stay unchanged.
See [the PDF/v3 contract](./DRAFT_PDF_EVIDENCE_V1_CONTRACT.md).

New Scope/Estimate reports share `outputs/draft_branding.py` and the exact supplied
PNG; historical files and canonical/legacy output renderers remain unchanged.
Scope/Estimate reports retain page-reference claims; source/scan changes flag active
downstream dependencies as stale without rewriting saved artifacts or outputs.
Historical generated reports contain previously saved Draft claims, not embedded
raw PDFs; their downloads retain normal ownership/permission/integrity checks.
No canonical physical model, technical approval, price, lock or release is created.
Full applicability still needs explicit structured criteria: current retrieval uses
only service type/substrate and leaves size, material, orientation, FRL and installation
criteria missing. The former next priority, a bounded criteria/constraint review,
was delivered in PR #195 as described below; full applicability remains incomplete.
Never turn existing text similarity into an Applicable verdict.

### Merged partial measured-limit review (first P2b, PR #195)

The existing candidate review retrieves records through text comparison and captures
Scope, target, source and release. It is not a compatibility engine. The new
`draft_constraint_review.py` adds two deterministic checks: substrate thickness and
the measured minimum/maximum annular gap. The same FastAPI/Jinja screen explicitly
selects one retained candidate, records measurements and their evidence/method note,
saves, reopens and downloads the resulting unapproved review.

Current architecture -> change -> reason -> consequences -> migration:

- New technical publications use `CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v3` and an
  explicit `technical_fields` snapshot shared with retrieval by
  `technical_field_snapshot.py`. Earlier manifests pin identity/version/source but
  do not freeze numeric limits; they cannot support a claim that limits were published.
- Existing publisher permissions, active-record/source checks and release transaction
  remain. No Draft activation or approval authority is added. New manifests hash the
  field snapshot; old releases are not rewritten or silently republished.
- Existing `DraftSystemMatch`/Revision rows store backward-compatible v1 and new v2
  envelopes. v2 adds `constraint_review`; the original immutable retrieval basis
  remains unchanged. `save_review` and `save_constraint_review` share the revision
  append/CAS path. No new table, database, orchestrator, agent or dependency is needed.
- Scope and release dependencies are locked for new measurement reviews, current
  ownership/permissions and source bytes are checked, and stale dependencies block
  new checks. Read/history still retain earlier results with current stale warnings.
- An explicit opening is required. Gap review additionally needs a selected linked
  service; no aggregate quantity or plane is repurposed as a measurement. Decimal
  range comparisons return within_limits/outside_limits/unresolved with reasons.
  Missing complete bounds cannot yield a within-limits result. Known violated bounds
  can yield outside_limits; inconsistent source ranges remain unresolved.
- v2 records manual measurement provenance, selected candidate, published field hash,
  results and a fixed unassessed-conditions list. Validation recomputes checks. These
  are unapproved input claims and partial checks, never a system applicability verdict.
  Existing keep/reject notes preserve the measured review. Attached Estimates retain
  their exact v2 bytes and become stale after later match revisions.

UI -> existing authenticated/CSRF route -> shared `save_constraint_review` -> locked
Scope/release/source checks -> pure numeric evaluation -> immutable revision/audit ->
read/download. No next capability runs. Future ChatGPT uses this same command through
an appropriately authenticated adapter; no business logic belongs in chat memory.

The synthetic P2B source explicitly states its fake numeric limits and is separately
versioned from the retained P2A fixture. Chrome demonstrated within/outside/unknown
outcomes and exact history after restart. See [contract/demo](./DRAFT_CONSTRAINT_REVIEW.md)
and PROJECT_STATE.md for actual checks. This does not complete P2b.

**Unresolved:** source-defined service-size meaning, material/FRL/insulation/seal depth,
configuration, spacing/support/fixings, exclusions, contradictions and authorized
technical review. Full System Match portability and complete applicability need
further contracts and evidence; no fallback to keyword matching is permitted.

### Current implemented increment: pricing workbook selection (first P3b)

Current architecture -> change -> reason -> consequences -> migration:
manual Draft rates/free-text notes and PDF-specific intake -> shared retained-source
intake plus bounded XLSX parsing and explicit rate selection -> make prices traceable
to actual workbook cells -> Estimate v2 freezes unapproved selection events while
v1 remains supported -> additive migration 0033; old source/report bytes unchanged.
No new framework, dependency, AI agent, canonical pricing writer or orchestration layer.

UI routes in `draft_pricing_ui.py` call `draft_pricing_intake.preview/apply_rate`.
`draft_source_intake.py` centralizes the prior PDF ownership, storage, ClamD and
shared quarantine protections; PDF wrappers retain existing behavior. A separately
bound DraftPricingSource and fixed disposable XLSX worker feed explicit sheet/header/
column mapping. Strict units/Decimal prices, row/document hashes and revision CAS
control application to one existing line. Prices never supply technical authority.

Estimate v2 links every source selection to its override event and retained workbook,
scan, parsed-document and row hashes. Exact cells preserve reference, description,
unit/rate, currency/tax, date, labour/materials and inclusions/exclusions. Existing
quantity, initial rate, stale-input and reasoned override rules remain. Formula rates,
missing prices and unsupported units stay unresolved. Workbook reads additionally
require library permission. Reports use the same frozen Estimate revision, with a
versioned PDF provenance section and XLSX Pricing sources sheet; no recomputation
on download. Shared commands can later serve ChatGPT without duplicated rules.

See [the contract](./DRAFT_PRICING_XLSX.md) for limits, security and revision details.
Windows parser limits are not a complete sandbox. Scanner operations, source download/
retention and full portability remain open. Recovery notes and workbook rows remain
unapproved human/source claims; this does not deliver all pricing methods or recovery.

### Implemented current increment: independent scope-and-system reports (P4b)

Current architecture -> change -> reason: extend the existing `draft_scope_reports`
service/table and `outputs/draft_scope.py` renderers with a second snapshot profile,
rather than creating another report pipeline. Saved review revisions already contain
an exact Scope and source-bound candidate evidence; reporting that review should not
require a Draft Estimate. `draft_scope_ui.py` adds explicit preview/create routes
linked from candidate review. Shared presentation shows readable saved findings,
then complete captured source/decision/numeric detail, in UI/PDF/XLSX.

`CLASSIFIRE-DRAFT-SCOPE-REPORT-v2`, profile `scope-and-system`, renderer 2 adds the
complete validated saved `system_match` to the existing snapshot. Embedded Scopes
must be exactly equal. Exact retained review identity/hash/content is checked before
retention and on reads. Both outputs persist atomically in `DraftScopeReport`;
old scope-only schema-v1/renderer-1 downloads are never regenerated. No database
migration, dependency, agent or scheduler is added. This is an additive application
contract; all readers must retain both versions. Each output remains capped at 8 MiB.

Project ownership/read and active-human boundaries remain. Creation additionally
requires project write; all system-profile reads/exports require technical read,
matching the existing review JSON boundary. Estimate export is not required for a
non-estimate artifact. Users without technical access do not receive these report
entries in the recent-report list. CSRF, bounded forms, exact source binding,
metadata-only audit and escaped/literal output handling remain enforced.

Latest Scope/project/review changes and source/release/scan uncertainty mark a
retained report stale without rewriting it. Historical source claims stay historical;
no live source file or approval is silently embedded or granted. Reporting calls no
retrieval, calculation, provider or canonical writer. Full applicability, pricing and
human release remain unavailable in this profile. See [contract](./DRAFT_SYSTEM_REPORT_CONTRACT.md).

### Merged measured service sizes (P2b, PR #198)

Current architecture -> change -> reason: the same saved measured-review command
now supports a v3 match envelope with a measured service-size range and separate
measurement/source dimension meanings. Existing pinned min/max service-size fields
did not establish their meaning. Explicit unapproved human interpretation avoids
silently treating nominal size, bundle dimensions or rectangular widths as diameter.
No new library metadata or canonical physical dimension is asserted by this UI.

`draft_constraint_review.py` adds positive strict-decimal size inputs and one partial
range check. Both recorded meanings must be individual outside diameter, the target
must be an explicit nonblank opening/service, and the retained published fields must
be hash-bound. A known exceeded bound is outside; within requires a complete valid
range. Unknown/unsupported meanings and missing evidence remain unresolved. The
range covers recorded observations only; instance counts, complete coverage, material,
configuration and approved source interpretation remain unassessed.

`draft_system_match_contract.py` keeps v1/v2 readers and introduces v3 explicitly.
The v2 validator still rejects new inputs. `save_constraint_review(...,
service_size=True)` retains v3; an old-form write against v3 is refused rather than
silently losing size claims. Keep/reject copies the whole saved review. Existing
revision/hash/persistence, ownership/technical rights, CSRF, stale-source checks and
concurrency controls are reused. No database migration, dependency or agent is added.

The current measured-review template exposes the new inputs; shared presentation
propagates them into scope-and-system reports. Explicit Draft Estimate creation
retains the complete v3 match unchanged. Estimate-only rendering continues to show
a review reference; complete technical/commercial reporting remains a separate
profile. No report is rerendered on read. The separately versioned synthetic size
fixture preserves older demo source bytes and refuses unrelated fixture adoption.
See [the v3 contract and limits](./DRAFT_SERVICE_SIZE_REVIEW.md).

### Merged complete Draft reports (P4b, PR #199)

Current architecture -> change -> reason: the existing Estimate report command now
accepts an explicit complete profile because its retained Estimate already contains
the exact Scope and optional System Match. Reuse the same report table, persistence,
source binding, transaction and permissions. No new database, orchestration layer,
provider or domain calculation is needed. Original profiles and downloads remain intact.

Report schema v2/renderer 3 identifies complete composition; schema v1 preserves
estimate-only renderer 1/2. Mixed versions/profiles fail validation. Shared Scope
composition and technical review presentation join existing commercial lines/history
in one frozen PDF/XLSX pair. UI preview/create/history/download selects a saved Estimate
and profile; missing sections are unavailable and current staleness is visible.
Technical/library/export rights remain enforced. The profile grants no approval,
canonical write, lock or release. No migration or new dependency is required.
See [the contract](./DRAFT_COMPLETE_REPORT_CONTRACT.md).

### Merged selected Draft package (P5, PR #200)

Current architecture -> change -> reason: users can now collect coherent selected
Scope/review/Estimate revisions and existing reports in one portable ZIP. Shared
`draft_project_packages` reads existing validated services and report retention;
`draft_project_package_ui` adds configuration, no-write preview, explicit save,
history and download. No business logic is duplicated or upstream capability run.

Migration 0034 adds immutable package records with exact manifest/archive hashes,
workspace revision/parent links and creator/time. Scope-only selection is independent;
optional content uses its existing technical, commercial and export permissions.
Source bodies stay external/withheld with explicit pointers. A selected workspace
package does not claim all project workspaces, source files or historical revisions.
The structural ZIP inspector never extracts or grants import authority. Historical
bytes remain unchanged; current source/dependency changes are displayed separately.
See [contract](./DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md).

**Next proposed visible slice:** safe new-project package import. Validate the full
selected membership and all capability schemas, retain foreign provenance and exact
originals, and map identities/dependencies explicitly without granting foreign
approval or local technical authority. Unsupported inputs must be rejected or
visibly retained unresolved, never silently dropped. This requires actual import
contracts for review/Estimate data; current export is not proof of those contracts.
A thin ChatGPT adapter follows proven shared commands. Full source redistribution,
project/history coverage, retention/quotas and operational assurance remain debt.

### Separate production and adapter backlog

Remaining OpenClaw contract characterisation is required before replacement
wiring/retirement, not before the manual prototype. Provider execution needs
its established explicit authority, capture assurance and privacy controls.
Broader technical-source lineage, formats, pricing inference, full archive
migration/conflict handling, deployment recovery, scale and accuracy tuning
follow supported-path needs and user evidence. Never postpone a known security
or correctness defect on the path exposed by the prototype.

Phase 8-14 authoritative exits, canonical submission/locks and Human Release
remain separately governed. They do not block all independent Draft development.
The [roadmap](./CLASSIFIRE_ROADMAP.md) controls delivery order; the
[project snapshot](./PROJECT_STATE.md) controls factual implementation claims.

## 13. Deprecated or superseded paths

- Whole-file database hashes and count equality as semantic acceptance.
- Placeholder Services for blank openings.
- Generic writer authority or lock creation during initial submission.
- A persistent autonomous agent fleet as a mandatory domain or runtime path.
- Completing all schemas, orchestration or edge cases before a usable UI slice.
- Reusing guarded canonical physical writers as permissive Draft storage.
- Treating model output, desk quotes, chat, or Mission Control as canonical truth.
- Treating the conflicted legacy root or draft PR stack as a bulk merge path.
- Treating a successful transport, test suite, or CI run as technical approval,
  deployment proof, or Human Release.

Structural-steel protection and complete fire-rated duct runs remain deferred
domains requiring their own schemas, sources, calculations, and acceptance
evidence.


### Implemented amendment: editable imported projects and v2 origin archives

**Current architecture -> change -> reason:** PR #202 could inspect a selected ZIP,
but could not reopen it as editable work. The existing modular services now expose
explicit new-project import, owner-scoped local revisions and traceable re-export.
No new orchestration framework, provider dependency or autonomous agent is required.

| Component | Implemented responsibility | Boundary |
| --- | --- | --- |
| UI | Upload/preview, explicit confirmation, new imported-project screen, Scope/review/Estimate links, report scan/download and normal package configuration | Session, active human, ownership, CSRF, exact-file confirmation; untrusted labels escaped |
| Shared integration/use cases | `draft_package_import.inspect_package` and `preview_import`; `draft_package_materialization.create_import` | A future ChatGPT adapter calls these services; it must not duplicate domain rules |
| Orchestration | Existing synchronous explicit commands and transaction helper | No hidden automatic capability chaining, provider run, canonical admission, lock or release |
| Domain services | Existing Scope import/revisions, Match review, Estimate edits and report snapshot renderers | Exact dependencies, preserved original values, visible staleness and foreign authority |
| Optional AI | Existing proposal adapters only | No AI is needed for this import or manual prototype |
| Persistence | Migration 0035 adds original ZIP/mapping retention and imported report bindings; native rows/revisions retained | Match has exactly one native-release or imported-origin basis; no fake local eligibility |
| Package schema | Native v1 unchanged; imported-project v2 includes selected local artifacts plus exact `origins/<sha>.zip` and mapping | Bound recursive inventory, immutable foreign history, no source-body redistribution or approval transfer |
| Validation/security | Existing schemas/byte hashes/permissions, shared scan/quarantine and bounded report worker | PostgreSQL required for report-bearing import; active or unscanned binaries never download/re-export |

**Data flow:** upload -> read-only semantic inspection -> signed exact-file/session
confirmation -> one new owned Draft transaction -> preserve original ZIP and map new
artifact identities -> retain report attachments pending scan -> independently edit
Scope/review/Estimate -> validate and save new local revisions -> explicitly select
coherent revisions -> recheck all included origin rights and binary readiness -> save
and download a v2 package. Restart uses database/storage; chat or agent memory is
irrelevant. Reimport preserves nested originals instead of silently dropping outputs.

**Consequences:** Imported Match v4 and Estimate v3 wrap their existing native content
schemas with explicit `foreign_unverified` origins. Original values and history stay
intact. Local review notes/decisions and Estimate overrides are editable; foreign
technical measurement evidence cannot be rebound implicitly to a local release.
Report snapshots/PDF/XLSX stay original foreign attachments; new local reports carry
unverified-origin warnings. Current access and shared quarantine are checked again
when downloading previously saved packages. Scope-only and nonbinary imports can
use SQLite; report-bearing imports require existing PostgreSQL containment support.

**Migration:** 0034 -> 0035 preserves native artifact/revision/package bytes and
relationships, adds imported-origin tables/columns and enforces origin/file binding.
Historical migrations are unchanged. Revised migration fixtures use reflected old
columns and retain FK, exact-byte and downgrade-refusal assertions. A current ORM is
not run against an unmigrated historical schema. No operational database was migrated.

See [the package contract](./DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md#imported-project-lifecycle-and-v2-re-export)
for fields, size/depth limits, supported formats and failure behavior.

**Planned and unresolved:** This remains selected-workspace portability, not every
project record, source body or full revision graph. Imported signatures/approvals
never activate local authority. Existing-project merges, redistribution, retention/
quotas, production process sandboxing, tenant isolation, full technical applicability,
governed pricing and ChatGPT authentication/client parity still need their own proof.
Keep broad polish behind interactive trials; preserve protection parity before
retiring OpenClaw. ADRs 0001/0002 remain accepted and unchanged.


## Implemented client amendment: first authenticated Draft interaction

Current architecture -> change -> reason -> consequences -> migration:

- Existing browser sessions and shared Draft services remain. An opt-in MCP resource
  server uses the official SDK over Streamable HTTP in the same FastAPI application.
  This gives ChatGPT-compatible clients shared create/read/edit/package commands
  without moving business logic into an agent or introducing a second database.
- The operator enables `draft_client_config` and the `chatgpt` dependency extra.
  JWT verification uses explicit issuer/resource, pinned public keys, short token
  lifetime, subject-to-local-User mappings, allowed clients/scopes and local revocation.
  Every operation checks current account/role/ownership; external clients remain
  owner-only even when the mapped local user is an administrator. No automatic
  account linking, client-supplied keys, token passthrough or browser-cookie MCP access.
- Create/edit/package tools retain a proposed command. Only the same human's browser
  session, CSRF check and explicit confirmation execute existing Draft services.
  A compare-and-set and caller-owned transaction bind the decision and resulting
  revision together. Stale writes, duplicate decisions and revoked grants fail closed.
  Proposal and human decision audits retain the client, actor, payload hash and result.
- Read and ZIP download tools use the same saved revisions and existing permissions,
  integrity and quarantine checks. Downloads use an authenticated backend URL or the
  existing logged-in browser route; credentials never enter URLs. No capability runs
  implicitly and foreign approvals remain unverified.
- Migration 0036 adds only `draft_client_requests`; historical migrations and native
  artifact bytes remain unchanged. Retained review history prevents destructive downgrade.
  Current-head readiness fixtures advance explicitly; old upgrade baselines remain old.
- Scope proposals are rendered with the existing readable Scope component. Sign-in
  returns only to a validated local review identifier, not an arbitrary redirect URL.

```mermaid
flowchart LR
  C[ChatGPT-compatible MCP client] --> A[OAuth resource server]
  A --> R[Retained client request]
  H[Signed-in human] --> V[Review and confirm]
  R --> V
  V --> D[Shared Draft services]
  U[Standalone UI] --> D
  D --> S[Governed database and retained files]
  A --> D
  S --> X[Exact authenticated package download]
```

The client is a deterministic adapter, not an AI provider or orchestration fleet.
The local proof uses synthetic signed tokens and the official SDK plus Chrome.
A production OAuth authorization server, account linking, HTTPS deployment and a
real ChatGPT session have not been configured or demonstrated. Key rotation and
issuer-side revocation operations still need deployment validation; local policy
revocation is immediate, otherwise accepted tokens expire within 15 minutes.
PR #204 first covered Scope and selected package operations. The following amendment
extends the same confirmed client boundary; real OAuth integration remains unproven.
See [client contract and setup](./DRAFT_CLIENT_V1_CONTRACT.md) for exact boundaries.


## Implemented client amendment: independent capability commands

**Current -> change -> reason:** the first client shared Scope/package commands but
could not call the other existing Draft capabilities. Typed discriminated operations
in `services/draft_client_capabilities.py` and the tool adapter now expose saved
candidate retrieval/keep/reject, independent manual estimating and all four reports.
They reuse existing services, contracts, rendering and permissions; no new agent,
workflow framework, database or dependency is introduced. Capability completion stops.

Preparation validates command shape and selected input reads, hashes immutable Scope,
Match/Estimate/release/project inputs, and saves only a pending request. It does not
simulate a write then roll it back or calculate a proposed result. The review UI
shows the exact requested values and readable selected saved inputs. Same-user
session confirmation rechecks the input binding and invokes the existing service
inside the atomic decision transaction. Domain validation can refuse confirmation;
it is not claimed complete merely because preparation succeeded. Estimate edits use
expected revisions and preserve original rates/history; reports freeze explicit
saved revisions and never rerun matching or pricing. Reads expose current staleness.

Technical and estimating OAuth scopes are additional to the existing user roles.
Nested saved content, report downloads and package exports cannot bypass them.
Existing client configuration is not expanded automatically: clients previously
exporting sensitive content need explicit grants. v2 whole-origin ZIPs require both
sensitive scopes until a narrower archive disclosure policy is proven. Foreign
approvals remain untrusted, and shared quarantine/integrity/export checks still apply.

**Migration/consequences:** additive 0037 extends the request command constraint with
`capability`; old requests and artifact bytes remain. Downgrade refuses retained new
requests. Resource metadata advertises five scopes. The normal app remains usable
without the optional client, and external tools cannot confirm their own requests.

**Remaining gaps:** measured-constraint/service-size review and workbook price-selection
client commands, full applicability/pricing/domain breadth, real OAuth/ChatGPT setup,
in-chat downloads, operational tenancy/retention/rate limiting and production acceptance.
The next bounded task is measured-review client parity against the existing shared
commands. Technical truth, commercial recovery and Human Release boundaries are unchanged.
