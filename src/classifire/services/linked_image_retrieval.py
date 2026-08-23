from __future__ import annotations

import hashlib
import http.client
import ipaddress
import os
import re
import socket
import ssl
import tempfile
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

LINKED_IMAGE_RECEIPT_SCHEMA = "CLASSIFIRE-REAL-UAT-LINKED-IMAGE-RETRIEVAL-v2"
READY_STATUSES = frozenset({"VERIFIED", "CACHED"})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
TRANSIENT_STATUSES = frozenset({408, 429, 502, 503, 504})
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class LinkedImageError(RuntimeError):
    """A deliberately redacted linked-image failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Linked image retrieval failed: {code}")


@dataclass(frozen=True)
class LinkedImagePolicy:
    version: str = "CLASSIFIRE-LINKED-IMAGE-POLICY-v2"
    allowed_hosts: frozenset[str] = frozenset({"twiddle.onuptick.com"})
    expected_query_keys: frozenset[str] = frozenset(
        {"Expires", "Key-Pair-Id", "Signature", "public_id", "transform"}
    )
    allowed_suffixes: frozenset[str] = frozenset({".jpg", ".jpeg"})
    minimum_overlap_ratio: float = 0.90
    low_resolution_long_side_px: int = 900
    minimum_full_resolution_long_side_px: int = 900
    minimum_full_resolution_pixels: int = 500_000
    minimum_long_side_scale: float = 2.0
    minimum_pixel_area_scale: float = 4.0
    thumbnail_transforms: tuple[str, ...] = (
        "FULL_FRAME_RESIZE",
        "CENTER_CROP_COVER",
    )
    maximum_thumbnail_hash_distance: int = 8
    maximum_thumbnail_mean_error: float = 0.08
    minimum_thumbnail_luma_stddev: float = 0.06
    minimum_thumbnail_entropy_bits: float = 3.5
    minimum_thumbnail_mean_gradient: float = 0.005
    thumbnail_tile_grid: int = 4
    maximum_thumbnail_tile_mean_error: float = 0.10
    maximum_thumbnail_worst_tile_mean_error: float = 0.14
    minimum_thumbnail_matching_tile_ratio: float = 0.75
    maximum_thumbnail_comparison_side_px: int = 256
    minimum_detail_evaluation_side_px: int = 512
    maximum_detail_evaluation_side_px: int = 2048
    minimum_usable_detail_residual: float = 0.0015
    minimum_usable_detail_matching_tiles: int = 4
    maximum_uri_characters: int = 4096
    maximum_annotations: int = 500
    maximum_candidates: int = 100
    maximum_image_bytes: int = 25 * 1024 * 1024
    maximum_run_bytes: int = 512 * 1024 * 1024
    maximum_pixels: int = 50_000_000
    maximum_side_px: int = 12_000
    maximum_redirects: int = 3
    chunk_size: int = 64 * 1024
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    total_timeout_seconds: float = 45.0
    maximum_transient_retries: int = 1


DEFAULT_LINKED_IMAGE_POLICY = LinkedImagePolicy()


@dataclass(frozen=True)
class LinkedImageCandidate:
    photo_id: str
    page_number: int
    required: bool
    embedded_path: Path
    embedded_sha256: str
    embedded_width: int
    embedded_height: int
    photo_bbox: tuple[float, float, float, float]
    annotation_bbox: tuple[float, float, float, float]
    overlap_ratio: float
    annotation_xrefs: tuple[int, ...]
    uri_sha256: str
    host: str
    path_sha256: str
    suffix: str
    query_keys: tuple[str, ...]
    uri: str = field(repr=False, compare=False)


@dataclass(frozen=True)
class LinkedImageResult:
    photo_id: str
    page_number: int
    required: bool
    status: str
    embedded_sha256: str | None = None
    embedded_width: int | None = None
    embedded_height: int | None = None
    photo_bbox: tuple[float, float, float, float] | None = None
    annotation_bbox: tuple[float, float, float, float] | None = None
    overlap_ratio: float | None = None
    annotation_xrefs: tuple[int, ...] = ()
    uri_sha256: str | None = None
    host: str | None = None
    path_sha256: str | None = None
    suffix: str | None = None
    query_keys: tuple[str, ...] = ()
    redirect_count: int = 0
    resolved_address_count: int | None = None
    tls_version: str | None = None
    content_type: str | None = None
    declared_bytes: int | None = None
    received_bytes: int | None = None
    content_sha256: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail_hash_distance: int | None = None
    thumbnail_mean_error: float | None = None
    embedded_pixel_sha256: str | None = None
    thumbnail_transform: str | None = None
    thumbnail_crop_box: tuple[float, float, float, float] | None = None
    thumbnail_luma_stddev: float | None = None
    thumbnail_entropy_bits: float | None = None
    thumbnail_mean_gradient: float | None = None
    thumbnail_matching_tiles: int | None = None
    thumbnail_tile_count: int | None = None
    thumbnail_worst_tile_mean_error: float | None = None
    thumbnail_comparison_group_count: int | None = None
    usable_detail_gradient_gain_ratio: float | None = None
    usable_detail_residual: float | None = None
    usable_detail_matching_tiles: int | None = None
    stored_path: str | None = None

    def receipt_row(self) -> dict[str, Any]:
        return {
            "photo_id": self.photo_id,
            "page_number": self.page_number,
            "full_resolution_required": self.required,
            "status": self.status,
            "embedded_sha256": self.embedded_sha256,
            "embedded_width": self.embedded_width,
            "embedded_height": self.embedded_height,
            "photo_bbox": list(self.photo_bbox) if self.photo_bbox else None,
            "annotation_bbox": list(self.annotation_bbox) if self.annotation_bbox else None,
            "overlap_ratio": self.overlap_ratio,
            "annotation_xrefs": list(self.annotation_xrefs),
            "uri_sha256": self.uri_sha256,
            "origin_host": self.host,
            "uri_path_sha256": self.path_sha256,
            "uri_suffix": self.suffix,
            "query_key_names": list(self.query_keys),
            "redirect_count": self.redirect_count,
            "resolved_address_count": self.resolved_address_count,
            "tls_version": self.tls_version,
            "content_type": self.content_type,
            "declared_bytes": self.declared_bytes,
            "received_bytes": self.received_bytes,
            "content_sha256": self.content_sha256,
            "decoded_width": self.width,
            "decoded_height": self.height,
            "thumbnail_hash_distance": self.thumbnail_hash_distance,
            "thumbnail_mean_error": self.thumbnail_mean_error,
            "embedded_pixel_sha256": self.embedded_pixel_sha256,
            "thumbnail_transform": self.thumbnail_transform,
            "thumbnail_crop_box_normalized": (
                list(self.thumbnail_crop_box) if self.thumbnail_crop_box else None
            ),
            "thumbnail_luma_stddev": self.thumbnail_luma_stddev,
            "thumbnail_entropy_bits": self.thumbnail_entropy_bits,
            "thumbnail_mean_gradient": self.thumbnail_mean_gradient,
            "thumbnail_matching_tiles": self.thumbnail_matching_tiles,
            "thumbnail_tile_count": self.thumbnail_tile_count,
            "thumbnail_worst_tile_mean_error": self.thumbnail_worst_tile_mean_error,
            "thumbnail_comparison_group_count": self.thumbnail_comparison_group_count,
            "usable_detail_gradient_gain_ratio": self.usable_detail_gradient_gain_ratio,
            "usable_detail_residual": self.usable_detail_residual,
            "usable_detail_matching_tiles": self.usable_detail_matching_tiles,
            "stored_path": self.stored_path,
        }


@dataclass(frozen=True)
class LinkedImageBatch:
    rows: tuple[dict[str, Any], ...]
    receipt: dict[str, Any]
    results: tuple[LinkedImageResult, ...]
    ok: bool


@dataclass(frozen=True)
class _ValidatedUri:
    uri: str = field(repr=False)
    host: str = ""
    path_sha256: str = ""
    suffix: str = ""
    query_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class _FetchHop:
    status: int
    content_type: str | None = None
    content_encoding: str | None = None
    declared_length: int | None = None
    body: bytes = field(default=b"", repr=False)
    redirect_location: str | None = field(default=None, repr=False)
    resolved_address_count: int = 0
    tls_version: str | None = None


@dataclass(frozen=True)
class ThumbnailBindingEvidence:
    width: int
    height: int
    embedded_pixel_sha256: str
    transform: str
    crop_box: tuple[float, float, float, float]
    hash_distance: int
    mean_error: float
    luma_stddev: float
    entropy_bits: float
    mean_gradient: float
    matching_tiles: int
    tile_count: int
    worst_tile_mean_error: float
    comparison_group_count: int
    usable_detail_gradient_gain_ratio: float | None = None
    usable_detail_residual: float | None = None
    usable_detail_matching_tiles: int | None = None


@dataclass(frozen=True)
class _EmbeddedGroup:
    pixel_sha256: str
    photo_ids: tuple[str, ...]
    file_sha256_by_photo_id: tuple[tuple[str, str], ...]
    width: int
    height: int
    image: Image.Image = field(repr=False, compare=False)


@dataclass(frozen=True)
class _TransformBindingMetrics:
    transform: str
    crop_box: tuple[float, float, float, float]
    hash_distance: int
    mean_error: float
    luma_stddev: float
    entropy_bits: float
    mean_gradient: float
    matching_tiles: int
    tile_count: int
    worst_tile_mean_error: float


Resolver = Callable[[str, int], Sequence[tuple[int, str]]]
Transport = Callable[[str, LinkedImagePolicy, Resolver], _FetchHop]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_controls(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _validate_uri(uri: str, policy: LinkedImagePolicy) -> _ValidatedUri:
    if (
        not isinstance(uri, str)
        or not uri
        or len(uri) > policy.maximum_uri_characters
        or not uri.isascii()
        or _contains_controls(uri)
        or "\\" in uri
    ):
        raise LinkedImageError("UNSAFE_URI")
    if _BAD_PERCENT_ESCAPE.search(uri):
        raise LinkedImageError("UNSAFE_URI")
    try:
        parsed = urlsplit(uri)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise LinkedImageError("UNSAFE_URI") from None
    if parsed.scheme.lower() != "https":
        raise LinkedImageError("UNSAFE_SCHEME")
    if parsed.username is not None or parsed.password is not None:
        raise LinkedImageError("UNSAFE_USERINFO")
    if host not in policy.allowed_hosts:
        raise LinkedImageError("UNAPPROVED_HOST")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise LinkedImageError("IP_LITERAL_HOST")
    if port not in {None, 443}:
        raise LinkedImageError("UNSAFE_PORT")
    if parsed.fragment:
        raise LinkedImageError("UNSAFE_FRAGMENT")
    if not parsed.path.startswith("/") or _contains_controls(parsed.path):
        raise LinkedImageError("UNSAFE_PATH")
    try:
        decoded_path = unquote(parsed.path, errors="strict")
    except (UnicodeDecodeError, ValueError):
        raise LinkedImageError("UNSAFE_PATH") from None
    if "\\" in decoded_path or _contains_controls(decoded_path):
        raise LinkedImageError("UNSAFE_PATH")
    if re.search(r"%(?:2f|5c)", parsed.path, flags=re.IGNORECASE):
        raise LinkedImageError("UNSAFE_PATH")
    segments = decoded_path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise LinkedImageError("UNSAFE_PATH")
    suffix = Path(decoded_path).suffix.lower()
    if suffix not in policy.allowed_suffixes:
        raise LinkedImageError("UNAPPROVED_IMAGE_PATH")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise LinkedImageError("UNSAFE_QUERY") from None
    keys = [key for key, _value in pairs]
    if (
        len(keys) != len(set(keys))
        or frozenset(keys) != policy.expected_query_keys
        or any(
            not key or not value or _contains_controls(key) or _contains_controls(value)
            for key, value in pairs
        )
    ):
        raise LinkedImageError("UNEXPECTED_QUERY_KEYS")
    expires = dict(pairs).get("Expires", "")
    if not expires.isdigit() or int(expires) <= int(time.time()):
        raise LinkedImageError("EXPIRED_SIGNED_URI")
    return _ValidatedUri(
        uri=uri,
        host=host,
        path_sha256=_sha256_bytes(parsed.path.encode("utf-8")),
        suffix=suffix,
        query_keys=tuple(sorted(keys)),
    )


def _bbox_overlap_ratio(photo_bbox: Sequence[float], link_bbox: Sequence[float]) -> float:
    if len(photo_bbox) != 4 or len(link_bbox) != 4:
        return 0.0
    px0, py0, px1, py1 = (float(value) for value in photo_bbox)
    lx0, ly0, lx1, ly1 = (float(value) for value in link_bbox)
    photo_area = max(px1 - px0, 0.0) * max(py1 - py0, 0.0)
    if photo_area <= 0:
        return 0.0
    intersection = max(min(px1, lx1) - max(px0, lx0), 0.0) * max(min(py1, ly1) - max(py0, ly0), 0.0)
    return intersection / photo_area


def _eligible_raster(row: Mapping[str, Any]) -> bool:
    if bool(row.get("decorative_candidate")) or bool(row.get("tiny_artifact")):
        return False
    width = int(row.get("native_width") or row.get("width") or 0)
    height = int(row.get("native_height") or row.get("height") or 0)
    return width > 0 and height > 0


def _eligible_low_resolution(row: Mapping[str, Any], policy: LinkedImagePolicy) -> bool:
    if not _eligible_raster(row):
        return False
    width = int(row.get("native_width") or row.get("width") or 0)
    height = int(row.get("native_height") or row.get("height") or 0)
    return max(width, height) < policy.low_resolution_long_side_px


def _candidate_from_matches(
    row: Mapping[str, Any],
    matches: list[tuple[str, tuple[float, float, float, float], float, int]],
    policy: LinkedImagePolicy,
) -> LinkedImageCandidate:
    by_uri: dict[str, list[tuple[tuple[float, float, float, float], float, int]]] = {}
    for uri, annotation_bbox, overlap, xref in matches:
        by_uri.setdefault(uri, []).append((annotation_bbox, overlap, xref))
    if len(by_uri) != 1:
        raise LinkedImageError("AMBIGUOUS_IMAGE_LINK")
    uri, occurrences = next(iter(by_uri.items()))
    validated = _validate_uri(uri, policy)
    annotation_bbox, overlap, _xref = max(occurrences, key=lambda item: item[1])
    native_raw = str(row.get("native_path") or "").strip()
    if not native_raw:
        raise LinkedImageError("EMBEDDED_THUMBNAIL_MISSING")
    embedded_path = Path(native_raw)
    if not embedded_path.is_file():
        raise LinkedImageError("EMBEDDED_THUMBNAIL_MISSING")
    embedded_width = int(row.get("native_width") or row.get("width") or 0)
    embedded_height = int(row.get("native_height") or row.get("height") or 0)
    raw_photo_bbox = row["bbox"]
    if not isinstance(raw_photo_bbox, Sequence) or len(raw_photo_bbox) != 4:
        raise LinkedImageError("INVALID_PHOTO_BBOX")
    photo_bbox = (
        float(raw_photo_bbox[0]),
        float(raw_photo_bbox[1]),
        float(raw_photo_bbox[2]),
        float(raw_photo_bbox[3]),
    )
    return LinkedImageCandidate(
        photo_id=str(row["photo_id"]),
        page_number=int(row["page_number"]),
        required=_eligible_low_resolution(row, policy),
        embedded_path=embedded_path,
        embedded_sha256=_sha256_file(embedded_path),
        embedded_width=embedded_width,
        embedded_height=embedded_height,
        photo_bbox=photo_bbox,
        annotation_bbox=annotation_bbox,
        overlap_ratio=overlap,
        annotation_xrefs=tuple(sorted({item[2] for item in occurrences if item[2] > 0})),
        uri_sha256=_sha256_bytes(uri.encode("utf-8")),
        host=validated.host,
        path_sha256=validated.path_sha256,
        suffix=validated.suffix,
        query_keys=validated.query_keys,
        uri=uri,
    )


def extract_candidates(
    report: Path,
    photo_rows: Sequence[Mapping[str, Any]],
    policy: LinkedImagePolicy = DEFAULT_LINKED_IMAGE_POLICY,
    *,
    unresolved_links: list[dict[str, Any]] | None = None,
    secondary_activation_regions: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, LinkedImageCandidate], dict[str, str], set[str]]:
    """Map image URI annotations to non-decorative raster occurrences without fetching."""

    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is mandatory in this project
        raise RuntimeError("PyMuPDF is required for linked image extraction.") from exc

    eligible: dict[int, list[Mapping[str, Any]]] = {}
    for row in photo_rows:
        if _eligible_raster(row):
            eligible.setdefault(int(row.get("page_number") or 0), []).append(row)
    matches: dict[str, list[tuple[str, tuple[float, float, float, float], float, int]]] = {}
    linked_occurrences: set[str] = set()
    ambiguous_photos: set[str] = set()
    unresolved = unresolved_links if unresolved_links is not None else []
    secondary = secondary_activation_regions if secondary_activation_regions is not None else []
    unmatched_allowed: list[dict[str, Any]] = []
    annotation_count = 0
    document = pymupdf.open(str(report))
    try:
        for page_number in range(1, len(document) + 1):
            rows = eligible.get(page_number, [])
            page = document.load_page(page_number - 1)
            links = page.get_links()
            annotation_count += len(links)
            if annotation_count > policy.maximum_annotations:
                raise LinkedImageError("TOO_MANY_PDF_ANNOTATIONS")
            for link in links:
                if int(link.get("kind") or 0) != int(pymupdf.LINK_URI):
                    continue
                uri = link.get("uri")
                rect_raw = link.get("from")
                if not isinstance(uri, str) or rect_raw is None:
                    continue
                rect = pymupdf.Rect(rect_raw)
                if rect.is_empty or rect.is_infinite:
                    continue
                annotation_bbox = (
                    float(rect.x0),
                    float(rect.y0),
                    float(rect.x1),
                    float(rect.y1),
                )
                overlapping_rows: list[tuple[Mapping[str, Any], float]] = []
                for row in rows:
                    overlap = _bbox_overlap_ratio(row.get("bbox") or (), annotation_bbox)
                    if overlap < policy.minimum_overlap_ratio:
                        continue
                    overlapping_rows.append((row, overlap))
                if not overlapping_rows:
                    try:
                        validated = _validate_uri(uri, policy)
                    except LinkedImageError:
                        continue
                    unmatched_allowed.append(
                        {
                            "page_number": page_number,
                            "annotation_xref": int(link.get("xref") or 0),
                            "annotation_bbox": list(annotation_bbox),
                            "uri_sha256": _sha256_bytes(uri.encode("utf-8")),
                            "origin_host": validated.host,
                            "uri_path_sha256": validated.path_sha256,
                            "uri_suffix": validated.suffix,
                            "query_key_names": list(validated.query_keys),
                        }
                    )
                    continue
                if len(overlapping_rows) > 1:
                    for row, _overlap in overlapping_rows:
                        photo_id = str(row.get("photo_id") or "").strip()
                        if photo_id:
                            linked_occurrences.add(photo_id)
                            ambiguous_photos.add(photo_id)
                    continue
                for row, overlap in overlapping_rows:
                    photo_id = str(row.get("photo_id") or "").strip()
                    if not photo_id:
                        continue
                    linked_occurrences.add(photo_id)
                    matches.setdefault(photo_id, []).append(
                        (uri, annotation_bbox, overlap, int(link.get("xref") or 0))
                    )
    finally:
        document.close()

    bound_uri_hashes = {
        _sha256_bytes(uri.encode("utf-8"))
        for photo_matches in matches.values()
        for uri, _annotation_bbox, _overlap, _xref in photo_matches
    }
    for item in unmatched_allowed:
        if str(item["uri_sha256"]) in bound_uri_hashes:
            secondary.append({**item, "status": "SECONDARY_ACTIVATION_REGION"})
        else:
            unresolved.append({**item, "status": "UNBOUND_IMAGE_LINK"})

    candidates: dict[str, LinkedImageCandidate] = {}
    failures: dict[str, str] = {
        photo_id: "AMBIGUOUS_ANNOTATION_BINDING" for photo_id in ambiguous_photos
    }
    rows_by_id = {
        str(row.get("photo_id")): row
        for row in photo_rows
        if str(row.get("photo_id") or "").strip()
    }
    for photo_id in sorted(linked_occurrences):
        if photo_id in failures:
            continue
        try:
            candidates[photo_id] = _candidate_from_matches(
                rows_by_id[photo_id], matches[photo_id], policy
            )
        except LinkedImageError as exc:
            failures[photo_id] = exc.code
    if (
        len(candidates) + len(failures) + len(unresolved) + len(secondary)
        > policy.maximum_candidates
    ):
        raise LinkedImageError("TOO_MANY_IMAGE_LINKS")
    return candidates, failures, linked_occurrences


def _public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def resolve_public_addresses(host: str, port: int = 443) -> tuple[tuple[int, str], ...]:
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise LinkedImageError("DNS_FAILURE") from None
    addresses: list[tuple[int, str]] = []
    for family, _type, _proto, _canonname, sockaddr in resolved:
        value = str(sockaddr[0])
        if not _public_ip(value):
            raise LinkedImageError("NON_PUBLIC_DNS_ADDRESS")
        item = (int(family), value)
        if item not in addresses:
            addresses.append(item)
    if not addresses:
        raise LinkedImageError("DNS_FAILURE")
    return tuple(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        pinned_address: str,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host=host, port=443, timeout=timeout, context=context)
        self._pinned_address = pinned_address
        self._ssl_context = context

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._pinned_address, self.port), timeout=self.timeout
        )
        try:
            self.sock = self._ssl_context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def _header_length(value: str | None, maximum: int) -> int | None:
    if value is None:
        return None
    if not re.fullmatch(r"[0-9]+", value.strip()):
        raise LinkedImageError("INVALID_CONTENT_LENGTH")
    length = int(value)
    if length > maximum:
        raise LinkedImageError("IMAGE_TOO_LARGE")
    return length


def _pinned_https_get(
    uri: str,
    policy: LinkedImagePolicy,
    resolver: Resolver,
) -> _FetchHop:
    validated = _validate_uri(uri, policy)
    parsed = urlsplit(uri)
    addresses = tuple(resolver(validated.host, 443))
    if not addresses or any(not _public_ip(address) for _family, address in addresses):
        raise LinkedImageError("NON_PUBLIC_DNS_ADDRESS")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    for _family, address in addresses:
        connection = _PinnedHTTPSConnection(
            validated.host,
            address,
            timeout=policy.connect_timeout_seconds,
            context=context,
        )
        try:
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            connection.request(
                "GET",
                target,
                headers={
                    "Accept": "image/jpeg",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "Host": validated.host,
                    "User-Agent": "CLASSIFIRE-linked-image-retrieval/1",
                },
            )
            response = connection.getresponse()
            if connection.sock is not None:
                connection.sock.settimeout(policy.read_timeout_seconds)
            status = int(response.status)
            content_type = response.getheader("Content-Type")
            content_encoding = response.getheader("Content-Encoding")
            declared_length = _header_length(
                response.getheader("Content-Length"), policy.maximum_image_bytes
            )
            tls_version = connection.sock.version() if connection.sock is not None else None
            if status in REDIRECT_STATUSES:
                return _FetchHop(
                    status=status,
                    redirect_location=response.getheader("Location"),
                    resolved_address_count=len(addresses),
                    tls_version=tls_version,
                )
            chunks: list[bytes] = []
            received = 0
            while True:
                chunk = response.read(policy.chunk_size)
                if not chunk:
                    break
                received += len(chunk)
                if received > policy.maximum_image_bytes:
                    raise LinkedImageError("IMAGE_TOO_LARGE")
                chunks.append(chunk)
            return _FetchHop(
                status=status,
                content_type=content_type,
                content_encoding=content_encoding,
                declared_length=declared_length,
                body=b"".join(chunks),
                resolved_address_count=len(addresses),
                tls_version=tls_version,
            )
        except LinkedImageError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException):
            pass
        finally:
            connection.close()
    raise LinkedImageError("NETWORK_FAILURE") from None


def _fetch_with_redirects(
    candidate: LinkedImageCandidate,
    policy: LinkedImagePolicy,
    resolver: Resolver,
    transport: Transport,
) -> tuple[_FetchHop, int]:
    current = candidate.uri
    started = time.monotonic()
    redirect_count = 0
    while True:
        if time.monotonic() - started > policy.total_timeout_seconds:
            raise LinkedImageError("TOTAL_TIMEOUT")
        validated = _validate_uri(current, policy)
        if validated.host != candidate.host:
            raise LinkedImageError("CROSS_HOST_REDIRECT")
        try:
            hop = transport(current, policy, resolver)
        except LinkedImageError:
            raise
        except BaseException:
            raise LinkedImageError("NETWORK_FAILURE") from None
        if time.monotonic() - started > policy.total_timeout_seconds:
            raise LinkedImageError("TOTAL_TIMEOUT")
        if hop.status in REDIRECT_STATUSES:
            if redirect_count >= policy.maximum_redirects or not hop.redirect_location:
                raise LinkedImageError("REDIRECT_REJECTED")
            next_uri = urljoin(current, hop.redirect_location)
            next_validated = _validate_uri(next_uri, policy)
            if next_validated.host != candidate.host:
                raise LinkedImageError("CROSS_HOST_REDIRECT")
            current = next_uri
            redirect_count += 1
            continue
        return hop, redirect_count


def _validate_fetch(hop: _FetchHop, policy: LinkedImagePolicy) -> bytes:
    if hop.status in TRANSIENT_STATUSES:
        raise LinkedImageError("TRANSIENT_HTTP_STATUS")
    if hop.status != 200:
        raise LinkedImageError("HTTP_STATUS_REJECTED")
    encoding = str(hop.content_encoding or "identity").strip().lower()
    if encoding not in {"", "identity"}:
        raise LinkedImageError("CONTENT_ENCODING_REJECTED")
    media_type = str(hop.content_type or "").split(";", 1)[0].strip().lower()
    if media_type != "image/jpeg":
        raise LinkedImageError("CONTENT_TYPE_REJECTED")
    body = hop.body
    if not isinstance(body, bytes) or not body.startswith(b"\xff\xd8\xff"):
        raise LinkedImageError("JPEG_MAGIC_REJECTED")
    if len(body) > policy.maximum_image_bytes:
        raise LinkedImageError("IMAGE_TOO_LARGE")
    if hop.declared_length is not None and hop.declared_length != len(body):
        raise LinkedImageError("CONTENT_LENGTH_MISMATCH")
    return body


def _decoded_jpeg(
    body: bytes,
    policy: LinkedImagePolicy,
) -> tuple[Image.Image, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(body)) as probe:
                if probe.format != "JPEG" or int(getattr(probe, "n_frames", 1)) != 1:
                    raise LinkedImageError("DECODED_FORMAT_REJECTED")
                width, height = probe.size
                if (
                    width <= 0
                    or height <= 0
                    or max(width, height) > policy.maximum_side_px
                    or width * height > policy.maximum_pixels
                ):
                    raise LinkedImageError("IMAGE_DIMENSIONS_REJECTED")
                probe.verify()
            with Image.open(BytesIO(body)) as decoded:
                decoded.load()
                image = ImageOps.exif_transpose(decoded).convert("RGB")
    except LinkedImageError:
        raise
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise LinkedImageError("INVALID_JPEG") from None
    return image, image.width, image.height


def _difference_hash(image: Image.Image) -> int:
    resized = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(resized.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value <<= 1
            if pixels[row * 9 + column] > pixels[row * 9 + column + 1]:
                value |= 1
    return value


def _load_embedded_image(path: Path, policy: LinkedImagePolicy) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as raw:
                if int(getattr(raw, "n_frames", 1)) != 1:
                    raise LinkedImageError("EMBEDDED_THUMBNAIL_INVALID")
                width, height = raw.size
                if (
                    width <= 0
                    or height <= 0
                    or max(width, height) > policy.maximum_side_px
                    or width * height > policy.maximum_pixels
                ):
                    raise LinkedImageError("EMBEDDED_THUMBNAIL_INVALID")
                raw.load()
                return ImageOps.exif_transpose(raw).convert("RGB")
    except LinkedImageError:
        raise
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise LinkedImageError("EMBEDDED_THUMBNAIL_INVALID") from None


def _canonical_pixel_sha256(image: Image.Image) -> str:
    digest = hashlib.sha256()
    digest.update(b"CLASSIFIRE-CANONICAL-RGB-v1\0")
    digest.update(int(image.width).to_bytes(8, "big"))
    digest.update(int(image.height).to_bytes(8, "big"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def _comparison_image(image: Image.Image, policy: LinkedImagePolicy) -> Image.Image:
    maximum = int(policy.maximum_thumbnail_comparison_side_px)
    if maximum <= 0:
        raise LinkedImageError("INVALID_BINDING_POLICY")
    if max(image.size) <= maximum:
        return image.copy()
    scale = maximum / max(image.size)
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _embedded_groups_from_items(
    items: Sequence[tuple[str, Path]],
    policy: LinkedImagePolicy,
) -> tuple[_EmbeddedGroup, ...]:
    grouped: dict[str, dict[str, Any]] = {}
    for photo_id, path in items:
        try:
            image = _load_embedded_image(path, policy)
            file_sha256 = _sha256_file(path)
        except (OSError, LinkedImageError):
            continue
        pixel_sha256 = _canonical_pixel_sha256(image)
        entry = grouped.setdefault(
            pixel_sha256,
            {
                "image": _comparison_image(image, policy),
                "width": image.width,
                "height": image.height,
                "members": [],
            },
        )
        entry["members"].append((photo_id, file_sha256))
    groups: list[_EmbeddedGroup] = []
    for pixel_sha256, entry in sorted(grouped.items()):
        members = tuple(sorted(entry["members"]))
        groups.append(
            _EmbeddedGroup(
                pixel_sha256=pixel_sha256,
                photo_ids=tuple(photo_id for photo_id, _sha256 in members),
                file_sha256_by_photo_id=members,
                width=int(entry["width"]),
                height=int(entry["height"]),
                image=entry["image"],
            )
        )
    return tuple(groups)


def _build_embedded_groups(
    photo_rows: Sequence[Mapping[str, Any]],
    policy: LinkedImagePolicy,
) -> tuple[_EmbeddedGroup, ...]:
    items: list[tuple[str, Path]] = []
    for row in photo_rows:
        if not _eligible_raster(row):
            continue
        photo_id = str(row.get("photo_id") or "").strip()
        native_raw = str(row.get("native_path") or "").strip()
        if photo_id and native_raw:
            items.append((photo_id, Path(native_raw)))
    return _embedded_groups_from_items(items, policy)


def _mean_rgb_error(left: Image.Image, right: Image.Image) -> float:
    channel_means = ImageStat.Stat(ImageChops.difference(left, right)).mean
    return sum(channel_means) / (len(channel_means) * 255.0)


def _mean_luma_gradient(image: Image.Image) -> float:
    grayscale = ImageOps.grayscale(image).filter(ImageFilter.GaussianBlur(radius=1.0))
    if grayscale.width < 2 or grayscale.height < 2:
        return 0.0
    horizontal = ImageChops.difference(
        grayscale.crop((1, 0, grayscale.width, grayscale.height)),
        grayscale.crop((0, 0, grayscale.width - 1, grayscale.height)),
    )
    vertical = ImageChops.difference(
        grayscale.crop((0, 1, grayscale.width, grayscale.height)),
        grayscale.crop((0, 0, grayscale.width, grayscale.height - 1)),
    )
    return (float(ImageStat.Stat(horizontal).mean[0]) + float(ImageStat.Stat(vertical).mean[0])) / (
        2.0 * 255.0
    )


def _usable_detail_metrics(
    embedded: Image.Image,
    candidate: Image.Image,
    transform: str,
    policy: LinkedImagePolicy,
) -> tuple[float, float, int]:
    minimum = int(policy.minimum_detail_evaluation_side_px)
    maximum = int(policy.maximum_detail_evaluation_side_px)
    if minimum <= 0 or maximum < minimum:
        raise LinkedImageError("INVALID_BINDING_POLICY")
    evaluation_long_side = min(
        maximum,
        max(minimum, max(embedded.size) * 2),
    )
    if embedded.width >= embedded.height:
        target_size = (
            evaluation_long_side,
            max(1, round(evaluation_long_side * embedded.height / embedded.width)),
        )
    else:
        target_size = (
            max(1, round(evaluation_long_side * embedded.width / embedded.height)),
            evaluation_long_side,
        )
    transformed = next(
        image
        for name, _crop_box, image in _transform_variants(
            candidate,
            target_size,
            policy,
        )
        if name == transform
    )
    baseline = embedded.resize(target_size, Image.Resampling.LANCZOS)
    transformed_luma = ImageOps.grayscale(transformed).filter(ImageFilter.GaussianBlur(radius=1.0))
    baseline_luma = ImageOps.grayscale(baseline).filter(ImageFilter.GaussianBlur(radius=1.0))
    transformed_structure = ImageChops.difference(
        transformed_luma,
        transformed_luma.filter(ImageFilter.GaussianBlur(radius=2.0)),
    )
    baseline_structure = ImageChops.difference(
        baseline_luma,
        baseline_luma.filter(ImageFilter.GaussianBlur(radius=2.0)),
    )
    residual_image = ImageChops.difference(transformed_structure, baseline_structure)
    residual = float(ImageStat.Stat(residual_image).mean[0]) / 255.0
    grid = int(policy.thumbnail_tile_grid)
    if grid <= 0 or transformed_luma.width < grid or transformed_luma.height < grid:
        raise LinkedImageError("INVALID_BINDING_POLICY")
    matching_tiles = 0
    for row in range(grid):
        for column in range(grid):
            box = (
                round(column * transformed_luma.width / grid),
                round(row * transformed_luma.height / grid),
                round((column + 1) * transformed_luma.width / grid),
                round((row + 1) * transformed_luma.height / grid),
            )
            tile_residual = float(ImageStat.Stat(residual_image.crop(box)).mean[0]) / 255.0
            if tile_residual >= policy.minimum_usable_detail_residual:
                matching_tiles += 1
    baseline_gradient = _mean_luma_gradient(baseline)
    if baseline_gradient <= 0.0:
        return 0.0, residual, matching_tiles
    return (
        _mean_luma_gradient(transformed) / baseline_gradient,
        residual,
        matching_tiles,
    )


def _thumbnail_information(image: Image.Image) -> tuple[float, float, float]:
    grayscale = ImageOps.grayscale(image)
    luma_stddev = float(ImageStat.Stat(grayscale).stddev[0]) / 255.0
    entropy_bits = float(grayscale.entropy())
    if grayscale.width < 2 or grayscale.height < 2:
        return luma_stddev, entropy_bits, 0.0
    horizontal = ImageChops.difference(
        grayscale.crop((1, 0, grayscale.width, grayscale.height)),
        grayscale.crop((0, 0, grayscale.width - 1, grayscale.height)),
    )
    vertical = ImageChops.difference(
        grayscale.crop((0, 1, grayscale.width, grayscale.height)),
        grayscale.crop((0, 0, grayscale.width, grayscale.height - 1)),
    )
    mean_gradient = (
        float(ImageStat.Stat(horizontal).mean[0]) + float(ImageStat.Stat(vertical).mean[0])
    ) / (2.0 * 255.0)
    return luma_stddev, entropy_bits, mean_gradient


def _center_crop_box(
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> tuple[float, float, float, float]:
    source_width, source_height = source_size
    target_width, target_height = target_size
    source_ratio = source_width / source_height
    target_ratio = target_width / target_height
    if source_ratio >= target_ratio:
        crop_height = float(source_height)
        crop_width = crop_height * target_ratio
    else:
        crop_width = float(source_width)
        crop_height = crop_width / target_ratio
    left = (source_width - crop_width) / 2.0
    top = (source_height - crop_height) / 2.0
    return (
        round(left / source_width, 8),
        round(top / source_height, 8),
        round((left + crop_width) / source_width, 8),
        round((top + crop_height) / source_height, 8),
    )


def _transform_variants(
    candidate: Image.Image,
    target_size: tuple[int, int],
    policy: LinkedImagePolicy,
) -> tuple[tuple[str, tuple[float, float, float, float], Image.Image], ...]:
    supported = {"FULL_FRAME_RESIZE", "CENTER_CROP_COVER"}
    configured = tuple(policy.thumbnail_transforms)
    if (
        not configured
        or len(configured) != len(set(configured))
        or not set(configured) <= supported
    ):
        raise LinkedImageError("INVALID_BINDING_POLICY")
    variants: list[tuple[str, tuple[float, float, float, float], Image.Image]] = []
    for transform in configured:
        if transform == "FULL_FRAME_RESIZE":
            variants.append(
                (
                    transform,
                    (0.0, 0.0, 1.0, 1.0),
                    candidate.resize(target_size, Image.Resampling.LANCZOS),
                )
            )
        elif transform == "CENTER_CROP_COVER":
            variants.append(
                (
                    transform,
                    _center_crop_box(candidate.size, target_size),
                    ImageOps.fit(candidate, target_size, Image.Resampling.LANCZOS),
                )
            )
    return tuple(variants)


def _transform_metrics(
    embedded: Image.Image,
    transformed: Image.Image,
    transform: str,
    crop_box: tuple[float, float, float, float],
    policy: LinkedImagePolicy,
) -> _TransformBindingMetrics:
    grid = int(policy.thumbnail_tile_grid)
    if grid <= 0 or embedded.width < grid or embedded.height < grid:
        raise LinkedImageError("INVALID_BINDING_POLICY")
    difference = ImageChops.difference(embedded, transformed)
    tile_errors: list[float] = []
    for row in range(grid):
        for column in range(grid):
            box = (
                round(column * embedded.width / grid),
                round(row * embedded.height / grid),
                round((column + 1) * embedded.width / grid),
                round((row + 1) * embedded.height / grid),
            )
            tile = difference.crop(box)
            channel_means = ImageStat.Stat(tile).mean
            tile_errors.append(sum(channel_means) / (len(channel_means) * 255.0))
    luma_stddev, entropy_bits, mean_gradient = _thumbnail_information(embedded)
    return _TransformBindingMetrics(
        transform=transform,
        crop_box=crop_box,
        hash_distance=(_difference_hash(embedded) ^ _difference_hash(transformed)).bit_count(),
        mean_error=_mean_rgb_error(embedded, transformed),
        luma_stddev=luma_stddev,
        entropy_bits=entropy_bits,
        mean_gradient=mean_gradient,
        matching_tiles=sum(
            error <= policy.maximum_thumbnail_tile_mean_error for error in tile_errors
        ),
        tile_count=len(tile_errors),
        worst_tile_mean_error=max(tile_errors),
    )


def _binding_metrics_pass(
    metrics: _TransformBindingMetrics,
    policy: LinkedImagePolicy,
) -> bool:
    return bool(
        metrics.hash_distance <= policy.maximum_thumbnail_hash_distance
        and metrics.mean_error <= policy.maximum_thumbnail_mean_error
        and metrics.luma_stddev >= policy.minimum_thumbnail_luma_stddev
        and metrics.entropy_bits >= policy.minimum_thumbnail_entropy_bits
        and metrics.mean_gradient >= policy.minimum_thumbnail_mean_gradient
        and metrics.matching_tiles / metrics.tile_count
        >= policy.minimum_thumbnail_matching_tile_ratio
        and metrics.worst_tile_mean_error <= policy.maximum_thumbnail_worst_tile_mean_error
    )


def _group_metrics(
    group: _EmbeddedGroup,
    candidate: Image.Image,
    policy: LinkedImagePolicy,
    variant_cache: dict[
        tuple[int, int],
        tuple[tuple[str, tuple[float, float, float, float], Image.Image], ...],
    ]
    | None = None,
) -> tuple[_TransformBindingMetrics, ...]:
    variants = variant_cache.get(group.image.size) if variant_cache is not None else None
    if variants is None:
        variants = _transform_variants(candidate, group.image.size, policy)
        if variant_cache is not None:
            variant_cache[group.image.size] = variants
    return tuple(
        _transform_metrics(group.image, variant, transform, crop_box, policy)
        for transform, crop_box, variant in variants
    )


def _confirm_decoded_binding(
    primary_group: _EmbeddedGroup,
    candidate: Image.Image,
    width: int,
    height: int,
    groups: Sequence[_EmbeddedGroup],
    policy: LinkedImagePolicy,
    *,
    primary_detail_image: Image.Image | None = None,
    require_usable_detail_gain: bool = False,
) -> ThumbnailBindingEvidence:
    variant_cache: dict[
        tuple[int, int],
        tuple[tuple[str, tuple[float, float, float, float], Image.Image], ...],
    ] = {}
    primary_metrics = _group_metrics(
        primary_group,
        candidate,
        policy,
        variant_cache,
    )
    passing = [item for item in primary_metrics if _binding_metrics_pass(item, policy)]
    if not passing:
        sample = primary_metrics[0]
        if (
            sample.luma_stddev < policy.minimum_thumbnail_luma_stddev
            or sample.entropy_bits < policy.minimum_thumbnail_entropy_bits
            or sample.mean_gradient < policy.minimum_thumbnail_mean_gradient
        ):
            raise LinkedImageError("LOW_INFORMATION_THUMBNAIL")
        raise LinkedImageError("THUMBNAIL_MISMATCH")
    transform_order = {
        transform: index for index, transform in enumerate(policy.thumbnail_transforms)
    }
    winner = min(
        passing,
        key=lambda item: (
            item.mean_error,
            item.hash_distance,
            item.worst_tile_mean_error,
            transform_order[item.transform],
        ),
    )
    for alternate in groups:
        if alternate.pixel_sha256 == primary_group.pixel_sha256:
            continue
        if any(
            _binding_metrics_pass(item, policy)
            for item in _group_metrics(
                alternate,
                candidate,
                policy,
                variant_cache,
            )
        ):
            raise LinkedImageError("AMBIGUOUS_THUMBNAIL_BINDING")
    detail_gain: float | None = None
    detail_residual: float | None = None
    detail_matching_tiles: int | None = None
    if primary_detail_image is not None:
        detail_gain, detail_residual, detail_matching_tiles = _usable_detail_metrics(
            primary_detail_image,
            candidate,
            winner.transform,
            policy,
        )
    if require_usable_detail_gain and (
        detail_residual is None
        or detail_residual < policy.minimum_usable_detail_residual
        or detail_matching_tiles is None
        or detail_matching_tiles < policy.minimum_usable_detail_matching_tiles
    ):
        raise LinkedImageError("NO_USABLE_DETAIL_GAIN")
    return ThumbnailBindingEvidence(
        width=width,
        height=height,
        embedded_pixel_sha256=primary_group.pixel_sha256,
        transform=winner.transform,
        crop_box=winner.crop_box,
        hash_distance=winner.hash_distance,
        mean_error=winner.mean_error,
        luma_stddev=winner.luma_stddev,
        entropy_bits=winner.entropy_bits,
        mean_gradient=winner.mean_gradient,
        matching_tiles=winner.matching_tiles,
        tile_count=winner.tile_count,
        worst_tile_mean_error=winner.worst_tile_mean_error,
        comparison_group_count=len(groups),
        usable_detail_gradient_gain_ratio=detail_gain,
        usable_detail_residual=detail_residual,
        usable_detail_matching_tiles=detail_matching_tiles,
    )


def confirm_image_binding(
    embedded_path: Path,
    candidate_jpeg: bytes,
    *,
    alternate_embedded_paths: Sequence[Path] = (),
    policy: LinkedImagePolicy = DEFAULT_LINKED_IMAGE_POLICY,
    require_usable_detail_gain: bool = False,
) -> ThumbnailBindingEvidence:
    """Confirm a URI-free embedded-to-JPEG relation under the v2 binding policy."""

    if not isinstance(candidate_jpeg, bytes) or not candidate_jpeg.startswith(b"\xff\xd8\xff"):
        raise LinkedImageError("JPEG_MAGIC_REJECTED")
    if len(candidate_jpeg) > policy.maximum_image_bytes:
        raise LinkedImageError("IMAGE_TOO_LARGE")
    items = [("PRIMARY", embedded_path)]
    items.extend(
        (f"ALTERNATE-{index:04d}", path)
        for index, path in enumerate(alternate_embedded_paths, start=1)
    )
    groups = _embedded_groups_from_items(items, policy)
    primary_group = next(
        (group for group in groups if "PRIMARY" in group.photo_ids),
        None,
    )
    if primary_group is None:
        raise LinkedImageError("EMBEDDED_THUMBNAIL_INVALID")
    embedded = _load_embedded_image(embedded_path, policy)
    image, width, height = _decoded_jpeg(candidate_jpeg, policy)
    return _confirm_decoded_binding(
        primary_group,
        image,
        width,
        height,
        groups,
        policy,
        primary_detail_image=embedded,
        require_usable_detail_gain=require_usable_detail_gain,
    )


def _validate_image_binding(
    candidate: LinkedImageCandidate,
    body: bytes,
    policy: LinkedImagePolicy,
    embedded_groups: Sequence[_EmbeddedGroup],
) -> ThumbnailBindingEvidence:
    if len(body) > policy.maximum_image_bytes or not body.startswith(b"\xff\xd8\xff"):
        raise LinkedImageError("JPEG_MAGIC_REJECTED")
    image, width, height = _decoded_jpeg(body, policy)
    embedded_area = candidate.embedded_width * candidate.embedded_height
    if (
        max(width, height) < policy.minimum_full_resolution_long_side_px
        or width * height < policy.minimum_full_resolution_pixels
        or max(width, height)
        < max(candidate.embedded_width, candidate.embedded_height) * policy.minimum_long_side_scale
        or width * height < embedded_area * policy.minimum_pixel_area_scale
    ):
        raise LinkedImageError("NOT_HIGHER_RESOLUTION")
    primary_group = next(
        (group for group in embedded_groups if candidate.photo_id in group.photo_ids),
        None,
    )
    if primary_group is None:
        raise LinkedImageError("EMBEDDED_THUMBNAIL_INVALID")
    expected_file_sha256 = dict(primary_group.file_sha256_by_photo_id).get(candidate.photo_id)
    if expected_file_sha256 != candidate.embedded_sha256 or (
        primary_group.width,
        primary_group.height,
    ) != (candidate.embedded_width, candidate.embedded_height):
        raise LinkedImageError("EMBEDDED_THUMBNAIL_CHANGED")
    detail_image = _load_embedded_image(candidate.embedded_path, policy)
    try:
        current_embedded_sha256 = _sha256_file(candidate.embedded_path)
    except OSError:
        raise LinkedImageError("EMBEDDED_THUMBNAIL_CHANGED") from None
    if current_embedded_sha256 != candidate.embedded_sha256:
        raise LinkedImageError("EMBEDDED_THUMBNAIL_CHANGED")
    return _confirm_decoded_binding(
        primary_group,
        image,
        width,
        height,
        embedded_groups,
        policy,
        primary_detail_image=detail_image,
        require_usable_detail_gain=True,
    )


def _stored_relative_path(content_sha256: str) -> Path:
    return Path("photo-linked") / "by-sha256" / content_sha256[:2] / f"{content_sha256}.jpg"


def _atomic_store(destination_root: Path, body: bytes, content_sha256: str) -> str:
    root = destination_root.resolve()
    relative = _stored_relative_path(content_sha256)
    target = (root / relative).resolve()
    cache_root = (root / "photo-linked" / "by-sha256").resolve()
    if not target.is_relative_to(cache_root):
        raise LinkedImageError("UNSAFE_STORAGE_PATH")
    temporary_name: str | None = None
    failure: LinkedImageError | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_file() and _sha256_file(target) == content_sha256:
                return relative.as_posix()
            raise LinkedImageError("CONTENT_ADDRESS_COLLISION")
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="linked-", suffix=".part", dir=target.parent, delete=False
        ) as temporary:
            temporary.write(body)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        if _sha256_file(Path(temporary_name)) != content_sha256:
            raise LinkedImageError("STORAGE_HASH_MISMATCH")
        os.replace(temporary_name, target)
        temporary_name = None
    except LinkedImageError as exc:
        failure = exc
    except OSError:
        failure = LinkedImageError("STORAGE_FAILURE")
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                failure = LinkedImageError("STORAGE_CLEANUP_FAILED")
    if failure is not None:
        raise failure from None
    return relative.as_posix()


def preferred_verified_linked_path(
    row: Mapping[str, Any],
    destination_root: Path,
    *,
    policy: LinkedImagePolicy = DEFAULT_LINKED_IMAGE_POLICY,
) -> Path | None:
    status = str(row.get("full_resolution_status") or row.get("status") or "").upper()
    if status not in READY_STATUSES:
        return None
    sha256 = str(row.get("full_resolution_sha256") or row.get("content_sha256") or "").lower()
    raw_path = str(row.get("full_resolution_path") or row.get("stored_path") or "").strip()
    if not _HEX_SHA256.fullmatch(sha256) or not raw_path:
        return None
    relative = Path(raw_path)
    if relative.is_absolute():
        return None
    root = destination_root.resolve()
    cache_root = (root / "photo-linked" / "by-sha256").resolve()
    candidate = (root / relative).resolve()
    expected = (cache_root / sha256[:2] / f"{sha256}.jpg").resolve()
    if candidate != expected or not candidate.is_relative_to(cache_root) or not candidate.is_file():
        return None
    if _sha256_file(candidate) != sha256:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(candidate) as image:
                if image.format != "JPEG" or int(getattr(image, "n_frames", 1)) != 1:
                    return None
                raw_width, raw_height = image.size
                if (
                    raw_width <= 0
                    or raw_height <= 0
                    or max(raw_width, raw_height) > policy.maximum_side_px
                    or raw_width * raw_height > policy.maximum_pixels
                ):
                    return None
                image.verify()
            with Image.open(candidate) as image:
                oriented = ImageOps.exif_transpose(image)
                oriented.load()
                width, height = oriented.size
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None
    expected_width = int(row.get("full_resolution_width") or row.get("decoded_width") or 0)
    expected_height = int(row.get("full_resolution_height") or row.get("decoded_height") or 0)
    if (
        expected_width <= 0
        or expected_height <= 0
        or (width, height)
        != (
            expected_width,
            expected_height,
        )
    ):
        return None
    return candidate


def _candidate_base(candidate: LinkedImageCandidate) -> dict[str, Any]:
    return {
        "embedded_sha256": candidate.embedded_sha256,
        "embedded_width": candidate.embedded_width,
        "embedded_height": candidate.embedded_height,
        "photo_bbox": candidate.photo_bbox,
        "annotation_bbox": candidate.annotation_bbox,
        "overlap_ratio": candidate.overlap_ratio,
        "annotation_xrefs": candidate.annotation_xrefs,
        "uri_sha256": candidate.uri_sha256,
        "host": candidate.host,
        "path_sha256": candidate.path_sha256,
        "suffix": candidate.suffix,
        "query_keys": candidate.query_keys,
    }


def _prior_result(
    candidate: LinkedImageCandidate,
    prior_receipt: Mapping[str, Any] | None,
    destination_root: Path,
    report_sha256: str,
    policy: LinkedImagePolicy,
    embedded_groups: Sequence[_EmbeddedGroup],
) -> LinkedImageResult | None:
    if not prior_receipt:
        return None
    if (
        prior_receipt.get("schema") != LINKED_IMAGE_RECEIPT_SCHEMA
        or str(prior_receipt.get("policy_version")) != policy.version
        or str(prior_receipt.get("report_sha256")).lower() != report_sha256.lower()
    ):
        return None
    items = prior_receipt.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or str(item.get("photo_id")) != candidate.photo_id:
            continue
        if (
            str(item.get("uri_sha256") or "") != candidate.uri_sha256
            or str(item.get("embedded_sha256") or "") != candidate.embedded_sha256
            or tuple(item.get("photo_bbox") or ()) != candidate.photo_bbox
            or tuple(item.get("annotation_bbox") or ()) != candidate.annotation_bbox
            or str(item.get("origin_host") or "") != candidate.host
            or str(item.get("uri_path_sha256") or "") != candidate.path_sha256
            or str(item.get("status") or "").upper() not in READY_STATUSES
        ):
            return None
        verification_row = {
            "full_resolution_status": item.get("status"),
            "full_resolution_path": item.get("stored_path"),
            "full_resolution_sha256": item.get("content_sha256"),
            "full_resolution_width": item.get("decoded_width"),
            "full_resolution_height": item.get("decoded_height"),
        }
        path = preferred_verified_linked_path(verification_row, destination_root)
        if path is None:
            return None
        try:
            cached_body = path.read_bytes()
            evidence = _validate_image_binding(
                candidate,
                cached_body,
                policy,
                embedded_groups,
            )
        except (OSError, LinkedImageError):
            return None
        return LinkedImageResult(
            photo_id=candidate.photo_id,
            page_number=candidate.page_number,
            required=candidate.required,
            status="CACHED",
            **_candidate_base(candidate),
            redirect_count=int(item.get("redirect_count") or 0),
            resolved_address_count=item.get("resolved_address_count"),
            tls_version=item.get("tls_version"),
            content_type=item.get("content_type"),
            declared_bytes=item.get("declared_bytes"),
            received_bytes=len(cached_body),
            content_sha256=str(item.get("content_sha256")),
            width=evidence.width,
            height=evidence.height,
            thumbnail_hash_distance=evidence.hash_distance,
            thumbnail_mean_error=evidence.mean_error,
            embedded_pixel_sha256=evidence.embedded_pixel_sha256,
            thumbnail_transform=evidence.transform,
            thumbnail_crop_box=evidence.crop_box,
            thumbnail_luma_stddev=evidence.luma_stddev,
            thumbnail_entropy_bits=evidence.entropy_bits,
            thumbnail_mean_gradient=evidence.mean_gradient,
            thumbnail_matching_tiles=evidence.matching_tiles,
            thumbnail_tile_count=evidence.tile_count,
            thumbnail_worst_tile_mean_error=evidence.worst_tile_mean_error,
            thumbnail_comparison_group_count=evidence.comparison_group_count,
            usable_detail_gradient_gain_ratio=(evidence.usable_detail_gradient_gain_ratio),
            usable_detail_residual=evidence.usable_detail_residual,
            usable_detail_matching_tiles=evidence.usable_detail_matching_tiles,
            stored_path=str(item.get("stored_path")),
        )
    return None


def _retrieve_candidate(
    candidate: LinkedImageCandidate,
    destination_root: Path,
    policy: LinkedImagePolicy,
    resolver: Resolver,
    transport: Transport,
    remaining_run_bytes: int,
    embedded_groups: Sequence[_EmbeddedGroup],
) -> tuple[LinkedImageResult, int]:
    last_error = "NETWORK_FAILURE"
    consumed_bytes = 0
    for attempt in range(policy.maximum_transient_retries + 1):
        try:
            hop, redirects = _fetch_with_redirects(candidate, policy, resolver, transport)
            consumed_bytes += len(hop.body) if isinstance(hop.body, bytes) else 0
            if consumed_bytes > remaining_run_bytes:
                raise LinkedImageError("RUN_BYTE_LIMIT_EXCEEDED")
            body = _validate_fetch(hop, policy)
            evidence = _validate_image_binding(
                candidate,
                body,
                policy,
                embedded_groups,
            )
            content_sha256 = _sha256_bytes(body)
            stored_path = _atomic_store(destination_root, body, content_sha256)
            result = LinkedImageResult(
                photo_id=candidate.photo_id,
                page_number=candidate.page_number,
                required=candidate.required,
                status="VERIFIED",
                **_candidate_base(candidate),
                redirect_count=redirects,
                resolved_address_count=hop.resolved_address_count,
                tls_version=hop.tls_version,
                content_type=str(hop.content_type or "").split(";", 1)[0].lower(),
                declared_bytes=hop.declared_length,
                received_bytes=len(body),
                content_sha256=content_sha256,
                width=evidence.width,
                height=evidence.height,
                thumbnail_hash_distance=evidence.hash_distance,
                thumbnail_mean_error=evidence.mean_error,
                embedded_pixel_sha256=evidence.embedded_pixel_sha256,
                thumbnail_transform=evidence.transform,
                thumbnail_crop_box=evidence.crop_box,
                thumbnail_luma_stddev=evidence.luma_stddev,
                thumbnail_entropy_bits=evidence.entropy_bits,
                thumbnail_mean_gradient=evidence.mean_gradient,
                thumbnail_matching_tiles=evidence.matching_tiles,
                thumbnail_tile_count=evidence.tile_count,
                thumbnail_worst_tile_mean_error=evidence.worst_tile_mean_error,
                thumbnail_comparison_group_count=evidence.comparison_group_count,
                usable_detail_gradient_gain_ratio=(evidence.usable_detail_gradient_gain_ratio),
                usable_detail_residual=evidence.usable_detail_residual,
                usable_detail_matching_tiles=evidence.usable_detail_matching_tiles,
                stored_path=stored_path,
            )
            return result, consumed_bytes
        except LinkedImageError as exc:
            last_error = exc.code
            if (
                exc.code
                not in {
                    "NETWORK_FAILURE",
                    "DNS_FAILURE",
                    "TOTAL_TIMEOUT",
                    "TRANSIENT_HTTP_STATUS",
                }
                or attempt >= policy.maximum_transient_retries
            ):
                break
    return (
        LinkedImageResult(
            photo_id=candidate.photo_id,
            page_number=candidate.page_number,
            required=candidate.required,
            status=last_error,
            **_candidate_base(candidate),
        ),
        consumed_bytes,
    )


def _enrich_row(row: Mapping[str, Any], result: LinkedImageResult) -> dict[str, Any]:
    enriched = dict(row)
    enriched.update(
        {
            "full_resolution_required": result.required,
            "full_resolution_status": result.status,
            "full_resolution_path": result.stored_path,
            "full_resolution_sha256": result.content_sha256,
            "full_resolution_width": result.width,
            "full_resolution_height": result.height,
            "full_resolution_binding_transform": result.thumbnail_transform,
            "full_resolution_binding_crop_box": (
                list(result.thumbnail_crop_box) if result.thumbnail_crop_box else None
            ),
            "full_resolution_embedded_pixel_sha256": result.embedded_pixel_sha256,
            "full_resolution_usable_detail_gradient_gain_ratio": (
                result.usable_detail_gradient_gain_ratio
            ),
            "full_resolution_usable_detail_residual": result.usable_detail_residual,
            "full_resolution_usable_detail_matching_tiles": (result.usable_detail_matching_tiles),
        }
    )
    return enriched


def materialize_linked_images(
    report: Path,
    photo_rows: list[dict],
    destination_root: Path,
    *,
    report_sha256: str,
    policy: LinkedImagePolicy = DEFAULT_LINKED_IMAGE_POLICY,
    prior_receipt: dict | None = None,
    resolver: Resolver = resolve_public_addresses,
    transport: Transport | None = None,
) -> LinkedImageBatch:
    """Materialize verified image-overlay links without exposing signed capability URIs."""

    photo_ids = [str(row.get("photo_id") or "").strip() for row in photo_rows]
    if any(not photo_id for photo_id in photo_ids) or len(photo_ids) != len(set(photo_ids)):
        raise LinkedImageError("INVALID_PHOTO_INVENTORY")
    report_digest = _sha256_file(report)
    if not _HEX_SHA256.fullmatch(report_sha256.lower()) or report_digest != report_sha256.lower():
        raise LinkedImageError("REPORT_SHA256_MISMATCH")
    selected_transport = transport or _pinned_https_get
    unresolved_links: list[dict[str, Any]] = []
    secondary_activation_regions: list[dict[str, Any]] = []
    candidates, extraction_failures, linked_occurrences = extract_candidates(
        report,
        photo_rows,
        policy,
        unresolved_links=unresolved_links,
        secondary_activation_regions=secondary_activation_regions,
    )
    embedded_groups = _build_embedded_groups(photo_rows, policy)
    rows_by_id = {
        str(row.get("photo_id")): row
        for row in photo_rows
        if str(row.get("photo_id") or "").strip()
    }
    results_by_id: dict[str, LinkedImageResult] = {}
    total_received = 0
    for photo_id, row in rows_by_id.items():
        if photo_id in extraction_failures:
            results_by_id[photo_id] = LinkedImageResult(
                photo_id=photo_id,
                page_number=int(row.get("page_number") or 0),
                required=_eligible_low_resolution(row, policy),
                status=extraction_failures[photo_id],
            )
        elif photo_id not in linked_occurrences:
            results_by_id[photo_id] = LinkedImageResult(
                photo_id=photo_id,
                page_number=int(row.get("page_number") or 0),
                required=False,
                status="NOT_REQUIRED" if not _eligible_low_resolution(row, policy) else "NO_LINK",
            )

    for photo_id in sorted(candidates):
        candidate = candidates[photo_id]
        cached = _prior_result(
            candidate,
            prior_receipt,
            destination_root,
            report_digest,
            policy,
            embedded_groups,
        )
        if cached is not None:
            results_by_id[photo_id] = cached
            continue
        remaining_run_bytes = policy.maximum_run_bytes - total_received
        if remaining_run_bytes <= 0:
            results_by_id[photo_id] = LinkedImageResult(
                photo_id=candidate.photo_id,
                page_number=candidate.page_number,
                required=candidate.required,
                status="RUN_BYTE_LIMIT_EXCEEDED",
                **_candidate_base(candidate),
            )
            continue
        result, received = _retrieve_candidate(
            candidate,
            destination_root,
            policy,
            resolver,
            selected_transport,
            remaining_run_bytes,
            embedded_groups,
        )
        total_received += received
        if total_received > policy.maximum_run_bytes:
            result = LinkedImageResult(
                photo_id=candidate.photo_id,
                page_number=candidate.page_number,
                required=candidate.required,
                status="RUN_BYTE_LIMIT_EXCEEDED",
                **_candidate_base(candidate),
            )
        results_by_id[photo_id] = result

    results = tuple(results_by_id[str(row["photo_id"])] for row in photo_rows)
    rows = tuple(_enrich_row(row, result) for row, result in zip(photo_rows, results, strict=True))
    failures = [
        result for result in results if result.required and result.status not in READY_STATUSES
    ]
    ok = not failures and not unresolved_links
    receipt = {
        "schema": LINKED_IMAGE_RECEIPT_SCHEMA,
        "policy_version": policy.version,
        "report_sha256": report_digest,
        "ok": ok,
        "photo_occurrence_count": len(photo_rows),
        "required_count": sum(1 for result in results if result.required),
        "verified_count": sum(1 for result in results if result.status == "VERIFIED"),
        "cached_count": sum(1 for result in results if result.status == "CACHED"),
        "failure_count": len(failures) + len(unresolved_links),
        "optional_link_failure_count": sum(
            1
            for result in results
            if not result.required
            and result.status not in READY_STATUSES
            and result.status not in {"NOT_REQUIRED", "NO_LINK"}
        ),
        "unresolved_image_link_count": len(unresolved_links),
        "secondary_activation_region_count": len(secondary_activation_regions),
        "total_received_bytes": total_received,
        "policy": {
            "allowed_hosts": sorted(policy.allowed_hosts),
            "expected_query_key_names": sorted(policy.expected_query_keys),
            "minimum_overlap_ratio": policy.minimum_overlap_ratio,
            "low_resolution_long_side_px": policy.low_resolution_long_side_px,
            "minimum_full_resolution_long_side_px": (policy.minimum_full_resolution_long_side_px),
            "minimum_full_resolution_pixels": policy.minimum_full_resolution_pixels,
            "thumbnail_transforms": list(policy.thumbnail_transforms),
            "maximum_thumbnail_hash_distance": policy.maximum_thumbnail_hash_distance,
            "maximum_thumbnail_mean_error": policy.maximum_thumbnail_mean_error,
            "minimum_thumbnail_luma_stddev": policy.minimum_thumbnail_luma_stddev,
            "minimum_thumbnail_entropy_bits": policy.minimum_thumbnail_entropy_bits,
            "minimum_thumbnail_mean_gradient": policy.minimum_thumbnail_mean_gradient,
            "thumbnail_tile_grid": policy.thumbnail_tile_grid,
            "maximum_thumbnail_tile_mean_error": (policy.maximum_thumbnail_tile_mean_error),
            "maximum_thumbnail_worst_tile_mean_error": (
                policy.maximum_thumbnail_worst_tile_mean_error
            ),
            "minimum_thumbnail_matching_tile_ratio": (policy.minimum_thumbnail_matching_tile_ratio),
            "maximum_thumbnail_comparison_side_px": (policy.maximum_thumbnail_comparison_side_px),
            "minimum_detail_evaluation_side_px": (policy.minimum_detail_evaluation_side_px),
            "maximum_detail_evaluation_side_px": (policy.maximum_detail_evaluation_side_px),
            "minimum_usable_detail_residual": policy.minimum_usable_detail_residual,
            "minimum_usable_detail_matching_tiles": (policy.minimum_usable_detail_matching_tiles),
            "maximum_candidates": policy.maximum_candidates,
            "maximum_image_bytes": policy.maximum_image_bytes,
            "maximum_run_bytes": policy.maximum_run_bytes,
            "maximum_pixels": policy.maximum_pixels,
            "maximum_side_px": policy.maximum_side_px,
            "maximum_redirects": policy.maximum_redirects,
        },
        "unresolved_image_links": unresolved_links,
        "secondary_activation_regions": secondary_activation_regions,
        "items": [result.receipt_row() for result in results],
    }
    return LinkedImageBatch(rows=rows, receipt=receipt, results=results, ok=ok)
