"""Layered, conservative diagnostics for a CarSim run directory."""
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

DIAGNOSTIC_LAYERS = (
    "environment", "base", "scenario", "compile", "solver", "license",
    "output", "echo", "database", "cosim", "version",
)


@dataclass(frozen=True)
class Diagnostic:
    """One classified finding."""

    layer: str
    code: str
    severity: str
    message: str
    suggestion: str | None = None

    def __post_init__(self) -> None:
        if self.layer not in DIAGNOSTIC_LAYERS:
            raise ValueError(f"Unknown diagnostic layer: {self.layer}")
        if self.severity not in {"error", "warning", "info"}:
            raise ValueError(f"Unknown diagnostic severity: {self.severity}")


@dataclass
class DiagnosticResult:
    """Findings plus a PASS/FAIL/NOT RUN summary by layer."""

    diagnostics: list[Diagnostic] = field(default_factory=list)
    layer_status: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


def _parse_started(manifest: dict) -> float | None:
    value = manifest.get("run", {}).get("started_utc")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def diagnose_run(directory: str | Path) -> DiagnosticResult:
    """Inspect known artifacts without over-interpreting unknown solver text."""
    root = Path(directory)
    findings: list[Diagnostic] = []
    status = {layer: "NOT RUN" for layer in DIAGNOSTIC_LAYERS}

    def add(layer: str, code: str, severity: str, message: str,
            suggestion: str | None = None) -> None:
        findings.append(Diagnostic(layer, code, severity, message, suggestion))
        if severity == "error":
            status[layer] = "FAIL"
        elif status[layer] == "NOT RUN":
            status[layer] = "PASS" if severity == "info" else "WARN"

    manifest_path = root / "run_manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            status["scenario"] = "PASS"
            status["base"] = "PASS"
        except (OSError, ValueError) as exc:
            add("scenario", "manifest_invalid", "error", str(exc))

    runtime = manifest.get("carsim", {})
    solver = Path(runtime["solver"]) if runtime.get("solver") else None
    dll = Path(runtime["dll"]) if runtime.get("dll") else None
    if solver and not solver.is_file():
        add("environment", "solver_missing", "error", f"Solver executable missing: {solver}",
            "Re-run scripts/setup_paths.py or correct PROG")
    elif solver:
        status["environment"] = "PASS"
    if dll and not dll.is_file():
        add("environment", "dll_missing", "error", f"Solver DLL missing: {dll}")

    override = root / "override.par"
    simfile = root / "simfile.sim"
    if not override.is_file() or not simfile.is_file():
        add("compile", "compiled_input_missing", "error",
            "override.par or simfile.sim is missing")
    else:
        status["compile"] = "PASS"
        sim_text = simfile.read_text(encoding="utf-8", errors="replace")
        dll_line = re.search(r"^DLLFILE\s+(.+)$", sim_text, re.MULTILINE)
        if not dll_line or "carsim_64.dll" not in dll_line.group(1).casefold():
            add("compile", "dll_mismatch", "error",
                "simfile does not pin carsim_64.dll",
                "Regenerate the simfile through scenario_runner")

    stdout_path = root / "solver_stdout.txt"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.is_file() else ""
    if stdout:
        folded = stdout.casefold()
        if any(marker in folded for marker in (
                "unable to load library", "need a running copy", "solver license")):
            add("license", "license_failure", "error",
                "Solver output indicates a license/library failure",
                "Start the CarSim GUI or cslm.exe and verify DLL bitness")
        else:
            status["license"] = "PASS"
        if "termination at simulation time" not in folded:
            add("solver", "termination_missing", "error",
                "Solver output lacks normal termination")
        else:
            status["solver"] = "PASS"

    csv_path = root / "run.csv"
    started = _parse_started(manifest)
    if not csv_path.is_file():
        add("output", "run_csv_missing", "error", "run.csv is missing")
    elif started is not None and csv_path.stat().st_mtime < started:
        add("output", "run_csv_stale", "error", "run.csv predates this run")
    else:
        try:
            pd.read_csv(csv_path, nrows=5)
            status["output"] = "PASS"
        except (OSError, pd.errors.ParserError) as exc:
            add("output", "run_csv_parse", "error", str(exc))

    echo_path = root / "run_echo.par"
    if not echo_path.is_file():
        add("echo", "echo_missing", "error", "run_echo.par is missing")
    else:
        status["echo"] = "PASS"
        echo = echo_path.read_text(encoding="utf-8", errors="replace")
        for item in manifest.get("scenario", {}).get("parameters", []):
            if item.get("type", "scalar") != "scalar" or item.get("echo_validation", "required") == "none":
                continue
            key, requested = item["keyword"], item["value"]
            matches = re.findall(r"^\s*" + re.escape(key) + r"\s+([-+0-9.eEdD]+)", echo, re.MULTILINE)
            if not matches:
                severity = "error" if item.get("echo_validation", "required") == "required" else "warning"
                add("echo", "echo_absent", severity, f"{key} is absent from run_echo.par")
                continue
            actual = float(matches[-1].replace("D", "E").replace("d", "e"))
            if not math.isclose(actual, requested, rel_tol=1e-6, abs_tol=1e-8):
                add("echo", "echo_mismatch", "error",
                    f"{key} differs from the requested value")

    if runtime.get("version_verified") is False:
        add("version", "version_unverified", "warning",
            runtime.get("compatibility_warning") or "Detected CarSim version is unverified")
    elif runtime.get("version_verified") is True:
        status["version"] = "PASS"
    return DiagnosticResult(findings, status)


def format_diagnostics(result: DiagnosticResult) -> str:
    """Render the layer summary and likely causes."""
    lines = [f"{layer.title()}: {result.layer_status.get(layer, 'NOT RUN')}"
             for layer in DIAGNOSTIC_LAYERS]
    for item in result.diagnostics:
        lines.append(f"[{item.severity.upper()}] {item.layer}/{item.code}: {item.message}")
        if item.suggestion:
            lines.append("  Suggestion: " + item.suggestion)
    return "\n".join(lines)
