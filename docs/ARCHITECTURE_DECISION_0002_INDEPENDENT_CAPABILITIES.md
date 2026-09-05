# Architecture Decision 0002 - Independent product capabilities

**Status:** Proposed for explicit architecture approval; not an amendment in force.
**Prepared:** 2026-09-05 (AEST).
**Verified baseline:** `3b437dad9e42ec7ba2adf512b8ee67816d243473` (PR #186).
**Relationship:** Refines [Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).
Decision 0001 remains accepted. Publication of this proposal does not approve it.

## Decision requested

Keep the approved hybrid modular application, and expose four independently
callable capabilities: scope analysis, technical-system matching, estimating,
and reporting. Connect them through explicit versioned artifacts and optional
user-requested workflows. Keep domain evidence and authority prerequisites;
remove any requirement that another capability ran in the same session.

This records the architecture implications of the newly supplied product brief.
It does not authorize a rewrite, production operation, permission change,
OpenClaw removal, or automatic acceptance of manual/imported technical claims.

## Current architecture -> proposed change -> reason

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

**Proposed change:** retain the same application and domain services, add stable
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

## Migration and priority impact if approved

1. Reconcile the three-file Draft ProjectPackage candidate against common artifact
   identity, capability payloads, dependency freshness and partial exports. Reuse
   proven archive validation; do not discard unrelated work or freeze an incomplete
   v1 contract. First slice: common artifact envelope and an independently validatable
   Scope Package contract using existing physical/evidence identifiers.
2. Prove standalone scope validation and safe export/import contracts with
   synthetic multi-service/opening cases and explicit incomplete evidence. Select
   the smallest application use case from current source; do not claim full source
   analysis merely because a schema validates.
3. Add or expose matching and estimation use cases that accept saved/manual inputs
   and check all material prerequisites without depending on prior session state.
4. Add snapshot-only partial reporting with consistent PDF/XLSX content. Reuse
   renderers where valid and preserve the current canonical export guards.
5. Complete governed projection, revision storage, download, quarantine/import and
   shared interfaces as bounded slices. Continue OpenClaw replacement only against
   Decision 0001's independently proven parity requirements.

Phases 8-14 remain gates for authoritative end-to-end results. Draft capability
contracts and partial reporting are separate development milestones, not evidence
that those phase exits are complete. On approval, reconcile the four maintained
documents and replace their former package-publication-first handoff accordingly.

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

## Unresolved details and approval boundary

The four-capability direction is explicit in the supplied product brief. The
implementation amendment remains proposed until confirmed: exact artifact schema,
manual-input admission, provisional estimate/report profiles, freshness storage,
override precedence and source redistribution need mapping to current policies.
Do not silently relax existing canonical guards to implement independence.

This review changed no executable code, schema, migration, permissions or runtime.
Approve this amendment to make its revised contract-first priority authoritative;
then implement the smallest proven slice and update the four continuity documents.
