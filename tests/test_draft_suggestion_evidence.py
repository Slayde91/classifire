from __future__ import annotations

import io
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from openpyxl import load_workbook
from test_draft_entity_evidence_outputs import page_reference, report_snapshot
from test_draft_scope_outputs import _id, _pdf_text, _seal, _snapshot
from test_draft_workbook_evidence_outputs import workbook_report, workbook_scope

from classifire.outputs import draft_estimate as estimate_outputs
from classifire.outputs import draft_scope as scope_outputs
from classifire.services import draft_estimate_reports as estimate_reports
from classifire.services import draft_package_import as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as scope_reports
from classifire.services.draft_scope_evidence import (
    SUGGESTION_EVIDENCE_SCHEMA_VERSION,
    observation_hash,
    reference_status,
    validate_suggestion_claim,
)

PROFILES = ("scope-only", "scope-and-system", "estimate-only", "complete")
VERSIONS = dict(zip(PROFILES, (7, 8, 8, 9), strict=True))
WHEN = datetime(2026, 9, 6, 3, tzinfo=UTC)


def suggestion_claim(kind, item):
    proposed = deepcopy(item)
    if kind == "defect":
        proposed["description"] = "Original proposed defect; location needs human review"
    else:
        proposed["state"] = "Inferred"
    if kind == "opening":
        proposed.update(width_mm=None, height_mm=None)
    elif kind == "service":
        proposed["quantity"] = None
    return dict(
        schema="CLASSIFIRE-DRAFT-PDF-SUGGESTION-CLAIM-v1",
        suggestion_id=_id(950),
        provider="scripted",
        model="synthetic-page-suggester",
        prompt_version="draft-pdf-suggestions-v1",
        input_sha256="1" * 64,
        response_sha256="2" * 64,
        page_image_sha256="3" * 64,
        generated_at="2026-09-06T02:00:00+00:00",
        proposed_item=proposed,
        basis="both",
        quote='=HYPERLINK("https://example.invalid/", "untrusted source text")',
        rationale="<script>untrusted suggested rationale</script>",
    )


def suggestion_scope():
    scope = workbook_scope()
    defect = scope["content"]["defects"][0]
    ref = scope["evidence_refs"][0]
    ref["suggestion"] = suggestion_claim("defect", defect)
    ref["target_sha256"] = observation_hash(defect)
    observation = dict(id=_id(951), text="Suggested uncertain observation", state="Inferred")
    scope["content"]["observations"].append(observation)
    scope["evidence_refs"].append(
        page_reference()
        | dict(
            target_kind="observation",
            target_id=observation["id"],
            target_sha256=observation_hash(observation),
            suggestion=suggestion_claim("observation", observation),
        )
    )
    scope["schema_version"] = SUGGESTION_EVIDENCE_SCHEMA_VERSION
    return _seal(scope)


def successor(prior, content=None, **kwargs):
    return scopes._revision_envelope(
        draft_id=prior["artifact_id"],
        project_id=prior["project_id"],
        actor_id=prior["created_by"],
        expected_revision=prior["revision"],
        created=WHEN,
        content=deepcopy(prior["content"]) if content is None else content,
        prior=prior,
        **kwargs,
    )


def test_mixed_v6_preserves_existing_pdf_workbook_and_original_suggestion_claims():
    scope = suggestion_scope()
    before = deepcopy(scope)
    assert scopes.validate_portable_artifact(scopes._json(scope)) == scope
    assert scope == before
    assert {r.get("source_kind", "pdf") for r in scope["evidence_refs"]} == {"pdf", "xlsx"}
    ref = scope["evidence_refs"][0]
    assert ref["suggestion"]["proposed_item"] != scope["content"]["defects"][0]
    assert "AI suggestion" in reference_status(ref, scope["content"])
    assert "no technical or physical approval" in reference_status(ref, scope["content"])


@pytest.mark.parametrize("kind", ("defect", "opening", "service", "observation"))
def test_original_proposed_items_reuse_the_normalized_draft_contract(kind):
    scope = _snapshot(imported=False)["scope"]
    item = scope["content"][kind + "s"][0]
    claim = suggestion_claim(kind, item)
    before = deepcopy(claim)
    validate_suggestion_claim(claim, target_kind=kind, target_id=item["id"])
    assert claim == before
    if kind != "defect":
        claim["proposed_item"]["state"] = "Confirmed"
        with pytest.raises(ValueError, match="suggestion authority"):
            validate_suggestion_claim(claim, target_kind=kind, target_id=item["id"])
    if kind == "opening":
        claim["proposed_item"].update(state="Inferred", width_mm="1")
        with pytest.raises(ValueError, match="suggestion dimensions"):
            validate_suggestion_claim(claim, target_kind=kind, target_id=item["id"])
    elif kind == "service":
        claim["proposed_item"].update(state="Inferred", quantity="1")
        with pytest.raises(ValueError, match="suggestion quantity"):
            validate_suggestion_claim(claim, target_kind=kind, target_id=item["id"])


@pytest.mark.parametrize(
    "field,value",
    (
        ("schema", "other"),
        ("suggestion_id", "not-a-uuid"),
        ("provider", "trusted-by-import"),
        ("model", ""),
        ("model", "x" * 101),
        ("prompt_version", "unbounded"),
        ("input_sha256", "A" * 64),
        ("response_sha256", 123),
        ("page_image_sha256", "a" * 63),
        ("generated_at", "2026-09-06T02:00:00"),
        ("generated_at", "2026-09-06T03:00:00+01:00"),
        ("basis", "inferred-from-price"),
        ("quote", "x" * 501),
        ("quote", False),
        ("rationale", "x" * 1001),
        ("proposed_item", {}),
    ),
)
def test_invalid_ai_metadata_is_refused_even_with_a_recomputed_artifact_hash(field, value):
    scope = suggestion_scope()
    scope["evidence_refs"][0]["suggestion"][field] = value
    _seal(scope)
    with pytest.raises(scopes.DraftScopeError, match="DRAFT_IMPORT_INVALID"):
        scopes.validate_portable_artifact(scopes._json(scope))


def test_claim_shapes_target_identity_and_legacy_versions_are_strict():
    original = suggestion_scope()
    for change in ("extra", "missing", "different_id", "unnormalized", "xlsx", "plain_observation"):
        scope = deepcopy(original)
        ref = scope["evidence_refs"][0]
        claim = ref["suggestion"]
        if change == "extra":
            claim["tool_authority"] = "canonical-write"
        elif change == "missing":
            claim.pop("response_sha256")
        elif change == "different_id":
            claim["proposed_item"]["id"] = _id(999)
        elif change == "unnormalized":
            claim["proposed_item"]["label"] += " "
        elif change == "xlsx":
            ref = next(r for r in scope["evidence_refs"] if r.get("source_kind") == "xlsx")
            ref["suggestion"] = deepcopy(claim)
        else:
            scope["evidence_refs"][-1].pop("suggestion")
        with pytest.raises(ValueError):
            scopes._envelope_shape(scope)
    for version in ("v3", "v4", "v5"):
        scope = deepcopy(original)
        scope["schema_version"] = "CLASSIFIRE-DRAFT-SCOPE-" + version
        with pytest.raises(ValueError):
            scopes._envelope_shape(scope)


def test_manual_edits_and_deleted_ai_observations_keep_originals_but_legacy_pruning_stays():
    original = suggestion_scope()
    before = scopes._json(original)
    content = deepcopy(original["content"])
    content["defects"][0]["description"] = "Human changed the location after review"
    content["observations"] = []
    edited = successor(original, content)
    refs = edited["evidence_refs"]
    assert edited["schema_version"] == SUGGESTION_EVIDENCE_SCHEMA_VERSION
    assert (
        edited["parent_hash"] == original["sha256"]
        and edited["revision"] == original["revision"] + 1
    )
    assert not any("observation_id" in ref for ref in refs)
    ai_refs = [ref for ref in refs if "suggestion" in ref]
    assert ai_refs == [ref for ref in original["evidence_refs"] if "suggestion" in ref]
    assert "Item changed since AI-assisted page review" in reference_status(ai_refs[0], content)
    assert "Item removed since AI-assisted page review" in reference_status(ai_refs[1], content)
    assert scopes._json(original) == before
    assert scopes.validate_portable_artifact(scopes._json(edited)) == edited


def test_human_page_rereview_retains_ai_origin_and_does_not_duplicate_reference_budget(monkeypatch):
    original = suggestion_scope()
    original_refs = deepcopy(original["evidence_refs"])
    content = deepcopy(original["content"])
    content["defects"][0]["description"] = "Corrected by the reviewer"
    ref = deepcopy(original_refs[0])
    ref.pop("suggestion")
    ref.update(target_sha256=observation_hash(content["defects"][0]), reviewed_at=WHEN.isoformat())
    reviewed = successor(original, content, entity_evidence_refs=[ref])
    saved = next(
        r
        for r in reviewed["evidence_refs"]
        if r.get("target_id") == ref["target_id"] and r["source_id"] == ref["source_id"]
    )
    assert saved["suggestion"] == original_refs[0]["suggestion"]
    assert saved["target_sha256"] == observation_hash(content["defects"][0])
    assert len(reviewed["evidence_refs"]) == len(original_refs)
    assert original["evidence_refs"] == original_refs
    # An exact next-envelope byte budget must include the retained original suggestion.
    exact = len(scopes._json(reviewed))
    monkeypatch.setattr(scopes, "MAX_ARTIFACT_BYTES", exact)
    assert successor(original, content, entity_evidence_refs=[ref]) == reviewed
    monkeypatch.setattr(scopes, "MAX_ARTIFACT_BYTES", exact - 1)
    with pytest.raises(scopes.DraftScopeError, match="DRAFT_ARTIFACT_TOO_LARGE"):
        successor(original, content, entity_evidence_refs=[ref])
    assert original["evidence_refs"] == original_refs


def test_v6_sticks_through_ordinary_pdf_and_workbook_reviews():
    prior = suggestion_scope()
    old = deepcopy(prior["evidence_refs"])
    observation = prior["content"]["observations"][0]
    ref = page_reference() | dict(
        observation_id=observation["id"],
        observation_sha256=observation_hash(observation),
        method="human_page_review",
        page_number=2,
    )
    after_pdf = successor(prior, evidence_ref=ref)
    workbook_ref = deepcopy(next(r for r in old if r.get("source_kind") == "xlsx"))
    after_xlsx = successor(after_pdf, entity_evidence_refs=[workbook_ref])
    assert (
        after_pdf["schema_version"]
        == after_xlsx["schema_version"]
        == SUGGESTION_EVIDENCE_SCHEMA_VERSION
    )
    assert [r for r in after_xlsx["evidence_refs"] if "suggestion" in r] == [
        r for r in old if "suggestion" in r
    ]
    empty_claims = deepcopy(prior)
    empty_claims["evidence_refs"] = []
    _seal(empty_claims)
    assert successor(empty_claims)["schema_version"] == SUGGESTION_EVIDENCE_SCHEMA_VERSION


def test_imported_claims_remain_unverified_and_survive_another_manual_revision():
    original = suggestion_scope()
    local = _snapshot(imported=False)["scope"]
    imported = successor(
        local, deepcopy(original["content"]), import_source=original, source_file_sha256="f" * 64
    )
    assert imported["schema_version"] == SUGGESTION_EVIDENCE_SCHEMA_VERSION
    assert imported["provenance"] == "imported"
    assert all(ref["origin"] == "imported_unverified" for ref in imported["evidence_refs"])
    for source, copied in zip(original["evidence_refs"], imported["evidence_refs"], strict=True):
        assert copied == source | {"origin": "imported_unverified"}
        assert (
            reference_status(copied, imported["content"])
            == "Imported source and review claims are unverified"
        )
    edited = successor(imported)
    assert edited["evidence_refs"] == imported["evidence_refs"]
    assert edited["import_lineage"] == imported["import_lineage"]
    assert scopes.validate_portable_artifact(scopes._json(edited)) == edited


def suggestion_report(profile):
    report = report_snapshot(profile, suggestion_scope())
    report["render_version"] = VERSIONS[profile]
    return _seal(report)


@pytest.mark.parametrize("profile", PROFILES)
def test_v6_reports_show_original_suggestions_and_human_facts_as_safe_literal_content(profile):
    snapshot = suggestion_report(profile)
    before = deepcopy(snapshot)
    service = estimate_reports if "estimate" in snapshot else scope_reports
    service.validate_report_snapshot(snapshot)
    if "estimate" in snapshot:
        pdf = estimate_outputs.render_estimate_report_pdf(snapshot)
        workbook = estimate_outputs.render_estimate_report_xlsx(snapshot)
    else:
        pdf = scope_outputs.render_scope_report_pdf(snapshot)
        workbook = scope_outputs.render_scope_report_xlsx(snapshot)
    text = " ".join(_pdf_text(pdf).split())
    book = load_workbook(io.BytesIO(workbook), data_only=False)
    cells = [c for sheet in book for row in sheet for c in row]
    strings = " ".join(str(c.value) for c in cells if c.value is not None)
    for expected in (
        "Original proposed defect; location needs human review",
        "Original AI proposal retained separately from human-edited facts",
        "no approval or execution authority",
        "synthetic-page-suggester",
        "draft-pdf-suggestions-v1",
        "Suggested uncertain observation",
        "untrusted suggested rationale",
        "Defects!C14 (formula): =1+2",
        "no technical or physical approval",
    ):
        assert expected in text and expected in strings
    assert all(c.data_type != "f" and c.hyperlink is None for c in cells)
    assert snapshot == before


@pytest.mark.parametrize("profile", PROFILES)
def test_v6_rejects_old_renderer_selection_while_v5_and_v4_keep_exact_contracts(profile):
    newest = suggestion_report(profile)
    service = estimate_reports if "estimate" in newest else scope_reports
    for old in (workbook_report(profile), report_snapshot(profile)):
        before = packages.encode(old)
        service.validate_report_snapshot(old)
        assert packages.encode(old) == before
        bad = deepcopy(newest)
        bad["render_version"] = old["render_version"]
        _seal(bad)
        with pytest.raises(scopes.DraftScopeError, match="SNAPSHOT_INVALID"):
            service.validate_report_snapshot(bad)


def test_v6_package_inventory_binds_the_complete_claim_and_withholds_source_bodies():
    scope = suggestion_scope()
    members = {"artifacts/scope.json": packages.encode(scope)}
    manifest = dict(
        schema_version=packages.SCHEMA,
        state="Draft",
        authority="historical_only",
        project=_snapshot(imported=False)["project"],
        draft_scope_id=scope["artifact_id"],
        selection=packages.selection({"scope_revision": scope["revision"]}).model_dump(),
        notice=packages.NOTICE,
        capabilities=dict(
            scope="included",
            system_match="not_selected",
            estimate="not_selected",
            reports="not_selected",
        ),
        source_manifest=packages.source_manifest(scope, None, None),
        members=[
            dict(path=name, sha256=packages.digest(raw), size_bytes=len(raw))
            for name, raw in members.items()
        ],
        package_id=_id(60),
        revision=1,
        parent_hash=None,
        created_by=_id(1),
        created_at=WHEN.isoformat(),
    )
    archive = packages._archive(manifest, members)
    inspected = imports.inspect_package(archive)
    assert inspected.scope == scope
    assert inspected.members == members
    assert all(ref["membership"] == "external" for ref in manifest["source_manifest"])
    manifest["source_manifest"].pop()
    with pytest.raises(packages.PackageError, match="PACKAGE_CONTENT_INVALID"):
        imports.inspect_package(packages._archive(manifest, members))


def test_v6_shared_template_shows_readable_original_metadata_and_escapes_content():
    from classifire.ui import templates

    scope = suggestion_scope()
    before = deepcopy(scope)
    rendered = templates.env.get_template("draft_scope_report_content.html").render(envelope=scope)
    assert "Original proposed defect; location needs human review" in rendered
    assert "synthetic-page-suggester" in rendered
    assert "&lt;script&gt;" in rendered and "<script>untrusted" not in rendered
    assert "AI suggestion" in rendered
    assert "Defects!C14" in rendered
    assert scope == before
