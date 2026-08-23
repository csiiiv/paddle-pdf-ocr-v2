#!/usr/bin/env python3
"""Run an inclusive slice of the canonical ordered ETL sequence."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from _common import PROJECT, parse_pages, resolve_pdf
from _shared.artifacts import write_json_atomic
from _shared.timestamps import iso_now

ETL = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ActiveStage:
    major: int
    insertion: int
    script: str
    accepted_settings: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[int, int]:
        return self.major, self.insertion

    @property
    def name(self) -> str:
        return Path(self.script).stem


# This is the single active execution order. Add an insertion explicitly;
# remove a defunct insertion explicitly and rebuild every downstream stage.
ACTIVE_STAGES = (
    ActiveStage(1, 0, "001.00-paddle-ocr.py", ("device",)),
    ActiveStage(2, 0, "002.00-layout.py", ("device", "layout_score")),
    ActiveStage(3, 0, "003.00-table-cells.py", ("device", "cells_score")),
    ActiveStage(4, 0, "004.00-extract.py"),
)

SETTING_FLAGS = {
    "device": "--device",
    "layout_score": "--layout-score",
    "cells_score": "--cells-score",
}


def stage_bound(value: str, *, end: bool) -> tuple[int, int]:
    """Parse `3` as 003.00/003.99, or an explicit `3.10` insertion."""
    parts = value.split(".", 1)
    try:
        major = int(parts[0])
        insertion = int(parts[1]) if len(parts) == 2 else (99 if end else 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid stage: {value}") from error
    if not 0 <= major <= 999 or not 0 <= insertion <= 99:
        raise argparse.ArgumentTypeError(f"stage outside 000.00..999.99: {value}")
    return major, insertion


def select_stages(start: tuple[int, int], end: tuple[int, int]) -> list[ActiveStage]:
    if end < start:
        raise ValueError("end stage precedes start stage")
    selected = [stage for stage in ACTIVE_STAGES if start <= stage.key <= end]
    if not selected:
        raise ValueError("stage range contains no active ETL scripts")
    return selected


def default_run_name(pdf: Path) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    return f"{pdf.stem}-etl-{timestamp}"


def build_command(stage: ActiveStage, *, pdf: Path, pages: list[int], run: str,
                  dpi: float, device: str, layout_score: float,
                  cells_score: float) -> list[str]:
    command = [sys.executable, str(ETL / stage.script),
               "--pdf", str(pdf), "--pages", ",".join(map(str, pages)),
               "--run", run, "--dpi", str(dpi)]
    settings = {"device": device, "layout_score": layout_score,
                "cells_score": cells_score}
    for setting in stage.accepted_settings:
        command.extend([SETTING_FLAGS[setting], str(settings[setting])])
    return command


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--pdf-source", type=Path, required=True)
    parser.add_argument("--pages", default="1",
                        help="One-based pages and inclusive ranges, e.g. 1-2,3,5-7")
    parser.add_argument("--start-stage", default="1")
    parser.add_argument("--end-stage", default="4")
    parser.add_argument("--run", help="Output run name (default: PDF stem + timestamp)")
    parser.add_argument("--dpi", type=float, default=200.0)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--layout-score", type=float, default=0.4)
    parser.add_argument("--cells-score", type=float, default=0.3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        pages = parse_pages(args.pages)
        start = stage_bound(args.start_stage, end=False)
        end = stage_bound(args.end_stage, end=True)
        stages = select_stages(start, end)
    except (ValueError, argparse.ArgumentTypeError) as error:
        raise SystemExit(str(error)) from error
    pdf = resolve_pdf(args.pdf_source)
    if not pdf.is_file():
        raise SystemExit(f"source PDF does not exist: {pdf}")
    run = args.run or default_run_name(pdf)
    if Path(run).name != run:
        raise SystemExit("--run must be one folder name")

    commands = [build_command(stage, pdf=pdf, pages=pages, run=run,
                              dpi=args.dpi, device=args.device,
                              layout_score=args.layout_score,
                              cells_score=args.cells_score)
                for stage in stages]
    print(f"ETL run: {run}")
    print(f"PDF: {pdf.resolve()}")
    print(f"Pages (1-based): {','.join(map(str, pages))}")
    print(f"Settings: dpi={args.dpi:g} device={args.device} "
          f"layout_score={args.layout_score:g} cells_score={args.cells_score:g}")
    for index, stage in enumerate(stages, 1):
        print(f"{index:02d}. {stage.name}")
    if args.dry_run:
        return

    started_at, started = iso_now(), time.perf_counter()
    executions = []
    exit_code = 0
    for stage, command in zip(stages, commands):
        node_started_at, node_started = iso_now(), time.perf_counter()
        print(f"\n>>> {stage.name}", flush=True)
        result = subprocess.run(command, cwd=PROJECT, check=False)
        executions.append({
            "stage": stage.name, "command": command,
            "started_at": node_started_at, "completed_at": iso_now(),
            "timestamp_source": "captured",
            "elapsed_s": round(time.perf_counter() - node_started, 3),
            "exit_code": result.returncode, "pass": result.returncode == 0,
        })
        if result.returncode:
            exit_code = result.returncode
            break

    summary = {
        "artifact_version": 1, "gate": "RUN_ETL", "name": "ordered_etl_slice",
        "run": run, "pdf": str(pdf.resolve()), "pages": pages,
        "page_selection": args.pages,
        "start_stage": args.start_stage, "end_stage": args.end_stage,
        "active_sequence": [stage.name for stage in stages],
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured",
        "elapsed_s": round(time.perf_counter() - started, 3),
        "n_planned": len(stages), "n_executed": len(executions),
        "pass": exit_code == 0 and len(executions) == len(stages),
        "executions": executions,
    }
    qa_path = PROJECT / "output" / run / "999.00-run-qa" / "execution.json"
    write_json_atomic(qa_path, summary)
    print(f"\nRun QA: {qa_path}")
    print(f"ETL {'PASS' if summary['pass'] else 'FAIL'}: "
          f"{summary['n_executed']}/{summary['n_planned']} stages, "
          f"{summary['elapsed_s']}s")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
