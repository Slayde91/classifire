# Draft measured-limit review: contract and synthetic demo

This first P2b interaction compares two numeric constraints, not full system
compatibility. State remains Draft/unreviewed. No technical selection, pricing,
canonical model, lock, AI or release runs automatically.

## Versioned contract

Existing `CLASSIFIRE-DRAFT-SYSTEM-MATCH-v1` retrieval/review bytes remain valid.
Explicit measurement review appends v2 to the same artifact/revision table. It keeps
the original Scope/release/target/candidates/retrieval basis and adds:

- One `candidate_id` from that exact saved candidate list.
- Inputs: substrate_thickness_mm, annular_gap_min_mm, annular_gap_max_mm, and a
  required measurement_note describing source/observation, method and interpretation.
- Manual reviewed_by/reviewed_at, published_fields_sha256 (or null for an older
  publication), deterministic checks, status partial_unapproved and explicit
  unassessed conditions. These are review claims, not authenticated measurement evidence.

Numeric inputs are nonnegative decimal strings in mm, at most ten integer digits
and four fractional digits. Thickness must be positive; a known measured minimum
cannot exceed its maximum. Null means unknown. Exponents, units embedded in numbers,
commas, nonfinite values and numeric coercion are refused. No rounding or conversion
from opening dimensions, Scope counts or plane labels occurs.

For the selected opening, thickness compares to published minimum/maximum substrate
thickness. Annular gap additionally requires a selected linked service and compares
the smallest/largest measured clearances to published annular_gap_min/max. Bounds
are inclusive. Both source bounds and all measurements must exist for within_limits;
a violated known bound yields outside_limits. Inconsistent bounds, incomplete
measurements, unknown source constraints/binding or an unpinned old release yield
unresolved with a reason. Other conditions are always listed as unassessed.

New `CLASSIFIRE-TECHNICAL-LIBRARY-RELEASE-v3` publications freeze the existing public
technical field allowlist inside their hashed records. No private source_json,
storage path or confidential extra field is added. Publication still requires the
existing technical approver/source/active-record checks. No historical release is
rewritten. v1/v2 releases remain available for retrieval but cannot prove published
numeric fields. New review checks reject live fields that drift from a v3 snapshot.

The shared `save_constraint_review` command requires active project write/technical
read permission and existing Draft ownership/admin access. It locks the Scope/release,
checks current dependency/source integrity, and appends with existing revision CAS.
Browser POST also requires bounded exact form fields and CSRF. Stale basis/revision
saves fail; historical reads retain old results and current stale warnings. Keep/reject
notes do not erase measurement provenance. A new match revision makes an attached
Estimate stale without rewriting the Estimate or prior reports.

No migration or new dependency is introduced. Source-defined service-size semantics,
FRL/insulation/seal-depth/configuration/exclusion evaluation and full applicability
remain open. These partial results must never be relabeled Applicable.

## Run the isolated synthetic demo

From the verified feature checkout or merged main:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts/run_draft_scope_demo.py `
  --data-dir C:\CLASSIFIRE\.tmp\my-new-constraint-demo `
  --port 8804 --seed-constraint-library
```

Choose an unused port and a new empty directory. Reuse the marked directory for
restart. The launcher accepts only isolated SQLite for library seeding and refuses
to adopt an existing different library. SYNTHETIC-P2B-001 is separate from P2A;
its retained fake PDF explicitly states thickness 100-200 mm and every annular gap
10-30 mm. These are test values, not fire-system advice or actual scanner/approval
results. The normal application never seeds this fixture.

1. Sign in with the printed synthetic account; create/import a Draft Scope with a
   linked pipe/opening pair. Save it and open System candidate review.
2. Select the synthetic release and explicit opening/service. Save retrieval.
3. Select a candidate. Enter thickness 100, smallest gap 10 and largest gap 30,
   plus a synthetic measurement/source note. Save measured-limit review.
4. Inspect within-limit reasons. Save thickness 99.9999 and observe outside_limits.
   Save blank measurements and observe unresolved. Nothing selects or approves a system.
5. Open earlier review revisions and download JSON. Restart with the same marked
   directory and verify the same historical bytes remain available.

Actual demonstration: loopback 8804; marked data `.tmp/constraint-demo-20260906`,
receipts/downloads/screenshots `.tmp/constraint-review-artifacts`, harnesses in
`.tmp/scope-browser-test-tools`. Four match revisions and exact r1/r2/r4 downloads
survived an actual process restart. The served logo matched the user PNG exactly.
These artifacts remain outside Git; PROJECT_STATE.md records validation/publication.
