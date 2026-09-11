from __future__ import annotations

import json
import re
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope_ui import _app, _assert_no_canonical_scope, _csrf, _login, _payload
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_client import configure
from classifire.draft_client_auth import ESTIMATE, EXPORT, READ, TECHNICAL, WRITE, ClientAuthority
from classifire.draft_project_package_ui import router as package_router
from classifire.models import DraftClientRequest, DraftScope, Project, User
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes

scope_app = _scope_app
scope_password_hash = _scope_password_hash
postgresql_session_factory = _postgres


@pytest.fixture
def client_case(scope_app, tmp_path, request):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public.update(alg="RS256", use="sig", kid="synthetic")
    policy = {
        "base_url": "https://testserver",
        "issuer": "https://auth.example.test",
        "public_keys": {"synthetic": public},
        "subjects": scope_app.users,
        "clients": {"synthetic-client": [READ, WRITE, EXPORT]},
    }
    policy.update(getattr(request, "param", {}))
    path = tmp_path / "client-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    authority = ClientAuthority(path)
    from classifire.draft_estimate_ui import router as estimate_router
    from classifire.draft_system_match_ui import router as match_router

    scope_app.app.include_router(estimate_router)
    scope_app.app.include_router(match_router)
    scope_app.app.include_router(package_router)
    mounted = configure(scope_app.app, authority, scope_app.factory)

    @asynccontextmanager
    async def lifespan(app):
        async with mounted.router.lifespan_context(mounted):
            yield

    scope_app.app.router.lifespan_context = lifespan

    def token(user="owner", **overrides):
        now = int(time.time())
        claims = {
            "iss": policy["issuer"],
            "aud": policy.get("oauth_resource", policy["base_url"] + "/mcp"),
            "sub": user,
            "client_id": "synthetic-client",
            "jti": "synthetic-token",
            "iat": now,
            "nbf": now,
            "exp": now + 600,
            "scope": " ".join([READ, WRITE, EXPORT]),
        }
        claims.update(overrides)
        return jwt.encode(
            claims, key, algorithm="RS256", headers={"kid": "synthetic", "typ": "at+jwt"}
        )

    return SimpleNamespace(
        scope=scope_app, authority=authority, key=key, policy=policy, path=path, token=token
    )


def rpc(client, token, method, params=None):
    return client.post(
        "/mcp",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def tool(client, token, name, arguments=None, *, error=False):
    response = rpc(client, token, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    value = response.json()["result"]
    assert bool(value.get("isError")) is error, value
    return value if error else value["structuredContent"]


def confirm(client, request, *, decision="confirm", status=200):
    page = client.get(request["review_url"])
    assert page.status_code == 200, page.text
    digest = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
    response = client.post(
        request["review_url"],
        data={"csrf_token": _csrf(page.text), "payload_hash": digest, "decision": decision},
    )
    assert response.status_code == status, response.text
    return response


def test_client_to_human_to_saved_draft_and_exact_package(client_case):
    case = client_case
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        token = case.token()
        discovery = rpc(client, token, "tools/list")
        assert discovery.status_code == 200, discovery.text
        names = {t["name"] for t in discovery.json()["result"]["tools"]}
        assert names == {
            "list_draft_projects",
            "read_draft_scope",
            "upload_draft_pdf",
            "list_draft_pdf_sources",
            "scan_draft_pdf",
            "read_draft_pdf_page",
            "read_draft_pdf_page_image",
            "propose_draft_project",
            "propose_draft_edit",
            "propose_project_package",
            "read_client_request",
            "project_package_download",
            "propose_capability",
            "list_technical_releases",
            "list_pricing_sources",
            "preview_pricing_rows",
            "list_pricing_row_observations",
            "read_pricing_row_observation",
            "preview_pricing_coverage",
            "list_pricing_evaluation_rosters",
            "read_pricing_evaluation_roster",
            "list_pricing_recipe_links",
            "read_pricing_recipe_link",
            "list_capability_artifacts",
            "read_capability_artifact",
            "report_download",
        }
        pending = tool(
            client,
            token,
            "propose_draft_project",
            {"reference": "CLIENT-01", "name": "Synthetic client project"},
        )
        with case.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(Project)) == 0
        assert client.post(pending["review_url"], data={"decision": "confirm"}).status_code == 401
        _login(client)
        confirm(client, pending)
        saved = tool(client, token, "read_client_request", {"request_id": pending["request_id"]})
        draft_id = saved["result"]["draft_id"]
        assert saved["status"] == "confirmed"
        before = tool(client, token, "read_draft_scope", {"draft_id": draft_id})
        pending_edit = tool(
            client,
            token,
            "propose_draft_edit",
            {"draft_id": draft_id, "expected_revision": 1, "content": _payload()},
        )
        assert tool(client, token, "read_draft_scope", {"draft_id": draft_id}) == before
        confirm(client, pending_edit)
        after = tool(client, token, "read_draft_scope", {"draft_id": draft_id})
        assert after["revision"] == 2 and len(after["content"]["openings"]) == 3
        assert "Cable group" in client.get("/scopes/" + draft_id).text
        proposal = tool(
            client,
            token,
            "propose_project_package",
            {"draft_id": draft_id, "selection": {"scope_revision": 2}},
        )
        confirm(client, proposal)
        saved = tool(client, token, "read_client_request", {"request_id": proposal["request_id"]})
        info = tool(
            client,
            token,
            "project_package_download",
            {"draft_id": draft_id, "package_id": saved["result"]["package_id"]},
        )
        binary = client.get(info["authenticated_url"], headers={"Authorization": "Bearer " + token})
        assert binary.status_code == 200 and binary.headers["cache-control"] == "no-store"
        assert packages.digest(binary.content) == info["sha256"]
        assert client.get(info["browser_url"]).content == binary.content
        manifest, members = packages.inspect_archive(binary.content)
        assert manifest["capabilities"]["scope"]
        assert any(b"Cable group" in value for value in members.values())
        assert client.get(info["authenticated_url"]).status_code == 401
    # A newly constructed app and session factory read the same retained records.
    restarted = _app(case.scope.factory)
    restarted.include_router(package_router)
    with TestClient(restarted, base_url="https://testserver") as browser:
        _login(browser)
        assert browser.get(info["browser_url"]).content == binary.content
    _assert_no_canonical_scope(case.scope.factory)


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "https://other.example.test/mcp"},
        {"iss": "https://other.example.test"},
        {"exp": 1},
        {"sub": "unknown"},
        {"client_id": "other-client"},
        {"scope": WRITE},
        {"exp": int(time.time()) + 3600},
        {"scope": READ + " administrator"},
    ],
)
def test_tokens_are_bound_to_resource_user_client_time_and_scope(client_case, overrides):
    assert client_case.authority.verify(client_case.token(**overrides)) is None


def test_foreign_revoked_stale_and_unconfirmed_writes_are_refused(client_case):
    case = client_case
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        token = case.token()
        _login(client)
        request = tool(
            client, token, "propose_draft_project", {"reference": "CLIENT-02", "name": "Owned"}
        )
        confirm(client, request)
        draft_id = tool(
            client, token, "read_client_request", {"request_id": request["request_id"]}
        )["result"]["draft_id"]
        for user in ("other", "admin"):
            tool(client, case.token(user), "read_draft_scope", {"draft_id": draft_id}, error=True)
        tool(
            client,
            case.token(scope=READ),
            "propose_draft_project",
            {"reference": "DENIED", "name": "Denied"},
            error=True,
        )
        pending = tool(
            client,
            token,
            "propose_draft_edit",
            {"draft_id": draft_id, "expected_revision": 1, "content": _payload()},
        )
        with case.scope.factory() as db:
            scopes.save_revision(db, db.get(User, case.scope.users["owner"]), draft_id, 1, {})
            db.commit()
        confirm(client, pending, status=409)
        with case.scope.factory() as db:
            assert db.get(DraftClientRequest, pending["request_id"]).status == "pending"
            assert db.get(DraftScope, draft_id).latest_revision == 2
        case.policy["revoked_token_ids"] = ["synthetic-token"]
        case.path.write_text(json.dumps(case.policy), encoding="utf-8")
        assert rpc(client, token, "tools/list").status_code == 401
        assert client.get(pending["review_url"]).status_code == 403
    _assert_no_canonical_scope(case.scope.factory)


def test_discovery_challenge_csrf_replay_and_rejection(client_case):
    case = client_case
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        denied = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert denied.status_code == 401
        assert "resource_metadata" in denied.headers["www-authenticate"]
        metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == "https://testserver/mcp"
        assert metadata.json()["authorization_servers"] == [case.policy["issuer"]]
        assert set(metadata.json()["scopes_supported"]) == {
            READ,
            WRITE,
            EXPORT,
            TECHNICAL,
            ESTIMATE,
        }
        token = case.token()
        request = tool(
            client,
            token,
            "propose_draft_project",
            {"reference": "<script>bad</script>", "name": "Synthetic"},
        )
        _login(client)
        page = client.get(request["review_url"])
        assert (
            "&lt;script&gt;bad&lt;/script&gt;" in page.text
            and "<script>bad</script>" not in page.text
        )
        digest = re.search(r'name="payload_hash" value="([^"]+)"', page.text).group(1)
        body = {"decision": "confirm", "payload_hash": digest, "csrf_token": "wrong"}
        assert client.post(request["review_url"], data=body).status_code == 403
        body["csrf_token"] = _csrf(page.text)
        body["payload_hash"] = "0" * 64
        assert client.post(request["review_url"], data=body).status_code == 409
        confirm(client, request, decision="reject")
        body["payload_hash"] = digest
        assert client.post(request["review_url"], data=body).status_code == 409
        with case.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(Project)) == 0
        oversized = client.post(
            "/mcp",
            content=b" " * 1048577,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        assert oversized.status_code == 413
    _assert_no_canonical_scope(case.scope.factory)


@pytest.mark.parametrize(
    "change", ["inactive", "read_only", "unmap", "remove_client", "remove_scope"]
)
def test_permissions_rechecked_between_proposal_and_human_confirmation(client_case, change):
    case = client_case
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        _login(client)
        token = case.token()
        request = tool(
            client, token, "propose_draft_project", {"reference": "PERMISSION", "name": "Synthetic"}
        )
        if change in {"inactive", "read_only"}:
            with case.scope.factory() as db:
                actor = db.get(User, case.scope.users["owner"])
                if change == "inactive":
                    actor.is_active = False
                else:
                    actor.role = "read_only"
                db.commit()
        else:
            if change == "unmap":
                del case.policy["subjects"]["owner"]
            elif change == "remove_client":
                case.policy["clients"] = {"different-client": [READ]}
            else:
                case.policy["clients"]["synthetic-client"] = [READ]
            case.path.write_text(json.dumps(case.policy), encoding="utf-8")
        assert client.get(request["review_url"]).status_code in {401, 403}
        with case.scope.factory() as db:
            assert db.scalar(select(func.count()).select_from(Project)) == 0


def test_bad_signature_headers_and_private_key_configuration(client_case):
    case = client_case
    token = case.token()
    header, body, signature = token.split(".")
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert case.authority.verify(".".join([header, body, changed_signature])) is None
    claims = jwt.decode(token, options={"verify_signature": False})
    for extra in (
        {"typ": "JWT"},
        {"jku": "https://untrusted.example.test/key"},
        {"kid": "unknown"},
    ):
        headers = {"kid": "synthetic", "typ": "at+jwt"} | extra
        bad = jwt.encode(claims, case.key, algorithm="RS256", headers=headers)
        assert case.authority.verify(bad) is None
    case.policy["public_keys"]["synthetic"]["d"] = "never-accept-private-material"
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    with pytest.raises(ValueError, match="Private"):
        ClientAuthority(case.path)
    assert case.authority.verify(token) is None


def test_postgresql_confirms_one_request_once(client_case, postgresql_session_factory):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from classifire.services import draft_client_requests as commands

    case = client_case
    factory = postgresql_session_factory
    with case.scope.factory() as original, factory() as db:
        source = original.get(User, case.scope.users["owner"])
        db.add(
            User(
                id=source.id,
                email=source.email,
                full_name=source.full_name,
                password_hash=source.password_hash,
                role=source.role,
                is_active=True,
            )
        )
        db.commit()
        identity = case.authority.verify(case.token())
        request = commands.prepare(
            db,
            case.authority,
            identity,
            "create",
            {"reference": "PG-CLIENT", "name": "Synthetic PG client"},
        )
        request_id, payload_hash = request.id, request.payload_hash
        db.commit()
    barrier = Barrier(2)

    def decide_once():
        with factory() as db:
            actor = db.get(User, identity.user_id)
            barrier.wait(timeout=20)
            try:
                result = commands.decide(db, case.authority, actor, request_id, payload_hash, True)
                db.commit()
                return result["status"]
            except scopes.DraftScopeError as exc:
                db.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: decide_once(), range(2)))
    assert sorted(outcomes) == ["CLIENT_REQUEST_ALREADY_DECIDED", "confirmed"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(DraftScope)) == 1
    _assert_no_canonical_scope(factory)


@pytest.mark.parametrize(
    "destination,expected",
    [
        (
            "/client-requests/00000000-0000-0000-0000-000000000001",
            "/client-requests/00000000-0000-0000-0000-000000000001",
        ),
        ("https://untrusted.example.test", "/"),
        ("//untrusted.example.test", "/"),
        ("/client-requests/../logout", "/"),
        (
            "/client-requests/00000000-0000-0000-0000-000000000001?next=https://untrusted.example.test",
            "/",
        ),
    ],
)
def test_login_returns_only_to_an_exact_local_review(scope_app, destination, expected):
    from test_draft_scope_ui import PASSWORD

    with TestClient(scope_app.app, base_url="https://testserver") as client:
        page = client.get("/login", params={"next": destination})
        assert f'name="return_to" value="{expected}"' in page.text
        response = client.post(
            "/login",
            data={
                "email": "owner@scope.example.test",
                "password": PASSWORD,
                "csrf_token": _csrf(page.text),
                "return_to": destination,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303 and response.headers["location"] == expected


def test_database_parameters_never_escape_as_tool_errors(client_case, monkeypatch, caplog):
    from sqlalchemy.exc import SQLAlchemyError

    case = client_case
    with case.scope.factory() as db:
        actor = db.get(User, case.scope.users["owner"])
        draft = scopes.create_draft_project(db, actor, "SQL-ERROR", "Synthetic")
        identifier = draft.id
        db.commit()

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("synthetic-private-database-parameter")

    monkeypatch.setattr(scopes, "read_revision", unavailable)
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        result = tool(
            client, case.token(), "read_draft_scope", {"draft_id": identifier}, error=True
        )
        assert "CLIENT_DATABASE_UNAVAILABLE" in json.dumps(result)
        assert "synthetic-private-database-parameter" not in json.dumps(result)
        assert "synthetic-private-database-parameter" not in caplog.text


@pytest.mark.parametrize("issuer", ["https://auth.example.test/",
                                   "https://auth.example.test/tenant/"])
def test_trailing_slash_issuer_is_preserved_and_matched_exactly(client_case, issuer):
    from fastapi import FastAPI

    case = client_case
    case.policy["issuer"] = issuer
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    authority = ClientAuthority(case.path)
    identity = authority.verify(case.token())
    assert identity is not None and identity.issuer == issuer
    assert authority.verify(case.token(iss=issuer.rstrip("/"))) is None
    app = FastAPI()
    configure(app, authority, case.scope.factory)
    with TestClient(app) as client:
        metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.status_code == 200
        assert metadata.json()["authorization_servers"] == [issuer]
    # The resource base remains an exact origin, not an issuer URL.
    case.policy["base_url"] += "/"
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    with pytest.raises(ValueError, match="base URL must be an origin"):
        ClientAuthority(case.path)


def test_optional_nbf_accepts_absence_but_validates_present_values(client_case):
    case = client_case
    claims = jwt.decode(case.token(), options={"verify_signature": False})
    del claims["nbf"]

    def signed(payload):
        return jwt.encode(payload, case.key, algorithm="RS256",
                          headers={"kid": "synthetic", "typ": "at+jwt"})

    token = signed(claims)
    assert case.authority.verify(token) is not None
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        assert rpc(client, token, "tools/list").status_code == 200
    for value in (claims["iat"] - 60, claims["iat"]):
        assert case.authority.verify(signed({**claims, "nbf": value})) is not None
    for value in (claims["iat"] + 3600, None, True, False, str(claims["iat"]),
                  float(claims["iat"]), float("inf"), float("-inf"), float("nan"), [], {}):
        assert case.authority.verify(signed({**claims, "nbf": value})) is None, repr(value)
    _assert_no_canonical_scope(case.scope.factory)


def test_absent_nbf_preserves_required_claims_and_security_checks(client_case):
    case = client_case
    claims = jwt.decode(case.token(), options={"verify_signature": False})
    del claims["nbf"]

    def signed(payload, **headers):
        return jwt.encode(payload, case.key, algorithm="RS256",
                          headers={"kid": "synthetic", "typ": "at+jwt", **headers})

    for field in ("iss", "aud", "iat", "exp", "sub", "client_id", "jti", "scope"):
        incomplete = {k: v for k, v in claims.items() if k != field}
        assert case.authority.verify(signed(incomplete)) is None, field
    invalid = [
        {"iss": "https://foreign.example.test"},
        {"aud": "https://foreign.example.test/mcp"},
        {"aud": [claims["aud"]]},
        {"sub": "unmapped"}, {"client_id": "unmapped"}, {"jti": ""},
        {"scope": WRITE}, {"scope": READ + " administrator"},
        {"iat": claims["iat"] + 60, "exp": claims["iat"] + 600},
        {"iat": claims["iat"] - 120, "exp": claims["iat"] - 60},
        {"exp": claims["iat"]}, {"exp": claims["iat"] + 901},
    ]
    invalid += [{field: value} for field in ("iat", "exp")
                for value in (None, True, False, str(claims[field]), float(claims[field]),
                              float("inf"), float("-inf"), float("nan"))]
    for overrides in invalid:
        assert case.authority.verify(signed({**claims, **overrides})) is None, overrides
    for headers in ({"typ": "JWT"}, {"kid": "unknown"}, {"jku": "https://foreign.test"}):
        assert case.authority.verify(signed(claims, **headers)) is None
    token = signed(claims)
    header, body, signature = token.split(".")
    changed = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert case.authority.verify(".".join([header, body, changed])) is None
    case.policy["revoked_token_ids"] = [claims["jti"]]
    case.path.write_text(json.dumps(case.policy), encoding="utf-8")
    assert case.authority.verify(token) is None


@pytest.mark.parametrize(
    "client_case", [{"oauth_resource": "https://gateway.example.test/v1/mcp/synthetic"}],
    indirect=True,
)
def test_external_resource_keeps_exact_audience_and_local_review_origin(client_case):
    case = client_case
    resource = case.policy["oauth_resource"]
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        metadata = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert metadata["resource"] == resource
        assert rpc(client, case.token(), "tools/list").status_code == 200
        for audience in ("https://testserver/mcp", resource + "/", resource + "-other", [resource]):
            assert rpc(client, case.token(aud=audience), "tools/list").status_code == 401
        request = tool(
            client, case.token(), "propose_draft_project",
            {"reference": "EXT-01", "name": "Synthetic external resource"},
        )
        assert request["review_url"].startswith("https://testserver/client-requests/")
    _assert_no_canonical_scope(case.scope.factory)
    for field, value in (("oauth_resource", resource + "-changed"), ("base_url", "https://other.example.test")):
        changed = {**case.policy, field: value}
        case.path.write_text(json.dumps(changed), encoding="utf-8")
        assert case.authority.verify(case.token()) is None


def test_invalid_explicit_oauth_resources_fail_closed(client_case):
    case = client_case
    for value in ("", "http://127.0.0.1:8820/mcp", "http://foreign.example.test/mcp",
                  "https://user:password@example.test/mcp", "https://example.test/mcp?q=1",
                  "https://example.test/mcp#fragment", "https://exa mple.test/mcp", [], 7):
        case.path.write_text(json.dumps({**case.policy, "oauth_resource": value}), encoding="utf-8")
        with pytest.raises(ValueError):
            ClientAuthority(case.path, development=True)


@pytest.mark.parametrize(
    "client_case",
    [{"issuer": "https://auth.example.test/", "auth0_oidc_compatibility": True}],
    indirect=True,
)
def test_opt_in_oidc_token_discovery_preserves_permissions(client_case):
    case = client_case
    resource = case.authority.initial.resource
    audience = [resource, case.policy["issuer"] + "userinfo"]
    token = case.token(aud=audience, scope="openid email " + READ)
    identity = case.authority.verify(token)
    assert identity is not None and identity.scopes == [READ]
    with TestClient(case.scope.app, base_url="https://testserver") as client:
        assert rpc(client, token, "tools/list").status_code == 200
        assert tool(client, token, "list_draft_projects") is not None
        tool(
            client,
            token,
            "propose_draft_project",
            {"reference": "OIDC", "name": "Synthetic"},
            error=True,
        )
    assert case.authority.verify(case.token(aud=list(reversed(audience)))) is not None
    assert case.authority.verify(case.token()) is not None
    for invalid in (
        [resource],
        audience + ["https://foreign.example/"],
        [resource, resource],
        [audience[1]],
        [audience[1], audience[1]],
        [resource, 42],
        [resource, {"value": audience[1]}],
        audience[1],
        [resource, audience[1] + "/"],
        [resource + "/", audience[1]],
    ):
        assert case.authority.verify(case.token(aud=invalid)) is None
    for overrides in (
        {"scope": "openid email"},
        {"scope": READ + " profile"},
        {"scope": READ + " offline_access"},
        {"scope": READ + " administrator"},
        {"iss": "https://other.example/"},
        {"client_id": "other"},
        {"sub": "unmapped-subject"},
        {"exp": int(time.time()) - 1},
        {"iat": int(time.time()) + 60},
        {"nbf": int(time.time()) + 60},
        {"exp": int(time.time()) + 1000},
    ):
        assert case.authority.verify(case.token(aud=audience, **overrides)) is None
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode(
        claims, other_key, algorithm="RS256", headers={"kid": "synthetic", "typ": "at+jwt"}
    )
    assert case.authority.verify(forged) is None
    case.path.write_text(
        json.dumps({**case.policy, "revoked_token_ids": ["synthetic-token"]}), encoding="utf-8"
    )
    assert case.authority.verify(token) is None
    _assert_no_canonical_scope(case.scope.factory)


def test_oidc_compatibility_is_default_off_and_requires_restart(client_case):
    case = client_case
    assert case.authority.verify(case.token(scope=READ + " openid email")) is None
    assert case.authority.verify(case.token(aud=[case.authority.initial.resource])) is None
    case.path.write_text(
        json.dumps({**case.policy, "issuer": "https://auth.example.test/"}), encoding="utf-8"
    )
    strict = ClientAuthority(case.path)
    case.path.write_text(
        json.dumps(
            {
                **case.policy,
                "issuer": "https://auth.example.test/",
                "auth0_oidc_compatibility": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Restart required"):
        strict.policy()
    case.path.write_text(
        json.dumps({**case.policy, "auth0_oidc_compatibility": True}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="exact HTTPS issuer"):
        ClientAuthority(case.path)
