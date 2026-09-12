# Multiple row reviews in a Draft project package

## User outcome

The register can show exact saved reviews for several Service rows and blank Openings.
Saving a review replaces that row's displayed reference and preserves the other choices.
An explicit ProjectPackage preview and separate save retain the whole chosen set.
Reopening the saved package uses those revisions even when newer reviews exist.
The working URL holds the current choices; a package is their durable checkpoint.

## Architecture and compatibility

Current architecture: independent immutable Scope, Match, Estimate and report artifacts
are composed by the existing ProjectPackage service. The initial register and package
selected one Match. A second row review displaced the first visible choice.

Change: a bounded exact Match collection in the register and forward package v6, plus
collection-aware inspection and imported identity mapping v3. Existing models already
store multiple Match artifacts and versioned package bytes. No selection table, model,
database migration, provider or canonical authority is added. Migration head remains 0047.

Legacy v1-v5 selections, paths, original archives and validation remain unchanged when
the new collection is absent or empty. A single legacy register review still uses the
legacy package pair, including service-only or occupied-opening-only historical targets.
New collections require explicit row targets. Older application versions cannot read
new v6 packages or mapping-v3 imports; a binary rollback after creating them is not
a transparent downgrade. Preserve the new records and original archives, and use an
explicit recovery plan rather than rewriting formats or restoring over user work.
An invalid register selection retains the manual editor and a visible warning; it cannot offer a silently reduced package link.

## Contract

A new selection uses `matches: [{match_id, match_revision}, ...]`. The collection is
sorted deterministically, contains at most 30 references, and cannot accompany a nonempty
legacy `match_id`/`match_revision` pair. IDs and revisions are explicit; the reader never
substitutes latest. Exact authorized reads bind the saved hash and Scope.

Row identity is Opening plus Service, or the blank Opening alone. Different reviews or
revisions for the same row are refused rather than resolved by last-write-wins. Historical
shared Services remain Opening-qualified and stay in the relationship review queue.
Empty or invalid relationships are not repaired by selecting or packaging a review.

Each Match is stored at `artifacts/system-match-{UUID}.json`. V6 retains the existing
128 MiB / 32-member aggregate archive limits and 2 MiB manifest limit. Thirty review references
is an upper bound, not a promise that every source/report combination will fit. Oversized
membership fails visibly; files or reviews are never silently truncated.

An optional Estimate still uses its one existing embedded Match, or no Match. In v6 that
exact dependency must be among the selected reviews; additional reviews do not become
Estimate inputs. Existing Scope/system and Estimate/complete reports retain their exact
snapshots and files. Each embedded Match must belong to the chosen set. Packaging several
reviews does not produce a combined multi-review report or rerun matching or calculations.

## Import and authority

V6 import validates every review and dependency before a transaction materializes all
local Match rows. Mapping-v3 records each original and local ID/revision/hash. An Estimate
is attached to its particular mapped dependency, never an arbitrary collection member.
Direct retained reports record their exact source/local review binding. Ancestor-only
reports retain their original identity with no fabricated local binding.

Original ZIPs, decisions, unknowns, provenance and report bytes remain retained. Imported
claims remain foreign and unverified. Scanning checks file safety, not technical truth.
Current source permissions, quarantine checks and nested-origin protections still apply.
No import creates an eligible technical release, canonical model, lock or human release.

Client package preparation, review, confirmation, download-link and ZIP access require the
technical client grant for any selected review collection. Local user permissions alone
cannot substitute for that grant. A tool prepares a pending request; a separate logged-in
browser confirmation with CSRF protection remains necessary to save it. No grant is widened.

## Acceptance checkpoint and limits

Synthetic service and UI tests cover old bytes, exact selections, duplicate/wrong-Scope
refusal, permissions/revocation, conflicts, rollback, import mappings, Estimate dependencies,
retained reports and nested originals. The actual isolated Edge journey creates reviews
for two Service rows and a blank Opening, updates one without losing the others, separately
saves/downloads v6, and reopens the exact set. A later review does not change that saved set.
Desktop/mobile screenshots and the ZIP are retained privately for inspection.

Exact test counts, restart results and Git/CI publication belong in PROJECT_STATE and the
private receipt; this contract alone is not test or deployment evidence. One Estimate is
still selected at a time. Existing single-review report formats remain unchanged. Broad
automatic interpretation, project-wide matching, calibrated pricing, large-project capacity
and production roadmap exits remain incomplete. Live 8820, OAuth/tunnel/host policy and
provider activation are outside this increment's authority.
