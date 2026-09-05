# Architecture Decision 0002 - Independent product capabilities

**Status:** Accepted target architecture by explicit user approval on 2026-09-05; implementation incomplete.
**Prepared:** 2026-09-05 (AEST).
**Verified baseline:** `3b437dad9e42ec7ba2adf512b8ee67816d243473` (PR #186).
**Relationship:** Refines [Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).
Decision 0001 remains accepted as refined here. The same approval directs delivery
toward a working, testable UI prototype before broad refinement and edge-case work.

## Accepted decision

Keep the approved hybrid modular application, and expose four independently
callable capabilities: scope analysis, technical-system matching, estimating,
and reporting. Connect them through explicit versioned artifacts and optional
user-requested workflows. Keep domain evidence and authority prerequisites;
remove any requirement that another capability ran in the same session.

This records the architecture implications of the newly supplied product brief.
It does not authorize a rewrite, production operation, permission change,
OpenClaw removal, or automatic acceptance of manual/imported technical claims.

## Current architecture -> accepted change -> reason

**Verified current architecture:** CLASSIFIRE already owns deterministic domain
logic, database/storage, physical governance, technical-library governance,
calculations, snapshots and output renderers. PR #185 added optional journal
lifecycle hooks to the bounded inference transports. Decision 0001 accepts
optional AI, shared interfaces and portable project revisions.

The standard estimate export route in `src/classifire/api/router.py` requires
an active physical-model lock and retained estimate snapshot. This is a valid
canonical-output guard; it is not a general independent Draft-report interface.
`services/snapshot.py:build_estimate_snapshot` calls `recalculate_estimate`.
It therefore cannot be reused unchanged for reporting an exact supplied artifact
without rerunning estimation. Existing desk-quote outputs are a narrower
proposal path, not proof of all four independently callable capabilities.

The untracked candidate at `.tmp/project-package-draft-20260905` has a generic
record inventory, project revision and stage statuses. Its existing 22 archive
tests passed in the previous documentation review. It does not establish
versioned Scope/System Match/Estimate artifact boundaries, dependency freshness,
independent capability entry points or whole-project database completeness.
Do not publish that schema as the final product contract without reconciliation.

**Accepted change:** retain the same application and domain services, add stable
capability contracts and explicit artifact dependency records, and let the user
choose which capability runs. An orchestration command may chain capabilities
only when explicitly requested. Four capabilities do not require four agents,
four servers, or four databases.

**Reason:** users need scope-only work, later/manual technical input, independent
estimates and partial reports without recreating hidden runtime context or
being forced to run the entire chain.

## Capability boundaries

| Capability | Required input boundary | Versioned output | Must not do implicitly |
| --- | --- | --- | --- |
| Scope analysis | Authorized retained evidence and explicit project/input configuration; unsupported content and gaps declared | Scope Package: observations, scope items, physical entities, quantities/bases, evidence, assumptions, contradictions and review state | Select a technical system, price work or start matching |
| System matching | Valid Scope Package or validated equivalent manual scope; referenced authorized technical-library revision | System Match Package: scope-item bindings, candidates, applicability constraints, reasons, provenance, limitations and review state | Run scope extraction, force a match, use price as technical proof or start estimating |
| Estimating | Valid scope/quantity/technical inputs sufficient for the stated estimate mode; authorized rates or explicit provisional method | Estimate Package: calculations, units, components, recovery ledger, rate/method provenance, overrides and review state | Infer missing technical approval, conceal unsupported quantities or start reporting |
| Reporting | Explicit selection of valid artifact revisions plus report profile and snapshot | Report snapshot and PDF/XLSX outputs bound to that same snapshot | Run analysis, matching or estimation, silently refresh inputs, invent missing sections or grant release authority |

Each capability needs its own callable application use case, validation and tests.
API/CLI/ChatGPT adapters delegate to those same use cases. UI-specific state and
agent memory never substitute for required input artifacts.

## Preserve the reasoning chain without forcing a session sequence

The evidence-to-Human-Release chain remains a correctness and authority rule.
Independent entry means that required information can come from previously saved
or manually prepared inputs which pass the same applicable checks. It does not
mean that required technical evidence or authorization can be skipped.

- A Scope Package may record performance requirements without selecting systems.
- A matching result may contain several candidates, insufficient evidence, or a
  provisional result. Only appropriately approved source records support an
  authoritative applicability claim. Unreviewed candidates remain visibly separate.
- A manually selected system or price is attributed input, not automatically an
  approved technical decision or authorized rate. Provisional estimates explicitly
  retain unresolved technical/quantity/commercial dependencies and limits on use.
- Draft scope-only or partial reports are allowed by profile and permission, with
  omitted/unresolved/stale sections visible. Canonical or Released claims retain
  the existing applicable lock, validation, snapshot and human-release gates.
- Importing, exporting or verifying signatures never activates foreign approval,
  lock or release authority. Local acceptance uses the existing governed boundaries.

Users can stop, inspect, edit, save, export, repeat, reject or replace a result.
Replacement creates a successor artifact; it does not erase reviewed history.

## Artifact and ProjectPackage contract

ProjectPackage remains the versioned interchange envelope. The governed database
and retained storage remain live canonical state. A capability artifact can be
exported independently or included in a project revision, with explicit external
references and omissions when its evidence is not distributable.

Define a common artifact envelope before freezing the Draft package schema:

- schema/type, stable artifact ID, project ID, revision and predecessor identity;
- immutable content identity and exact dependency artifact/release hashes;
- typed payload with stable scope/service/opening/plane/work-item identifiers;
- evidence identity and precise source locators, with ownership and rights;
- validation result, review/authority state, assumptions and unresolved blockers;
- creation method/version and actor attribution where available;
- included, withheld, omitted, stale and external content declarations.

Schema details and mappings must extend existing records, not duplicate them.
Independent artifact validation proves the declared contract; a trusted source
projection must separately prove database membership, permissions and redaction.
Imported payloads are quarantined and validated before local admission. Unknown
versions fail closed until a tested migration is available.

## Change propagation and user control

Store exact dependency identities. If an upstream dimension, selected system,
rate or source revision changes, mark the corresponding downstream relationship
as stale and explain what changed. Preserve the old artifact's original content
and approval history. Freshness relative to current inputs is separate from the
historical artifact's immutable hash and review facts.

Do not recalculate or replace downstream artifacts automatically. Let the user
preserve, compare, revise or explicitly rerun. Reports bind selected revisions
and a captured freshness assessment so PDF and XLSX cannot disagree because a
rate or source changed between renders. Stale or incomplete inputs cannot satisfy
an authoritative output profile merely because archive integrity passes.

## Pricing and technical-library implications

Keep technical applicability and commercial cost in separate services/records.
A default cost is a linked commercial record, not a technical applicability field.
Preserve exact authorized, mapped, component-built, analogous, parametric,
user-defined and unresolved price bases distinctly. Do not treat an authorized
source rate as authorization of an inferred mapping or extrapolation.

Preserve workbook/version/cell provenance and original values. Overrides require
an explicit permitted scope, attribution, reason where supplied, and retained
prior value. Organization-level precedence requires an approved tenancy model;
it must not be invented in the current package implementation. Transparent
component/rules methods and holdout error evidence precede claims about reliable
price inference. No new pricing algorithm or redistribution right is approved here.

## Prototype-first delivery and migration

The user explicitly approved this amendment and prioritized an interactive
prototype over polishing every detail. The minimum artifact contract belongs
inside a usable UI slice; it is not a separate programme to finish before UI.
The [roadmap](./CLASSIFIRE_ROADMAP.md#prototype-delivery-track) defines delivery
order and measurable user-facing exits.

1. **First slice: persisted Draft Scope workspace.** Extend the existing FastAPI/
   Jinja UI and shared services so a user can create/open a synthetic project,
   manually enter distinct openings/services and uncertainties, validate, save,
   reopen and download a versioned Draft Scope JSON artifact. Include only the
   schema, persistence, permission and revision behavior needed for that slice.
   Draft data must not write guarded canonical physical rows or imply approval.
2. Add safe Draft Scope import/replacement and supported evidence-assisted intake
   as bounded UI increments. Explicitly report unsupported input; do not await
   comprehensive format coverage or AI availability to demonstrate manual scope.
3. Expose matching and estimating workspaces from saved or validated manual
   inputs. Preserve their separate contracts and never run the next capability
   implicitly. Develop with synthetic approved-library fixtures and clearly
   provisional commercial inputs until real-source authority is established.
4. Provide independent Draft reporting from selected artifact revisions. Produce
   PDF/XLSX from one snapshot without recalculation, show missing/stale sections,
   inspect both formats, and extend the report profiles as capabilities arrive.
5. Reconcile and reuse the untracked ProjectPackage archive candidate when
   assembling multiple capability artifacts, then prove governed projection,
   storage/download and quarantined import. A Draft Scope download is not the
   complete project-package product. Do not freeze v1 around today's narrow record
   list or make complete ZIP/import infrastructure a prerequisite for first UI.
6. Add a thin ChatGPT adapter to proven application commands; keep both clients
   on the same core. Prioritize observed user feedback, then broaden accuracy,
   format coverage, performance and production operation. OpenClaw replacement
   remains a separate parity-gated track and is not required for the manual UI.

Phases 8-14 remain gates for authoritative end-to-end results, not a blanket ban
on development of independent Draft capabilities. Each prototype slice retains
permissions, ownership, provenance, explicit uncertainty, safe input handling,
applicable calculation checks and existing authority boundaries. Broader edge-case
coverage can follow user testing; a known security or correctness defect on the
supported path must be fixed before declaring that slice usable.

## Acceptance evidence for the amended architecture

- Each capability runs against explicit fixtures without another capability's
  runtime/session state; default completion never invokes the next capability.
- Manual/saved inputs pass the same semantic, ownership and authority checks.
- Evidence-to-item-to-technical-to-quantity-to-rate lineage remains inspectable;
  wrong references, unit errors, unsupported conclusions and double recovery fail.
- Upstream revision changes identify stale dependencies without mutating approved
  downstream artifact bytes, totals or review history.
- Independent artifact and complete-project round trips preserve IDs, hashes,
  uncertainty and explicit omissions; imports confer no active authority.
- Scope-only, scope-plus-system, estimate and combined reports render PDF/XLSX
  from the same snapshot. Inspect content/layout, identifiers, units and totals;
  test malformed input, spreadsheet formula injection and missing sections.
- With AI disabled, valid manual artifact workflows still operate. ChatGPT and
  standalone adapters use the same domain validation and authorization services.

## Remaining implementation decisions

Architecture approval is complete. Exact payload/schema evolution, Draft storage
mapping, manual-input admission, provisional report profiles, freshness storage,
override precedence and source redistribution still need mapping to current
policies when the relevant slice is built. Resolve ordinary implementation details
using existing abstractions. Surface only material policy choices not covered by
approval; do not ask again whether four independent capabilities are approved.

Approval and documentation do not implement a prototype or authorize a live
provider/customer run, canonical write, lock, deployment or release. No such
operation occurred in this documentation change.
