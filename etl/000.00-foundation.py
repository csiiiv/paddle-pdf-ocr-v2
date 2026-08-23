#!/usr/bin/env python3
"""Stage 000.00: run repository contracts and retain foundation QA.

Inputs: numbered ETL nodes, etl/_shared/, and etl/tests/
Outputs: output/<run>/000.00-foundation/qa/{tests,summary}.json
"""

from __future__ import annotations

import argparse
import os
import platform
import time
from pathlib import Path
from typing import Any

import pytest

from _common import PROJECT
from _shared.artifacts import ArtifactStore, write_json_atomic
from _shared.contracts import ARTIFACT_VERSION
from _shared.timestamps import iso_now


class ResultCollector:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "setup" and report.failed:
            status = "error"
        elif report.when == "call":
            status = "skip" if report.skipped else ("pass" if report.passed else "fail")
        elif report.when == "teardown" and report.failed:
            status = "error"
        else:
            return
        self.records[report.nodeid] = {
            "id": report.nodeid, "file": report.location[0],
            "line": int(report.location[1]) + 1, "test": report.location[2],
            "status": status, "duration_ms": round(float(report.duration) * 1000, 3),
            "detail": str(report.longrepr) if report.failed or report.skipped else None,
        }


def run_stage(*, project_root: Path, run_dir: Path,
              pytest_args: list[str] | None = None) -> tuple[dict[str, Any], int]:
    collector = ResultCollector()
    command_args = list(pytest_args or ["etl/tests", "-q"])
    started_at, started = iso_now(), time.perf_counter()
    old_cwd = Path.cwd()
    try:
        os.chdir(project_root)
        exit_code = int(pytest.main(command_args, plugins=[collector]))
    finally:
        os.chdir(old_cwd)
    records = [collector.records[key] for key in sorted(collector.records)]
    counts = {status: sum(record["status"] == status for record in records)
              for status in ("pass", "fail", "error", "skip")}
    summary = {
        "artifact_version": ARTIFACT_VERSION, "gate": "UNIT",
        "name": "repository_tests", "started_at": started_at,
        "completed_at": iso_now(), "timestamp_source": "captured",
        "python": platform.python_version(), "pytest": pytest.__version__,
        "command_args": command_args, "n_tests": len(records),
        "n_pass": counts["pass"], "n_fail": counts["fail"],
        "n_error": counts["error"], "n_skip": counts["skip"],
        "elapsed_s": round(time.perf_counter() - started, 3),
        "pass": exit_code == 0, "exit_code": exit_code,
    }
    store = ArtifactStore(run_dir)
    write_json_atomic(store.stage_qa_path("foundation", "tests.json"),
                      {**summary, "tests": records})
    write_json_atomic(store.stage_qa_path("foundation"), summary)
    return summary, exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="foundation")
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args()
    if Path(args.run).name != args.run:
        raise SystemExit("--run must be one folder name")
    run_dir = PROJECT / "output" / args.run
    summary, exit_code = run_stage(
        project_root=PROJECT,
        run_dir=run_dir,
        pytest_args=args.pytest_args or None,
    )
    print(
        f"Foundation QA {'PASS' if summary['pass'] else 'FAIL'}: "
        f"pass={summary['n_pass']} fail={summary['n_fail']} "
        f"error={summary['n_error']} skip={summary['n_skip']}"
    )
    print(f"Detailed: {run_dir / '000.00-foundation' / 'qa' / 'tests.json'}")
    print(f"Summary:  {run_dir / '000.00-foundation' / 'qa' / 'summary.json'}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
