# Architecture Decision 0001 - Hybrid CLASSIFIRE Architecture

**Status:** Accepted target architecture on 2026-09-05; migration not yet complete

**Refinement:** [Decision 0002](./ARCHITECTURE_DECISION_0002_INDEPENDENT_CAPABILITIES.md)
was explicitly approved on 2026-09-05. It defines independent capability artifacts
and prototype-first UI delivery without weakening this decision's retirement gates.

**Scope:** Orchestration, bounded AI execution, ChatGPT and standalone
interfaces, portable project packages, and eventual OpenClaw retirement

**Verified implementation baseline:** `7e8f473` (PR #174 merge, 2026-09-05
AEST)

## 1. Context

CLASSIFIRE is a safety-, evidence-, and commercially-sensitive application. Its
governing sequence is:

```text
Evidence
-> Physical Model
-> Technical Selection
-> Quantity and Labour
-> Commercial Recovery
-> Validation
-> Snapshot
-> Output
-> Human Release
```

The implemented application already keeps its domain rules, persisted state,
validation, canonical-write guards, locks, and authority boundaries inside
CLASSIFIRE. OpenClaw currently supports selected proposal inference and a
separate constrained controlled-write bridge. Across those boundaries it
provides session creation, provider/model routing, tool-policy attestation,
loopback transport, and audit evidence. Mission Control provides a limited
client/bootstrap and may mirror operational tasks; it is not canonical workflow
state.

Repository evidence does not demonstrate an operational autonomous fleet. The
implemented Phase 8 path is a deterministic CLASSIFIRE controller that invokes
separate Physical and Validator model roles through narrow inference ports. The
controller, not either model role, fixes the stage order, correction limit,
protected-state checks, and outcome.

CLASSIFIRE also does not yet have a complete portable project-package schema,
project-package importer/exporter, package download endpoint, production
ChatGPT integration, or production standalone interface.

## 2. Decision

CLASSIFIRE adopts a **hybrid architecture**:

1. Deterministic CLASSIFIRE application and domain services own all durable
   workflow, state, validation, calculations, package lifecycle, approvals,
   canonical writes, locks, outputs, and release.
2. Bounded AI calls are retained only for evidence interpretation or
   independent challenge where measured evidence shows that they add value.
3. Model calls are stateless, isolated, least-privilege, schema-constrained,
   evidence-bound, and proposal-only.
4. A persistent autonomous multi-agent fleet is not a required product or
   runtime foundation.
5. ChatGPT and standalone clients use the same authenticated CLASSIFIRE
   application commands and queries. Core business logic is never duplicated
   in an interface or model prompt.
6. OpenClaw becomes a transitional adapter. It remains available until
   CLASSIFIRE-owned replacements meet the security, recovery, observability,
   and compatibility gates in this decision.

Acceptance of this decision changes the approved target architecture only. It
does not mean that OpenClaw has been removed, that a replacement inference
adapter exists, or that MCP or portable-project-package functionality has been
implemented.

### 2.1 Foundations that remain unchanged

- The evidence-to-Human-Release reasoning chain and phase dependencies.
- The governed database and content-addressed storage as live canonical state.
- Exact-byte evidence ownership, provenance, locators, quarantine, and
  uncertainty.
- Distinct Defect, Opening, Service, substrate, relationship, repair,
  technical, quantity, and commercial records.
- Deterministic, fail-closed workflow and domain rules inside CLASSIFIRE.
- Separate proposal, review, canonical, lock, technical, commercial,
  deployment, and Human Release authorities.
- Signed admissions, immutable receipts, idempotency, concurrency protection,
  and audit attribution.
- Pinned, immutable technical and commercial releases.
- Snapshot semantic identity and complete-document integrity.
- Human-only final release.

### 2.2 Deterministic workflow core

Project creation and editing, evidence retention, package membership,
validation, physical state, technical eligibility, quantities, commercial
recovery, snapshots, output generation, and Human Release must execute as
ordinary testable CLASSIFIRE commands.

The target orchestration layer is deliberately small. It provides persistent
jobs, runs, stages, leases, idempotency, deadlines, retries, cancellation, safe
outcomes, and audit correlation. It is not a general agent platform and does
not allow a model to choose or invent authority-bearing workflow transitions.

### 2.3 Bounded optional AI roles

Initial retained roles are limited to work such as:

- proposing observations from ambiguous documents or images; and
- performing an independent, sealed challenge where a measured accuracy or
  safety benefit justifies the additional call.

Separate roles require separate contexts, prompt/policy versions, identities,
and receipts. They do not require persistent agent memory, peer-to-peer
communication, autonomous task planning, or generic tools. A model may produce
a proposal for a governed command, but it may not execute that command merely
because it produced the proposal.

AI must be optional. Disabling every model adapter must not prevent users from
creating, editing, validating, importing, exporting, or downloading a project
package through deterministic workflows.

### 2.4 ChatGPT and standalone interfaces

The preferred ChatGPT-native target at the date of this decision is a thin
MCP-based CLASSIFIRE integration with optional interactive UI where inspection,
editing, review, confirmation, or download benefits from it. The integration
exposes coarse project-scoped commands rather than low-level database or writer
tools.

A standalone web, desktop, on-premises, or command-line client calls the same
application layer. Interface adapters may differ, but validation, persistence,
permissions, package generation, and domain behaviour must remain identical.

ChatGPT may provide conversation, collect intent, display status and blockers,
request explicit actions, and present download links. The external or locally
installed CLASSIFIRE backend owns authentication, tenant/project mapping,
evidence processing, persistence, model credentials, privileged commands,
package construction, and audit.

### 2.5 Canonical state and the ProjectPackage boundary

The word "package" has two distinct meanings:

- `ProposalReviewPackage` is the existing narrow, proposal-only review
  artifact. It is not a complete portable project.
- `ProjectPackage` is the planned complete, versioned interoperability
  contract for a CLASSIFIRE project.

The truth model is:

- **Live canonical state:** the governed CLASSIFIRE database and
  content-addressed storage for that application instance.
- **Canonical interchange contract:** the versioned `ProjectPackage` schema.
- **Exported package:** an immutable, hash-bound snapshot of one governed
  project version.
- **Imported package:** untrusted input until quarantine, integrity, schema,
  lineage, ownership, permission, conflict, and authority checks pass.
- **Standalone instance:** its local CLASSIFIRE database and storage are
  canonical for that instance; the common package format transfers immutable
  versions between instances.

A downloaded archive is never edited in place as live state. A user changes the
governed project and produces a successor package revision linked to its parent
hash. Imported approvals, locks, signatures, technical decisions, and release
records always remain historical evidence. Integrity and signature checks prove
package provenance only; they do not activate local authority. Active local
authority always requires a new explicit local record created through the full
applicable CLASSIFIRE gate.

Policy-permitted Draft, Provisional, Validated, Locked, and Released package
exports are allowed. The manifest preserves the exact lifecycle state,
unresolved blockers, and authority status, and export never upgrades that state.
Only a package claiming canonical or Released output requires the applicable
Phase 12 validation, Phase 13 canonical output, and Phase 14 Human Release gates.

## 3. Target components and data flow

```text
ChatGPT MCP/UI                 Standalone UI or CLI
       \                             /
        CLASSIFIRE API, identity, and permissions
                         |
             Application commands and queries
                         |
        Deterministic workflow and job coordinator
            /                            \
  CLASSIFIRE domain services       Bounded AI adapters
  Evidence, Physical, Technical,   Proposer and independent
  Quantity, Commercial, Snapshot,  validator where justified
  Output, Package, Release                  |
            \                            /
     Governed database and content-addressed storage
                         |
     Audit, malware boundary, secrets, metrics, traces
```

The normal project-package flow is:

```text
Governed project draft
-> deterministic validation
-> immutable package revision
-> optional trusted signature or seal
-> permission-checked, audited download

Untrusted import
-> quarantine and malware/archive checks
-> schema, hash, signature, lineage, and conflict validation
-> explicit import plan and human admission
-> new governed local project or revision
```

The planned archive is deterministic and ZIP-compatible, with a versioned
manifest binding its package ID, revision, parent hash, project identity,
export profile, lifecycle state, unresolved blockers, every entry path/media
type/size/hash, release pins, semantic project hash, deterministic entry/content
root, actor, time, application version, confidentiality classification, and
optional signature over that root. The manifest does not bind the final archive-byte hash
because that would require the archive to contain its own digest. CLASSIFIRE
stores the final archive-byte SHA-256 externally on the registered artifact and
its download receipt. The package may contain governed project and estimate
state, evidence permitted by the export profile, physical and technical
decisions, commercial state, snapshots, approvals, receipts, outputs, and a
bounded audit proof.

Secrets, credentials, signing private keys, local filesystem paths, and
temporary signed URLs are never package members. Proprietary technical or
commercial material is included only where licence and confidentiality policy
permit it.

## 4. OpenClaw and Mission Control responsibilities to replace

| Current responsibility | CLASSIFIRE-owned target |
| --- | --- |
| Provider and model routing | Provider-neutral inference adapter with explicit allowlists |
| Session creation | Fresh immutable run/stage identity for every invocation |
| Physical/Validator separation | Separate sealed requests and contexts |
| Effective no-tool policy | No tool definitions or executor, rejection of tool-call-shaped output, and tested policy evidence |
| Prompt/model/profile binding | Immutable invocation manifest and receipt |
| Gateway transport and tokens | Backend transport with governed secret custody |
| Timeouts and failures | Deadlines, cancellation, bounded retries, and content-safe failure codes |
| Post-call tool audit | Invocation validation and immutable run outcome |
| Session recovery | Durable run/stage state and crash-safe recovery |
| Operational visibility | CLASSIFIRE run dashboard and/or read-only telemetry projection |
| Controlled-write plugin | Deterministic application commands under existing scopes, signed admissions, and human gates |
| Untrusted-content isolation | Dedicated constrained parsing/inference workers where required |

Mission Control may consume a read-only operational projection during or after
migration, but it may not own project state, workflow truth, approval state, or
command authority. It may be retired when CLASSIFIRE-owned run visibility is
adequate.

## 5. Security-parity and OpenClaw retirement gates

OpenClaw must not be disabled for new execution until all applicable gates pass:

1. Every used OpenClaw responsibility and call site is inventoried.
2. Synthetic tests freeze the current no-tool, context-separation, input-binding,
   receipt, safe-error, timeout, and protected-state contracts.
3. Provider-neutral adapters remain outside domain services and expose no
   generic writer capability.
4. CLASSIFIRE persists durable job/run/stage outcomes for success, refusal,
   timeout, cancellation, duplicate delivery, and crash/restart.
5. Every model request binds exact governed evidence plus prompt, policy,
   provider, model, and adapter versions.
6. Every model egress is governed by data classification and minimisation, an
   explicitly permitted provider and endpoint, tenant/project isolation,
   retention and residency policy, a network allowlist, governed secret custody,
   and content-safe telemetry.
7. No tools are supplied, no tool executor exists, and tool-call-shaped output
   fails closed for proposal-only roles.
8. Negative tests prove that ChatGPT and model output cannot cross physical,
   technical, commercial, canonical-write, lock, deployment, or release gates,
   and reject cross-tenant access and confused-deputy requests.
9. Historical OpenClaw receipts remain readable and verifiable.
10. A feature-flag rollback path is tested.
11. Synthetic golden, malformed-output, timeout, concurrency, duplicate,
    cancellation, crash-recovery, cross-tenant, and confused-deputy tests pass.
12. Clean-machine startup, package workflows, monitoring, and recovery succeed
    without an OpenClaw installation.
13. A separately authorised controlled run demonstrates equivalent safety and
    evidence invariants after synthetic parity. This decision does not provide
    that run authority.
14. Final operational retirement occurs only after an observation period and a
    separate deployment decision.

## 6. Alternatives considered

| Option | Decision |
| --- | --- |
| Retain the OpenClaw fleet | Rejected as the long-term default. It preserves useful controls but adds runtime, identity, credential, deployment, and debugging surfaces without evidence that a fleet is required. |
| Preserve the fleet using another orchestration framework | Rejected. It risks exchanging one dependency for another while retaining unnecessary multi-agent complexity. |
| Build a CLASSIFIRE-specific agent orchestrator | Rejected as a general platform. A small deterministic job/workflow coordinator is accepted. |
| Replace every agent with deterministic modules | Rejected as an absolute rule. It is the correct baseline but could discard useful bounded interpretation and independent challenge. |
| Deterministic core plus bounded AI roles | Accepted. It preserves useful inference while keeping authority-bearing work reliable and testable. |

## 7. Consequences and trade-offs

Benefits:

- fewer runtime dependencies and credentials;
- one canonical state and permission model;
- reproducible workflow transitions and easier debugging;
- shared business logic for ChatGPT and standalone clients;
- provider and interface adapters can change without rewriting domain rules;
- model cost and latency are incurred only where justified; and
- project packages become a stable portability boundary.

Costs and limitations:

- CLASSIFIRE must own durable job/run persistence, retry, cancellation,
  recovery, and observability;
- OpenClaw's current no-tool and audit evidence must be deliberately replaced;
- package export/import introduces archive, tamper, confidentiality, conflict,
  and cross-instance identity risks;
- model-provider behaviour still requires monitoring and version binding; and
- fully offline or multi-instance package synchronisation requires later product
  and security decisions.

## 8. Migration and compatibility

Migration is additive and reversible. The sequence below records replacement
adapter dependencies, not a requirement to finish OpenClaw work before building
the product. Under accepted Decision 0002, the UI prototype and minimum Draft
contracts proceed first; package and interface steps may run independently of
provider replacement. Synchronous bounded manual commands need no general job
scheduler. Background execution becomes necessary when the selected workflow
actually needs durable long-running work.

Within the OpenClaw replacement track:

1. Characterise the current OpenClaw contract with synthetic inputs and golden
   receipts.
2. Define the smallest provider-neutral run contract behind the existing
   inference ports.
3. Add CLASSIFIRE-owned job/run/stage persistence and execution handlers.
4. Implement a replacement inference adapter behind a feature flag.
5. Prove failure, security, receipt, and recovery parity while retaining
   OpenClaw as rollback.
6. Implement `ProjectPackage` v1 deterministic export and audited download,
   followed separately by quarantined new-project import.
7. Add MCP and standalone adapters over the same application services.
8. Replace any required controlled-write bridge with deterministic backend
   commands under existing authority checks.
9. Retire Mission Control or retain it only as a read-only projection.
10. Remove the required OpenClaw runtime only after every retirement gate passes.

Historical OpenClaw receipt schemas and verification remain supported. Existing
database migrations are not rewritten. The current Phase 8 evidence, review,
preflight, signing, submission, and replacement-lock gates remain unchanged.

## 9. Explicit non-goals and authority exclusions

This decision does not:

- implement the target architecture;
- authorise a real report, Gateway, OpenClaw, or provider run;
- authorise customer evidence use;
- create or import a canonical project record;
- approve or submit a Physical Model;
- create, amend, replace, or invalidate a lock;
- approve a technical source, variant, system, or release;
- price work or approve commercial recovery;
- deploy software or change branch protection;
- grant Human Release; or
- mark any roadmap phase complete.

## 10. Validation required before implementation stages complete

- Domain services have no dependency on OpenClaw, ChatGPT, MCP, or a model SDK.
- All interfaces pass contract tests against the same application services.
- Model adapters can be disabled without breaking deterministic package work.
- Model invocations use fresh bounded contexts and durable content-safe receipts.
- Provider egress tests prove classification/minimisation, permitted
  provider/endpoint enforcement, tenant/project isolation, retention/residency
  policy, network allowlisting, secret custody, content-safe telemetry, and
  cross-tenant/confused-deputy refusal.
- Supported-database tests prove concurrency, idempotency, retry, cancellation,
  and crash recovery.
- Complete and redacted package exports are deterministic and tamper-evident.
- Export-to-blank-instance import preserves the governed semantic aggregate.
- Import rejects traversal, links, duplicate or case-colliding paths,
  decompression bombs, malware, tampering, incompatible schemas, stale bases,
  and foreign authority.
- Logs, traces, packages, and failure receipts pass a sensitive-content review.
- Clean-machine setup, migration, backup, restore, and rollback evidence passes.

## 11. Decision history and supersession

This is the first numbered CLASSIFIRE architecture decision. A future decision
may refine or supersede it, but must identify the affected boundaries, migration
impact, compatibility treatment, and evidence supporting the change.

Related governing documents:

- [CLASSIFIRE Architecture](./CLASSIFIRE_ARCHITECTURE.md)
- [CLASSIFIRE Master Roadmap](./CLASSIFIRE_ROADMAP.md)
- [CLASSIFIRE Project State](./PROJECT_STATE.md)
- [CLASSIFIRE Session Handoff](./SESSION_HANDOFF.md)
