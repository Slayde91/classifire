"""Opt-in OAuth resource boundary. No token issuance or automatic account linking."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from mcp.server.auth.provider import AccessToken
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .models import User
from .services.draft_scope import DraftScopeError

READ = "classifire:draft:read"
WRITE = "classifire:draft:propose"
EXPORT = "classifire:draft:export"
SCOPES = {READ, WRITE, EXPORT}


class ClientPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    base_url: str
    issuer: str
    public_keys: dict[str, dict[str, Any]]
    subjects: dict[str, str]
    clients: dict[str, list[str]]
    revoked_token_ids: list[str] = Field(default_factory=list)

    @property
    def resource(self) -> str:
        return self.base_url + "/mcp"


def load_policy(path: Path, *, development: bool = False) -> ClientPolicy:
    # Operator-owned local policy, never a client-selected URL, key or filesystem path.
    raw = path.read_bytes()
    if len(raw) > 1048576:
        raise ValueError("Client policy exceeds limit")
    policy = ClientPolicy.model_validate_json(raw)
    for value in (policy.base_url, policy.issuer):
        parsed = urlsplit(value)
        local = development and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (parsed.scheme != "https" and not (local and parsed.scheme == "http")) or (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or value.endswith("/")
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Client endpoints require exact HTTPS URLs")
    if urlsplit(policy.base_url).path:
        raise ValueError("Client base URL must be an origin")
    if not policy.public_keys or not policy.subjects or not policy.clients:
        raise ValueError("Client policy requires public keys and explicit account/client bindings")
    for key_id, key in policy.public_keys.items():
        if key.get("kty") != "RSA" or key.get("alg") != "RS256" or key.get("use") != "sig":
            raise ValueError("Only RS256 signing public keys are accepted")
        if set(key) - {"kty", "alg", "use", "kid", "n", "e", "key_ops"}:
            raise ValueError("Private or unsupported key material is forbidden")
        if key.get("key_ops", ["verify"]) != ["verify"] or key.get("kid") != key_id:
            raise ValueError("Signing key ID and verification purpose must match")
        if jwt.PyJWK.from_dict(key, algorithm="RS256").key.key_size < 2048:
            raise ValueError("RSA public keys must be at least 2048 bits")
    for identifier in policy.subjects.values():
        if str(UUID(identifier)) != identifier:
            raise ValueError("Bind subjects to exact local User IDs")
    if any(not set(scopes) <= SCOPES for scopes in policy.clients.values()):
        raise ValueError("Unsupported client scopes")
    return policy


@dataclass(frozen=True)
class ClientIdentity:
    user_id: str
    subject: str
    client_id: str
    issuer: str
    resource: str
    token_id: str
    expires_at: int
    scopes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClientAuthority:
    def __init__(self, path: Path, *, development: bool = False):
        self.path, self.development = path, development
        self.initial = load_policy(path, development=development)

    def policy(self) -> ClientPolicy:
        policy = load_policy(self.path, development=self.development)
        if (policy.issuer, policy.resource) != (self.initial.issuer, self.initial.resource):
            raise ValueError("Restart required when client issuer or resource changes")
        return policy

    def check(self, identity: ClientIdentity, scope: str) -> None:
        try:
            policy = self.policy()
            valid = (
                identity.issuer == policy.issuer
                and identity.resource == policy.resource
                and identity.expires_at > time.time()
                and policy.subjects.get(identity.subject) == identity.user_id
                and identity.client_id in policy.clients
                and identity.token_id not in policy.revoked_token_ids
                and scope in identity.scopes
                and scope in policy.clients[identity.client_id]
            )
        except (OSError, ValueError, TypeError):
            valid = False
        if not valid:
            raise DraftScopeError("CLIENT_AUTHORIZATION_REQUIRED", 403)

    def actor(self, db: Session, identity: ClientIdentity, scope: str) -> User:
        self.check(identity, scope)
        actor = db.get(User, identity.user_id, populate_existing=True)
        if actor is None or not actor.is_active:
            raise DraftScopeError("CLIENT_AUTHORIZATION_REQUIRED", 403)
        return actor

    def verify(self, token: str) -> ClientIdentity | None:
        try:
            if len(token) > 16384:
                return None
            policy = self.policy()
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or header.get("typ") != "at+jwt":
                return None
            if set(header) - {"alg", "typ", "kid"}:
                return None
            key = policy.public_keys[header["kid"]]
            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(key, algorithm="RS256"),
                algorithms=["RS256"],
                issuer=policy.issuer,
                audience=policy.resource,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "exp",
                        "iat",
                        "nbf",
                        "sub",
                        "client_id",
                        "jti",
                        "scope",
                    ],
                    "strict_aud": True,
                },
            )
            if any(type(claims[k]) is not int for k in ("exp", "iat", "nbf")):
                return None
            if not 0 < claims["exp"] - claims["iat"] <= 900:
                return None
            if any(
                not isinstance(claims[k], str) or not claims[k]
                for k in ("sub", "client_id", "jti", "scope")
            ):
                return None
            scopes = claims["scope"].split()
            if not set(scopes) <= SCOPES:
                return None
            identity = ClientIdentity(
                policy.subjects[claims["sub"]],
                claims["sub"],
                claims["client_id"],
                policy.issuer,
                policy.resource,
                claims["jti"],
                claims["exp"],
                scopes,
            )
            self.check(identity, READ)
            return identity
        except (jwt.PyJWTError, OSError, ValueError, KeyError, TypeError, DraftScopeError):
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self.verify(token)
        if identity is None:
            return None
        return AccessToken(
            token=token,
            client_id=identity.client_id,
            scopes=identity.scopes,
            expires_at=identity.expires_at,
            resource=identity.resource,
            subject=identity.subject,
            claims=identity.as_dict(),
        )


def stored_identity(raw: str) -> ClientIdentity:
    try:
        return ClientIdentity(**json.loads(raw))
    except (TypeError, ValueError) as exc:
        raise DraftScopeError("CLIENT_REQUEST_CORRUPT", 409) from exc
