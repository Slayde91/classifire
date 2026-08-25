from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

RuntimeConfigurationCode = Literal[
    "PRODUCTION_SECRET_KEY_WEAK",
    "PRODUCTION_SESSION_HTTPS_REQUIRED",
    "PRODUCTION_POSTGRESQL_REQUIRED",
    "PRODUCTION_TRUSTED_HOSTS_REQUIRED",
    "PRODUCTION_TRUSTED_HOST_WILDCARD",
    "PRODUCTION_TRUSTED_HOST_INVALID",
    "PRODUCTION_ALLOWED_ORIGINS_REQUIRED",
    "PRODUCTION_ALLOWED_ORIGIN_WILDCARD",
    "PRODUCTION_ALLOWED_ORIGIN_HTTPS_REQUIRED",
    "PRODUCTION_ALLOWED_ORIGIN_INVALID",
    "PRODUCTION_ALLOWED_ORIGIN_HOST_UNTRUSTED",
]


@dataclass(frozen=True, slots=True)
class RuntimeConfigurationFinding:
    """A stable, safe-to-display production configuration finding."""

    code: RuntimeConfigurationCode
    message: str


class RuntimeConfigurationError(RuntimeError):
    """Raised before work starts when production configuration is unsafe."""

    def __init__(self, findings: tuple[RuntimeConfigurationFinding, ...]) -> None:
        if not findings:
            raise ValueError("RuntimeConfigurationError requires at least one finding")
        self.findings = findings
        codes = ", ".join(finding.code for finding in findings)
        super().__init__(f"Production configuration rejected: {codes}")


_KNOWN_SECRET_KEYS = frozenset(
    {
        "change-me",
        "change-me-immediately",
        "change-this-to-a-long-random-value",
        "development-only-change-me",
    }
)


def _secret_key_is_weak(secret_key: str) -> bool:
    repeated_unit = bool(secret_key and secret_key in (secret_key + secret_key)[1:-1])
    return (
        secret_key != secret_key.strip()
        or len(secret_key) < 32
        or secret_key.casefold() in _KNOWN_SECRET_KEYS
        or len(set(secret_key)) < 8
        or repeated_unit
    )


def _is_postgresql_url(database_url: str) -> bool:
    if database_url != database_url.strip():
        return False
    try:
        parsed = make_url(database_url)
    except (ArgumentError, ValueError):
        return False
    return parsed.drivername == "postgresql+psycopg" and bool(parsed.host) and bool(parsed.database)


def normalise_exact_host(host: str) -> str | None:
    if not host or host != host.strip() or "*" in host:
        return None
    if any(character in host for character in ("/", "?", "#", "@")) or "://" in host:
        return None

    candidate = host.casefold()
    try:
        address = ip_address(candidate)
        return str(address) if address.version == 4 else None
    except ValueError:
        pass

    if len(candidate) > 253 or candidate.startswith(".") or candidate.endswith("."):
        return None
    labels = candidate.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(
            character.isascii() and (character.isalnum() or character == "-") for character in label
        )
        for label in labels
    ):
        return None
    return candidate


def _origin_host(origin: str) -> tuple[str | None, str | None]:
    """Return a normalised host and any safe validation category."""

    if (
        not origin
        or origin != origin.strip()
        or "*" in origin
        or "\\" in origin
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in origin
        )
    ):
        return None, "wildcard" if "*" in origin else "invalid"
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return None, "invalid"
    if parsed.scheme.casefold() != "https":
        return None, "https"
    if (
        not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        return None, "invalid"
    if port is not None and not 1 <= port <= 65535:
        return None, "invalid"
    host = normalise_exact_host(parsed.hostname)
    if host is None:
        return None, "invalid"
    canonical_origin = f"https://{host}"
    if port is not None and port != 443:
        canonical_origin = f"{canonical_origin}:{port}"
    if origin != canonical_origin:
        return None, "invalid"
    return host, None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLASSIFIRE_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/classifire.db"
    secret_key: str = "development-only-change-me"  # noqa: S105 - non-production default
    host: str = "127.0.0.1"
    port: int = 8787
    storage_root: Path = Path("./data/storage")
    max_upload_mb: int = 100
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8787", "http://localhost:8787"]
    )
    trusted_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])
    session_https_only: bool = False
    clamav_host: str | None = None
    clamav_port: int = 3310
    mission_control_url: str = "http://127.0.0.1:3000"
    mission_control_api_key: str | None = None
    openclaw_config_path: Path | None = None
    openclaw_state_dir: Path | None = None
    adjudicated_initial_submission_enabled: bool = False
    adjudicated_admission_public_keys: dict[str, str] = Field(default_factory=dict)
    adjudicated_admission_issuer_key_ids: dict[str, list[str]] = Field(default_factory=dict)
    currency: str = "AUD"
    tax_name: str = "GST"
    tax_rate: str = "0.10"
    jurisdiction: str = "NSW/ACT, Australia"
    default_length_unit: str = "mm"
    default_area_unit: str = "m2"

    @field_validator("allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "adjudicated_admission_public_keys",
        "adjudicated_admission_issuer_key_ids",
        mode="before",
    )
    @classmethod
    def require_mapping_configuration(cls, value: object) -> object:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("must be a JSON object")
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def production_findings(self) -> tuple[RuntimeConfigurationFinding, ...]:
        if self.env != "production":
            return ()

        findings: dict[str, RuntimeConfigurationFinding] = {}

        def add(code: RuntimeConfigurationCode, message: str) -> None:
            findings.setdefault(code, RuntimeConfigurationFinding(code=code, message=message))

        if _secret_key_is_weak(self.secret_key):
            add(
                "PRODUCTION_SECRET_KEY_WEAK",
                "CLASSIFIRE_SECRET_KEY must be a strong, private random value "
                "of at least 32 characters",
            )
        if not self.session_https_only:
            add(
                "PRODUCTION_SESSION_HTTPS_REQUIRED",
                "CLASSIFIRE_SESSION_HTTPS_ONLY must be true in production",
            )
        if not _is_postgresql_url(self.database_url):
            add(
                "PRODUCTION_POSTGRESQL_REQUIRED",
                "CLASSIFIRE_DATABASE_URL must use PostgreSQL in production",
            )

        trusted_hosts: set[str] = set()
        if not self.trusted_hosts:
            add(
                "PRODUCTION_TRUSTED_HOSTS_REQUIRED",
                "CLASSIFIRE_TRUSTED_HOSTS must explicitly list at least one host in production",
            )
        for host in self.trusted_hosts:
            if "*" in host:
                add(
                    "PRODUCTION_TRUSTED_HOST_WILDCARD",
                    "CLASSIFIRE_TRUSTED_HOSTS must not contain wildcard entries",
                )
                continue
            normalised_host = normalise_exact_host(host)
            if normalised_host is None:
                add(
                    "PRODUCTION_TRUSTED_HOST_INVALID",
                    "CLASSIFIRE_TRUSTED_HOSTS must contain only exact host names or IPv4 addresses",
                )
                continue
            trusted_hosts.add(normalised_host)

        if not self.allowed_origins:
            add(
                "PRODUCTION_ALLOWED_ORIGINS_REQUIRED",
                "CLASSIFIRE_ALLOWED_ORIGINS must explicitly list at least one "
                "HTTPS origin in production",
            )
        for origin in self.allowed_origins:
            origin_host, invalid_category = _origin_host(origin)
            if invalid_category == "wildcard":
                add(
                    "PRODUCTION_ALLOWED_ORIGIN_WILDCARD",
                    "CLASSIFIRE_ALLOWED_ORIGINS must not contain wildcard entries",
                )
                continue
            if invalid_category == "https":
                add(
                    "PRODUCTION_ALLOWED_ORIGIN_HTTPS_REQUIRED",
                    "CLASSIFIRE_ALLOWED_ORIGINS must contain only HTTPS origins",
                )
                continue
            if invalid_category == "invalid" or origin_host is None:
                add(
                    "PRODUCTION_ALLOWED_ORIGIN_INVALID",
                    "CLASSIFIRE_ALLOWED_ORIGINS must contain exact origins without "
                    "paths, credentials, queries, or fragments",
                )
                continue
            if origin_host not in trusted_hosts:
                add(
                    "PRODUCTION_ALLOWED_ORIGIN_HOST_UNTRUSTED",
                    "Every CLASSIFIRE_ALLOWED_ORIGINS host must also be listed in "
                    "CLASSIFIRE_TRUSTED_HOSTS",
                )

        return tuple(findings.values())

    def validate_production(self) -> list[str]:
        """Return legacy string findings for existing callers."""

        return [finding.message for finding in self.production_findings()]


def require_runtime_configuration(settings: Settings) -> None:
    findings = settings.production_findings()
    if findings:
        raise RuntimeConfigurationError(findings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
