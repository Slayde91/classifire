from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_draft_scope_demo.py"
ORIGIN = "http://127.0.0.1:8820"
READ = "classifire:draft:read"
WRAPPER = """
import json,os,runpy,sys
from pathlib import Path
import uvicorn
from fastapi.testclient import TestClient

def check_app(app, **kwargs):
    assert kwargs['host'] == '127.0.0.1'
    with TestClient(app,base_url='http://127.0.0.1:8820') as client:
        metadata=client.get('/.well-known/oauth-protected-resource/mcp')
        assert metadata.status_code == 200
        external = os.environ.get('SYNTHETIC_DEMO_TEST_TOKEN')
        issuer = 'https://auth.example.test/' if external else 'http://127.0.0.1:8820'
        assert metadata.json()['authorization_servers'] == [issuer]
        headers={'Accept':'application/json, text/event-stream',
                 'MCP-Protocol-Version':'2025-11-25'}
        body={'jsonrpc':'2.0','id':1,'method':'tools/list'}
        assert client.post('/mcp',headers=headers,json=body).status_code == 401
        token=external or Path('synthetic-client-token.txt').read_text()
        headers['Authorization']='Bearer '+token
        assert client.post('/mcp',headers=headers,json=body).status_code == 200
        assert client.get('/scopes',follow_redirects=False).status_code in (302,303,307)
        assert client.get('/login').status_code == 200
        assert client.get('/brand/classifire-logo.png').status_code == 200
    print('EXTERNAL_APP_CHECKS_PASSED')
uvicorn.run=check_app
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
"""


@pytest.fixture
def external_policy(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public.update(alg="RS256", use="sig", kid="synthetic")
    policy = {
        "base_url": ORIGIN,
        "issuer": "https://auth.example.test/",
        "public_keys": {"synthetic": public},
        "subjects": {"synthetic-human": str(uuid4())},
        "clients": {"synthetic-human-client": [READ]},
    }
    path = tmp_path / "operator-policy.json"
    return key, policy, path


def run_demo(directory, *arguments, token=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLASSIFIRE_")}
    env["PYTHONPATH"] = str(ROOT / "src")
    if token is not None:
        env["SYNTHETIC_DEMO_TEST_TOKEN"] = token
    return subprocess.run(  # noqa: S603 - fixed repo script and synthetic test arguments
        [
            sys.executable,
            "-c",
            WRAPPER,
            str(SCRIPT),
            "--data-dir",
            str(directory),
            "--port",
            "8820",
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_external_demo_preparation_restart_and_binding_guards(tmp_path, external_policy):
    key, policy, path = external_policy
    directory = tmp_path / "trial"
    prepared = run_demo(directory, "--prepare-external-client")
    assert prepared.returncode == 0, prepared.stderr
    assert "No listener started" in prepared.stdout
    user_id = re.search(r"estimator ID: ([0-9a-f-]{36})", prepared.stdout).group(1)
    with sqlite3.connect(directory / "demo.sqlite3") as db:
        assert db.execute("SELECT role FROM users").fetchall() == [("estimator",)]
        assert db.execute("SELECT count(*) FROM projects").fetchone() == (0,)
    policy["subjects"] = {"synthetic-human": user_id}
    path.write_text(json.dumps(policy), encoding="utf-8")
    original = path.read_bytes()
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": policy["issuer"],
            "aud": ORIGIN + "/mcp",
            "sub": "synthetic-human",
            "client_id": "synthetic-human-client",
            "jti": "synthetic",
            "iat": now,
            "exp": now + 600,
            "scope": READ,
        },
        key,
        algorithm="RS256",
        headers={"kid": "synthetic", "typ": "at+jwt"},
    )
    for _ in range(2):
        started = run_demo(directory, "--external-client-policy", str(path), token=token)
        assert started.returncode == 0, started.stderr
        assert "EXTERNAL_APP_CHECKS_PASSED" in started.stdout
        assert path.read_bytes() == original
        assert not (directory / "synthetic-client-token.txt").exists()
    refused = run_demo(directory, "--client-demo")
    assert refused.returncode != 0 and "not a Draft Scope demo directory" in refused.stderr
    policy["subjects"] = {"synthetic-human": str(uuid4())}
    path.write_text(json.dumps(policy), encoding="utf-8")
    refused = run_demo(directory, "--external-client-policy", str(path))
    assert refused.returncode != 0 and "does not bind" in refused.stderr
    with sqlite3.connect(directory / "demo.sqlite3") as db:
        assert db.execute("SELECT role FROM users").fetchall() == [("estimator",)]
        assert db.execute("SELECT count(*) FROM projects").fetchone() == (0,)
    with sqlite3.connect(directory / "demo.sqlite3") as db:
        db.execute("UPDATE users SET role='administrator'")
    refused = run_demo(directory, "--external-client-policy", str(path))
    assert refused.returncode != 0 and "active synthetic estimator" in refused.stderr
    with sqlite3.connect(directory / "demo.sqlite3") as db:
        assert db.execute("SELECT role FROM users").fetchall() == [("administrator",)]
    # An existing administrator-style marker cannot be adopted as an external trial.
    marker = directory / "classifire-draft-scope-demo.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    del payload["external_client"]
    marker.write_text(json.dumps(payload), encoding="utf-8")
    refused = run_demo(directory, "--prepare-external-client")
    assert refused.returncode != 0 and "not a Draft Scope demo directory" in refused.stderr


def test_external_policy_rejects_broader_or_mismatched_authority(external_policy):
    _, policy, path = external_policy
    spec = importlib.util.spec_from_file_location("external_demo_policy_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    user_id = next(iter(policy["subjects"].values()))
    path.write_text(json.dumps(policy), encoding="utf-8")
    module.validate_external_policy(path, ORIGIN, user_id)
    changes = [
        {"base_url": "http://127.0.0.1:8822"},
        {"issuer": "http://127.0.0.1:8820"},
        {"subjects": {"synthetic-human": str(uuid4())}},
        {"subjects": {"one": user_id, "two": user_id}},
        {"clients": {"one": [READ], "two": [READ]}},
        {"clients": {"one": [READ, "classifire:draft:technical"]}},
        {"clients": {"one": [READ, "classifire:draft:estimate"]}},
        {"clients": {"one": ["classifire:draft:propose"]}},
    ]
    private = copy.deepcopy(policy["public_keys"])
    private["synthetic"]["d"] = "not-a-real-private-key"
    changes.append({"public_keys": private})
    for change in changes:
        path.write_text(json.dumps({**policy, **change}), encoding="utf-8")
        with pytest.raises(ValueError):
            module.validate_external_policy(path, ORIGIN, user_id)


def test_original_synthetic_client_mode_remains_separate(tmp_path):
    directory = tmp_path / "original-demo"
    result = run_demo(directory, "--client-demo")
    assert result.returncode == 0, result.stderr
    assert "EXTERNAL_APP_CHECKS_PASSED" in result.stdout
    assert (directory / "synthetic-client-token.txt").exists()
    marker = json.loads((directory / "classifire-draft-scope-demo.json").read_text())
    assert "external_client" not in marker
    with sqlite3.connect(directory / "demo.sqlite3") as db:
        assert db.execute("SELECT role FROM users").fetchall() == [("administrator",)]
    refused = run_demo(directory, "--prepare-external-client")
    assert refused.returncode != 0 and "not a Draft Scope demo directory" in refused.stderr
