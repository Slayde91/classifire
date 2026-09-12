"""Read-only navigation and existing-record boundaries in the unified workspace."""

from __future__ import annotations

import re
import secrets

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope_ui import (
    ScopeApplication,
    _create,
    _csrf,
    _login,
    scope_app,  # noqa: F401 - shared isolated application fixture
    scope_password_hash,  # noqa: F401 - shared fixture dependency
)

from classifire.library_ui import router as library_router
from classifire.models import AuditEvent, DraftScope, DraftScopeRevision, Estimate, Project, User
from classifire.services.draft_scope import create_draft_project
from classifire.technical_admin import router as technical_router
from classifire.ui import LIBRARY_SECTIONS


def _nav(html: str, label: str) -> str:
    match = re.search(
        r'<nav[^>]*aria-label="' + re.escape(label) + r'"[^>]*>(.*?)</nav>', html, re.S
    )
    assert match
    return match.group(1)


def _counts(application: ScopeApplication) -> list[int]:
    with application.factory() as db:
        return [
            db.scalar(select(func.count()).select_from(model))
            for model in (Project, DraftScope, DraftScopeRevision, Estimate, AuditEvent)
        ]


def test_workspace_combines_existing_project_scope_and_estimate_without_writes(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["owner"])
        draft = create_draft_project(db, actor, "COMBINED-001", "Combined saved project")
        estimate = Estimate(
            project_id=draft.project_id,
            reference="COMBINED-EST-001",
            title="Existing synthetic estimate",
            revision=1,
        )
        db.add(estimate)
        db.commit()
        project_id, draft_id, estimate_id = draft.project_id, draft.id, estimate.id
    with TestClient(scope_app.app) as client:
        _login(client)
        before = _counts(scope_app)
        for path in ("/projects", "/scopes"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert f'data-project-id="{project_id}"' in response.text
            assert f'href="/scopes/{draft_id}"' in response.text
            assert f'href="/estimates/{estimate_id}"' in response.text
            assert response.text.count("data-project-id=") == 1
            nav = _nav(response.text, "Primary navigation")
            assert 'href="/projects" class="nav-link active" aria-current="page"' in nav
            assert 'href="/scopes"' not in nav
            assert "Draft Scope workspace" not in nav
        assert _counts(scope_app) == before


def test_workspace_draft_only_project_identity_stays_owner_scoped(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    with TestClient(scope_app.app) as owner:
        _login(owner)
        path = _create(owner, "PRIVATE-DRAFT-IDENTITY")
    with TestClient(scope_app.app) as other:
        _login(other, "other")
        for route in ("/projects", "/scopes"):
            response = other.get(route)
            assert response.status_code == 200
            assert "PRIVATE-DRAFT-IDENTITY" not in response.text
            assert path not in response.text
    with TestClient(scope_app.app) as admin:
        _login(admin, "admin")
        assert path in admin.get("/projects").text


def test_workspace_keeps_legacy_projects_and_hides_read_only_creation(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    with scope_app.factory() as db:
        project = Project(reference="LEGACY-PROJECT", name="Existing project without a draft")
        db.add(project)
        db.commit()
        project_id = project.id
    with TestClient(scope_app.app) as client:
        _login(client, "reader")
        response = client.get("/projects")
        assert response.status_code == 200
        assert f'data-project-id="{project_id}"' in response.text
        assert 'action="/scopes"' not in response.text
        assert 'action="/projects"' not in response.text
        assert "New estimate revision" not in response.text


def test_workspace_word_entry_reuses_existing_scope_creation(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        page = client.get("/projects")
        assert 'name="next" value="word"' in page.text
        response = client.post(
            "/scopes",
            data={
                "csrf_token": _csrf(page.text),
                "reference": "WORD-ENTRY",
                "name": "Synthetic Word entry",
                "next": "word",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert re.fullmatch(r"/scopes/[0-9a-f-]{36}/word", response.headers["location"])
    with scope_app.factory() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(DraftScope)) == 1
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0


def test_libraries_share_primary_navigation_and_preserve_existing_routes(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    scope_app.app.include_router(library_router)
    scope_app.app.include_router(technical_router)
    with TestClient(scope_app.app) as client:
        _login(client)
        before = _counts(scope_app)
        overview = client.get("/libraries")
        assert overview.status_code == 200
        primary = _nav(overview.text, "Primary navigation")
        assert 'href="/libraries" class="nav-link active" aria-current="page"' in primary
        for section in LIBRARY_SECTIONS:
            assert f'href="{section["href"]}"' not in primary
            assert section["label"] in overview.text
            response = client.get(section["href"])
            assert response.status_code == 200
            assert f"<h1>{section['label']}</h1>" in response.text
            internal = _nav(response.text, "Libraries")
            assert f'href="{section["href"]}" aria-current="page"' in internal
            assert internal.count('aria-current="page"') == 1
        assert _counts(scope_app) == before


def test_library_navigation_respects_technical_access_and_authentication(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    with TestClient(scope_app.app) as client:
        assert client.get("/libraries", follow_redirects=False).status_code == 401
    with scope_app.factory() as db:
        user = db.get(User, scope_app.users["other"])
        user.role = "pricing_manager"
        db.commit()
    with TestClient(scope_app.app) as client:
        _login(client, "other")
        page = client.get("/libraries")
        assert page.status_code == 200
        nav = _nav(page.text, "Libraries")
        assert "Technical Evidence Library" not in nav
        assert "Technical System Library" not in nav
        assert "Item Price Library" in nav
        assert client.get("/technical").status_code == 403
        assert 'href="/projects"' not in _nav(page.text, "Primary navigation")


def test_workspace_lists_saved_draft_estimate_and_keeps_owner_boundary(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    from classifire.services import draft_estimates

    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["owner"])
        draft = create_draft_project(db, actor, "DRAFT-ESTIMATE-001", "Saved draft estimate")
        estimate = draft_estimates.create_estimate(db, actor, draft.id, 1)
        db.commit()
        expected = f"/scopes/{draft.id}/estimates/{estimate.id}?revision=1"
    with TestClient(scope_app.app) as client:
        _login(client)
        before = _counts(scope_app)
        page = client.get("/projects")
        assert page.status_code == 200
        assert f'href="{expected}"' in page.text
        assert "Draft estimate &middot; revision 1" in page.text
        assert "Scope revision 1" in page.text
        assert "No estimate revisions." not in page.text
        assert _counts(scope_app) == before
    with TestClient(scope_app.app) as other:
        _login(other, "other")
        assert expected not in other.get("/projects").text


def test_workspace_damaged_draft_estimate_is_visible_as_unresolved(
    scope_app: ScopeApplication,  # noqa: F811
) -> None:
    from classifire.services import draft_estimates

    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["owner"])
        draft = create_draft_project(db, actor, "DAMAGED-DRAFT-ESTIMATE", "History review")
        estimate = draft_estimates.create_estimate(db, actor, draft.id, 1)
        estimate.latest_hash = "0" * 64
        db.commit()
        estimate_id = estimate.id
    with TestClient(scope_app.app) as client:
        _login(client)
        before = _counts(scope_app)
        page = client.get("/projects")
        assert page.status_code == 200
        assert "Saved Draft estimate history needs review" in page.text
        assert estimate_id not in page.text
        assert _counts(scope_app) == before


def test_workspace_requires_estimate_read_permission_for_saved_draft_estimates(
    scope_app: ScopeApplication,  # noqa: F811
    monkeypatch,
) -> None:
    from classifire.security import ROLE_PERMISSIONS
    from classifire.services import draft_estimates

    monkeypatch.setitem(ROLE_PERMISSIONS, "scope_only_test", {"project:read"})
    with scope_app.factory() as db:
        actor = db.get(User, scope_app.users["owner"])
        draft = create_draft_project(db, actor, "SCOPE-READ-ONLY", "Scope without estimate access")
        estimate = draft_estimates.create_estimate(db, actor, draft.id, 1)
        other_actor = db.get(User, scope_app.users["other"])
        other_draft = create_draft_project(
            db, other_actor, "PRIVATE-ESTIMATE-PROJECT", "Another owner's estimate project"
        )
        db.add(
            Estimate(
                project_id=other_draft.project_id,
                reference="PRIVATE-EST-001",
                title="Existing synthetic estimate",
                revision=1,
            )
        )
        actor.role = "scope_only_test"
        db.commit()
        scope_link = f"/scopes/{draft.id}"
        estimate_link = f"/scopes/{draft.id}/estimates/{estimate.id}"
    with TestClient(scope_app.app) as client:
        _login(client)
        before = _counts(scope_app)
        page = client.get("/projects")
        assert page.status_code == 200
        assert f'href="{scope_link}"' in page.text
        assert estimate_link not in page.text
        assert "PRIVATE-ESTIMATE-PROJECT" not in page.text
        assert "PRIVATE-EST-001" not in page.text
        assert _counts(scope_app) == before


def test_navigation_without_permission_context_does_not_advertise_protected_routes() -> None:
    from types import SimpleNamespace

    from starlette.datastructures import QueryParams

    from classifire.ui import templates

    html = templates.get_template("base.html").render(
        request=SimpleNamespace(query_params=QueryParams()),
        user=SimpleNamespace(full_name="Standalone preview", role="administrator"),
        csrf_token=secrets.token_hex(16),
        attribution="CLASSIFIRE",
    )
    for route in ("/projects", "/libraries", "/rules", "/proposal-reviews", "/releases", "/audit"):
        assert f'href="{route}"' not in html
    assert 'href="/docs"' in html
