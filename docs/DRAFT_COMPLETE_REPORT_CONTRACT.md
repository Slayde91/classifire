# Complete Draft report profile

Status: implemented Draft profile under accepted ADRs 0001/0002. The explicit
multiple-review extension is locally validated; publication and restart verification
are tracked in [PROJECT_STATE.md](./PROJECT_STATE.md), not inferred from source presence.

## Interaction and boundaries

Open a saved Draft Estimate, choose Estimate PDF/XLSX reports, select the Complete
profile and preview. Explicit creation retains PDF and XLSX together from that
Estimate revision and its embedded Scope/optional System Match. The Complete profile
also accepts explicitly selected additional row reviews, with the exact inclusion
rules below. Historical revisions are allowed; the UI warns when their retained
dependencies changed or are unavailable.
No matching, pricing, upstream mutation, provider, canonical write or release runs.

Complete means all available saved sections, not complete evidence, applicability,
commercial recovery or production approval. An empty Estimate may be reported: missing
commercial work and a missing System Match are explicitly unavailable. Zero subtotal
is not a quote. Unknown quantities/rates stay unknown; partial AUD amounts exclude
uncalculated tax. Saving a report does not endorse imported or manual claims.

## Additive snapshot and lifecycle

`draft_estimate_reports.create_report(..., profile="complete")` reuses the existing
DraftEstimateReport table, exact source validation, paired output transaction and
checksum/retention checks. Without a review collection, the snapshot remains
`CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v2`, profile `complete`; existing renderer dispatch
selects versions 3/5/7/9/11 according to retained evidence. Its fields remain one full
validated Estimate envelope plus project labels, report identity, author/time,
Draft/unreviewed status and snapshot hash. Mixed schema, profile, renderer or
authority combinations fail validation. Existing Estimate and embedded review
versions remain supported through their shared validators.

The default service call and original two-field POST still create estimate-only
reports with the original schema/renderer rules. Only the complete form sends the
profile field. Unknown profiles, duplicate scalar fields, unrecognized fields and
invalid revisions are refused; only the explicit `matches` field may repeat. GET
preview supports `profile=estimate-only|complete`; the existing
report detail/download routes derive their profile from the validated saved snapshot.
History labels identify the profile. No database migration or dependency is added.

Creation verifies the exact retained Estimate, each selected review and current
project labels again after rendering, then persists both files atomically. Reads
verify source/snapshot/output
integrity and return original bytes without rerendering. Later Scope, review, source,
pricing, Estimate or project changes produce current UI staleness warnings without
rewriting earlier files. Downloaded snapshots describe the saved basis; a later
staleness assessment is not silently stamped into those immutable bytes.

## Explicit review collection

`draft_estimate_reports.preview_report(..., revision=N, profile="complete", matches=refs)`
reads exact saved inputs without allocating report IDs, rendering or writing.
`create_report` accepts the same optional list of `{match_id, match_revision}` pairs.
A nonempty list creates `CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v3`, render version 12,
with `system_matches` holding full exact review envelopes sorted by review ID.
The original Estimate envelope, including its embedded Scope and optional review,
is retained unchanged. This extends the existing Complete profile and table; it
adds no model, migration, dependency or report profile.

The collection contains one to thirty unique reviews for distinct Opening/Service
rows or blank Openings, all bound to the Estimate's exact embedded Scope. If the
Estimate has an embedded review, the user must explicitly include that full exact
revision. A missing dependency, substitution of a newer bound-review revision,
duplicate ID, competing row target, Scope mismatch or non-Complete profile fails; the service never fills a missing
selection, substitutes a latest revision or drops to another profile. Shared Services
remain distinct at each Opening. Review count is never a work quantity.

The browser route is
`/scopes/{draft_id}/estimates/{estimate_id}/reports?revision=N&profile=complete`
with repeated `matches=UUID:revision` parameters. `N` is the saved Estimate revision;
its Scope revision is displayed and cannot be independently substituted. The picker
retains exact selected older reviews outside the recent twenty. Without an explicit
collection, the Estimate-bound review is offered unchecked, preserving the legacy
form and snapshot. Legacy service-only or nonblank-opening-only reviews remain
available in the existing Complete report; they cannot be added to a row-review collection.
A separate CSRF-protected POST submits the previewed revision, profile and references.

Additional reviews are labeled report-only context, separate from the Estimate-bound
review. Original rates, overrides, partial totals, unknown quantities/rates, tax and
recovery are unchanged; adding technical context does not approve or price more work.
The collection JSON limit is the existing Estimate limit plus thirty existing review
limits plus 8 KiB. Each output remains capped at 8 MiB. Oversized output fails without
omitting reviews or source history. Empty/absent collections retain legacy dispatch.

## Permissions and presentation

Reuse active-human project ownership, project/Estimate read/write, technical read
for every included review, library read for retained workbook selections, and explicit
Estimate export permission for downloads. These checks apply to historical reads
and are rechecked at existing service boundaries. CSRF and bounded forms remain.
No import, approval, lock, foreign authority or release privilege is created.

The typed client `estimate_report` command accepts the same optional `matches` list
only for profile `complete`. Its technical, Estimate and export grants remain
separate from local permissions. Preparation, pending review, confirmation, retained
reads and downloads recheck applicable authority. Same-user browser confirmation
is separate from proposal creation and package confirmation. Legacy command
serialization and five-field input hashes remain unchanged when no collection is
present. No grant, OAuth, tunnel or host-policy change is part of this increment.

PDF includes readable physical Scope, saved technical findings, work lines,
originals/overrides, omissions/unknowns, source/pricing history and detailed retained
technical evidence. The existing Scope composition is shared without changing its
content. XLSX retains exact decimal text and safe optional numeric subtotals, with
filterable technical summary, coverage, candidates and measured-limit sheets added
to existing Estimate sheets. Formula/URL interpretation stays disabled. Original
source files are not embedded or redistributed by this report. The supplied logo
is retained unchanged. Both outputs derive from one frozen snapshot.

## Package history and rollback

ProjectPackage v6 can retain the Complete pair only with the exact selected Estimate
and all exact report review dependencies. It reuses import mapping v4, including
all report review source IDs/revisions/hashes and available local bindings. A retained
ancestor collection report also requires v4; ancestor-only bindings may remain
nonlocal. Imports remain unapproved, and original report/archive bytes survive
import and re-export. Packages without collection reports keep older mapping shapes.
No new package or import schema is introduced for Complete reports.

Older binaries cannot read new Complete v3 reports. Mapping-v4 readers from the
Scope-and-system collection increment must also understand the Complete v3 report before
reading these new imports. A binary downgrade after new writes is not a transparent
rollback. Any activation needs its approved exact-version backup/storage, disposable
restore, restart and rollback plan; preserve later records and original files.

## Verification and remaining work

Synthetic tests cover exact Estimate retention, original/override decimal text,
unknown work, absent or historical reviews, explicit dependencies, incompatible
selections, atomic paired output, no upstream writes, ownership/permissions/client
grants, stale history, package import ancestry and exact original-byte re-export.
Existing Estimate-only and Complete legacy UI behavior remains covered.

The isolated Complete browser journey separately saved the report and package with
three selected reviews and Estimate revision 4. Its partial subtotal remained 3.01,
with original rate 1.005, overridden rate 1.505 and an unknown second line retained.
The 21-page PDF was inspected in overviews and at readable pages 1 and 3; desktop
and mobile views showed no observed clipping. XLSX contents and the ZIP were inspected,
and the packaged pair matched the saved report bytes. Native Excel visual inspection
was not performed.

An actual isolated port-8844 restart preserved exact PDF/XLSX/ZIP/Scope bytes and all
66 checked domain-table hashes. A second restart also verified exact raw downloads
of Estimate revisions 2 and 4. The first verifier had compared pretty-printed fixture
JSON with compact download JSON; values and the original pre-restart ZIP Estimate
bytes matched. That failed comparison was retained, corrected to raw-byte comparison
and rechecked without an application change. Current receipts and publication status
belong in PROJECT_STATE.md. This does not establish customer accuracy, production
readiness or Phase 13/14 exit.

ProjectPackage and typed client reporting reuse existing implemented paths. Remaining
work includes representative physical/technical/commercial acceptance, governed
production gates and any separately approved activation. A register shortcut to
Complete reporting is deferred; the existing Estimate report route is available.
