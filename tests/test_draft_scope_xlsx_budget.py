from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_xlsx as xlsx
from classifire.services.draft_scope_xlsx_contract import FIELDS, SCHEMA

BUDGET_TIME = datetime.max.replace(tzinfo=UTC)


def _uid(number):
    return str(UUID(int=number))


class NoWriteSession:
    @property
    def no_autoflush(self):
        return nullcontext()

    def __getattr__(self, name):
        raise AssertionError(f"Preview attempted database operation: {name}")


def _case(monkeypatch, *, description_size=2000):
    actor = SimpleNamespace(id=_uid(1))
    empty, _ = scopes.validate_payload({})
    current = scopes._revision_envelope(
        draft_id=_uid(2),
        project_id=_uid(3),
        actor_id=actor.id,
        expected_revision=0,
        created=datetime(2026, 9, 6, tzinfo=UTC),
        content=empty.model_dump(mode="json"),
        prior=None,
    )
    payload = deepcopy(current["content"])
    cells, targets, selections = [], [], []
    for row in range(2, 27):
        cells.extend(
            [
                dict(address=f"A{row}", row=row, column=1, kind="text", value=f"Defect {row}"),
                dict(
                    address=f"B{row}", row=row, column=2, kind="text", value="x" * description_size
                ),
            ]
        )
        for index, kind in enumerate(("defect", "opening", "service")):
            identity = _uid(100 + row * 3 + index)
            payload[kind + "s"].append(dict(id=identity, label=f"{kind} {row}"))
            targets.append(dict(target_kind=kind, target_id=identity, row=row, image_ids=[]))
        selections.append(dict(row=row, kinds=["defect", "opening", "service"]))
    mapping = dict.fromkeys(FIELDS)
    mapping.update(defect_label=1, defect_description=2)
    plan = dict(sheet_index=1, header_row=1, mapping=mapping, selections=selections)
    document = dict(
        schema=SCHEMA,
        manifest=dict(source_sha256="a" * 64, source_size_bytes=12000),
        sheets=[dict(name="Defects", index=1, rows=26, columns=2, cells=cells, images=[])],
    )
    case = SimpleNamespace(
        actor=actor,
        current=current,
        payload=payload,
        targets=targets,
        plan=plan,
        document=document,
        db=NoWriteSession(),
    )

    def context(_db, _actor, draft_id, source_id, revision, document_hash, _settings):
        assert draft_id == _uid(2) and source_id == _uid(4)
        assert revision == case.current["revision"] and document_hash == "b" * 64
        binding = dict(
            schema="CLASSIFIRE-DRAFT-XLSX-SCOPE-REVIEW-v1",
            actor_id=actor.id,
            draft_id=draft_id,
            expected_revision=revision,
            current_hash=case.current["sha256"],
            source_id=source_id,
            source_sha256="a" * 64,
            source_size_bytes=12000,
            original_filename="Synthetic defects.xlsx",
            document_sha256=document_hash,
            scan_sha256="c" * 64,
        )
        return actor, case.current, case.document, binding

    def no_writer(*_args, **_kwargs):
        raise AssertionError("Preview called the revision writer")

    monkeypatch.setattr(xlsx, "_review_context", context)
    monkeypatch.setattr(xlsx, "_actor", lambda *_args: actor)
    monkeypatch.setattr(xlsx, "read_revision", lambda *_args: case.current)
    monkeypatch.setattr(xlsx, "_append_revision", no_writer)
    return case


def _preview(case):
    return xlsx.preview_review(
        case.db,
        case.actor,
        _uid(2),
        _uid(4),
        case.current["revision"],
        case.payload,
        case.plan,
        case.targets,
        "b" * 64,
        settings=None,
    )


def _envelope(case, preview):
    return scopes._revision_envelope(
        draft_id=_uid(2),
        project_id=_uid(3),
        actor_id=case.actor.id,
        expected_revision=case.current["revision"],
        created=BUDGET_TIME,
        content=preview["payload"],
        prior=case.current,
        entity_evidence_refs=xlsx._review_refs(preview, BUDGET_TIME.isoformat()),
    )


def test_legal_25_row_batch_with_long_source_cells_is_refused_before_confirmation(monkeypatch):
    case = _case(monkeypatch, description_size=4000)
    before = deepcopy((case.current, case.payload, case.document, case.plan, case.targets))
    assert len(case.plan["selections"]) == 25 and len(case.targets) == 75
    scopes.validate_payload(case.payload)
    with pytest.raises(scopes.DraftScopeError, match="DRAFT_ARTIFACT_TOO_LARGE"):
        _preview(case)
    assert (case.current, case.payload, case.document, case.plan, case.targets) == before


def test_exact_budget_rereview_replaces_refs_and_one_extra_byte_refuses_without_writes(monkeypatch):
    case = _case(monkeypatch)
    # The writer counts UTF-8 bytes, not Python characters, without forcing ASCII escapes.
    case.payload["defects"][0]["description"] = "\u00e9"
    assert len(scopes._json(case.payload["defects"][0]["description"])) == 4
    first = _envelope(case, _preview(case))
    remaining = scopes.MAX_ARTIFACT_BYTES - len(scopes._json(first))
    assert 0 < remaining < 25 * 4000
    for item in case.payload["defects"]:
        old = item.get("description", "")
        added = min(4000 - len(old), remaining)
        item["description"] = old + "x" * added
        remaining -= added
    assert remaining == 0
    first = _envelope(case, _preview(case))
    assert len(scopes._json(first)) == scopes.MAX_ARTIFACT_BYTES
    assert len(first["evidence_refs"]) == 75
    case.current = first
    before = deepcopy((case.current, case.payload))
    reviewed = _envelope(case, _preview(case))
    assert len(reviewed["evidence_refs"]) == 75
    assert len(scopes._json(reviewed)) == scopes.MAX_ARTIFACT_BYTES
    assert (case.current, case.payload) == before
    for item in case.payload["defects"]:
        if len(item["description"]) < 4000:
            item["description"] += "x"
            break
    with pytest.raises(scopes.DraftScopeError, match="DRAFT_ARTIFACT_TOO_LARGE"):
        _preview(case)
    assert case.current == before[0]


def test_shared_builder_keeps_imported_entity_history_and_prunes_deleted_observations(monkeypatch):
    case = _case(monkeypatch, description_size=1)
    candidate = _envelope(case, _preview(case))
    observation = dict(id=_uid(500), text="Historical PDF observation", state="Unresolved")
    payload = deepcopy(candidate["content"])
    payload["observations"].append(observation)
    page_ref = dict(
        observation_id=observation["id"],
        observation_sha256="d" * 64,
        source_id=_uid(501),
        source_sha256="e" * 64,
        source_size_bytes=100,
        original_filename="Historical.pdf",
        page_number=1,
        locator_key="page:1",
        page_text_sha256="f" * 64,
        document_sha256="a" * 64,
        scan_sha256="b" * 64,
        reviewed_by=case.actor.id,
        reviewed_at=BUDGET_TIME.isoformat(),
        method="human_page_review",
        origin="local_retained",
    )
    history = scopes._revision_envelope(
        draft_id=_uid(2),
        project_id=_uid(3),
        actor_id=case.actor.id,
        expected_revision=2,
        created=BUDGET_TIME,
        content=payload,
        prior=candidate,
        evidence_ref=page_ref,
    )
    assert history["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
    removed = deepcopy(history["content"])
    removed["observations"] = []
    deleted_service = removed["services"].pop()["id"]
    before = deepcopy(history)
    imported = scopes._revision_envelope(
        draft_id=_uid(600),
        project_id=_uid(601),
        actor_id=case.actor.id,
        expected_revision=1,
        created=BUDGET_TIME,
        content=removed,
        prior=case.current,
        import_source=history,
        source_file_sha256="f" * 64,
    )
    assert len(imported["evidence_refs"]) == 75
    assert all(ref["origin"] == "imported_unverified" for ref in imported["evidence_refs"])
    assert any(ref.get("target_id") == deleted_service for ref in imported["evidence_refs"])
    assert imported["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
    assert imported["provenance"] == "imported" and len(imported["import_lineage"]) == 1
    assert history == before
