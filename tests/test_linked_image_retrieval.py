from __future__ import annotations

import json
import socket
import traceback
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageOps

from classifire.services import linked_image_retrieval as linked

LEAK_MARKER = "capability-value-that-must-never-leak"


def _uri(*, host: str = "twiddle.onuptick.com", path: str = "/media/photo.jpg") -> str:
    return (
        f"https://{host}{path}?Expires=32503680000&Key-Pair-Id=PAIR"
        f"&Signature={LEAK_MARKER}&public_id=PUBLIC-ID&transform=FULL-SIZE"
    )


def _jpeg_bytes(size: tuple[int, int], *, different: bool = False) -> bytes:
    colour = (235, 15, 210) if different else (20, 80, 160)
    image = Image.new("RGB", size, colour)
    draw = ImageDraw.Draw(image)
    if different:
        draw.rectangle((0, 0, size[0] // 2, size[1]), fill=(250, 220, 10))
    else:
        draw.ellipse(
            (size[0] // 5, size[1] // 5, size[0] * 4 // 5, size[1] * 4 // 5),
            fill=(220, 170, 30),
        )
        draw.line(
            (0, 0, size[0], size[1]),
            fill=(245, 245, 245),
            width=max(1, size[0] // 20),
        )
    spacing = max(4, min(size) // 40)
    grid_colours = (
        ((90, 70, 20), (120, 95, 25))
        if different
        else (
            (35, 95, 175),
            (15, 65, 145),
        )
    )
    for index, offset in enumerate(range(0, min(size), spacing)):
        vertical = tuple(min(255, value + (index % 7) * 4) for value in grid_colours[0])
        horizontal = tuple(min(255, value + (index % 5) * 5) for value in grid_colours[1])
        draw.line((offset, 0, offset, size[1]), fill=vertical, width=1)
        draw.line((0, offset, size[0], offset), fill=horizontal, width=1)
    if different:
        for index in range(12):
            y0 = round(index * size[1] / 12)
            y1 = round((index + 1) * size[1] / 12)
            draw.rectangle(
                (size[0] // 2, y0, size[0], y1),
                fill=(70 + index * 8, 105 + index * 6, 30 + index * 3),
            )
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _write_embedded(path: Path, source: bytes) -> None:
    with Image.open(BytesIO(source)) as image:
        image.resize((50, 50), Image.Resampling.LANCZOS).save(path, format="JPEG", quality=90)


def _write_embedded_fit(
    path: Path,
    source: bytes,
    *,
    size: tuple[int, int] = (50, 50),
    centering: tuple[float, float] = (0.5, 0.5),
) -> None:
    with Image.open(BytesIO(source)) as image:
        ImageOps.fit(
            image.convert("RGB"),
            size,
            Image.Resampling.LANCZOS,
            centering=centering,
        ).save(path, format="PNG")


def _jpeg_from_image(image: Image.Image) -> bytes:
    output = BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=95)
    return output.getvalue()


def _photo_row(embedded: Path, *, photo_id: str = "P001-I01") -> dict:
    return {
        "photo_id": photo_id,
        "page_number": 1,
        "bbox": [10.0, 10.0, 60.0, 60.0],
        "native_path": str(embedded),
        "native_width": 50,
        "native_height": 50,
        "width": 50,
        "height": 50,
        "digest": "embedded-digest",
        "tiny_artifact": False,
        "decorative_candidate": False,
    }


def _candidate(embedded: Path, *, uri: str | None = None) -> linked.LinkedImageCandidate:
    raw_uri = uri or _uri()
    validated = linked._validate_uri(raw_uri, linked.DEFAULT_LINKED_IMAGE_POLICY)
    return linked.LinkedImageCandidate(
        photo_id="P001-I01",
        page_number=1,
        required=True,
        embedded_path=embedded,
        embedded_sha256=linked._sha256_file(embedded),
        embedded_width=50,
        embedded_height=50,
        photo_bbox=(10.0, 10.0, 60.0, 60.0),
        annotation_bbox=(10.0, 10.0, 60.0, 60.0),
        overlap_ratio=1.0,
        annotation_xrefs=(42, 43),
        uri_sha256=linked._sha256_bytes(raw_uri.encode("utf-8")),
        host=validated.host,
        path_sha256=validated.path_sha256,
        suffix=validated.suffix,
        query_keys=validated.query_keys,
        uri=raw_uri,
    )


def _report(tmp_path: Path) -> tuple[Path, str]:
    report = tmp_path / "report.pdf"
    report.write_bytes(b"controlled test report")
    return report, linked._sha256_file(report)


def _patch_candidate_extraction(
    monkeypatch: pytest.MonkeyPatch, candidate: linked.LinkedImageCandidate
) -> None:
    monkeypatch.setattr(
        linked,
        "extract_candidates",
        lambda _report, _rows, _policy, **_kwargs: (
            {candidate.photo_id: candidate},
            {},
            {candidate.photo_id},
        ),
    )


def test_candidate_repr_and_receipt_never_contain_raw_signed_uri(tmp_path: Path) -> None:
    embedded = tmp_path / "embedded.jpg"
    embedded.write_bytes(_jpeg_bytes((50, 50)))
    candidate = _candidate(embedded)
    result = linked.LinkedImageResult(
        photo_id=candidate.photo_id,
        page_number=1,
        required=True,
        status="UNAPPROVED_HOST",
        uri_sha256=candidate.uri_sha256,
    )

    assert LEAK_MARKER not in repr(candidate)
    assert LEAK_MARKER not in json.dumps(result.receipt_row())
    assert "uri" not in result.receipt_row()


@pytest.mark.parametrize(
    ("uri", "reason"),
    [
        (_uri(host="evil.example"), "UNAPPROVED_HOST"),
        (_uri(path="/media/photo.png"), "UNAPPROVED_IMAGE_PATH"),
        (_uri() + "&extra=value", "UNEXPECTED_QUERY_KEYS"),
        (_uri().replace("https://", "http://"), "UNSAFE_SCHEME"),
        (_uri().replace("https://", "https://user@"), "UNSAFE_USERINFO"),
        (_uri() + "#fragment", "UNSAFE_FRAGMENT"),
        (_uri(path="/media%2Fphoto.jpg"), "UNSAFE_PATH"),
    ],
)
def test_exact_uri_policy_rejects_unapproved_forms(uri: str, reason: str) -> None:
    with pytest.raises(linked.LinkedImageError) as captured:
        linked._validate_uri(uri, linked.DEFAULT_LINKED_IMAGE_POLICY)
    assert captured.value.code == reason
    assert LEAK_MARKER not in str(captured.value)


def test_malformed_query_traceback_suppresses_capability_value() -> None:
    malformed = _uri().replace("&public_id=", f"&bad-field-{LEAK_MARKER}&public_id=")
    try:
        linked._validate_uri(malformed, linked.DEFAULT_LINKED_IMAGE_POLICY)
    except linked.LinkedImageError as exc:
        rendered = "".join(traceback.format_exception(exc))
    else:  # pragma: no cover - defensive assertion
        pytest.fail("malformed query unexpectedly passed")
    assert LEAK_MARKER not in rendered


def test_public_address_policy_rejects_private_and_mixed_answers() -> None:
    assert linked._public_ip("8.8.8.8") is True
    assert linked._public_ip("127.0.0.1") is False
    with pytest.raises(linked.LinkedImageError) as captured:
        linked._pinned_https_get(
            _uri(),
            linked.DEFAULT_LINKED_IMAGE_POLICY,
            lambda _host, _port: [
                (socket.AF_INET, "8.8.8.8"),
                (socket.AF_INET, "10.0.0.1"),
            ],
        )
    assert captured.value.code == "NON_PUBLIC_DNS_ADDRESS"


def test_materialize_validates_jpeg_and_reuses_bound_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)
    calls: list[str] = []

    def transport(uri: str, _policy, resolver) -> linked._FetchHop:
        calls.append(uri)
        assert resolver("twiddle.onuptick.com", 443) == [(socket.AF_INET, "8.8.8.8")]
        return linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            declared_length=len(source),
            body=source,
            resolved_address_count=1,
            tls_version="TLSv1.3",
        )

    batch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        resolver=lambda _host, _port: [(socket.AF_INET, "8.8.8.8")],
        transport=transport,
    )

    assert batch.ok is True
    assert batch.rows[0]["full_resolution_status"] == "VERIFIED"
    assert batch.rows[0]["full_resolution_width"] == 1000
    assert batch.rows[0]["full_resolution_height"] == 1000
    assert linked.preferred_verified_linked_path(batch.rows[0], tmp_path) is not None
    item = batch.receipt["items"][0]
    assert batch.receipt["schema"].endswith("-v2")
    assert batch.receipt["policy_version"].endswith("-v2")
    assert item["thumbnail_transform"] == "FULL_FRAME_RESIZE"
    assert item["thumbnail_crop_box_normalized"] == [0.0, 0.0, 1.0, 1.0]
    assert item["thumbnail_matching_tiles"] == 16
    assert item["thumbnail_tile_count"] == 16
    assert item["thumbnail_comparison_group_count"] == 1
    assert item["usable_detail_gradient_gain_ratio"] > 1.1
    serialized = json.dumps(batch.receipt)
    assert LEAK_MARKER not in serialized
    assert _uri() not in serialized
    assert len(calls) == 1

    def forbidden_transport(_uri_value, _policy, _resolver) -> linked._FetchHop:
        raise AssertionError("a valid bound prior receipt must not redownload")

    cached = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        prior_receipt=batch.receipt,
        resolver=lambda _host, _port: [(socket.AF_INET, "8.8.8.8")],
        transport=forbidden_transport,
    )
    assert cached.ok is True
    assert cached.rows[0]["full_resolution_status"] == "CACHED"


def test_materialize_fails_closed_on_private_dns_without_leaking_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)

    batch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        resolver=lambda _host, _port: [(socket.AF_INET, "127.0.0.1")],
        transport=linked._pinned_https_get,
    )

    assert batch.ok is False
    assert batch.rows[0]["full_resolution_status"] == "NON_PUBLIC_DNS_ADDRESS"
    assert LEAK_MARKER not in repr(batch)
    assert LEAK_MARKER not in json.dumps(batch.receipt)


def test_materialize_rejects_mime_confusion_and_thumbnail_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)

    wrong_mime = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "mime",
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="text/html",
            body=source,
        ),
    )
    assert wrong_mime.rows[0]["full_resolution_status"] == "CONTENT_TYPE_REJECTED"

    different = _jpeg_bytes((1000, 1000), different=True)
    mismatch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "mismatch",
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=different,
        ),
    )
    assert mismatch.rows[0]["full_resolution_status"] == "THUMBNAIL_MISMATCH"


def test_absolute_resolution_floor_and_run_budget_are_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    embedded = tmp_path / "embedded.jpg"
    small = _jpeg_bytes((200, 200))
    _write_embedded(embedded, small)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)

    too_small = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "small",
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=small,
        ),
    )
    assert too_small.rows[0]["full_resolution_status"] == "NOT_HIGHER_RESOLUTION"

    large = _jpeg_bytes((1000, 1000))
    budget_policy = replace(linked.DEFAULT_LINKED_IMAGE_POLICY, maximum_run_bytes=10)
    exhausted = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "budget",
        report_sha256=report_sha256,
        policy=budget_policy,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=large,
        ),
    )
    assert exhausted.rows[0]["full_resolution_status"] == "RUN_BYTE_LIMIT_EXCEEDED"
    assert exhausted.receipt["total_received_bytes"] == len(large)


def test_extract_candidates_rejects_one_annotation_overlapping_two_photos(
    tmp_path: Path,
) -> None:
    import pymupdf

    report = tmp_path / "linked.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(10, 10, 60, 60),
            "uri": _uri(),
        }
    )
    document.save(report)
    document.close()
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(_jpeg_bytes((50, 50)))
    second.write_bytes(_jpeg_bytes((50, 50)))
    rows = [_photo_row(first, photo_id="P001-I01"), _photo_row(second, photo_id="P001-I02")]

    candidates, failures, required = linked.extract_candidates(report, rows)

    assert candidates == {}
    assert required == {"P001-I01", "P001-I02"}
    assert failures == {
        "P001-I01": "AMBIGUOUS_ANNOTATION_BINDING",
        "P001-I02": "AMBIGUOUS_ANNOTATION_BINDING",
    }


def test_preferred_path_revalidates_hash_format_and_recorded_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)
    batch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    row = dict(batch.rows[0])
    assert linked.preferred_verified_linked_path(row, tmp_path) is not None
    row["full_resolution_width"] = 999
    assert linked.preferred_verified_linked_path(row, tmp_path) is None
    row["full_resolution_width"] = 1000
    row["full_resolution_sha256"] = "a" * 64
    assert linked.preferred_verified_linked_path(row, tmp_path) is None


def test_duplicate_photo_ids_fail_before_extraction(tmp_path: Path) -> None:
    report, report_sha256 = _report(tmp_path)
    embedded = tmp_path / "embedded.jpg"
    embedded.write_bytes(_jpeg_bytes((50, 50)))
    row = _photo_row(embedded)
    with pytest.raises(linked.LinkedImageError) as captured:
        linked.materialize_linked_images(
            report,
            [row, dict(row)],
            tmp_path,
            report_sha256=report_sha256,
        )
    assert captured.value.code == "INVALID_PHOTO_INVENTORY"


def test_same_host_redirect_is_revalidated_and_cross_host_redirect_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)
    responses = [
        linked._FetchHop(
            status=302,
            redirect_location=_uri(path="/media/redirected.jpg"),
        ),
        linked._FetchHop(status=200, content_type="image/jpeg", body=source),
    ]
    passed = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "same-host",
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: responses.pop(0),
    )
    assert passed.ok is True
    assert passed.results[0].redirect_count == 1

    rejected = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "cross-host",
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=302,
            redirect_location=_uri(host="evil.example"),
        ),
    )
    assert rejected.ok is False
    assert rejected.rows[0]["full_resolution_status"] == "UNAPPROVED_HOST"
    assert LEAK_MARKER not in json.dumps(rejected.receipt)


@pytest.mark.parametrize(
    ("hop", "expected_status"),
    [
        (
            linked._FetchHop(
                status=200,
                content_type="image/jpeg",
                content_encoding="gzip",
                body=b"not-used",
            ),
            "CONTENT_ENCODING_REJECTED",
        ),
        (
            linked._FetchHop(
                status=200,
                content_type="image/jpeg",
                declared_length=999,
                body=b"\xff\xd8\xffshort",
            ),
            "CONTENT_LENGTH_MISMATCH",
        ),
        (
            linked._FetchHop(
                status=200,
                content_type="image/jpeg",
                body=b"\xff\xd8\xffnot-a-valid-jpeg",
            ),
            "INVALID_JPEG",
        ),
    ],
)
def test_response_encoding_length_and_invalid_jpeg_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hop: linked._FetchHop,
    expected_status: str,
) -> None:
    report, report_sha256 = _report(tmp_path)
    embedded = tmp_path / "embedded.jpg"
    embedded.write_bytes(_jpeg_bytes((50, 50)))
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)

    batch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / expected_status,
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: hop,
    )
    assert batch.ok is False
    assert batch.rows[0]["full_resolution_status"] == expected_status


def test_byte_and_pixel_limits_reject_before_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)

    byte_policy = replace(
        linked.DEFAULT_LINKED_IMAGE_POLICY,
        maximum_image_bytes=len(source) - 1,
    )
    byte_limited = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "byte-limit",
        report_sha256=report_sha256,
        policy=byte_policy,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    assert byte_limited.rows[0]["full_resolution_status"] == "IMAGE_TOO_LARGE"

    pixel_policy = replace(linked.DEFAULT_LINKED_IMAGE_POLICY, maximum_pixels=900_000)
    pixel_limited = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "pixel-limit",
        report_sha256=report_sha256,
        policy=pixel_policy,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    assert pixel_limited.rows[0]["full_resolution_status"] == "IMAGE_DIMENSIONS_REJECTED"


def test_content_address_collision_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)
    destination = tmp_path / "collision"
    digest = linked._sha256_bytes(source)
    target = destination / linked._stored_relative_path(digest)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing-different-bytes")

    batch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        destination,
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    assert batch.rows[0]["full_resolution_status"] == "CONTENT_ADDRESS_COLLISION"
    assert target.read_bytes() == b"existing-different-bytes"


def test_prior_cache_is_rebound_after_content_and_embedded_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    original_candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, original_candidate)
    initial = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    stored = linked.preferred_verified_linked_path(initial.rows[0], tmp_path)
    assert stored is not None
    stored.write_bytes(b"tampered-cache-bytes")
    content_calls = 0

    def content_transport(_uri_value, _policy, _resolver) -> linked._FetchHop:
        nonlocal content_calls
        content_calls += 1
        return linked._FetchHop(status=200, content_type="image/jpeg", body=source)

    content_tamper = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        prior_receipt=initial.receipt,
        transport=content_transport,
    )
    assert content_calls == 1
    assert content_tamper.rows[0]["full_resolution_status"] == "CONTENT_ADDRESS_COLLISION"

    replacement = _jpeg_bytes((1000, 1000), different=True)
    _write_embedded(embedded, replacement)
    replacement_candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, replacement_candidate)
    embedded_calls = 0

    def embedded_transport(_uri_value, _policy, _resolver) -> linked._FetchHop:
        nonlocal embedded_calls
        embedded_calls += 1
        return linked._FetchHop(status=200, content_type="image/jpeg", body=replacement)

    embedded_tamper = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path / "new-embedded",
        report_sha256=report_sha256,
        prior_receipt=initial.receipt,
        transport=embedded_transport,
    )
    assert embedded_calls == 1
    assert embedded_tamper.rows[0]["full_resolution_status"] == "VERIFIED"


def test_atomic_store_failure_cleans_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _jpeg_bytes((1000, 1000))
    digest = linked._sha256_bytes(body)

    def fail_replace(_source, _target) -> None:
        raise OSError("controlled storage failure")

    monkeypatch.setattr(linked.os, "replace", fail_replace)
    with pytest.raises(linked.LinkedImageError) as captured:
        linked._atomic_store(tmp_path, body, digest)
    assert captured.value.code == "STORAGE_FAILURE"
    assert list(tmp_path.rglob("*.part")) == []


def test_ipv4_mapped_private_address_is_rejected() -> None:
    assert linked._public_ip("::ffff:127.0.0.1") is False
    assert linked._public_ip("::ffff:10.0.0.1") is False


def test_total_timeout_is_checked_after_transport_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)
    monotonic_values = iter((0.0, 0.0, 100.0, 0.0, 0.0, 100.0))
    monkeypatch.setattr(linked.time, "monotonic", lambda: next(monotonic_values))

    batch = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    assert batch.rows[0]["full_resolution_status"] == "TOTAL_TIMEOUT"


def test_v2_declared_center_crop_records_evidence_and_rejects_off_center_or_mirror(
    tmp_path: Path,
) -> None:
    source = _jpeg_bytes((900, 1200))
    embedded = tmp_path / "embedded-center.png"
    _write_embedded_fit(embedded, source)

    evidence = linked.confirm_image_binding(
        embedded,
        source,
        require_usable_detail_gain=True,
    )

    assert evidence.transform == "CENTER_CROP_COVER"
    assert evidence.crop_box == pytest.approx((0.0, 0.125, 1.0, 0.875))
    assert evidence.hash_distance <= 8
    assert evidence.mean_error <= 0.08
    assert evidence.matching_tiles >= 12
    assert evidence.worst_tile_mean_error <= 0.14

    off_center = tmp_path / "embedded-off-center.png"
    _write_embedded_fit(off_center, source, centering=(0.5, 0.0))
    with pytest.raises(linked.LinkedImageError) as cropped:
        linked.confirm_image_binding(off_center, source)
    assert cropped.value.code in {"LOW_INFORMATION_THUMBNAIL", "THUMBNAIL_MISMATCH"}

    with Image.open(BytesIO(source)) as image:
        mirrored = _jpeg_from_image(ImageOps.mirror(image))
    with pytest.raises(linked.LinkedImageError) as reflected:
        linked.confirm_image_binding(embedded, mirrored)
    assert reflected.value.code == "THUMBNAIL_MISMATCH"


def test_v2_rejects_low_information_hash_collisions_and_localized_substitution(
    tmp_path: Path,
) -> None:
    uniform = Image.new("RGB", (1000, 1000), (120, 120, 120))
    uniform_body = _jpeg_from_image(uniform)
    uniform_embedded = tmp_path / "uniform.png"
    _write_embedded_fit(uniform_embedded, uniform_body)
    with pytest.raises(linked.LinkedImageError) as low_information:
        linked.confirm_image_binding(uniform_embedded, uniform_body)
    assert low_information.value.code == "LOW_INFORMATION_THUMBNAIL"

    size = 1000
    grayscale = Image.new("RGB", (size, size))
    colour_shifted = Image.new("RGB", (size, size))
    grayscale_draw = ImageDraw.Draw(grayscale)
    shifted_draw = ImageDraw.Draw(colour_shifted)
    for x in range(size):
        value = 35 + round(180 * x / (size - 1))
        grayscale_draw.line((x, 0, x, size), fill=(value, value, value))
        shifted_draw.line(
            (x, 0, x, size),
            fill=(min(255, value + 55), max(0, value - 25), value),
        )
    grayscale_body = _jpeg_from_image(grayscale)
    shifted_body = _jpeg_from_image(colour_shifted)
    gradient_embedded = tmp_path / "gradient.png"
    _write_embedded_fit(gradient_embedded, grayscale_body)
    with Image.open(gradient_embedded) as raw:
        expected_hash = linked._difference_hash(raw.convert("RGB"))
    with Image.open(BytesIO(shifted_body)) as raw:
        candidate_hash = linked._difference_hash(
            raw.resize((50, 50), Image.Resampling.LANCZOS).convert("RGB")
        )
    assert (expected_hash ^ candidate_hash).bit_count() <= 8
    with pytest.raises(linked.LinkedImageError) as colour_collision:
        linked.confirm_image_binding(gradient_embedded, shifted_body)
    assert colour_collision.value.code == "THUMBNAIL_MISMATCH"

    source = _jpeg_bytes((1000, 1000))
    localized_embedded = tmp_path / "localized.png"
    _write_embedded_fit(localized_embedded, source)
    with Image.open(BytesIO(source)) as raw:
        changed = raw.convert("RGB")
    ImageDraw.Draw(changed).rectangle((0, 0, 499, 499), fill=(250, 15, 15))
    permissive_global_policy = replace(
        linked.DEFAULT_LINKED_IMAGE_POLICY,
        maximum_thumbnail_hash_distance=64,
        maximum_thumbnail_mean_error=0.40,
        minimum_thumbnail_luma_stddev=0.0,
        minimum_thumbnail_entropy_bits=0.0,
        minimum_thumbnail_mean_gradient=0.0,
    )
    with pytest.raises(linked.LinkedImageError) as localized:
        linked.confirm_image_binding(
            localized_embedded,
            _jpeg_from_image(changed),
            policy=permissive_global_policy,
        )
    assert localized.value.code == "THUMBNAIL_MISMATCH"


def test_v2_groups_exact_pixels_but_rejects_nonexact_alternate_binding(
    tmp_path: Path,
) -> None:
    source = _jpeg_bytes((1000, 1000))
    primary = tmp_path / "primary.jpg"
    _write_embedded(primary, source)
    with Image.open(primary) as raw:
        pixels = raw.convert("RGB")
    exact_reencoding = tmp_path / "exact-reencoding.png"
    pixels.save(exact_reencoding, format="PNG", compress_level=9)

    exact = linked.confirm_image_binding(
        primary,
        source,
        alternate_embedded_paths=[exact_reencoding],
    )
    assert exact.comparison_group_count == 1

    altered = pixels.copy()
    altered.putpixel((0, 0), (0, 0, 0))
    alternate = tmp_path / "near-duplicate.png"
    altered.save(alternate, format="PNG")
    with pytest.raises(linked.LinkedImageError) as ambiguous:
        linked.confirm_image_binding(
            primary,
            source,
            alternate_embedded_paths=[alternate],
        )
    assert ambiguous.value.code == "AMBIGUOUS_THUMBNAIL_BINDING"


def test_v2_requires_proven_usable_detail_gain_for_selection(tmp_path: Path) -> None:
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    with Image.open(embedded) as raw:
        upscaled = raw.resize((1000, 1000), Image.Resampling.LANCZOS)

    evidence = linked.confirm_image_binding(embedded, _jpeg_from_image(upscaled))
    assert evidence.usable_detail_gradient_gain_ratio is not None
    assert evidence.usable_detail_gradient_gain_ratio < 1.1
    assert evidence.usable_detail_residual is not None
    assert evidence.usable_detail_residual < 0.0015
    assert evidence.usable_detail_matching_tiles is not None
    assert evidence.usable_detail_matching_tiles < 4
    with pytest.raises(linked.LinkedImageError) as no_gain:
        linked.confirm_image_binding(
            embedded,
            _jpeg_from_image(upscaled),
            require_usable_detail_gain=True,
        )
    assert no_gain.value.code == "NO_USABLE_DETAIL_GAIN"


def test_extract_discovers_link_on_already_usable_native_as_optional(
    tmp_path: Path,
) -> None:
    import pymupdf

    source = _jpeg_bytes((2400, 2400))
    with Image.open(BytesIO(source)) as raw:
        detailed = raw.convert("RGB")
    detail_draw = ImageDraw.Draw(detailed)
    for index in range(240):
        x = (index * 97) % 2380
        y = (index * 193) % 2380
        colour = (
            30 + (index * 11) % 190,
            25 + (index * 17) % 200,
            20 + (index * 23) % 210,
        )
        detail_draw.rectangle((x, y, x + 8, y + 8), fill=colour)
    source = _jpeg_from_image(detailed)
    embedded = tmp_path / "embedded-usable.jpg"
    with Image.open(BytesIO(source)) as raw:
        raw.resize((1000, 1000), Image.Resampling.LANCZOS).save(
            embedded,
            format="JPEG",
            quality=92,
        )
    row = _photo_row(embedded)
    row.update({"native_width": 1000, "native_height": 1000, "width": 1000, "height": 1000})
    report = tmp_path / "usable-native.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(10, 10, 60, 60),
            "uri": _uri(),
        }
    )
    document.save(report)
    document.close()

    candidates, failures, linked_occurrences = linked.extract_candidates(report, [row])
    assert failures == {}
    assert linked_occurrences == {"P001-I01"}
    assert candidates["P001-I01"].required is False

    batch = linked.materialize_linked_images(
        report,
        [row],
        tmp_path / "output",
        report_sha256=linked._sha256_file(report),
        transport=lambda _uri_value, _policy, _resolver: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    assert batch.ok is True
    assert batch.rows[0]["full_resolution_required"] is False
    assert batch.rows[0]["full_resolution_status"] == "VERIFIED"
    assert batch.rows[0]["full_resolution_usable_detail_residual"] >= 0.0015
    assert batch.rows[0]["full_resolution_usable_detail_matching_tiles"] >= 4


def test_unbound_allowed_image_link_is_sanitized_and_blocks_batch(tmp_path: Path) -> None:
    import pymupdf

    embedded = tmp_path / "embedded.jpg"
    embedded.write_bytes(_jpeg_bytes((50, 50)))
    row = _photo_row(embedded)
    row["bbox"] = [100.0, 100.0, 150.0, 150.0]
    report = tmp_path / "unbound.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(10, 10, 60, 60),
            "uri": _uri(),
        }
    )
    document.save(report)
    document.close()

    batch = linked.materialize_linked_images(
        report,
        [row],
        tmp_path / "output",
        report_sha256=linked._sha256_file(report),
        transport=lambda *_args: pytest.fail("unbound link must not be fetched"),
    )

    assert batch.ok is False
    assert batch.receipt["unresolved_image_link_count"] == 1
    assert batch.receipt["unresolved_image_links"][0]["status"] == "UNBOUND_IMAGE_LINK"
    serialized = json.dumps(batch.receipt)
    assert LEAK_MARKER not in serialized
    assert "https://" not in serialized


def test_same_uri_bound_thumbnail_and_label_region_is_nonblocking(tmp_path: Path) -> None:
    import pymupdf

    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    row = _photo_row(embedded)
    report = tmp_path / "bound-with-label.pdf"
    document = pymupdf.open()
    page = document.new_page()
    for rect in (pymupdf.Rect(10, 10, 60, 60), pymupdf.Rect(10, 70, 60, 85)):
        page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": _uri()})
    document.save(report)
    document.close()

    unresolved: list[dict] = []
    secondary: list[dict] = []
    candidates, failures, linked_occurrences = linked.extract_candidates(
        report,
        [row],
        unresolved_links=unresolved,
        secondary_activation_regions=secondary,
    )
    assert set(candidates) == {"P001-I01"}
    assert failures == {}
    assert linked_occurrences == {"P001-I01"}
    assert unresolved == []
    assert len(secondary) == 1
    assert secondary[0]["status"] == "SECONDARY_ACTIVATION_REGION"

    batch = linked.materialize_linked_images(
        report,
        [row],
        tmp_path / "output",
        report_sha256=linked._sha256_file(report),
        transport=lambda *_args: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    assert batch.ok is True
    assert batch.receipt["unresolved_image_link_count"] == 0
    assert batch.receipt["secondary_activation_region_count"] == 1
    serialized = json.dumps(batch.receipt)
    assert LEAK_MARKER not in serialized
    assert "https://" not in serialized


def test_v1_or_different_policy_receipt_never_bypasses_v2_rebinding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, report_sha256 = _report(tmp_path)
    source = _jpeg_bytes((1000, 1000))
    embedded = tmp_path / "embedded.jpg"
    _write_embedded(embedded, source)
    candidate = _candidate(embedded)
    _patch_candidate_extraction(monkeypatch, candidate)
    initial = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        transport=lambda *_args: linked._FetchHop(
            status=200,
            content_type="image/jpeg",
            body=source,
        ),
    )
    stale = dict(initial.receipt)
    stale["policy_version"] = "CLASSIFIRE-LINKED-IMAGE-POLICY-v1"
    calls = 0

    def transport(*_args) -> linked._FetchHop:
        nonlocal calls
        calls += 1
        return linked._FetchHop(status=200, content_type="image/jpeg", body=source)

    rebound = linked.materialize_linked_images(
        report,
        [_photo_row(embedded)],
        tmp_path,
        report_sha256=report_sha256,
        prior_receipt=stale,
        transport=transport,
    )
    assert calls == 1
    assert rebound.rows[0]["full_resolution_status"] == "VERIFIED"


def test_current_private_pdf_maps_31_links_without_serializing_raw_urls() -> None:
    root = Path(__file__).resolve().parents[1]
    report = (
        root
        / "data"
        / "storage"
        / "65"
        / "0b"
        / "650be58f438fb38e2bb33383cfb31e97ca91377faa6dfd5947b9548fe7ae8f0e.pdf"
    )
    inventory = root / "data" / "real-uat" / "20260809-182033" / "16-photo-inventory.json"
    linked_inventory = (
        root / "data" / "real-uat" / "20260809-182033" / "16b-photo-inventory-linked.json"
    )
    if not report.is_file() or not inventory.is_file() or not linked_inventory.is_file():
        pytest.skip("private real-UAT fixture is not available in this checkout")
    rows = json.loads(linked_inventory.read_text(encoding="utf-8"))["photos"]

    unresolved: list[dict] = []
    secondary: list[dict] = []
    candidates, failures, required = linked.extract_candidates(
        report,
        rows,
        unresolved_links=unresolved,
        secondary_activation_regions=secondary,
    )

    assert len(candidates) == 31
    assert len(required) == 31
    assert failures == {}
    assert unresolved == []
    assert secondary
    assert all(item["status"] == "SECONDARY_ACTIVATION_REGION" for item in secondary)
    sanitized = json.dumps(
        {photo_id: linked._candidate_base(candidate) for photo_id, candidate in candidates.items()},
        default=str,
    )
    assert "https://" not in sanitized
    assert "Signature=" not in sanitized
    assert "Key-Pair-Id=" not in sanitized

    destination_root = linked_inventory.parent
    embedded_groups = linked._build_embedded_groups(
        rows,
        linked.DEFAULT_LINKED_IMAGE_POLICY,
    )
    evidence = []
    for photo_id, candidate in sorted(candidates.items()):
        row = next(item for item in rows if item["photo_id"] == photo_id)
        body = (destination_root / row["full_resolution_path"]).read_bytes()
        evidence.append(
            linked._validate_image_binding(
                candidate,
                body,
                linked.DEFAULT_LINKED_IMAGE_POLICY,
                embedded_groups,
            )
        )
    assert len(evidence) == 31
    assert all(item.transform == "CENTER_CROP_COVER" for item in evidence)
    assert all(
        item.usable_detail_gradient_gain_ratio is not None
        and item.usable_detail_gradient_gain_ratio >= 1.1
        for item in evidence
    )
