# Package 16 profile split plan

Status: DEVELOPMENT / REAPPROVAL REQUIRED

Historical source: `PFEOS_16_Runtime_Profile_and_Data_Readiness_v2.8.txt`.

Package 16 must not be copied wholesale into production agent prompts. Migrate it into separately versioned, reviewable profiles:

1. Organisation Profile
2. Jurisdiction Profile
3. Technical Policy Profile
4. Commercial Policy Profile
5. Runtime Capability Profile
6. Output and Brand Profile
7. Security and Retention Profile

## Rules

- Preserve the historical Package 16 source unchanged.
- Every migrated field retains source document/version/section provenance.
- Mutable operational settings must become structured records, not buried prompt text.
- Conflicting or stale values remain blocked until reviewed.
- No split profile receives production authority until owner reapproval and regression testing.
- Jobs/estimates must pin the exact approved profile releases used at calculation time.

## Immediate blockers

- Full Package 16 field-level extraction and conflict register not yet committed to this repository.
- Current approved organisation, jurisdiction and commercial values must be reconciled against the historical source.
- Brand/runtime/security settings require independent review before release.

## Acceptance criteria

Package 16 migration is complete only when all seven profiles have schemas, migrated records, provenance, release IDs, hashes, approval records and tests, and an approved aggregate runtime manifest references those exact profile releases.
