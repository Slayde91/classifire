from __future__ import annotations

import hashlib
import re

from fastapi.testclient import TestClient
from test_draft_estimates import add_payload
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_pdf_ui import pdf_setup as _pdf_setup
from test_draft_pricing import MAPPING, workbook_bytes
from test_draft_scope import sample_payload
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture
from test_technical_release_publication import _bound_variant, _publish

from classifire.draft_estimate_ui import router as estimate_router
from classifire.draft_pricing_ui import router
from classifire.models import DraftEstimate, User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope as scope
from classifire.services.draft_system_match_contract import canonical

pdf_app = _pdf_app
pdf_setup = _pdf_setup
scope_password_hash = _password_hash
postgresql_session_factory = _postgres_fixture


def test_upload_map_select_download_and_http_boundaries(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(router)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        scope.save_revision(db, actor, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, actor, x.ids[2], 2)
        envelope = estimates.add_line(db, actor, x.ids[2], estimate.id, 1, add_payload())
        line_id = envelope["lines"][0]["line_id"]
        base = f"/scopes/{x.ids[2]}/estimates/{estimate.id}"
        db.add(
            User(
                email="admin@scope.example.test",
                full_name="Synthetic pricing reviewer",
                password_hash=actor.password_hash,
                role="administrator",
                is_active=True,
            )
        )
        db.commit()
    with (
        TestClient(x.app) as client,
        TestClient(x.app) as other,
        TestClient(x.app) as admin,
    ):
        _login(client)
        _login(other, "other")
        _login(admin, "admin")
        page = client.get(base + "/pricing")
        assert page.status_code == 200
        invalid_kind = client.post(
            base + "/pricing/upload",
            data={"csrf_token": _csrf(page.text), "dataset_kind": "filename_guess"},
            files={"file": ("synthetic.xlsx", workbook_bytes())},
        )
        assert invalid_kind.status_code == 422
        response = client.post(
            base + "/pricing/upload",
            data={"csrf_token": _csrf(page.text), "dataset_kind": "general_pricelist"},
            files={"file": ("synthetic.xlsx", workbook_bytes())},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        path = response.headers["location"]
        assert other.get(path).status_code == 404
        assert client.post(path + "/scan", data={"csrf_token": "bad"}).status_code == 403
        token = _csrf(client.get(path).text)
        response = client.post(path + "/scan", data={"csrf_token": token}, follow_redirects=False)
        assert response.status_code == 303, response.text
        form = {
            "csrf_token": token,
            "sheet_index": "1",
            "header_row": "1",
            "price_meaning": "sell_price",
            **{key: str(value) for key, value in MAPPING.items()},
        }
        bad = client.post(path + "/preview", data={**form, "rate": "1"})
        assert bad.status_code == 422
        page = client.post(path + "/preview", data=form)
        assert page.status_code == 200, page.text
        assert "Apply row 2 rate" in page.text
        assert "Apply row 4 rate" not in page.text
        assert "D2: 120.25" in page.text
        assert "Save unapproved profile revision 1" in page.text
        assert "Sell price" in page.text
        import re

        def hidden(name):
            return re.search(r'name="' + name + r'" value="([^"]+)"', page.text).group(1)

        profile_form = {
            **form,
            "expected_profile_revision": hidden("expected_profile_revision"),
            "document_sha256": hidden("document_sha256"),
            "preview_hash": hidden("preview_hash"),
        }
        assert (
            client.post(
                path + "/profiles",
                data={**profile_form, "expected_profile_revision": "+0"},
            ).status_code
            == 422
        )
        profile = client.post(
            path + "/profiles", data=profile_form, follow_redirects=False
        )
        assert profile.status_code == 303, profile.text
        assert client.post(path + "/profiles", data=profile_form).status_code == 409
        profile_page = client.get(profile.headers["location"])
        assert profile_page.status_code == 200
        assert "Saved profile revision 1" in profile_page.text
        assert "Unapproved" in profile_page.text
        profile_download = client.get(profile.headers["location"] + "/download")
        assert profile_download.status_code == 200
        assert profile_download.json()["definition"]["dataset"]["kind"] == "general_pricelist"
        review_path = profile.headers["location"] + "/decisions"
        profile_hash = re.search(
            r'name="profile_sha256" value="([0-9a-f]{64})"',
            admin.get(profile.headers["location"]).text,
        ).group(1)
        review_form = {
            "csrf_token": _csrf(profile_page.text),
            "profile_sha256": profile_hash,
            "decision": "approve",
            "reason": "The exact mapping and sell-price declaration were checked.",
        }
        assert client.post(review_path, data=review_form).status_code == 403
        admin_page = admin.get(profile.headers["location"])
        review_form["csrf_token"] = _csrf(admin_page.text)
        reviewed = admin.post(review_path, data=review_form, follow_redirects=False)
        assert reviewed.status_code == 303, reviewed.text
        reopened = client.get(profile.headers["location"])
        assert "Human review decision" in reopened.text
        assert "Approve" in reopened.text
        assert "exact mapping and sell-price declaration" in reopened.text
        decision_path = re.search(
            r'href="([^"]+/decisions/[^"]+/download)"', reopened.text
        ).group(1)
        decision_download = client.get(decision_path)
        assert decision_download.status_code == 200
        assert decision_download.json()["profile_sha256"] == profile_hash
        assert decision_download.json()["effects"]["estimate_changed"] is False
        admin_row_page = admin.get(profile.headers["location"])
        assert "Classify this exact row" in admin_row_page.text
        row_preview = admin.post(
            profile.headers["location"] + "/rows/2/preview",
            data={
                "csrf_token": _csrf(admin_row_page.text),
                "item_kind": "service",
                "normalized_reference": "SYN-1",
                "evidence_state": "confirmed",
                "review_reason": "The retained description identifies service work.",
                "unresolved_fields": "",
            },
        )
        assert row_preview.status_code == 200, row_preview.text
        assert "No write has occurred" in row_preview.text
        assert "Save immutable row observation" in row_preview.text

        def row_hidden(name):
            return re.search(r'name="' + name + r'" value="([^"]*)"', row_preview.text).group(1)

        row_saved = admin.post(
            profile.headers["location"] + "/rows/2/observations",
            data={
                "csrf_token": _csrf(row_preview.text),
                "item_kind": row_hidden("item_kind"),
                "normalized_reference": row_hidden("normalized_reference"),
                "evidence_state": row_hidden("evidence_state"),
                "review_reason": row_hidden("review_reason"),
                "unresolved_fields": row_hidden("unresolved_fields"),
                "profile_sha256": row_hidden("profile_sha256"),
                "decision_sha256": row_hidden("decision_sha256"),
                "row_sha256": row_hidden("row_sha256"),
                "preview_hash": row_hidden("preview_hash"),
            },
            follow_redirects=False,
        )
        assert row_saved.status_code == 303, row_saved.text
        reviewed_row_page = client.get(profile.headers["location"])
        assert "Reviewed Dataset A observation" in reviewed_row_page.text
        assert "SYN-1" in reviewed_row_page.text
        assert "Service" in reviewed_row_page.text
        observation_path = re.search(
            r'href="([^"]+/observations/[^"]+/download)"', reviewed_row_page.text
        ).group(1)
        observation_download = client.get(observation_path)
        assert observation_download.status_code == 200
        assert observation_download.json()["definition"]["row"]["sha256"] == row_hidden(
            "row_sha256"
        )
        assert observation_download.json()["definition"]["effects"]["estimate_changed"] is False
        review_form["csrf_token"] = _csrf(admin.get(profile.headers["location"]).text)
        assert admin.post(review_path, data=review_form).status_code == 409
        assert client.get(base + "/download?revision=2").status_code == 200
        with x.factory() as db:
            assert db.get(DraftEstimate, estimate.id).latest_revision == 2

        apply = {
            **{key: value for key, value in form.items() if key != "price_meaning"},
            "expected_revision": "2",
            "line_id": line_id,
            "row_number": "2",
            "document_sha256": hidden("document_sha256"),
            "row_sha256": hidden("row_sha256"),
            "recovery_note": "Service work only; excludes shared closure",
        }
        response = client.post(path + "/apply", data=apply, follow_redirects=False)
        assert response.status_code == 303, response.text
        download = client.get(base + "/download?revision=3")
        assert download.status_code == 200, download.text
        assert download.json()["pricing_sources"][0]["row"]["fields"]["rate"]["address"] == "D2"
        assert client.post(path + "/apply", data=apply).status_code == 409


def test_dataset_b_system_mapping_preview_save_and_download_ui(pdf_app, monkeypatch):
    x = pdf_app
    monkeypatch.setattr("classifire.draft_pricing_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_estimate_ui.get_settings", lambda: x.settings)
    x.app.include_router(estimate_router)
    x.app.include_router(router)
    with x.factory() as db:
        owner = db.get(User, x.ids[0])
        scope.save_revision(db, owner, x.ids[2], 1, sample_payload())
        estimate = estimates.create_estimate(db, owner, x.ids[2], 2)
        admin = User(
            email="admin@scope.example.test",
            full_name="Synthetic Dataset B reviewer",
            password_hash=owner.password_hash,
            role="administrator",
            is_active=True,
        )
        db.add(admin)
        db.flush()
        variant, _ = _bound_variant(db, x.settings.storage_root, suffix="UI-B")
        release = _publish(
            db,
            actor=admin,
            storage_root=x.settings.storage_root,
            version="TECH-UI-B",
        )
        source = pricing.retain_source(
            db,
            owner,
            x.ids[2],
            "dataset-b.xlsx",
            workbook_bytes(),
            "firefly_system_prices",
            settings=x.settings,
        )
        pricing.intake().scan_source(db, owner, x.ids[2], source.id, settings=x.settings)
        preview = pricing.preview_profile(
            db,
            owner,
            x.ids[2],
            source.id,
            1,
            1,
            MAPPING,
            "sell_price",
            settings=x.settings,
        )
        profile = pricing.save_profile(
            db,
            owner,
            x.ids[2],
            source.id,
            1,
            1,
            MAPPING,
            "sell_price",
            0,
            source.document_sha256,
            preview["preview_hash"],
            settings=x.settings,
        )
        pricing.save_profile_decision(
            db,
            admin,
            x.ids[2],
            source.id,
            profile["profile_id"],
            hashlib.sha256(canonical(profile)).hexdigest(),
            "approve",
            "The exact Dataset B profile was checked.",
        )
        db.commit()
        release_id = release.id
        variant_id = variant.id
        profile_path = (
            f"/scopes/{x.ids[2]}/estimates/{estimate.id}/pricing/{source.id}/profiles/"
            f"{profile['profile_id']}"
        )
    with TestClient(x.app) as client, TestClient(x.app) as admin_client:
        _login(client)
        _login(admin_client, "admin")
        owner_page = client.get(profile_path)
        assert owner_page.status_code == 200
        assert "authorised pricing reviewer with technical-library access" in owner_page.text
        admin_page = admin_client.get(profile_path)
        assert admin_page.status_code == 200
        assert "Map this exact Firefly price row" in admin_page.text
        row_path = profile_path + "/rows/2/system-mapping"
        form = {
            "csrf_token": _csrf(admin_page.text),
            "technical_release_id": release_id,
            "mapping_status": "mapped",
            "normalized_reference": "SYN-1",
            "selected_variant_id": variant_id,
            "candidate_variant_ids": "",
            "identity_evidence_fields": "reference,description",
            "review_reason": "The exact reference and description identify this variant.",
            "unresolved_fields": "",
        }
        denied = client.post(
            row_path + "/preview",
            data={**form, "csrf_token": _csrf(owner_page.text)},
        )
        assert denied.status_code == 403
        mapping_preview = admin_client.post(row_path + "/preview", data=form)
        assert mapping_preview.status_code == 200, mapping_preview.text
        assert "No write has occurred" in mapping_preview.text
        assert "Save immutable system mapping" in mapping_preview.text

        def hidden(name):
            match = re.search(
                r'name="' + name + r'" value="([^"]*)"', mapping_preview.text
            )
            assert match is not None
            return match.group(1)

        save_form = {
            "csrf_token": _csrf(mapping_preview.text),
            **{
                name: hidden(name)
                for name in (
                    "technical_release_id",
                    "mapping_status",
                    "normalized_reference",
                    "selected_variant_id",
                    "candidate_variant_ids",
                    "identity_evidence_fields",
                    "review_reason",
                    "unresolved_fields",
                    "profile_sha256",
                    "decision_sha256",
                    "row_sha256",
                    "technical_release_sha256",
                    "preview_hash",
                )
            },
        }
        saved = admin_client.post(
            row_path + "s", data=save_form, follow_redirects=False
        )
        assert saved.status_code == 303, saved.text
        reviewed = admin_client.get(profile_path)
        assert "Reviewed Dataset B system mapping" in reviewed.text
        assert "Current" in reviewed.text
        download_match = re.search(
            r'href="([^"]+/system-mappings/[^"]+/download)"', reviewed.text
        )
        assert download_match is not None
        assert client.get(download_match.group(1)).status_code == 403
        downloaded = admin_client.get(download_match.group(1))
        assert downloaded.status_code == 200
        assert downloaded.json()["definition"]["interpretation"]["selected_variant_id"] == (
            variant_id
        )
        assert downloaded.json()["definition"]["effects"]["estimate_changed"] is False
