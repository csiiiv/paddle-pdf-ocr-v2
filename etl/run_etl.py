#!/usr/bin/env python3
"""Run an inclusive slice of the canonical ordered ETL sequence."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from _common import PROJECT, load_pages_from_json, parse_pages, resolve_pdf
from _shared.artifacts import write_json_atomic
from _shared.timestamps import iso_now
from storage_estimate import estimate_run_storage, format_storage_estimate

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
    ActiveStage(2, 10, "002.10-token-geometry.py"),
    ActiveStage(2, 11, "002.11-token-geometry-repair.py"),
    ActiveStage(2, 20, "002.20-table-structure.py"),
    ActiveStage(2, 30, "002.30-by-ou-tree.py"),
    ActiveStage(2, 40, "002.40-pap-tree.py"),
    ActiveStage(2, 50, "002.50-tree-totals.py"),
)

SETTING_FLAGS = {
    "device": "--device",
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
    """Stable run folder so smokes and partial stage reruns overwrite in place."""
    return pdf.stem


def build_command(stage: ActiveStage, *, pdf: Path, pages: list[int], run: str,
                  dpi: float, device: str) -> list[str]:
    command = [sys.executable, str(ETL / stage.script),
               "--pdf", str(pdf), "--pages", ",".join(map(str, pages)),
               "--run", run, "--dpi", str(dpi)]
    settings = {"device": device}
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
    parser.add_argument(
        "--pages-json", type=Path,
        help="JSON file with named page sets (overrides --pages when set)",
    )
    parser.add_argument(
        "--pages-obj",
        help="Object name inside --pages-json (e.g. edge_pages, contiguous_spans)",
    )
    parser.add_argument("--start-stage", default="1")
    parser.add_argument("--end-stage", default="2.50")
    parser.add_argument(
        "--run",
        help="Output run name under output/ (default: PDF stem; overwrites in place)",
    )
    parser.add_argument("--dpi", type=float, default=200.0)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-storage-overcommit",
        action="store_true",
        help="Proceed even when estimated output size exceeds free disk (+ headroom)",
    )
    args = parser.parse_args()

    try:
        if args.pages_json is not None or args.pages_obj is not None:
            if args.pages_json is None or not args.pages_obj:
                raise ValueError("--pages-json and --pages-obj must be used together")
            pages = load_pages_from_json(args.pages_json, args.pages_obj)
            page_selection = {
                "source": "pages_json",
                "pages_json": str(args.pages_json),
                "pages_obj": args.pages_obj,
                "ignored_pages_arg": args.pages,
            }
        else:
            pages = parse_pages(args.pages)
            page_selection = {"source": "pages", "pages": args.pages}
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
                              dpi=args.dpi, device=args.device)
                for stage in stages]
    print(f"ETL run: {run}")
    print(f"PDF: {pdf.resolve()}")
    if page_selection["source"] == "pages_json":
        print(f"Pages from {page_selection['pages_json']} "
              f"object {page_selection['pages_obj']!r} "
              f"(overrides --pages={page_selection['ignored_pages_arg']!r})")
    print(f"Pages (1-based): {','.join(map(str, pages))}")
    print(f"Settings: dpi={args.dpi:g} device={args.device}")
    for index, stage in enumerate(stages, 1):
        print(f"{index:02d}. {stage.name}")
    output_root = PROJECT / "output"
    storage = estimate_run_storage(
        pages=pages,
        stages=[stage.name for stage in stages],
        output_root=output_root,
    )
    print(format_storage_estimate(storage), flush=True)
    if args.dry_run:
        return
    if not storage.ok_to_run and not args.allow_storage_overcommit:
        raise SystemExit(
            "Refusing to start: estimated output storage exceeds free disk "
            "(plus headroom). Pass --allow-storage-overcommit to override."
        )

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
        "page_selection": page_selection,
        "start_stage": args.start_stage, "end_stage": args.end_stage,
        "active_sequence": [stage.name for stage in stages],
        "storage_estimate": storage.as_dict(),
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
