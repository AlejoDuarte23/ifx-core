import hashlib
import importlib
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .manifest import declared_schema, file_hash

if TYPE_CHECKING:
    from .mesh import Tolerances

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / "target" / "ifc-validation-build.json"


def source_hash() -> str:
    files = [ROOT / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")]
    files += list((ROOT / "src").rglob("*.rs"))
    files += list((ROOT / "crates").rglob("*.rs"))
    files += list((ROOT / "crates").rglob("Cargo.toml"))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(bytes.fromhex(file_hash(path)))
    return digest.hexdigest()


def binary_info() -> dict[str, str]:
    module = importlib.import_module("ifx_core.ifx_core")
    path = Path(module.__file__).resolve()
    return {"path": str(path), "sha256": file_hash(path)}


def validation_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(bytes.fromhex(file_hash(path)))
    return digest.hexdigest()


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    partial.replace(path)


def build() -> None:
    before = source_hash()
    environment = {**os.environ, "VIRTUAL_ENV": sys.prefix}
    environment.pop("CONDA_PREFIX", None)
    result = subprocess.run(
        [sys.executable, "-m", "maturin", "develop"],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"native build failed with exit code {result.returncode}")
    if source_hash() != before:
        raise RuntimeError("Rust sources changed during the build; build again")
    write_json(
        STAMP,
        {
            "version": 1,
            "source_sha256": before,
            "binary": binary_info(),
            "python": str(Path(sys.executable).resolve()),
        },
    )


def preflight() -> dict[str, object]:
    import ifcopenshell

    import ifx_core

    required = ("model_data", "entity_data", "geometry_data_buffers", "extract_ifc")
    if any(not callable(getattr(ifx_core, name, None)) for name in required):
        raise RuntimeError("installed ifx-core does not provide the required extraction functions")
    if not STAMP.is_file():
        raise RuntimeError("build stamp is missing; run python -m scripts.ifc_validation build")
    stamp = json.loads(STAMP.read_text())
    if stamp.get("source_sha256") != source_hash() or stamp.get("binary") != binary_info():
        raise RuntimeError("native build is stale; run python -m scripts.ifc_validation build")
    return {
        "ifcopenshell": ifcopenshell.version,
        "python": sys.version,
        "platform": platform.platform(),
        "source_sha256": stamp["source_sha256"],
        "binary": stamp["binary"],
        "validation_sha256": validation_hash(),
    }


def worker(job: dict[str, object], result_path: Path) -> None:
    import ifcopenshell
    import ifcopenshell.util.unit

    import ifx_core

    from .checks import (
        check_entities,
        check_geometry,
        check_model,
        geometry_products,
        reference_geometry,
    )
    from .mesh import Tolerances, compare_metrics

    started = time.monotonic()
    stages: dict[str, dict[str, object]] = {}
    result = {"id": job["id"], "schema": job["schema"], "status": "running", "stages": stages}

    def checkpoint() -> None:
        result["seconds"] = round(time.monotonic() - started, 3)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result["peak_rss_mib"] = round(rss / (1024**2 if sys.platform == "darwin" else 1024), 2)
        write_json(result_path, result)

    def stage(name: str, action: Callable[[], dict[str, object]]) -> None:
        result["active_stage"] = name
        checkpoint()
        begin = time.monotonic()
        try:
            stages[name] = action()
        except Exception as error:
            stages[name] = {"status": "fail", "error": f"{type(error).__name__}: {error}"}
        stages[name]["seconds"] = round(time.monotonic() - begin, 3)
        checkpoint()

    path = Path(job["path"])
    if "validation_sha256" in job and job["validation_sha256"] != validation_hash():
        raise ValueError("validation scripts changed during the run")
    if file_hash(path) != job["sha256"] or declared_schema(path) != job["schema"]:
        raise ValueError("model changed after manifest validation")
    source = path.read_bytes()
    model = ifcopenshell.open(str(path))
    reference_schema = getattr(model, "schema_identifier", model.schema)
    if reference_schema != job["schema"]:
        raise ValueError(f"reference schema differs: {reference_schema}")
    result["sha256"] = job["sha256"]
    analytic = job.get("analytic")
    limits = Tolerances(**job["tolerances"])
    stage("model", lambda: check_model(model, ifx_core.model_data(source)))
    extraction: dict[str, object] = {}

    def full_extract() -> dict[str, object]:
        if "error" in stages["model"]:
            return {
                "status": "fail",
                "error": "model extraction failed; partial geometry is diagnostic only",
            }
        extraction.update(ifx_core.extract_ifc(source, "high"))
        for key in ("model", "entities", "geometry"):
            if key not in extraction:
                raise ValueError(f"full extraction is missing {key}")
        return check_model(model, extraction["model"])

    stage("extraction", full_extract)
    stage(
        "entities",
        lambda: check_entities(
            model,
            extraction.get("entities") or ifx_core.entity_data(source, placements=True),
        ),
    )

    reference: dict[int, dict[str, object]] = {}

    def make_reference() -> dict[str, object]:
        if analytic is not None and analytic["reference_method"] == "analytic":
            reference[analytic["element_id"]] = analytic
            return {"status": "pass", "method": "analytic grid intersection and box dimensions"}
        products, _ = geometry_products(model)
        reference.update(reference_geometry(model, products))
        missing = sorted({entity.id() for entity in products} - reference.keys())
        failures = []
        if analytic is not None and analytic["element_id"] in reference:
            failures = compare_metrics(analytic, reference[analytic["element_id"]], limits)
        return {
            "status": "fail" if missing or failures else "pass",
            "method": "IfcOpenShell world metres with opening subtraction",
            "mesh_count": len(reference),
            "missing_ids": missing,
            "analytic_failures": failures,
        }

    stage("reference_geometry", make_reference)
    stage(
        "geometry",
        lambda: check_geometry(
            model,
            extraction.get("geometry") or ifx_core.geometry_data_buffers(source, "high"),
            reference,
            limits,
            analytic,
        ),
    )
    result.pop("active_stage", None)
    result["status"] = (
        "pass" if all(item["status"] == "pass" for item in stages.values()) else "fail"
    )
    result["native_extraction_verified"] = result["status"] == "pass"
    result["scope"] = "native extraction; browser streaming requires a separate browser check"
    checkpoint()


def run_case(job: dict[str, object], directory: Path, timeout: float) -> dict[str, object]:
    started = time.monotonic()
    job_path = directory / f"{job['id']}-job.json"
    result_path = directory / f"{job['id']}-result.json"
    log_path = directory / f"{job['id']}.log"
    write_json(job_path, job)
    timed_out = False
    with log_path.open("w") as log:
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.ifc_validation",
                    "worker",
                    str(job_path),
                    str(result_path),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
                env={**os.environ, "RAYON_NUM_THREADS": "2"},
            )
            code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out, code = True, None
    result = (
        json.loads(result_path.read_text())
        if result_path.exists()
        else {
            "id": job["id"],
            "schema": job["schema"],
            "stages": {},
        }
    )
    if timed_out or code != 0 or result.get("status") == "running":
        result.update(
            status="fail",
            native_extraction_verified=False,
            error="timeout" if timed_out else f"worker exit: {code}",
        )
        with log_path.open("rb") as log:
            log.seek(max(0, log_path.stat().st_size - 4096))
            result["log_tail"] = log.read().decode(errors="replace")
    result["log_path"] = str(log_path)
    result["wall_seconds"] = round(time.monotonic() - started, 3)
    return result


def run_suite(
    models: list[dict[str, object]],
    report_path: Path,
    timeout: float,
    limits: "Tolerances",
    include_fixtures: bool = True,
) -> dict[str, object]:
    from .fixtures import FEATURES, SCHEMAS, make_fixture

    provenance = preflight()
    results: list[dict[str, object]] = []
    report: dict[str, object] = {
        "version": 1,
        "status": "running",
        "provenance": provenance,
        "tolerances": asdict(limits),
        "model_count": len(models),
        "scope": (
            "native schema, product metadata, supported relationships, "
            "materials, and geometry metrics"
        ),
        "browser_verified": False,
        "cases": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    details = Path(tempfile.mkdtemp(prefix=f"{report_path.stem}-", dir=report_path.parent))
    report["details_directory"] = str(details)
    write_json(report_path, report)
    fixture_directory = details / "fixtures"
    fixture_directory.mkdir()
    fixtures = []
    if include_fixtures:
        for schema in SCHEMAS:
            for feature in FEATURES:
                source, analytic = make_fixture(schema, feature)
                path = Path(fixture_directory) / f"{schema.lower()}-{feature}.ifc"
                path.write_bytes(source)
                fixtures.append(
                    {
                        "id": f"fixture-{schema.lower()}-{feature}",
                        "schema": schema,
                        "path": str(path),
                        "sha256": file_hash(path),
                        "analytic": analytic,
                    }
                )
    cases = [*fixtures, *models]
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("manifest model IDs conflict with fixture IDs")
    report["expected_case_count"] = len(cases)
    report["fixture_count"] = len(fixtures)
    for case in cases:
        result = run_case(
            {
                **case,
                "tolerances": asdict(limits),
                "validation_sha256": provenance["validation_sha256"],
            },
            details,
            timeout,
        )
        results.append(result)
        print(f"{result['status']:4} {case['id']}", flush=True)
        write_json(report_path, report)
    report["status"] = (
        "pass" if results and all(item["status"] == "pass" for item in results) else "fail"
    )
    report["summary"] = {
        label: sum(item["status"] == label for item in results) for label in ("pass", "fail")
    }
    if validation_hash() != provenance["validation_sha256"]:
        report["status"] = "fail"
        report["error"] = "validation scripts changed during the run"
    write_json(report_path, report)
    return report
