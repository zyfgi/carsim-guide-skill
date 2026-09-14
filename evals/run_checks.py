"""Record executable contract evidence separately from manual trigger evals."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from experiment_runner import provenance  # noqa: E402
from vehicle_registry import sha256  # noqa: E402


def redact_runtime(record, text):
    """Replace machine-specific runtime paths with placeholders before an
    error message is embedded in a published evidence record."""
    runtime = record.get("runtime", {})
    for key in ("cli", "dll"):
        if runtime.get(key):
            text = text.replace(runtime[key], "<RUNTIME>")
    for key, placeholder in (("prog", "<PROG>"), ("datadir", "<DATADIR>")):
        value = runtime.get(key, "")
        if value:
            text = text.replace(value.rstrip(chr(92) + "/"), placeholder)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Versioned JSON evidence file (must not exist)")
    parser.add_argument("--live-manifest", action="append", default=[])
    parser.add_argument("--rejected-manifest", action="append", default=[],
                        help="Record a real solver/acceptance rejection, not a passed experiment")
    parser.add_argument("--functional", action="store_true", help="Also run licensed solver tests; requires explicit base")
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        parser.error("Output already exists; choose a new versioned record")
    now = datetime.now(timezone.utc)
    temp = ROOT / ".validation" / ("checks_" + now.strftime("%Y%m%dT%H%M%S%f"))
    temp.mkdir(parents=True)
    # Explicit test files avoid pytest directory/file deduplication dropping the
    # nonstandard functional_carsim.py name when tests/ is also supplied.
    test_files = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "tests").glob("test_*.py"))]
    command = [sys.executable, "-m", "pytest", *test_files, "-q", "-p", "no:cacheprovider",
               "--basetemp", str(temp / "tmp"), "--junitxml", str(temp / "tests.xml")]
    if args.functional:
        command.append("tests/functional_carsim.py")
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    (temp / "test-output.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    cases = ET.parse(temp / "tests.xml").findall(".//testcase")
    if args.functional and not any("functional_carsim" in c.get("classname", "") for c in cases):
        raise RuntimeError("Functional tests requested but not collected")
    verdicts = [{"id": c.get("classname") + "." + c.get("name"),
                 "status": "failed" if c.find("failure") is not None or c.find("error") is not None
                 else "skipped" if c.find("skipped") is not None else "passed"} for c in cases]
    live = []
    for filename in args.live_manifest:
        path = Path(filename)
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] != "passed":
            raise ValueError("Live experiment did not pass: %s" % path)
        for name, digest in {**record["input_sha256"], **record["output_sha256"]}.items():
            if sha256(path.parent / name) != digest:
                raise ValueError("Live evidence artifact changed: %s" % name)
        live.append({"experiment": record["config"], "status": record["status"],
                     "validation": record["validation"], "base_sha256": record["vehicle"]["base_sha256"],
                     "carsim_version": record["vehicle"]["carsim_version"],
                     "powertrain": record["vehicle"]["powertrain"],
                     "runtime_sha256": record["runtime_sha256"],
                     "source_sha256": record["provenance"]["source_sha256"],
                     "sensor_packets": record.get("sensor_packets"),
                     "manifest_sha256": sha256(path), "output_sha256": record["output_sha256"]})
    rejected = []
    for filename in args.rejected_manifest:
        path = Path(filename)
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] != "failed" or not record.get("error"):
            raise ValueError("Rejection evidence must have failed status and reason")
        for name, digest in record["input_sha256"].items():
            if sha256(path.parent / name) != digest:
                raise ValueError("Rejected input artifact changed: %s" % name)
        rejected.append({"experiment": record["config"], "status": "failed",
                         "error": redact_runtime(record, record["error"]), "manifest_sha256": sha256(path),
                         "source_sha256": record["provenance"]["source_sha256"]})
    evidence = {"record_version": 1, "created_utc": now.isoformat(), "kind": "executable_contract_checks",
                "provenance": provenance(), "pytest_exit_code": result.returncode,
                "counts": {v: sum(c["status"] == v for c in verdicts) for v in ("passed", "failed", "skipped")},
                "cases": verdicts, "licensed_experiments": live, "rejected_experiments": rejected,
                "functional_requested": args.functional, "recorder_sha256": sha256(__file__),
                "manual_trigger_evals": "not_run; see evals.json protocol"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
