# Assumption-Led Desk Quote Contract

## Purpose

CLASSIFIRE must be able to prepare a useful commercial proposal where a site
visit is not reasonably available. This contract defines a **desk quote** based
on retained report text, drawings, schedules and photographs.

A desk quote is a source-linked commercial scenario. It is not a site
observation, canonical Physical Model, technical system selection, compliance
determination, installation certificate or release approval.

## When to use it

Use a desk quote when the available evidence is sufficient to describe a
bounded commercial allowance but not sufficient to confirm every physical fact.
It can support early budget, tender, proposal and client decision workflows.

Do not use it to turn a concealed, unsupported or contradictory condition into
an observed fact. A later measurement, drawing, opening-up inspection or other
new evidence remains a governed amendment, not a silent overwrite.

## Required assumption record

Every assumption must contain:

- a stable assumption identifier and subject reference;
- one physical fact type, such as opening size, substrate, service material or
  service quantity;
- status `inferred`, `provisional`, `assumed` or `unresolved` — never
  `observed` or `confirmed`;
- a value and probability from 1 to 99 percent for a resolved assumption, or no
  value and probability 0 for an unresolved item;
- an explicit confidence band;
- one or more active CLASSIFIRE EvidenceSource identifiers, exact retained-file
  SHA-256 values, matching retained evidence references, and precise locators,
  such as report page, photograph or drawing call-out;
- rationale, a credible alternative explanation, and the required verification
  action; and
- one commercial treatment: included allowance, variation risk, or excluded
  pending verification.

An unresolved fact is always excluded pending verification. A commercial line
cannot depend on an excluded assumption. Every included allowance must name the
assumption(s) that support it and an exact governed pricing-library record.

## Governed pricing binding

The desk-quote payload names one active pricing release and, for each allowance,
one pricing-library record in that release. The caller does not provide a unit,
unit rate, rate-basis label or pricing description. CLASSIFIRE resolves those
values from the active record and verifies that its source-file SHA-256 value,
unit rate, entry version and record version exactly match the hash-bound
release manifest snapshot. It records the pricing-release version and manifest hash in
the quote receipt.

The rendered commercial rate is therefore traceable to a specific immutable
pricing record. It remains commercial evidence only: it never proves technical
suitability, a passive-fire system selection, or the actual physical condition.

## Mandatory client-facing wording

Every rendered desk quote states that:

1. it is an assumption-led commercial allowance based on named retained
   evidence, with no site inspection represented;
2. a material difference found at access or before work requires scope and
   price review before proceeding; and
3. it is not a technical system selection, installation certification or
   compliance determination.

The PDF and spreadsheet include an assumption register with the source
locators, probability, alternatives, commercial treatment and verification
action. Exclusions and variation risks appear alongside the price, not only in
an internal record.

## Application export

Authorised estimators use `POST /api/v1/desk-quotes/export/{artifact_type}` with a
complete `CLASSIFIRE_DESK_QUOTE_V1` payload. The supported artifact types are
`desk-quote-pdf` and `desk-quote-xlsx`.

Before it builds the receipt, the endpoint resolves every evidence locator to
an active EvidenceSource in an estimate for the named project. The source must
have the named immutable retained file, matching SHA-256 digest, matching
source reference, approved storage purpose and safe scan status. It also
resolves each allowance against the declared active pricing release and rejects
absent, inactive, expired, wrong-currency or non-manifest records. It renders
only the resulting hash-bound desk-quote receipt, stores the output under that
receipt hash, and records an audit event containing the quote reference,
artifact type, document class, non-technical position, pricing-release identity
and resolved evidence identifiers/digests. It does
not require or create a canonical Physical Model, active Physical Model Lock,
technical selection, approved estimate or release.

## Safety boundary

`site_observation` remains reserved for genuine retained observations and must
not be used to record a desk assumption. A desk quote has no canonical-model write capability. It cannot create an Opening, Service, link,
Physical Model Lock, technical selection, approved estimate or release.

Existing locked-estimate export remains unchanged. The desk-quote renderer is a
parallel, proposal-only artifact; it never weakens the approval gate for a
canonical technical estimate.

## Integrity

The renderer accepts only a hash-bound
`CLASSIFIRE_DESK_QUOTE_SNAPSHOT_V1` receipt. Before rendering, CLASSIFIRE
rebuilds the receipt from the source proposal and rejects any difference in the
assumptions, commercial allowances, totals, qualifications, exclusions,
verification actions, resolved pricing bindings or hash. The PDF and spreadsheet
show the governing pricing record for every allowance.

## Follow-up

At first access, compare the actual condition with the assumption register.
Confirmed differences require an explicit governed amendment or variation. The
desk quote must never be retrospectively described as a confirmed technical
assessment merely because the original allowance happened to be correct.
