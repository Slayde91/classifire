from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from classifire.models import StoredFile
from classifire.services.storage import (
    StoredFileBindingError,
    read_verified_stored_file,
)


def _stored_file(
    storage_root: Path,
    *,
    content: bytes = b'verified retained report bytes\n',
    purpose: str = 'project_evidence',
    scan_status: str = 'clean',
) -> tuple[StoredFile, Path]:
    storage_root.mkdir()
    path = storage_root / 'report.pdf'
    path.write_bytes(content)
    stored = StoredFile(
        original_filename='report.pdf',
        media_type='application/pdf',
        storage_path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        purpose=purpose,
        malware_scan_status=scan_status,
        immutable=True,
    )
    return stored, path


def test_verified_read_returns_the_exact_hash_bound_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    payload = b'verified retained report bytes\n'
    stored, _path = _stored_file(storage_root, content=payload)

    result = read_verified_stored_file(
        stored,
        storage_root=storage_root,
        required_purpose='project_evidence',
    )

    assert result.content == payload
    assert result.size_bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.media_type == 'application/pdf'


@pytest.mark.parametrize(
    ('purpose', 'scan_status', 'code'),
    [
        ('technical_evidence', 'clean', 'STORED_FILE_PURPOSE_MISMATCH'),
        ('project_evidence', 'pending', 'STORED_FILE_SCAN_STATUS_FORBIDDEN'),
    ],
)
def test_verified_read_rejects_file_state_outside_the_adapter_contract(
    tmp_path: Path,
    purpose: str,
    scan_status: str,
    code: str,
) -> None:
    storage_root = tmp_path / 'storage'
    stored, _path = _stored_file(
        storage_root,
        purpose=purpose,
        scan_status=scan_status,
    )

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == code


def test_verified_read_rejects_changed_size_before_it_returns_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    stored, path = _stored_file(storage_root)
    path.write_bytes(b'changed retained report bytes')

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_SIZE_MISMATCH'


def test_verified_read_rejects_same_size_hash_tampering(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    stored, path = _stored_file(storage_root)
    path.write_bytes(b'x' * stored.size_bytes)

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_HASH_MISMATCH'


def test_verified_read_rejects_path_outside_the_configured_storage_root(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / 'storage'
    stored, _path = _stored_file(storage_root)
    outside = tmp_path / 'outside.pdf'
    outside.write_bytes(b'outside storage root')
    stored.storage_path = str(outside)

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_PATH_OUTSIDE_ROOT'


def test_verified_read_rejects_symbolic_linked_retained_file(tmp_path: Path) -> None:
    storage_root = tmp_path / 'storage'
    stored, path = _stored_file(storage_root)
    target = storage_root / 'target.pdf'
    target.write_bytes(b'separate retained report bytes')
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip('symbolic links are unavailable in this environment')

    with pytest.raises(StoredFileBindingError) as raised:
        read_verified_stored_file(
            stored,
            storage_root=storage_root,
            required_purpose='project_evidence',
        )

    assert raised.value.code == 'STORED_FILE_PATH_UNSAFE'
