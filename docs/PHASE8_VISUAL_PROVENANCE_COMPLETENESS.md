# Phase 8 current visual-provenance completeness

Use this check when a Phase 8 proposal consumer needs proof that the current
linked visual run and its evidence-family inventory describe the same evidence
scope. It reads only the two JSON artefacts; it does not retrieve reports or
images, perform inference, access the database, create canonical state, or
create a Physical Model Lock.

`PASS` requires all of the following:

- a valid linked-visual-run receipt with an approved visual result;
- the expected estimate ID and defect reference exactly match the receipt;
- a structurally valid, content-free evidence-family inventory;
- the inventory's canonical SHA-256 matches the receipt; and
- the inventory's source-manifest SHA-256 matches the receipt.

Any blocked run, stale scope, malformed receipt, missing inventory, or hash
mismatch returns `INCOMPLETE`. It must not be treated as a substitute for a
human technical decision, a canonical submission, or a lock.

Assess two retained JSON artefacts directly:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts\assess_phase8_visual_provenance.py `
  --linked-visual-run-receipt C:\path\to\linked-visual-run-receipt.json `
  --evidence-family-inventory C:\path\to\evidence-family-inventory.json `
  --estimate-id ESTIMATE_ID `
  --defect-reference DEFECT_ID
```

For a new human-adjudicated proposal consumer that must also bind the source
visual-controller receipt, use both options with the existing proposal-only
validator:

```powershell
C:\CLASSIFIRE\.venv\Scripts\python.exe scripts\validate_phase8_human_adjudicated_proposal.py `
  --source-proposal C:\path\to\source-proposal.json `
  --source-controller-receipt C:\path\to\controller-receipt.json `
  --human-review-request C:\path\to\human-review-request.json `
  --human-review-response C:\path\to\human-review-response.json `
  --revised-proposal C:\path\to\human-adjudicated-proposal.json `
  --linked-visual-run-receipt C:\path\to\linked-visual-run-receipt.json `
  --evidence-family-inventory C:\path\to\evidence-family-inventory.json
```

The paired options deliberately select the stricter versioned validation mode.
Without both options, the historic proposal-only validator remains unchanged.
Even the strict result is `PASS_PROPOSAL_ONLY_WITH_LIMITATIONS` and
`admission_eligible: false`.
