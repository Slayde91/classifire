from __future__ import annotations

from types import SimpleNamespace

from physical_foundation_support import physical_session
from starlette.datastructures import QueryParams

from classifire import release_admin
from classifire.models import LibraryRelease


def _bound_record() -> dict[str, object]:
    return {
        "id": "technical-record-id",
        "key": "SYSTEM-001",
        "variant_id": "SYSTEM-001-QFREV02",
        "source_hash": "v" * 64,
        "source_binding": {
            "schema": "technical-release-source-binding-v1",
            "state": "bound",
            "technical_document": {
                "id": "technical-document-row-id",
                "document_id": "ASSESSMENT-001",
                "reference": "ASSESSMENT-REF",
                "revision": "Rev 3",
                "stored_file": {
                    "id": "stored-file-row-id",
                    "sha256": "f" * 64,
                    "size_bytes": 1234,
                },
            },
            "source_locator": {
                "document_reference": "ASSESSMENT-001",
                "page": "42",
                "table": "Table 7",
                "figure": "Figure 2",
            },
        },
    }


def test_technical_release_lineage_rows_preserve_bound_and_legacy_states() -> None:
    rows = release_admin._technical_release_lineage_rows(
        [
            _bound_record(),
            {
                "id": "explicit-legacy-record-id",
                "variant_id": "LEGACY-BOUNDING-001",
                "source_binding": {"state": "legacy_unbound"},
            },
            {"id": "legacy-record-id", "variant_id": "LEGACY-001"},
            {
                "id": "unknown-binding-record-id",
                "source_binding": {
                    "state": "unexpected",
                    "technical_document": {"id": "unexpected-document-id"},
                },
            },
        ]
    )

    assert rows[0]["source_state"] == "Bound retained source"
    assert rows[0]["source_state_badge"] == "active"
    assert rows[0]["document_id"] == "ASSESSMENT-001"
    assert rows[0]["document_detail_href"] == "/technical/documents/technical-document-row-id"
    assert rows[0]["stored_file_sha256"] == "f" * 64
    assert rows[0]["source_page"] == "42"
    assert rows[1]["source_state"] == "Legacy unbound"
    assert rows[1]["document_id"] == "—"
    assert rows[1]["document_detail_href"] == ""
    assert rows[2]["source_state"] == "Legacy manifest without source binding"
    assert rows[3]["source_state"] == "Unrecognised source state"
    assert rows[3]["document_detail_href"] == ""


def test_technical_release_lineage_escapes_bound_document_detail_path() -> None:
    rows = release_admin._technical_release_lineage_rows(
        [
            {
                "source_binding": {
                    "state": "bound",
                    "technical_document": {"id": "document / ? #", "document_id": "SAFE-001"},
                }
            }
        ]
    )

    assert rows[0]["document_detail_href"] == "/technical/documents/document%20%2F%20%3F%20%23"


def test_release_detail_template_renders_technical_lineage_without_claiming_authority() -> None:
    template = release_admin.templates.get_template("release_detail.html")
    records = [_bound_record()]
    common = {
        "request": SimpleNamespace(query_params=QueryParams()),
        "user": SimpleNamespace(full_name="Technical reviewer", role="administrator"),
        "csrf_token": "test-csrf-token",
        "attribution": "CLASSIFIRE",
        "has_permission": lambda _permission: False,
        "manifest": {"record_count": 1},
        "records": records,
        "technical_lineage": release_admin._technical_release_lineage_rows(records),
    }

    technical_html = template.render(
        **common,
        release=SimpleNamespace(
            library_type="technical",
            version="TECH-2026.09",
            status="active",
            effective_date=None,
            release_hash="r" * 64,
            notes=None,
        ),
    )
    pricing_html = template.render(
        **common,
        release=SimpleNamespace(
            library_type="pricing",
            version="PRICE-2026.09",
            status="active",
            effective_date=None,
            release_hash="r" * 64,
            notes=None,
        ),
    )

    assert "Published technical source lineage" in technical_html
    assert "It does not approve a source or prove current technical authority." in technical_html
    assert "Bound retained source" in technical_html
    assert "ASSESSMENT-001" in technical_html
    assert 'href="/technical/documents/technical-document-row-id"' in technical_html
    assert (
        "current read-only document record without changing the published binding"
        in technical_html
    )
    assert "File SHA-256" in technical_html
    assert "Manifest records" in pricing_html
    assert "Published technical source lineage" not in pricing_html


def test_release_detail_passes_structured_technical_lineage_to_the_template(monkeypatch) -> None:
    with physical_session() as db:
        release = LibraryRelease(
            library_type="technical",
            version="TECH-2026.09",
            status="active",
            source_manifest={"records": [_bound_record()]},
        )
        db.add(release)
        db.flush()
        captured: dict[str, object] = {}
        monkeypatch.setattr(release_admin, "_require", lambda *_args: object())
        monkeypatch.setattr(
            release_admin,
            "_context",
            lambda _request, _db, **values: values,
        )
        monkeypatch.setattr(
            release_admin.templates,
            "TemplateResponse",
            lambda _request, name, context: captured.update(name=name, context=context),
        )

        release_admin.release_detail(release.id, object(), db)  # type: ignore[arg-type]

        assert captured["name"] == "release_detail.html"
        context = captured["context"]
        assert isinstance(context, dict)
        assert context["technical_lineage"] == release_admin._technical_release_lineage_rows(
            [_bound_record()]
        )
