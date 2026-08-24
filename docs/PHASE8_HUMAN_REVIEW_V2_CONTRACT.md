# Phase 8 Human Review v2 Contract

This contract strengthens future proposal-only human reviews. It does not
change the validity of historic v1 requests, responses, or adjudicated
proposals. A v1 artifact remains a historic, hash-bound review record; it does
not gain v2 item-level coverage retrospectively.

## Purpose

Version 2 makes every requested review point traceable to a human decision.
This prevents a response from being hash-bound to the request while leaving an
individual issue or unresolved observation silently unaddressed.

The contract is validation-only. It does not retrieve evidence, infer facts,
merge evidence, write the database, submit a canonical model, create a lock,
sign anything, call a gateway, or release output.

## Preparing a v2 request

Start from a valid v1 request and use
build_phase8_human_review_request_v2 to create a local draft. It assigns a
deterministic review_item_id to every entry in both review_items and
unresolved_blind_observations.

The draft has a new schema and therefore a new file hash. It must be treated as
a new review request. The converter deliberately does not manufacture a review
response or decide which human decision covers an item.

## Recording the response

Use schema:

CLASSIFIRE-PHASE8-HUMAN-EVIDENCE-REVIEW-RESPONSE-v2

Every defect_decisions entry must include a non-empty request_item_ids list.
Each ID must exist in the v2 request. Every request ID must be covered exactly
once across the completed response:

- One decision may cover more than one request item.
- An item cannot be repeated in two decisions.
- An unknown item ID is rejected.
- An omitted item is rejected.

review_item remains the stable decision identifier used by a later
proposal-only revision source reference. Only confirmed decision identifiers
may support a service in that revision.

## Validation

Use the existing local-only command:

    C:\CLASSIFIRE\.venv\Scripts\python.exe scripts\validate_phase8_human_adjudicated_proposal.py --source-proposal C:\path\to\proposal.json --source-controller-receipt C:\path\to\proposal-controller-receipt.json --human-review-request C:\path\to\evidence-review-request-v2.json --human-review-response C:\path\to\human-review-response-v2.json --revised-proposal C:\path\to\human-adjudicated-proposal.json

PASS proves the submitted JSON artifacts are structurally valid and hash-bound.
It does not independently prove reviewer competence, make an unconfirmed fact
certain, or authorize any canonical operation.
