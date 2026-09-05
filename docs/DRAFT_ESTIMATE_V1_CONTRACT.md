# Draft Estimate v1 contract

Workbook-rate amendment: [Draft pricing XLSX](./DRAFT_PRICING_XLSX.md) adds Estimate v2
and report renderer v2 for source selections. This document retains the manual v1
contract; existing saved bytes are unchanged.

Status: implemented P3a prototype contract. This is an independent manual estimate,
not a canonical Estimate, technically approved system selection, complete quotation,
or a governed pricing-library calculation. ADR 0002 permits this bounded capability
without a Physical Model Lock, published pricing library, AI, or OpenClaw.

## Shared use case and authority

`services/draft_estimates.py` is shared business logic; interfaces supply validated
commands and own commit/rollback. `draft_estimate_contract.py` owns strict input,
artifact and arithmetic validation. New forward migration `0030_draft_estimates`
adds `draft_estimates` and `draft_estimate_revisions`; it preserves earlier tables and
refuses downgrade to protect retained artifacts. No dependencies were added.

Every operation requires a persisted active human, `project:read`, `estimate:read`,
and ownership of the containing Draft Scope or the administrator role. Mutations
require `project:write` and `estimate:write`; download additionally requires
`estimate:export`. An attached candidate review additionally requires
`technical:read`, including historical reads/downloads. Listing returns the newest
20 accessible estimates and omits attached artifacts when technical access is absent.
Authorities are rechecked immediately before retention and after attached-source
freshness checks. Agent principals cannot use
these user commands. Authentication/CSRF and request bounds belong to each interface;
the service repeats domain, object and role checks independently.

Commands flush inside the existing atomic Draft transaction wrapper; callers commit
or roll back. Audit events retain only artifact/project IDs, revision and dependency
hashes. Descriptions, rates, source notes and override reasons do not enter audit
payloads. No canonical Estimate, EstimateLine, Opening, Service, release, lock,
provider, source-file or technical-library write is performed.

## Frozen inputs and envelope

Creation selects one explicitly saved Scope v1/v2 revision, preserving its entire
verified envelope and hash. It may attach one exact saved Draft System Match revision
from the same Scope revision/hash. Attachment is a historical unapproved reference;
kept candidates do not prove suitability, grant approval or supply prices.

The JSON envelope has exactly these keys:

- `schema_version`: `CLASSIFIRE-DRAFT-ESTIMATE-v1`.
- `artifact_id`, `project_id`, `revision`, `parent_hash`, `created_by`, `created_at`.
- `state`: `Draft`; `review_status`: `unreviewed`; `provenance`: `manual_unit_sell`.
- `currency`: `AUD`; `tax_treatment`: `excluded_not_calculated`;
  `calculation_version`: integer 1.
- `scope`: full verified saved Scope envelope; `system_match`: full saved review or null.
- `lines`, `summary`, `sha256`.

UTC timestamps include their offset. Revision 1 has a null parent hash. The hash
binds canonical compact sorted UTF-8 JSON excluding only the top-level `sha256`.
A separate immutable basis hash binds saved Scope, optional review, currency, tax
policy and calculation version. Foreign imported Scope lineage stays a claim, never
local technical or commercial authority.

Maximum envelope size is 2 MiB, with 100 lines and 100 history events per line.
Capacity errors refuse a new revision; history and content are never truncated.
Inputs use strict extra-field rejection. Retained reads validate schema, nested
artifacts, arithmetic, recovery identity and history, exact serialized bytes, stored
hash, parent hash, actor/time identity, and the original saved dependency rows.
Missing or corrupted retained data fails closed. Reads never rerun matching or pricing.

## Supported recovery boundary

Each line explicitly targets either one saved `service` or one saved `blank_opening`.
The stable `recovery_key` is `target_kind:target_id`, unique within an estimate,
including omitted lines. Restore an omitted line instead of adding it again.

A service is represented once across all its saved `opening_ids`, in its saved Scope
unit (`each`, `m`, or `mm`). Its fixed work basis is
`service_specific_excluding_shared_opening_work`. This prototype does not add or
allocate shared-opening closure costs. All nonblank openings remain visibly
unassessed, whether they have one or several services or no known service links.

An explicitly blank opening uses `blank_opening_closure_only`, with unit `each` or
`m2` chosen on addition. Its original quantity is null; a manual nonnull quantity
requires a reason. Dimensions are never silently multiplied into a quantity.
Nonblank opening lines, duplicate targets, unit conversion, inferred rates and
automatic quantity 1 defaults are unsupported and refused.

## Line and override lineage

Each line retains `line_id`, `recovery_key`, `target_kind`, `target_id`, saved `label`,
`opening_ids`, `unit`, `work_basis`, `description`, `source_note`, `original_quantity`,
`original_rate`, current `quantity`, `unit_sell_rate`, `status`, `omission_reason`,
`created_by`, `created_at`, `history`, `subtotal_ex_tax`, and `pricing_status`.

Description and source/work-basis note are required. Target, unit, original rate,
original quantity, description and source note remain fixed after addition.
The original service quantity is retained exactly from the saved Scope. The original
rate is the nullable manual unit sell rate entered when adding the line. A changed
initial quantity requires a reason, including withholding a known quantity or
entering a blank-opening quantity. A fractional `each` source quantity stays visible
as the original but requires a reasoned integral or unknown effective quantity;
it is never rounded silently.

Later quantity/rate changes require a nonblank reason and append an attributed
`override` event. Omit/restore commands also require reasons, preserve quantities and
rates, and append events. Unchanged overrides and repeated status actions are refused.
An override may correct values on an omitted line without restoring that line.

History events have `event_id`, `action` (`added`, `override`, `omitted`, `restored`),
`before_quantity`, `quantity`, `before_rate`, `unit_sell_rate`, `reason`, `created_by`,
and `created_at`. Validation replays this history from the original values, checks
before/after continuity and attribution, and checks the retained final line state.
Every accepted command creates a new immutable revision; stale expected revisions
are refused by an atomic compare-and-swap on revision, latest hash and basis hash.

## Decimal arithmetic, unknowns and coverage

Quantity/rate inputs are strings or null, never JSON numbers. They allow at most
9 integer and 6 fractional digits, nonnegative and finite. Exponent notation,
float/bool coercion, excess precision, negatives and unsupported units are refused.
Effective `each` quantities are integral; other supported units allow 6 decimals.
No automatic unit or currency conversion is performed. Numeric strings normalize
without rounding. Null remains unknown; explicit zero remains distinct.

An active priced line uses direct `quantity * unit_sell_rate`, rounded once with
ROUND_HALF_UP to 2 decimal places using the existing pure `money` helper. Rates retain
6 decimals before multiplication. For example 2 x 1.005 produces 2.01, and 3 x 0.333333
produces 1.00. The summary sums already-rounded priced line amounts: two lines of
1 x 0.005 produce 0.02. Decimal calculations use precision 40 within a local context.
No material/labour breakup, markup, waste, minimum charge, exchange rate or tax
calculation is implied.

If quantity or rate is null, `subtotal_ex_tax` is null and `pricing_status` is
`unpriced`. Omitted lines likewise have null amount and status `omitted`. Both are
excluded from the priced subtotal. A known zero quantity and known rate are priced
at 0.00; a zero quantity with unknown rate remains unpriced.

The summary contains `priced_subtotal_ex_tax`, `is_partial` (always true),
`technical_status` (`unapproved`), `priced_line_count`, `unpriced_line_ids`,
`omitted_line_ids`, `unrepresented_targets` (kind/ID/label), and
`unassessed_opening_ids` (all nonblank openings). A line remains represented when
omitted. The subtotal is always provisional and partial, even if every entered line
is priced. Tax is excluded and not calculated; there is no fabricated zero-tax field.

## Retention and freshness

Selected source revisions, line history and earlier download bytes remain unchanged
when newer Scope/review revisions appear. Freshness is a separate read-only check:
`ESTIMATE_SCOPE_CHANGED`, `ESTIMATE_REVIEW_CHANGED`, and inherited candidate-review
release/source reason codes explain changed upstream inputs. Historical reads require
retained integrity and access, not current library eligibility or unchanged live
source bytes. Users may continue reasoned manual edits on a stale estimate; it stays
Draft, partial and unapproved. Creating a new estimate is required to use a different
Scope, attached review or recovery basis.

`revision_bytes` returns the exact canonical bytes of the requested retained revision.
The prototype supports JSON download, not estimate import, PDF/XLSX estimating outputs,
complete ProjectPackage ZIPs or human release. Future interfaces must call the same
service rather than recreate calculations or authority checks.

## Public service API

- `create_estimate(db, actor, draft_id, scope_revision, *, currency="AUD", match_id=None,
  match_revision=None)` returns the parent model, initially at an empty revision 1.
- `list_estimates(db, actor, draft_id)` returns the newest 20 accessible parents.
- `read_estimate_revision(db, actor, draft_id, estimate_id, revision=None)` returns
  the verified retained envelope.
- `add_line(..., expected_revision, payload)` accepts target_kind, target_id, unit,
  quantity, unit_sell_rate, description, source_note and reason.
- `override_line(..., expected_revision, line_id, payload)` accepts quantity,
  unit_sell_rate and reason. `set_line_status(..., expected_revision, line_id, status,
  reason)` accepts active/omitted. These commands return the new saved envelope.
- `revision_bytes(..., revision=None)` returns retained JSON bytes.
- `estimate_staleness(..., revision=None, *, storage_root)` returns safe reason codes.

Scope ownership and read authority are checked for every operation. Database/source
integrity errors are 409; absent artifacts/revisions 404; missing authority 403; invalid
inputs or capacity 422; stale/duplicate saves 409. Errors expose safe codes only.
