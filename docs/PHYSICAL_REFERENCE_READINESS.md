# Physical reference comparison readiness

This is preparation for a later authorised accuracy assessment, not a benchmark,
model evaluation, new reference schema or permission to execute customer evidence.
The existing Phase 8 and Phase 8C gates in the roadmap remain unchanged.

## Current implementation and evidence

The existing `phase8_human_reference_comparison.py` service and
`scripts/compare_phase8_human_reference.py` compare a completed, receipt-bound
proposal with an explicitly supplied post-inference reference. They have no database,
inference, signing or lock interface. Reuse them for their supported contract.

That contract (`CLASSIFIRE-HUMAN-PHYSICAL-REFERENCE-v1`) requires a definite opening
count, a Boolean blank/occupied value and explicit service groups for each opening.
Service material and quantity may be unknown. A completed proposal must satisfy the
existing controller, policy and evidence-binding validation before comparison.
A PASS is agreement with this reference for one supported defect, not a general
accuracy score or technical approval. Existing substrate matching is limited and
is not a calibrated physical-material classifier. A null expected substrate imposes
no substrate assertion; it does not measure unsupported claims or abstention quality.

The privately retained Draft reference was explicitly confirmed by the user after
review of assistant-generated findings and unknowns. Its provenance remains visible.
It is neither an independent blind holdout nor the definite-topology reference above.
Do not convert uncertain opening counts, vacancy, group membership or material into
fixed facts merely to satisfy the existing comparator. No application analysis or
accuracy percentage has been established by that review.

Optional Draft PDF suggestions currently use one page's extracted text and raster.
They do not automatically retrieve or analyse linked full-resolution photographs, and
they do not generate measured quantity or dimension values. Retained source intake,
manual review and proposal services are foundations to extend, not a full-report
accuracy workflow to claim complete.

## Proposed review taxonomy

Before choosing any future metric or threshold, preserve these independent fields:

| Dimension | Required distinction |
| --- | --- |
| Identity and relationships | Defect, opening and service identity; shared groups; repeated views; unresolved parent relationships |
| Physical observations | Type, material, substrate, plane, orientation and dimensions; source text versus image observations |
| Quantity | Known value and unit, lower bound or candidate count, unresolved count; no default one or zero |
| Evidence state | Confirmed, inferred, provisional, unknown, contradictory or awaiting review |
| Outcome | Correct supported claim, missed claim, unsupported additional claim, wrong link, incorrect certainty or appropriate abstention |
| Provenance | Exact source version and locator, extraction/transformation, prediction version, reviewer and correction history |

This table is a preparation checklist, not a new persisted domain model. Reference
uncertainty and prediction uncertainty must remain separate. The chosen evaluation
contract must support unresolved topology and withholding before this Draft reference
can be used without loss. Preserve original predictions and later corrections;
never relabel a corrected result as an independent original prediction.

## Gates and next executable work

1. Continue synthetic diagnostics and contract tests against existing services. Fix
   demonstrated defects without weakening validators or changing reviewed facts.
2. Complete the Phase 8 ordered recovery, a defensible replacement lock and an
   end-to-end prototype reaching snapshot-backed outputs before beginning the Phase
   8C programme. Only charter, taxonomy and data-rights preparation
   is authorised by that roadmap stage until its prerequisites are met.
3. Record the exact intended use and rights for each source family. Permission for
   local review or linked-photo download does not imply provider transfer, training,
   redistribution, canonical writes or a live project change. Keep private sources and
   signed URLs out of Git, fixtures, logs and model inputs unless that use is authorised.
4. Prepare an exact run plan using the current authorised runner, selected source
   hashes, provider/egress boundary, budget, stop rules, isolated state and retained
   outputs. Obtain any required run authority before execution. Keep reference answers
   out of inference inputs; define rights-cleared family splits and holdouts before tuning.
5. Once gates and authority are satisfied, compare an actual uncorrected application
   output, account for every expected defect and retained unknown, and report supported
   coverage and errors with their denominators. Do not invent pass thresholds or a
   single accuracy percentage from a manually compiled review.

No system matching, estimating, canonical submission, lock or release is implicit in
an accuracy run. Each remains independently requested and governed.
