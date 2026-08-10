from __future__ import annotations

import pytest

from classifire.services.technical_registry import (
    FIREFLY_TECHNICAL_LIBRARY,
    TechnicalLibraryDefinition,
    TechnicalLibraryReleaseReference,
    TechnicalRegistryRelease,
    technical_library_by_id,
)


def _release(library_id: str, release_id: str, version: str) -> TechnicalLibraryReleaseReference:
    return TechnicalLibraryReleaseReference(
        technical_library_id=library_id,
        technical_library_release_id=release_id,
        version=version,
        manifest_hash=(library_id + release_id).encode().hex()[:64].ljust(64, "0"),
    )


def test_package_15_is_identified_as_firefly_library() -> None:
    library = FIREFLY_TECHNICAL_LIBRARY

    assert library.technical_library_id == "TECHLIB-FIREFLY"
    assert library.library_name == "FIREFLY Technical System Library"
    assert library.manufacturer == "FIREFLY"
    assert library.source_package == "15"
    assert library.executable_variant_package == "17"


def test_registry_can_hold_multiple_independent_libraries() -> None:
    firefly = _release("TECHLIB-FIREFLY", "TECHLIBREL-FIREFLY-2.13", "2.13-runtime")
    promat = _release("TECHLIB-PROMAT", "TECHLIBREL-PROMAT-1.0", "1.0-runtime")
    registry = TechnicalRegistryRelease(
        registry_release_id="CLASSIFIRE-TECH-REGISTRY-3.0",
        version="3.0",
        library_releases=(promat, firefly),
    )

    manifest = registry.as_manifest()

    assert manifest["schema"] == "CLASSIFIRE-TECHNICAL-REGISTRY-RELEASE-v1"
    assert [row["technical_library_id"] for row in manifest["libraries"]] == [
        "TECHLIB-FIREFLY",
        "TECHLIB-PROMAT",
    ]


def test_registry_rejects_duplicate_library_release_members() -> None:
    first = _release("TECHLIB-FIREFLY", "REL-A", "1")
    second = _release("TECHLIB-FIREFLY", "REL-B", "2")

    with pytest.raises(ValueError, match="same library twice"):
        TechnicalRegistryRelease(
            registry_release_id="REG-1",
            version="1",
            library_releases=(first, second),
        )


def test_registry_requires_at_least_one_library() -> None:
    with pytest.raises(ValueError, match="at least one"):
        TechnicalRegistryRelease(
            registry_release_id="REG-EMPTY",
            version="1",
            library_releases=(),
        )


def test_library_lookup_is_explicit_and_fail_closed() -> None:
    assert technical_library_by_id("TECHLIB-FIREFLY") is FIREFLY_TECHNICAL_LIBRARY

    with pytest.raises(KeyError):
        technical_library_by_id("TECHLIB-NOT-REGISTERED")


def test_future_library_definition_does_not_change_firefly_identity() -> None:
    future = TechnicalLibraryDefinition(
        technical_library_id="TECHLIB-PROMAT",
        library_code="PROMAT-TECH",
        library_name="Promat Technical System Library",
        manufacturer="Promat",
        source_package=None,
        executable_variant_package=None,
        jurisdiction="Australia",
    )

    assert technical_library_by_id(
        "TECHLIB-FIREFLY",
        libraries=(future, FIREFLY_TECHNICAL_LIBRARY),
    ) is FIREFLY_TECHNICAL_LIBRARY
