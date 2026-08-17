from __future__ import annotations

import base64
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_classifire_real_uat_fireseals_visualvalidated as visual_module  # noqa: E402
from run_classifire_real_uat_fireseals_visualvalidated import (  # noqa: E402
    VisualValidatedTopologyController,
)


def _proposal() -> dict:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
        "openings": [
            {
                "opening_code": "O-A",
                "opening_type": "service_penetration",
                "substrate_type": "block wall",
                "substrate_plane": "wall",
                "orientation": "vertical",
            }
        ],
        "services": [
            {
                "service_code": "S-A",
                "primary_opening_code": "O-A",
                "opening_codes": ["O-A"],
                "service_type": "pipe",
                "material": "PEX",
                "quantity": 2,
            }
        ],
    }


def _approved() -> dict:
    return {
        "verdict":
            "APPROVED",
        "observed_opening_count":
            1,
        "observed_service_group_count":
            1,
        "issues":
            [],
        "limitations":
            [],
        "blind_reconciliation":
            [
                {
                    "blind_candidate_id":
                        "V-O-001",
                    "disposition":
                        "ACCOUNTED_FOR",
                    "proposal_refs":
                        ["O-A"],
                    "detail":
                        "blind Opening corresponds to O-A",
                    "evidence_refs":
                        ["photo-a.png"],
                },
                {
                    "blind_candidate_id":
                        "V-S-001",
                    "disposition":
                        "ACCOUNTED_FOR",
                    "proposal_refs":
                        ["S-A"],
                    "detail":
                        "blind Service corresponds to S-A",
                    "evidence_refs":
                        ["photo-a.png"],
                },
            ],
    }



def _blind_inventory() -> dict:
    return {
        "status": "COMPLETE",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "one candidate opening",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "pipe",
                "material": "PEX",
                "quantity": 2,
                "candidate_opening_ids": [
                    "V-O-001"
                ],
                "detail": "one homogeneous pipe group",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _rejected() -> dict:
    return {
        "verdict": "REJECTED",
        "observed_opening_count": 2,
        "observed_service_group_count": 1,
        "issues": [
            {
                "code": "MISSED_OPENING",
                "detail": "A second distinct core hole is visible.",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "limitations": [],
    }


def _bare_controller(tmp_path: Path, responses: list[dict]) -> VisualValidatedTopologyController:
    controller = object.__new__(VisualValidatedTopologyController)
    controller.receipt_dir = tmp_path
    controller.run_id = "test-run"
    controller.estimate_id = "estimate-test"
    controller._visual_physical_session = "physical-session"
    controller._visual_validator_session = "validator-session"

    image_path = tmp_path / "photo-a.png"
    image_path.write_bytes(b"not-a-real-image-needed-for-unit-test")

    controller._ensure_visual_sessions = lambda: ("physical-session", "validator-session")
    controller._visual_files_for_defect = lambda _i, _d: (
        [image_path],
        [{"role": "defect_photo", "path": str(image_path)}],
    )
    controller._cached_visual_approved_model = lambda _i, _b, _f: None
    controller._visual_gate_cache_key = lambda _b, _f: {"test": True}
    controller._blind_validator_inventory = (
        lambda **_kwargs: (
            _blind_inventory(),
            [],
        )
    )
    controller._invoke_visual_agent_json = lambda **_kwargs: responses.pop(0)
    return controller


def test_visual_gate_returns_supported_model_only_after_validator_approval(tmp_path: Path) -> None:
    proposal = _proposal()
    controller = _bare_controller(tmp_path, [proposal, _approved()])
    defect = SimpleNamespace(id="d1", external_defect_id="147031", defect_code="147031")

    result = controller._synthesise_defect(1, defect, "{}")

    assert result == proposal
    assert (tmp_path / "21-visual-defect-001-approved-model.json").is_file()
    assert (tmp_path / "21-visual-defect-001-approved-validator.json").is_file()


def test_visual_gate_repeated_rejection_returns_insufficient_evidence(tmp_path: Path) -> None:
    proposal = _proposal()
    controller = _bare_controller(
        tmp_path,
        [
            proposal,
            _rejected(),
            proposal,
            _rejected(),
            proposal,
            _rejected(),
        ],
    )
    defect = SimpleNamespace(id="d1", external_defect_id="147038", defect_code="147038")

    result = controller._synthesise_defect(1, defect, "{}")

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["openings"] == []
    assert result["services"] == []
    assert any("remained REJECTED" in item for item in result["limitations"])
    assert not (tmp_path / "21-visual-defect-001-approved-model.json").exists()


def test_v4b_out_of_scope_correction_is_rejected_without_replacing_original(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    validator = {
        "verdict": "REJECTED",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "issues": [
            {
                "code": "WRONG_SERVICE_OPENING_LINK",
                "detail": "The Service belongs to the other visible Opening.",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "limitations": [],
    }
    out_of_scope = deepcopy(proposal)
    out_of_scope["services"].append(
        {
            "service_code": "S-B",
            "primary_opening_code": "O-A",
            "opening_codes": ["O-A"],
            "service_type": "pipe",
            "material": "PEX",
            "quantity": 1,
        }
    )
    controller = _bare_controller(
        tmp_path,
        [proposal, validator, out_of_scope],
    )
    defect = SimpleNamespace(
        id="d1",
        external_defect_id="147192",
        defect_code="147192",
    )

    result = controller._synthesise_defect(1, defect, "{}")

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert any(
        "exceeded structured Validator scope" in item
        for item in result["limitations"]
    )
    receipt = json.loads(
        (
            tmp_path
            / "21-visual-defect-001-correction-scope-rejected-1.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["original_proposal"] == proposal
    assert receipt["rejected_correction"] == out_of_scope
    assert not (
        tmp_path / "21-visual-defect-001-approved-model.json"
    ).exists()


def test_v4b_insufficient_scoped_correction_is_terminal_without_structural_retry(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    corrected = deepcopy(proposal)
    corrected.update(
        {
            "status": "INSUFFICIENT_EVIDENCE",
            "limitations": [
                "The Validator issue cannot be resolved from the available images."
            ],
        }
    )
    responses = [proposal, _rejected(), corrected]
    receipt_names: list[str] = []
    controller = _bare_controller(tmp_path, responses)

    def invoke(**kwargs: object) -> dict:
        receipt_names.append(str(kwargs["receipt_name"]))
        return responses.pop(0)

    controller._invoke_visual_agent_json = invoke
    defect = SimpleNamespace(
        id="d1",
        external_defect_id="147039",
        defect_code="147039",
    )

    result = controller._synthesise_defect(1, defect, "{}")

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert any(
        "remained insufficient within structured Validator scope" in item
        for item in result["limitations"]
    )
    assert responses == []
    assert receipt_names == [
        "21-visual-defect-001-physical-pass-0",
        "21-visual-defect-001-validator-pass-0",
        "21-visual-defect-001-physical-correction-1",
    ]
    assert not any("physical-structural-retry" in name for name in receipt_names)
    assert not (tmp_path / "21-visual-defect-001-approved-model.json").exists()


def test_v4b_incomplete_supported_scoped_correction_is_terminal_without_retry(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    validator = {
        "verdict": "REJECTED",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "issues": [
            {
                "code": "WRONG_BARRIER",
                "detail": "The barrier construction is not supported.",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "limitations": [],
    }
    corrected = deepcopy(proposal)
    corrected["openings"][0]["substrate_type"] = None
    responses = [proposal, validator, corrected]
    receipt_names: list[str] = []
    controller = _bare_controller(tmp_path, responses)

    def invoke(**kwargs: object) -> dict:
        receipt_names.append(str(kwargs["receipt_name"]))
        return responses.pop(0)

    controller._invoke_visual_agent_json = invoke
    defect = SimpleNamespace(
        id="d1",
        external_defect_id="147039",
        defect_code="147039",
    )

    result = controller._synthesise_defect(1, defect, "{}")

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert any("missing substrate_type" in item for item in result["limitations"])
    assert responses == []
    assert len(receipt_names) == 3
    assert not any("physical-structural-retry" in name for name in receipt_names)
    assert not (tmp_path / "21-visual-defect-001-approved-model.json").exists()


def test_v4b_ambiguous_size_or_quantity_blocks_before_physical_correction(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    validator = {
        "verdict": "REJECTED",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "issues": [
            {
                "code": "UNSUPPORTED_SIZE_OR_QUANTITY",
                "detail": "The visible size or quantity is unsupported.",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "limitations": [],
    }
    responses = [proposal, validator]
    controller = _bare_controller(tmp_path, responses)
    defect = SimpleNamespace(
        id="d1",
        external_defect_id="147192",
        defect_code="147192",
    )

    result = controller._synthesise_defect(1, defect, "{}")

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert any("is ambiguous" in item for item in result["limitations"])
    assert responses == []
    receipt = json.loads(
        (
            tmp_path
            / "21-visual-defect-001-correction-scope-blocked.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["proposal"] == proposal
    assert any("is ambiguous" in error for error in receipt["errors"])



def test_openresponses_visual_transport_sends_all_images_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = object.__new__(
        VisualValidatedTopologyController
    )
    controller.receipt_dir = tmp_path
    controller.run_id = "transport-test"
    controller._openresponses_timeout_seconds = 1800.0
    controller.gateway_call = (
        lambda *_args, **_kwargs: {"events": []}
    )

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    first.write_bytes(b"first-image-bytes")
    second.write_bytes(b"second-image-bytes")
    controller._current_visual_manifest = [
        {
            "attachment_index": 1,
            "filename": first.name,
            "path": str(first),
            "role": "defect_photo",
            "primary_secondary": "PRIMARY",
            "relationship_to_primary": "SELF",
            "expected_sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
        },
        {
            "attachment_index": 2,
            "filename": second.name,
            "path": str(second),
            "role": "labelled_full_page",
            "primary_secondary": "SECONDARY",
            "relationship_to_primary": "REPORT_PAGE_CONTEXT",
            "expected_sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
        },
    ]

    monkeypatch.setenv(
        "OPENCLAW_GATEWAY_TOKEN",
        "unit-test-secret",
    )

    captured: dict = {}

    response_payload = {
        "id": "response-test",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            '{"status":"MODEL_SUPPORTED",'
                            '"limitations":[],'
                            '"openings":[],'
                            '"services":[]}'
                        ),
                    }
                ],
            }
        ],
    }

    class FakeResponse:
        status_code = 200
        text = json.dumps(response_payload)

        @staticmethod
        def json() -> dict:
            return response_payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            traceback,
        ) -> None:
            return None

        def post(
            self,
            path: str,
            *,
            headers: dict,
            json: dict,
        ) -> FakeResponse:
            captured["path"] = path
            captured["headers"] = headers
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(
        visual_module.httpx,
        "Client",
        FakeClient,
    )

    result = controller._invoke_visual_agent_json(
        agent_id="cf-validator",
        session_key="agent:cf-validator:test",
        files=[first, second],
        prompt="inspect both images",
        receipt_name="transport-test",
    )

    assert result["status"] == "MODEL_SUPPORTED"

    assert captured["path"] == "/v1/responses"
    assert captured["client_kwargs"]["timeout"] == 1800.0
    assert captured["payload"]["tool_choice"] == "none"
    assert (
        captured["headers"]["x-openclaw-agent-id"]
        == "cf-validator"
    )
    assert (
        captured["headers"]["x-openclaw-session-key"]
        == "agent:cf-validator:test"
    )

    content = captured["payload"]["input"][0]["content"]

    assert [
        item["type"]
        for item in content
    ] == [
        "input_text",
        "input_image",
        "input_image",
    ]

    assert base64.b64decode(
        content[1]["source"]["data"]
    ) == first.read_bytes()

    assert base64.b64decode(
        content[2]["source"]["data"]
    ) == second.read_bytes()

    receipt_text = (
        tmp_path / "transport-test.json"
    ).read_text(encoding="utf-8")

    assert "unit-test-secret" not in receipt_text


def test_physical_visual_runtime_policy_requires_guarded_writes_and_blocks_quantity(
    tmp_path: Path,
) -> None:
    controller = object.__new__(
        VisualValidatedTopologyController
    )
    controller.receipt_dir = tmp_path

    allowed = {
        "groups": [
            {
                "tools": [
                    {"id": "classifire_evidence_read"},
                    {"id": "classifire_physical_model_read"},
                    {"id": "classifire_submit_initial_physical_model"},
                    {"id": "classifire_lock_physical_model"},
                ],
            }
        ]
    }

    controller.gateway_call = (
        lambda *_args, **_kwargs: allowed
    )

    controller._assert_physical_visual_readonly(
        "agent:cf-physical-model:test-21-visual-physical"
    )

    forbidden = {
        "groups": [
            {
                "tools": [
                    {"id": "classifire_evidence_read"},
                    {"id": "classifire_physical_model_read"},
                    {"id": "classifire_submit_initial_physical_model"},
                    {"id": "classifire_lock_physical_model"},
                    {"id": "classifire_derive_quantity_labour"},
                ],
            }
        ]
    }

    controller.gateway_call = (
        lambda *_args, **_kwargs: forbidden
    )

    with pytest.raises(
        RuntimeError,
        match="forbidden downstream tool",
    ):
        controller._assert_physical_visual_readonly(
            "agent:cf-physical-model:test-21-visual-physical"
        )


def test_visual_transport_fails_closed_when_agent_uses_internal_tool(
    tmp_path: Path,
) -> None:
    controller = object.__new__(
        VisualValidatedTopologyController
    )
    controller.receipt_dir = tmp_path

    controller.gateway_call = (
        lambda *_args, **_kwargs: {
            "events": [
                {
                    "kind": "tool_action",
                    "toolName":
                        "classifire_physical_model_read",
                }
            ]
        }
    )

    with pytest.raises(
        RuntimeError,
        match="visual independence failed",
    ):
        controller._assert_no_visual_tool_actions(
            session_key="agent:cf-physical-model:test",
            after_ms=1,
            receipt_name="tool-audit-test",
        )



def test_visual_tool_audit_falls_back_to_legacy_rpc(
    tmp_path: Path,
) -> None:
    controller = object.__new__(
        VisualValidatedTopologyController
    )
    controller.receipt_dir = tmp_path

    calls: list[str] = []

    def fake_gateway_call(
        method: str,
        params: dict,
        receipt_name: str,
    ) -> dict:
        calls.append(method)

        assert params == {
            "sessionKey":
                "agent:cf-physical-model:test",
            "kind":
                "tool_action",
            "after":
                1234567890,
            "limit":
                100,
        }

        if method == "audit.activity.list":
            raise RuntimeError(
                "Gateway call "
                "audit.activity.list failed: "
                '{"ok":false,"error":{'
                '"code":"INVALID_REQUEST",'
                '"message":"unknown method: '
                'audit.activity.list"}}'
            )

        if method == "audit.list":
            return {
                "events": [],
            }

        raise AssertionError(
            f"Unexpected method: {method}"
        )

    controller.gateway_call = (
        fake_gateway_call
    )

    controller._assert_no_visual_tool_actions(
        session_key=(
            "agent:cf-physical-model:test"
        ),
        after_ms=1234567890,
        receipt_name="legacy-audit-test",
    )

    assert calls == [
        "audit.activity.list",
        "audit.list",
    ]
