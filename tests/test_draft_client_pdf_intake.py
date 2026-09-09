from __future__ import annotations

import base64
import hashlib
import json
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client import rpc, tool
from test_draft_pdf_intake import pdf_bytes
from test_draft_scope_ui import _app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.config import Settings
from classifire.draft_client import configure
from classifire.draft_client_auth import READ, WRITE, ClientAuthority
from classifire.draft_pdf_ui import router as pdf_router
from classifire.models import DraftClientRequest, DraftPdfSource, User
from classifire.services import draft_pdf_intake as pdf
from classifire.services import draft_scope as scopes
from classifire.services.malware_scan import ScanVerdict
from classifire.services.remote_file_retrieval import RetrievedFile

postgresql_session_factory = _postgres
scope_password_hash = _scope_password_hash


@pytest.fixture
def pdf_client_case(postgresql_session_factory, tmp_path, scope_password_hash, monkeypatch):
    factory = postgresql_session_factory
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public.update(alg="RS256", use="sig", kid="synthetic")
    with factory() as db:
        users: dict[str, str] = {}
        for name in ("owner", "other", "reader"):
            user = User(
                email=f"{name}@pdf-client.example.test",
                full_name=f"PDF client {name}",
                password_hash=scope_password_hash,
                role="read_only" if name == "reader" else "estimator",
                is_active=True,
            )
            db.add(user)
            db.flush()
            users[name] = user.id
        owner = db.get(User, users["owner"])
        draft = scopes.create_draft_project(
            db, owner, "CHATGPT-PDF", "ChatGPT PDF intake prototype"
        )
        db.commit()
        draft_id = draft.id

    policy = {
        "base_url": "https://testserver",
        "issuer": "https://auth.example.test",
        "public_keys": {"synthetic": public},
        "subjects": users,
        "clients": {"synthetic-client": [READ, WRITE]},
    }
    path = tmp_path / "client-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    authority = ClientAuthority(path)
    settings = Settings(
        storage_root=tmp_path / "retained",
        clamav_host="127.0.0.1",
        draft_client_file_download_hosts=["files.example.test"],
        _env_file=None,
    )
    settings.storage_root.mkdir()
    app = _app(factory)
    app.include_router(pdf_router)
    mounted = configure(app, authority, factory)

    @asynccontextmanager
    async def lifespan(application):
        async with mounted.router.lifespan_context(mounted):
            yield

    app.router.lifespan_context = lifespan

    content = pdf_bytes("ChatGPT selected PDF evidence")
    fetched: list[str] = []

    def retrieve(url, remote_policy):
        fetched.append(url)
        assert remote_policy.allowed_hosts == frozenset({"files.example.test"})
        assert remote_policy.maximum_bytes == 10 * 1024 * 1024
        return RetrievedFile(
            content=content,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            media_type="application/pdf",
            host="files.example.test",
            redirect_count=0,
            resolved_address_count=1,
            tls_version="TLSv1.3",
        )

    def clean(value, **kwargs):
        del kwargs
        now = datetime.now(UTC).isoformat()
        return ScanVerdict(
            hashlib.sha256(value).hexdigest(),
            len(value),
            "clean",
            "ClamAV synthetic",
            "synthetic-db",
            now,
            now,
        )

    from classifire import draft_client_evidence_tools as evidence_tools

    monkeypatch.setattr(evidence_tools, "get_settings", lambda: settings)
    monkeypatch.setattr(evidence_tools, "retrieve_file", retrieve)
    monkeypatch.setattr(pdf.malware_scan, "scan_bytes", clean)

    def token(user="owner", scopes=(READ, WRITE), **overrides):
        now = int(time.time())
        claims = {
            "iss": policy["issuer"],
            "aud": policy["base_url"] + "/mcp",
            "sub": user,
            "client_id": "synthetic-client",
            "jti": f"synthetic-{user}",
            "iat": now,
            "nbf": now,
            "exp": now + 600,
            "scope": " ".join(scopes),
        }
        claims.update(overrides)
        return jwt.encode(
            claims, key, algorithm="RS256", headers={"kid": "synthetic", "typ": "at+jwt"}
        )

    return SimpleNamespace(
        app=app,
        factory=factory,
        draft_id=draft_id,
        owner_id=users["owner"],
        settings=settings,
        fetched=fetched,
        content=content,
        token=token,
        evidence_tools=evidence_tools,
    )


def test_chatgpt_file_parameter_upload_scan_and_page_read(pdf_client_case):
    case = pdf_client_case
    signed_url = "https://files.example.test/download?token=never-persist-this"
    with TestClient(case.app, base_url="https://testserver") as client:
        token_value = case.token()
        discovery = rpc(client, token_value, "tools/list")
        assert discovery.status_code == 200, discovery.text
        exposed = {
            item["name"]: item for item in discovery.json()["result"]["tools"]
        }
        upload_tool = exposed["upload_draft_pdf"]
        assert upload_tool["annotations"] == {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        }
        assert upload_tool["_meta"] == {
            "securitySchemes": [{"type": "oauth2", "scopes": [READ, WRITE]}],
            "openai/fileParams": ["file"],
        }
        assert upload_tool["inputSchema"]["required"] == ["draft_id", "file"]
        file_schema = upload_tool["inputSchema"]["$defs"]["ChatGPTFile"]
        assert file_schema["required"] == ["download_url", "file_id"]
        assert set(file_schema["properties"]) == {
            "download_url",
            "file_id",
            "mime_type",
            "file_name",
        }

        uploaded = tool(
            client,
            token_value,
            "upload_draft_pdf",
            {
                "draft_id": case.draft_id,
                "file": {
                    "download_url": signed_url,
                    "file_id": "file_synthetic",
                    "mime_type": "application/pdf",
                    "file_name": "inspection-report.pdf",
                },
            },
        )
        assert case.fetched == [signed_url]
        assert uploaded["source"]["status"] == "pending"
        assert uploaded["source"]["ready"] is False
        assert uploaded["source"]["filename"] == "inspection-report.pdf"
        assert uploaded["source"]["sha256"] == hashlib.sha256(case.content).hexdigest()
        assert uploaded["retrieval"] == {
            "file_id": "file_synthetic",
            "sha256": hashlib.sha256(case.content).hexdigest(),
            "size_bytes": len(case.content),
            "media_type": "application/pdf",
            "host": "files.example.test",
            "redirect_count": 0,
        }
        assert signed_url not in json.dumps(uploaded)
        source_id = uploaded["source"]["id"]

        scanned = tool(
            client,
            token_value,
            "scan_draft_pdf",
            {"draft_id": case.draft_id, "source_id": source_id},
        )
        assert scanned["source"]["status"] == "clean"
        assert scanned["source"]["ready"] is True
        assert scanned["source"]["document_sha256"]

        page = tool(
            client,
            token_value,
            "read_draft_pdf_page",
            {
                "draft_id": case.draft_id,
                "source_id": source_id,
                "page_number": 1,
            },
        )
        assert page["document"]["schema"] == "CLASSIFIRE-DRAFT-PDF-v1"
        assert page["document"]["page_count"] == 1
        assert page["page"]["page_number"] == 1
        assert "ChatGPT selected PDF evidence" in page["page"]["text"]
        assert page["page"]["locator_key"]
        assert page["page"]["page_text_sha256"]

        listing = tool(
            client,
            token_value,
            "list_draft_pdf_sources",
            {"draft_id": case.draft_id},
        )
        assert listing["limit"] == 20
        assert len(listing["sources"]) == 1
        assert listing["sources"][0]["source"]["id"] == source_id

    with case.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftPdfSource)) == 1
        assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == 0
        assert scopes.read_revision(db, db.get(User, case.owner_id), case.draft_id)["revision"] == 1


def test_pdf_client_refuses_unauthorized_owner_and_invalid_metadata(
    pdf_client_case, monkeypatch
):
    case = pdf_client_case
    arguments = {
        "draft_id": case.draft_id,
        "file": {
            "download_url": "https://files.example.test/download?token=secret",
            "file_id": "file_synthetic",
            "mime_type": "application/pdf",
            "file_name": "inspection-report.pdf",
        },
    }
    with TestClient(case.app, base_url="https://testserver") as client:
        denied = tool(
            client,
            case.token(scopes=(READ,)),
            "upload_draft_pdf",
            arguments,
            error=True,
        )
        assert "CLIENT_AUTHORIZATION_REQUIRED" in str(denied)

        foreign = tool(
            client,
            case.token(user="other"),
            "upload_draft_pdf",
            arguments,
            error=True,
        )
        assert "DRAFT_NOT_FOUND" in str(foreign)

        invalid = dict(arguments)
        invalid["file"] = dict(arguments["file"], mime_type="text/html")
        wrong_media = tool(
            client,
            case.token(),
            "upload_draft_pdf",
            invalid,
            error=True,
        )
        assert "CLIENT_PDF_MEDIA_TYPE_INVALID" in str(wrong_media)

        monkeypatch.setattr(
            case.evidence_tools,
            "get_settings",
            lambda: Settings(
                storage_root=case.settings.storage_root,
                clamav_host="127.0.0.1",
                draft_client_file_download_hosts=[],
                _env_file=None,
            ),
        )
        not_configured = tool(
            client,
            case.token(),
            "upload_draft_pdf",
            arguments,
            error=True,
        )
        assert "CLIENT_FILE_POLICY_INVALID" in str(not_configured)

    assert case.fetched == []


def test_pdf_page_image_returns_bound_png_without_scope_writes(pdf_client_case):
    case = pdf_client_case
    with TestClient(case.app, base_url="https://testserver") as client:
        token = case.token()
        source = tool(client, token, "upload_draft_pdf", {
            "draft_id": case.draft_id, "file": {
                "download_url": "https://files.example.test/report.pdf",
                "file_id": "synthetic", "file_name": "inspection.pdf",
            },
        })["source"]
        args = {"draft_id": case.draft_id, "source_id": source["id"], "page_number": 1}
        tool(client, token, "read_draft_pdf_page_image", args, error=True)
        tool(client, token, "scan_draft_pdf", {
            "draft_id": case.draft_id, "source_id": source["id"],
        })
        response = rpc(client, case.token(scopes=(READ,)), "tools/call", {
            "name": "read_draft_pdf_page_image", "arguments": args,
        })
        assert response.status_code == 200
        result = response.json()["result"]
        assert not result.get("isError")
        metadata = result["structuredContent"]
        images = [block for block in result["content"] if block["type"] == "image"]
        assert len(images) == 1
        image = base64.b64decode(images[0]["data"], validate=True)
        assert images[0]["mimeType"] == "image/png"
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        assert metadata["image_sha256"] == hashlib.sha256(image).hexdigest()
        assert metadata["source"]["id"] == source["id"]
        assert metadata["source"]["document_sha256"]
        assert metadata["page_number"] == 1 and metadata["locator_key"]
        assert metadata["evidence_status"] == "unreviewed"
        with case.factory() as db:
            expected = pdf.page_preview(db, db.get(User, case.owner_id), case.draft_id,
                                        source["id"], 1, settings=case.settings)
            assert image == expected
        for invalid_page in (0, 2, True):
            tool(client, token, "read_draft_pdf_page_image",
                 dict(args, page_number=invalid_page), error=True)
        tool(client, case.token(user="other"), "read_draft_pdf_page_image", args, error=True)
        denied = rpc(client, case.token(scopes=(WRITE,)), "tools/call", {
            "name": "read_draft_pdf_page_image", "arguments": args,
        })
        assert denied.status_code == 401
        with case.factory() as db:
            db.get(DraftPdfSource, source["id"]).document_sha256 = "a" * 64
            db.commit()
        tool(client, token, "read_draft_pdf_page_image", args, error=True)
    with case.factory() as db:
        assert scopes.read_revision(db, db.get(User, case.owner_id), case.draft_id)["revision"] == 1
        assert db.scalar(select(func.count()).select_from(DraftClientRequest)) == 0
