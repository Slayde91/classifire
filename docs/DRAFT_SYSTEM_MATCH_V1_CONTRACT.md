# Draft System Match v1 contract

Status: P2a candidate-review prototype under accepted ADR 0002. A user selects a
saved Draft Scope revision, an explicit technical release and one target, inspects
retrieved candidates and missing criteria, records keep/reject notes, and saves or
downloads that unapproved review. This is not P2b applicability assessment.

## Shared use cases and authority

`services/draft_system_matches.py` owns creation, review persistence, authorization,
retained reads, downloads and separate staleness checks. The pure bounded contract
is in `services/draft_system_match_contract.py`. The standalone UI calls those
services; a future ChatGPT adapter can use the same commands.

- `create_match(db, actor, draft_id, scope_revision, release_id, opening_id,
  service_id, *, storage_root)` returns a persisted `DraftSystemMatch` with its
  first immutable review revision. The caller commits or rolls back.
- `list_matches` shows the newest 20 matches for a Draft; older IDs remain valid.
- `read_match_revision(..., match_id, revision=None)` returns the selected saved
  envelope. Omitting revision means the current saved review, not a new search.
- `save_review(..., match_id, expected_revision, decisions)` appends a revision
  using atomic compare-and-swap. Every retained candidate must appear once, with
  `candidate_id`, `decision` (`unreviewed`, `keep`, `reject`) and notes up to 4,000
  characters. Foreign IDs, duplicate IDs, extra fields and approval values fail.
- `revision_bytes(..., revision=None)` returns exact retained canonical JSON bytes.
- `match_staleness(..., revision=None, *, storage_root)` returns safe reason codes
  for live dependency changes. It never changes the retained review or runs search.
- `list_technical_releases(db, actor)` supplies lightweight active release choices;
  being listed does not prove the release passes creation checks.

Every access requires an active persisted human, `project:read`, `technical:read`,
and Draft ownership or administrator role. Creation and review saves additionally
require `project:write`. Creation rechecks access after source verification. A
technical reviewer role alone does not confer ownership of a project. Agents are
refused. This reuses existing application permission boundaries; it does not add
production tenant isolation or new source-document download rights.

`keep` means retained for further investigation, never Applicable or approved.
Reviewing a stale artifact is permitted because it only appends unapproved notes;
stale warnings remain visible. Different Scope/release inputs or another retrieval
require explicit creation of another match artifact.

## Target and retrieval coverage

At least one opening or service must be explicitly selected. If both are selected,
the saved Scope must contain their link. Opening-only selection represents that
whole opening; blank openings remain distinct. Service-only selection captures all
its saved opening links and explicitly states that no opening was selected.

The entire verified Scope v1/v2 envelope, including import provenance and uncertainty,
is retained. Coverage is always `selected_target_only`. Captured related entity IDs
provide context; the envelope identifies other opening/service IDs not assessed.
These lists do not imply that the selected target itself has passed applicability
assessment. No canonical Opening, Service or Estimate is created or selected.

Retrieval reuses `technical.search_variants` with explicitly validated release IDs,
`include_draft=False`, deterministic ID ordering before its bounded SQL prefilter,
and an ID tie-break for equal scores. It retains at most 20 results and reports
truncation when a 21st result exists. Retrieval is a limited shortlist, not an
exhaustive search or compatibility test.

Only explicitly selected service type and opening substrate supply search inputs.
Opening plane is not converted into orientation; opening dimensions are not treated
as service size. Missing material, FRL, insulation, dimensions, substrate thickness,
installation details and other criteria remain missing. Hard exclusions, dependencies,
shared-opening configuration and professional evidence review remain unassessed.
Candidate metadata exposes existing library constraints for inspection without
claiming those constraints were evaluated. SQL/text overlap and numeric scores are
retrieval signals only.

## New-creation release and source checks

Creation selects a release by ID and validates its technical type, manifest hash,
active status, effective date, manifest structure, unique IDs and declared record
count. Manifest size is bounded to 10,000 records. Existing current-release checks
validate variant activity/dates and bound document/StoredFile authority. Available
published identity, source and record-version values must match current variants.

The existing release format does not freeze every technical field. This artifact
therefore captures an allowlisted technical-field projection, its fingerprint,
record version, selected published record metadata, and source identity/locator
metadata. Source JSON, storage paths, file bytes, arbitrary manifest fields and
private access URLs are excluded. Source bytes remain in governed storage.

A source is labeled `bound`/`exact_bytes` only when the published source binding
matches the current approved document and immutable clean StoredFile and the existing
storage verifier checks its exact bytes. The variant/source/manifest hashes must
agree. Reads are deduplicated by StoredFile ID and bounded to 64 MiB in total for
the selected candidates. PostgreSQL uses the existing serialized clean-byte reader;
SQLite remains an isolated prototype and does not claim production containment
serialization. No malware verdict is fabricated or changed.

Legacy manifests without source bindings and legacy unbound records can appear only
as unresolved diagnostic candidates. Their observed source binding metadata and
variant source hash are retained so later locator/hash changes are detectable; these
observations do not become verified source evidence. Missing published record
versions are explicit blockers. Invalid current authority or invalid bound source
bytes refuse new creation without retaining a partial review.

## Immutable envelope and persistence

Forward migration `0029_draft_system_matches` creates a parent record and immutable
`draft_system_match_revisions`. The parent is bound by foreign key to a saved Scope
revision and the chosen release; it records their hashes, an immutable basis hash,
and current review revision/hash. Each revision has its own parent hash, exact JSON,
checksum, local actor and UTC timestamp. Downgrade refuses destruction of history.

The envelope has exactly these fields:

| Field | Meaning |
|---|---|
| `schema_version` | `CLASSIFIRE-DRAFT-SYSTEM-MATCH-v1` |
| `artifact_id`, `project_id` | Local match and project identities |
| `revision`, `parent_hash`, `sha256` | Immutable review lineage and envelope checksum |
| `created_by`, `created_at` | Local human actor and canonical UTC time |
| `state`, `review_status`, `provenance` | `Draft`, `unreviewed`, `manual_review` |
| `coverage` | `selected_target_only` |
| `scope` | Entire verified selected Scope v1/v2 envelope |
| `release` | Explicit ID, version, hash and effective date |
| `target` | Selected identities, retained links, blank status and unassessed IDs |
| `retrieval` | Version, inputs, missing/unassessed criteria, result limit/truncation and time |
| `candidates` | Fixed fields/fingerprints, source/published metadata, score, comparisons and blockers |
| `decisions` | One unapproved keep/reject/unreviewed decision and note per candidate |

Every source entry contains `state`, `binding`, `variant_source_hash`, `verified_at`
and `verification`. Observed binding metadata may exist while verification remains
`unresolved`; it must not be displayed as a published or verified binding.

Canonical JSON uses sorted keys, compact separators, UTF-8 and no nonfinite values.
The envelope is bounded to 1 MiB. Its checksum covers all fields except `sha256`.
Review saves preserve the entire basis; only decisions and revision metadata change.
Concurrent stale saves fail rather than overwrite another review. Failure/caller
rollback retains neither a partial artifact nor a creation/review audit. Audit
payloads contain identities, revisions and hashes, not notes or technical text.

Retained reads validate the strict contract, exact serialization, checksum, database
identity/time bindings, parent hash, immutable basis and original saved Scope
integrity. These are integrity checks, not signatures or proof of technical approval.
Database administrators remain trusted. This slice does not import System Match
artifacts or confer authority on claims from another installation.

## History versus current dependencies

Retained reads and downloads do not require the captured release to remain active.
Supersession, source expiry/quarantine and newer Scope revisions must not erase
review history. Saved bytes do not change and download does not rerun retrieval.

Separate freshness checks compare the latest Scope, current release identity/type/
version/hash/dates, current candidate fields/status/dates, and current source binding,
variant hash and authority. Exact-byte checks on previously verified sources detect
changed files even if their database path/hash metadata did not change. Unverified
legacy sources remain unresolved rather than acquiring authority through reopening.
Newer releases, unavailable/changed dependencies and source verification failures
produce visible safe reason codes. Historical metadata remains downloadable even
when current source use is blocked; source files are never included in this export.

This bounded slice stops at candidate review. Applicability coverage, technical
selection, pricing, estimating, report integration and complete ProjectPackage
portability retain their own later milestones and authority requirements.


## Compatible measured-review extension

v1 remains the retrieval/keep/reject contract above. Explicit measured-limit review
can append `CLASSIFIRE-DRAFT-SYSTEM-MATCH-v2` to the same artifact. It retains v1
basis/history and adds partial substrate/gap checks with manual measurement claims.
See [the v2 extension and demo](./DRAFT_CONSTRAINT_REVIEW.md). New technical release
v3 snapshots public fields; historical releases are not rewritten. Partial checks
never grant applicability or approval and do not change existing v1 bytes.

## Additive measured-size version

The [v3 service-size review](./DRAFT_SERVICE_SIZE_REVIEW.md) extends saved numeric
review with observed ranges and explicit measurement/source meanings. V1/v2 validation
and retained bytes remain unchanged. New semantics require the v3 envelope and an
explicit v3 save; unsupported meanings never become technical approval.

## Imported-origin amendment

Imported v4 wraps validated native v1/v2/v3 content with an explicit unverified
origin. It has no local LibraryRelease eligibility; saved decisions and notes remain
editable, while foreign candidates, source constraints and original history remain
retained. See [ProjectPackage import](./DRAFT_PROJECT_PACKAGE_V1_CONTRACT.md#imported-project-lifecycle-and-v2-re-export).
