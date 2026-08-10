from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class TechnicalLibraryDefinition:
    """Stable identity for one manufacturer or governed technical corpus."""

    technical_library_id: str
    library_code: str
    library_name: str
    manufacturer: str
    source_package: str | None
    executable_variant_package: str | None
    jurisdiction: str
    system_categories: tuple[str, ...] = ()

    def as_manifest_entry(self) -> dict[str, Any]:
        return {
            "technical_library_id": self.technical_library_id,
            "library_code": self.library_code,
            "library_name": self.library_name,
            "manufacturer": self.manufacturer,
            "source_package": self.source_package,
            "executable_variant_package": self.executable_variant_package,
            "jurisdiction": self.jurisdiction,
            "system_categories": list(self.system_categories),
        }


@dataclass(frozen=True, slots=True)
class TechnicalLibraryReleaseReference:
    """Immutable reference to one independently approved library release."""

    technical_library_id: str
    technical_library_release_id: str
    version: str
    manifest_hash: str
    status: str = "active"

    def as_manifest_entry(self) -> dict[str, str]:
        return {
            "technical_library_id": self.technical_library_id,
            "technical_library_release_id": self.technical_library_release_id,
            "version": self.version,
            "manifest_hash": self.manifest_hash,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class TechnicalRegistryRelease:
    """Estimate-pinnable umbrella over independently governed technical libraries."""

    registry_release_id: str
    version: str
    library_releases: tuple[TechnicalLibraryReleaseReference, ...]

    def __post_init__(self) -> None:
        library_ids = [item.technical_library_id for item in self.library_releases]
        if len(library_ids) != len(set(library_ids)):
            raise ValueError("A Technical Registry Release cannot contain the same library twice")
        if not self.library_releases:
            raise ValueError("A Technical Registry Release must contain at least one library release")

    def as_manifest(self) -> dict[str, Any]:
        return {
            "schema": "CLASSIFIRE-TECHNICAL-REGISTRY-RELEASE-v1",
            "registry_release_id": self.registry_release_id,
            "version": self.version,
            "libraries": [
                item.as_manifest_entry()
                for item in sorted(
                    self.library_releases,
                    key=lambda row: row.technical_library_id,
                )
            ],
        }


FIREFLY_TECHNICAL_LIBRARY = TechnicalLibraryDefinition(
    technical_library_id="TECHLIB-FIREFLY",
    library_code="FIREFLY-P15",
    library_name="FIREFLY Technical System Library",
    manufacturer="FIREFLY",
    source_package="15",
    executable_variant_package="17",
    jurisdiction="Australia",
    system_categories=(
        "service_penetrations",
        "fire_seals",
        "barrier_penetrations",
    ),
)


def technical_library_by_id(
    technical_library_id: str,
    libraries: Iterable[TechnicalLibraryDefinition] = (FIREFLY_TECHNICAL_LIBRARY,),
) -> TechnicalLibraryDefinition:
    for library in libraries:
        if library.technical_library_id == technical_library_id:
            return library
    raise KeyError(f"Unknown CLASSIFIRE technical library: {technical_library_id}")


__all__ = [
    "FIREFLY_TECHNICAL_LIBRARY",
    "TechnicalLibraryDefinition",
    "TechnicalLibraryReleaseReference",
    "TechnicalRegistryRelease",
    "technical_library_by_id",
]
