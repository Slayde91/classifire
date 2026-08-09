from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select

from classifire.canonical_models import Defect, EvidenceSource, PhysicalModelLock
from classifire.db import SessionLocal
from classifire.models import Estimate, Opening, Service
from classifire.services.workflow_db import assess_estimate_workflow


REQUIRED_INTAKE_TOOLS = {
    "pdf",
    "image",
    "classifire_register_evidence_observations",
}
REQUIRED_PHYSICAL_TOOLS = {
    "pdf",
    "image",
    "classifire_evidence_read",
    "classifire_submit_initial_physical_model",
    "classifire_lock_physical_model",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_json_envelope(raw: str) -> dict:
    text = raw.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise RuntimeError(f"OpenClaw did not return a JSON object. Output: {text}")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("Expected a JSON object from OpenClaw.")
    return value


def locate_openclaw_entry() -> tuple[str, str]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node.exe was not found on PATH.")
    candidates: list[Path] = []
    explicit = os.environ.get("OPENCLAW_CLI_MJS")
    if explicit:
        candidates.append(Path(explicit))
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "openclaw" / "openclaw.mjs")
    command = shutil.which("openclaw")
    if command:
        candidates.append(Path(command).resolve().parent / "node_modules" / "openclaw" / "openclaw.mjs")
    for candidate in candidates:
        if candidate.is_file():
            return node, str(candidate)
    raise RuntimeError("OpenClaw CLI entrypoint was not found. Set OPENCLAW_CLI_MJS if needed.")


def latest_prepared_receipt(root: Path) -> Path:
    candidates = sorted(
        root.glob("data/real-uat/*/00-prepared.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(
            "No prepared real-UAT receipt exists. Run scripts/prepare_classifire_real_uat.py first."
        )
    return candidates[0]


def load_receipt(root: Path, run_id: str | None) -> tuple[Path, dict]:
    path = (
        root / "data" / "real-uat" / run_id / "00-prepared.json"
        if run_id
        else latest_prepared_receipt(root)
    )
    if not path.is_file():
        raise RuntimeError(f"Prepared real-UAT receipt not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("ok") is not True or payload.get("interpretation_performed") is not False:
        raise RuntimeError("Prepared receipt is not an untouched CLASSIFIRE real-UAT preparation receipt.")
    return path, payload


def extract_visual_manifest(pdf_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf_path))
    rows: list[dict] = []
    extraction_errors: list[dict] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            keys = list(page.images.keys())
        except Exception as exc:
            extraction_errors.append({"page": page_number, "error": f"image-index: {exc}"})
            continue
        for image_index, key in enumerate(keys, start=1):
            try:
                image_file = page.images[key]
                pil = image_file.image
                if pil is None:
                    raise RuntimeError("pypdf returned no decoded PIL image")
                if not isinstance(pil, Image.Image):
                    raise RuntimeError("decoded PDF image is not a PIL Image")
                name = f"page-{page_number:04d}-image-{image_index:03d}.png"
                target = output_dir / name
                if pil.mode not in {"RGB", "RGBA", "L"}:
                    pil = pil.convert("RGB")
                pil.save(target, format="PNG")
                rows.append(
                    {
                        "page_number": page_number,
                        "image_index": image_index,
                        "filename": name,
                        "width": pil.width,
                        "height": pil.height,
                        "sha256": sha256_file(target),
                        "source_object": str(key),
                    }
                )
            except Exception as exc:
                extraction_errors.append(
                    {"page": page_number, "image_index": image_index, "error": str(exc)}
                )
    manifest = {
        "schema": "CLASSIFIRE-REAL-UAT-VISUAL-MANIFEST-v1",
        "pdf": str(pdf_path),
        "page_count": len(reader.pages),
        "image_count": len(rows),
        "images": rows,
        "extraction_errors": extraction_errors,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return manifest


class Controller:
    def __init__(self, receipt: dict, *, base_url: str, timeout_seconds: int) -> None:
        self.root = repo_root()
        self.receipt = receipt
        self.run_id = str(receipt["run_id"])
        self.estimate_id = str(receipt["estimate_id"])
        self.stored_file_id = str(receipt["stored_file_id"])
        self.report_name = str(receipt["report_filename"])
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.receipt_dir = self.root / "data" / "real-uat" / self.run_id
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        node, openclaw_mjs = locate_openclaw_entry()
        self.openclaw_prefix = [node, openclaw_mjs]
        self.api_process: subprocess.Popen | None = None

    def save_json(self, name: str, value: object) -> None:
        (self.receipt_dir / name).write_text(
            json.dumps(value, indent=2, default=str), encoding="utf-8"
        )

    def save_text(self, name: str, value: str) -> None:
        (self.receipt_dir / name).write_text(value, encoding="utf-8")

    def run_process(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or self.timeout_seconds,
            check=False,
        )
        if check and result.returncode != 0:
            detail = "\n".join(x for x in (result.stdout.strip(), result.stderr.strip()) if x)
            raise RuntimeError(f"Command failed with exit code {result.returncode}: {detail}")
        return result

    def openclaw(self, *args: str, timeout: int | None = None, check: bool = True):
        return self.run_process([*self.openclaw_prefix, *args], timeout=timeout, check=check)

    def api_health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/healthz", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok" and payload.get("product") == "CLASSIFIRE"
        except (OSError, urllib.error.URLError, ValueError):
            return False

    def ensure_api(self) -> None:
        if self.api_health():
            print("PASS CLASSIFIRE API health (existing process)")
            return
        log_dir = self.receipt_dir / "api"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = (log_dir / "stdout.log").open("w", encoding="utf-8")
        stderr = (log_dir / "stderr.log").open("w", encoding="utf-8")
        print("CLASSIFIRE API is offline; starting a temporary real-UAT API...")
        self.api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "classifire.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8787",
            ],
            cwd=self.root,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        for _ in range(40):
            if self.api_health():
                print("PASS CLASSIFIRE API health (temporary managed process)")
                return
            time.sleep(0.25)
        raise RuntimeError("CLASSIFIRE API could not be started for real-UAT intake.")

    def preflight(self) -> None:
        config = self.openclaw("config", "validate", "--json")
        self.save_text("01-openclaw-config.json", config.stdout)
        status = self.openclaw(
            "gateway", "status", "--require-rpc", "--timeout", "30000", timeout=40, check=False
        )
        if status.returncode != 0:
            print("OpenClaw Gateway RPC is unhealthy; restarting once...")
            self.openclaw("gateway", "restart", timeout=60)
            time.sleep(5)
            status = self.openclaw(
                "gateway", "status", "--require-rpc", "--timeout", "30000", timeout=40, check=False
            )
        if status.returncode != 0:
            raise RuntimeError("OpenClaw Gateway RPC preflight failed after retry.")
        self.save_text("02-openclaw-gateway.txt", status.stdout + status.stderr)
        print("PASS OpenClaw Gateway RPC")
        self.ensure_api()

    def workspace_report(self, agent_id: str) -> Path:
        raw = self.receipt.get("agent_workspace_evidence") or {}
        value = raw.get(agent_id)
        if not value:
            raise RuntimeError(f"Prepared receipt has no staged report path for {agent_id}.")
        path = Path(value)
        if not path.is_file():
            raise RuntimeError(f"Staged report is missing for {agent_id}: {path}")
        if sha256_file(path) != self.receipt["report_sha256"]:
            raise RuntimeError(f"Staged report SHA256 mismatch for {agent_id}.")
        return path

    def stage_visuals(self) -> dict:
        intake_pdf = self.workspace_report("cf-intake-evidence")
        intake_dir = intake_pdf.parent / "visuals"
        if intake_dir.exists():
            shutil.rmtree(intake_dir)
        manifest = extract_visual_manifest(intake_pdf, intake_dir)
        if manifest["extraction_errors"]:
            self.save_json("03-visual-extraction-errors.json", manifest["extraction_errors"])
            raise RuntimeError(
                "PDF embedded-image extraction reported errors. Real UAT stops fail-closed; "
                "see 03-visual-extraction-errors.json."
            )
        physical_pdf = self.workspace_report("cf-physical-model")
        physical_dir = physical_pdf.parent / "visuals"
        if physical_dir.exists():
            shutil.rmtree(physical_dir)
        shutil.copytree(intake_dir, physical_dir)
        self.save_json("03-visual-manifest.json", manifest)
        print(
            f"PASS evidence staging -> {manifest['page_count']} pages, "
            f"{manifest['image_count']} embedded images"
        )
        return manifest

    def initialize_session(self, agent_id: str, stage: str) -> str:
        alias = f"classifire-real-{self.run_id}-{stage}"
        result = self.openclaw(
            "agent",
            "--agent",
            agent_id,
            "--session-key",
            alias,
            "--message",
            "Controlled CLASSIFIRE real-UAT readiness check. Reply exactly READY. Do not call tools.",
            "--timeout",
            "180",
            "--json",
            timeout=210,
        )
        envelope = parse_json_envelope(result.stdout)
        self.save_json(f"{stage}-session.json", envelope)
        session_key = (
            envelope.get("result", {})
            .get("meta", {})
            .get("systemPromptReport", {})
            .get("sessionKey")
        )
        return str(session_key or f"agent:{agent_id}:{alias}")

    def effective_tools(self, session_key: str, receipt_name: str) -> set[str]:
        params = json.dumps({"sessionKey": session_key}, separators=(",", ":"))
        result = self.openclaw(
            "gateway",
            "call",
            "tools.effective",
            "--params",
            params,
            "--timeout",
            "60000",
            "--json",
            timeout=75,
        )
        payload = parse_json_envelope(result.stdout)
        self.save_json(receipt_name, payload)
        serialized = json.dumps(payload, separators=(",", ":"))
        import re

        return set(re.findall(r'(?<![A-Za-z0-9_])(?:classifire_[A-Za-z0-9_]+|pdf|image)(?![A-Za-z0-9_])', serialized))

    def require_tools(self, agent_id: str, session_key: str, tools: set[str], receipt_name: str) -> None:
        visible = self.effective_tools(session_key, receipt_name)
        missing = sorted(tools - visible)
        if missing:
            raise RuntimeError(
                f"{agent_id} is missing required real-UAT tools: {', '.join(missing)}. "
                "Visual report analysis cannot proceed safely."
            )
        print(f"PASS {agent_id} required tools")

    def agent_turn(self, agent_id: str, session_key: str, prompt: str, receipt_name: str) -> dict:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".md", delete=False
        ) as handle:
            handle.write(prompt)
            prompt_path = handle.name
        try:
            result = self.openclaw(
                "agent",
                "--agent",
                agent_id,
                "--session-key",
                session_key,
                "--message-file",
                prompt_path,
                "--timeout",
                str(self.timeout_seconds),
                "--verbose",
                "full",
                "--json",
                timeout=self.timeout_seconds + 60,
            )
            envelope = parse_json_envelope(result.stdout)
            self.save_json(receipt_name, envelope)
            if result.stderr.strip():
                self.save_text(receipt_name + ".stderr.txt", result.stderr)
            if envelope.get("ok") is False or envelope.get("status") in {"error", "timeout"}:
                raise RuntimeError(f"OpenClaw agent turn failed: {json.dumps(envelope)}")
            return envelope
        finally:
            Path(prompt_path).unlink(missing_ok=True)

    def intake_prompt(self, report: Path, manifest: dict) -> str:
        visual_dir = report.parent / "visuals"
        return f"""# CLASSIFIRE real-report intake UAT

You are `cf-intake-evidence`. Work only within your existing role boundary.

Canonical estimate_id: `{self.estimate_id}`
Canonical stored_file_id: `{self.stored_file_id}`
Immutable report: `{report}`
Visual manifest: `{visual_dir / 'manifest.json'}`
Report pages: {manifest['page_count']}
Extracted embedded images: {manifest['image_count']}

## Mandatory evidence review
1. Use the `pdf` tool to inspect the complete PDF. Review every page, all report text, tables, schedules, annotations and page context. Do not rely on text snippets alone.
2. Read the visual manifest. Use the `image` tool to inspect EVERY listed extracted image. Images may be defect photos, diagrams, logos or other non-scope graphics; classify what they actually show rather than assuming relevance.
3. Never assume one photograph = one Service, one penetration, one repair, one defect quantity or one pricing line.
4. Preserve uncertainty. Use observed/confirmed only when the evidence supports it; otherwise use provisional/inferred with an appropriate confidence.
5. Do not create Openings or Services. Do not select Package 15 systems. Do not price anything.

## Mandatory canonical registration
Use `classifire_register_evidence_observations` one or more times.

A. PAGE COVERAGE: register exactly one observation for every PDF page with:
- evidence_type = `report_page_review`
- stored_file_id = `{self.stored_file_id}`
- page_number = the 1-based page number as a string
- region_reference = `page:<page-number>`
- source_reference = `{self.report_name}`
- evidence_class = `observed`
- source_json should contain a concise page summary and whether scope/defect evidence appears on that page.

B. IMAGE COVERAGE: register exactly one observation for every manifest image with:
- evidence_type = `report_image_review`
- stored_file_id = `{self.stored_file_id}`
- page_number = the manifest page number as a string
- region_reference = `image:<filename>`
- source_reference = `{self.report_name}`
- evidence_class = `observed`
- source_json should state what is visibly shown and whether it is scope-relevant, non-scope, or uncertain.

C. DEFECT/SCOPE OBSERVATIONS: additionally register each distinct defect/report entry supported by the report. Preserve the report's external defect ID exactly when present. Include description, location, classification, page/photo/schedule reference and confidence. One defect ID may contain multiple physical services/openings; do not collapse them here.

If the document is not a passive-fire defect/scope report, register the page/image coverage honestly, register no invented defects, and state that limitation in your final response.

Finish with a concise JSON-like summary containing page reviews registered, image reviews registered, defect IDs observed, and material limitations. Do not perform any downstream stage.
"""

    def inspect_state(self) -> dict:
        with SessionLocal() as db:
            estimate = db.get(Estimate, self.estimate_id)
            if estimate is None:
                raise RuntimeError("Prepared estimate disappeared from the database.")
            evidence = list(
                db.scalars(
                    select(EvidenceSource).where(EvidenceSource.estimate_id == self.estimate_id)
                ).all()
            )
            defects = list(
                db.scalars(select(Defect).where(Defect.estimate_id == self.estimate_id)).all()
            )
            openings = list(
                db.scalars(select(Opening).where(Opening.estimate_id == self.estimate_id)).all()
            )
            opening_ids = [item.id for item in openings]
            services = (
                list(db.scalars(select(Service).where(Service.opening_id.in_(opening_ids))).all())
                if opening_ids
                else []
            )
            locks = list(
                db.scalars(
                    select(PhysicalModelLock).where(
                        PhysicalModelLock.estimate_id == self.estimate_id,
                        PhysicalModelLock.invalidated_at.is_(None),
                    )
                ).all()
            )
            assessment = assess_estimate_workflow(db, estimate)
            return {
                "estimate_id": self.estimate_id,
                "workflow_stage": assessment.stage,
                "evidence_count": len(evidence),
                "defect_count": len(defects),
                "opening_count": len(openings),
                "service_count": len(services),
                "physical_lock_count": len(locks),
                "physical_locks": [
                    {
                        "id": lock.id,
                        "validator_result": lock.validator_result,
                        "critical_unknowns": lock.critical_unknowns,
                        "content_hash": lock.content_hash,
                    }
                    for lock in locks
                ],
                "page_regions": sorted(
                    str(item.region_reference)
                    for item in evidence
                    if item.evidence_type == "report_page_review" and item.region_reference
                ),
                "image_regions": sorted(
                    str(item.region_reference)
                    for item in evidence
                    if item.evidence_type == "report_image_review" and item.region_reference
                ),
                "defects": [
                    {
                        "id": item.id,
                        "external_defect_id": item.external_defect_id,
                        "description": item.description,
                        "location": item.location,
                        "evidence_status": item.evidence_status,
                    }
                    for item in defects
                ],
            }

    def verify_intake_coverage(self, manifest: dict) -> dict:
        state = self.inspect_state()
        expected_pages = {f"page:{number}" for number in range(1, manifest["page_count"] + 1)}
        actual_pages = set(state["page_regions"])
        expected_images = {f"image:{row['filename']}" for row in manifest["images"]}
        actual_images = set(state["image_regions"])
        missing_pages = sorted(expected_pages - actual_pages)
        missing_images = sorted(expected_images - actual_images)
        result = {
            **state,
            "expected_page_reviews": len(expected_pages),
            "expected_image_reviews": len(expected_images),
            "missing_page_regions": missing_pages,
            "missing_image_regions": missing_images,
            "coverage_ok": not missing_pages and not missing_images,
        }
        self.save_json("11-intake-state.json", result)
        if missing_pages or missing_images:
            raise RuntimeError(
                "cf-intake-evidence did not register complete page/image coverage. "
                f"Missing pages={missing_pages}; missing images={missing_images}."
            )
        print(
            f"PASS intake coverage -> {len(expected_pages)} pages, "
            f"{len(expected_images)} images, {state['defect_count']} canonical defects"
        )
        return result

    def physical_prompt(self, report: Path, manifest: dict) -> str:
        visual_dir = report.parent / "visuals"
        return f"""# CLASSIFIRE real-report physical-model UAT

You are `cf-physical-model`. Work only within your existing role boundary.

Canonical estimate_id: `{self.estimate_id}`
Immutable report: `{report}`
Visual manifest: `{visual_dir / 'manifest.json'}`

The intake agent has completed canonical page/image registration. Your task is to build the evidence-backed physical model, not to choose technical systems or prices.

## Mandatory method
1. Call `classifire_evidence_read` for estimate `{self.estimate_id}` before modelling.
2. Use the PDF and the `image` tool to re-check any page/photo needed to resolve physical details. Do not rely on an intake conclusion when the source can be inspected directly.
3. Model Defect -> Opening(s) -> Service(s). A defect ID may contain multiple openings and multiple services. One photograph does not imply one service or one penetration.
4. Identify substrate plane independently for every opening. Do not combine wall and floor/soffit planes into one opening merely because they share a defect ID.
5. Every Service submitted through `classifire_submit_initial_physical_model` MUST have an explicit quantity greater than zero. Never default quantity to 1 because the report has one row or one photo.
6. Preserve confirmed/inferred/provisional uncertainty in evidence_status, relationship_status, confidence and notes. Do not invent material, dimensions, service count or opening relationships.
7. Submit the initial physical model exactly once only when the report supports at least one physical opening/service. If the supplied document contains no passive-fire physical scope, do not submit an empty or invented model.
8. After a supported model is submitted, call `classifire_lock_physical_model`. Accept a fail-closed/provisional result if critical unknowns remain. Do not override it.
9. Do NOT search Package 15, select a Repair Strategy, derive quantities/labour, or price anything in this turn.

If evidence is insufficient for a defensible physical model, stop and state the missing evidence rather than guessing.

Finish with a concise summary of opening count, service count, explicit service quantities, substrate planes, uncertainties, and lock result/limitation.
"""

    def run(self) -> dict:
        print("CLASSIFIRE real-report intake + physical-model UAT")
        print(f"Run ID: {self.run_id}")
        print(f"Estimate ID: {self.estimate_id}")
        print(f"Receipts: {self.receipt_dir}")
        self.preflight()
        manifest = self.stage_visuals()

        intake_agent = "cf-intake-evidence"
        intake_session = self.initialize_session(intake_agent, "10-intake")
        self.require_tools(
            intake_agent,
            intake_session,
            REQUIRED_INTAKE_TOOLS,
            "10-intake-effective.json",
        )
        intake_report = self.workspace_report(intake_agent)
        self.agent_turn(
            intake_agent,
            intake_session,
            self.intake_prompt(intake_report, manifest),
            "10-intake-agent.json",
        )
        intake_state = self.verify_intake_coverage(manifest)

        physical_agent = "cf-physical-model"
        physical_session = self.initialize_session(physical_agent, "20-physical")
        self.require_tools(
            physical_agent,
            physical_session,
            REQUIRED_PHYSICAL_TOOLS,
            "20-physical-effective.json",
        )
        physical_report = self.workspace_report(physical_agent)
        self.agent_turn(
            physical_agent,
            physical_session,
            self.physical_prompt(physical_report, manifest),
            "20-physical-agent.json",
        )
        final_state = self.inspect_state()
        final_state["run_id"] = self.run_id
        final_state["intake_coverage_ok"] = intake_state["coverage_ok"]
        final_state["status"] = (
            "PHYSICAL_MODEL_LOCKED"
            if final_state["physical_lock_count"] > 0
            else "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION"
        )
        self.save_json("21-physical-state.json", final_state)
        print(json.dumps(final_state, indent=2, default=str))
        return final_state

    def close(self) -> None:
        if self.api_process is not None and self.api_process.poll() is None:
            self.api_process.terminate()
            try:
                self.api_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.api_process.kill()
            print("Stopped temporary CLASSIFIRE real-UAT API.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the controlled real-report CLASSIFIRE/OpenClaw intake and physical-model UAT. "
            "If --run-id is omitted, the latest prepared real-UAT receipt is used."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    root = repo_root()
    _receipt_path, receipt = load_receipt(root, args.run_id)
    controller = Controller(
        receipt,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        state = controller.run()
        return 0 if state.get("status") in {
            "PHYSICAL_MODEL_LOCKED",
            "PARTIAL_SOURCE_OR_PHYSICAL_LIMITATION",
        } else 1
    except Exception as exc:
        print(f"CLASSIFIRE real-report intake UAT failed: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
