# Package 16 profile split plan

Status: DEVELOPMENT / BLOCKED PENDING VERIFIED QUANTIFIRE v2.13 SOURCE

## Source authority

The active migration source for Package 16 must be the verified QUANTIFIRE v2.13 Package 16 release. Earlier PFEOS v2.8 material is historical migration lineage only and must not be used as active runtime authority or substituted where v2.13 is missing.

## Target profile decomposition

Package 16 must not be copied wholesale into production agent prompts. After the v2.13 source is verified, migrate it into separately versioned, reviewable profiles:

1. Organisation Profile
2. Jurisdiction Profile
3. Technical Policy Profile
4. Commercial Policy Profile
5. Runtime Capability Profile
6. Output and Brand Profile
7. Security and Retention Profile

## Rules

- Preserve the verified v2.13 source unchanged as evidence.
- Every migrated field retains source document/version/section provenance and SHA-256 lineage.
- Mutable operational settings become structured records, not buried prompt text.
- Conflicting or stale values remain blocked until reviewed.
- No split profile receives production authority until owner reapproval and regression testing.
- Jobs/estimates pin the exact approved profile releases used at calculation time.
- Historical PFEOS v2.8 Package 16 content may be retained only in the compatibility/migration register.

## Immediate blockers

- Verified QUANTIFIRE v2.13 Package 16 source file has not yet been confirmed in the controlled source inventory.
- Field-level extraction cannot begin until the exact source file and SHA-256 are recorded.
- Current organisation, jurisdiction, commercial, brand, runtime and security values must be reconciled against the verified v2.13 source.

## Acceptance criteria

Package 16 migration is complete only when all seven profiles have schemas, migrated v2.13-derived records, provenance, release IDs, hashes, approval records and tests, and an approved aggregate runtime manifest references those exact profile releases.
