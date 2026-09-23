"""Select the external linear-aging baseline on validation overlays only.

The rule is the guard's G=600 validation rule: harm at most 300 seconds in every
(overlay, load) cell, then the largest worst-cell deadline-window gap closed.  The rule
does not turn aging into a guaranteed policy; it is an empirical protected comparator.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import parallel, provenance  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, summarise  # noqa: E402
from spjf_guard.experiment.report import write_csv  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import Trace, simulate  # noqa: E402
from spjf_guard.sim.policy import aging, fcfs, sjf  # noqa: E402


def _credits(cfg) -> list[float]:
    return [float(value) for value in cfg["scheduling"]["aging_baseline"]["credit_per_s_grid"]]


def _score(path: Path, column: str) -> np.ndarray:
    frame = pd.read_parquet(path, columns=[column])
    return frame[column].to_numpy("float64")


def _cell(cfg, args, score, overlay: int, level: int, scratch: Path) -> list[dict]:
    path = args.overlay_dir / f"{args.pool}_rep{overlay}.npz"
    trace, servers, labels = load_overlay(path, level, {}, cfg.limit_s)
    with np.load(path) as store:
        job_row = store["job_row"].astype(np.int64)
    trace = Trace(
        trace.arrival_us,
        trace.service_us,
        {"aging_score": score[job_row]},
        trace.limit_s,
    )
    window = int(cfg["run"]["segment_tree_window_ranks"])
    reference = simulate(trace, fcfs(), servers, window=window)
    base = summarise(reference, reference.wait_us, labels["in_window"], labels["is_heavy"])
    directory = parallel.write_cell(
        scratch / f"cell_{overlay}_{level}",
        trace,
        labels,
        reference.wait_us,
        trace.scores,
    )
    tasks = [
        {
            "tag": "SJF",
            "policy": sjf(),
            "servers": servers,
            "window": window,
            "limit_s": cfg.limit_s,
            "assert_bounds": False,
        }
    ] + [
        {
            "tag": f"aging-{credit:.12g}",
            "policy": aging("aging_score", credit, f"aging-{credit:.12g}"),
            "servers": servers,
            "window": window,
            "limit_s": cfg.limit_s,
            "assert_bounds": False,
        }
        for credit in _credits(cfg)
    ]
    measured = {
        tag: payload["summary"]
        for tag, payload in parallel.map_policies(
            directory, tasks, cfg.limit_s, tuple(trace.scores), args.workers
        )
    }
    shutil.rmtree(directory, ignore_errors=True)
    target = measured.pop("SJF").p99_dl_s
    return [
        {
            "overlay": overlay,
            "level": level,
            "k": servers,
            "credit_per_s": credit,
            "p99_dl_s": measured[f"aging-{credit:.12g}"].p99_dl_s,
            "harm_s": measured[f"aging-{credit:.12g}"].harm_s,
            "gap_closed": gap_closed(
                measured[f"aging-{credit:.12g}"].p99_dl_s, base.p99_dl_s, target
            ),
            "fcfs_p99_dl_s": base.p99_dl_s,
            "sjf_p99_dl_s": target,
        }
        for credit in _credits(cfg)
    ]


def _summaries(cfg, cells: list[dict]) -> list[dict]:
    reference = float(cfg["scheduling"]["aging_baseline"]["reference_promise_s"])
    harm_limit = reference * float(cfg["scheduling"]["selection"]["harm_fraction"])
    rows = []
    for credit in _credits(cfg):
        block = [row for row in cells if row["credit_per_s"] == credit]
        worst_gap = min(float(row["gap_closed"]) for row in block)
        worst_harm = max(float(row["harm_s"]) for row in block)
        rows.append(
            {
                "credit_per_s": credit,
                "worst_gap_closed": worst_gap,
                "worst_harm_s": worst_harm,
                "harm_limit_s": harm_limit,
                "feasible": worst_harm <= harm_limit,
                "n_cells": len(block),
            }
        )
    return rows


def _choose(rows: list[dict]) -> dict:
    feasible = [row for row in rows if row["feasible"]]
    if not feasible:
        raise RuntimeError("no aging credit satisfies the validation harm constraint")
    return max(
        feasible,
        key=lambda row: (
            row["worst_gap_closed"],
            -row["worst_harm_s"],
            row["credit_per_s"],
        ),
    )


def _write_protocol(cfg, summary, chosen, path: Path) -> Path:
    section = cfg["scheduling"]["aging_baseline"]
    document = {
        "label": section["label"],
        "guarantee": section["guarantee"],
        "priority": section["priority"],
        "grid": _credits(cfg),
        "selection_rule": section["selection"],
        "candidate_count": len(summary),
        "feasible_count": sum(bool(row["feasible"]) for row in summary),
        "selected": chosen,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_cells(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    numeric = {"overlay": int, "level": int, "k": int}
    floating = {
        "credit_per_s",
        "p99_dl_s",
        "harm_s",
        "gap_closed",
        "fcfs_p99_dl_s",
        "sjf_p99_dl_s",
    }
    return [
        {
            key: numeric[key](value)
            if key in numeric
            else (float(value) if key in floating else value)
            for key, value in row.items()
        }
        for row in rows
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--pool", default="validation")
    ap.add_argument("--overlay-dir", type=Path, default=None)
    ap.add_argument("--scores", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "selection_aging")
    ap.add_argument("--overlays", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--scratch", type=Path, default=None)
    ap.add_argument("--from-cells", action="store_true")
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    args.overlay_dir = args.overlay_dir or cfg.data_path("overlay_dir")
    args.scores = args.scores or cfg.data_path("score_dir", "forward_scores.parquet")
    score_key = str(
        cfg["scheduling"]["aging_baseline"].get(
            "ranking_score", cfg["scheduling"]["headline_ranking_score"]
        )
    )
    score = None if args.from_cells else _score(args.scores, score_key)
    scratch = args.scratch or Path(tempfile.mkdtemp(prefix="spjf_aging_"))
    started = time.time()
    if args.from_cells:
        cells = _read_cells(args.out_dir / "aging_cells.csv")
        expected = {
            (overlay, level)
            for overlay in (int(value) for value in args.overlays.split(","))
            for level in (int(value) for value in args.levels.split(","))
        }
        present = {(int(row["overlay"]), int(row["level"])) for row in cells}
        if present != expected or {row["credit_per_s"] for row in cells} != set(_credits(cfg)):
            raise SystemExit("aging_cells.csv does not cover the pinned cells and credit grid")
    else:
        assert score is not None
        cells = []
        for overlay in (int(value) for value in args.overlays.split(",")):
            for level in (int(value) for value in args.levels.split(",")):
                cells.extend(_cell(cfg, args, score, overlay, level, scratch))
                print(f"overlay {overlay} level {level}: aging grid complete", flush=True)
    if args.scratch is None:
        shutil.rmtree(scratch, ignore_errors=True)
    summary = _summaries(cfg, cells)
    chosen = _choose(summary)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = [
        write_csv(cells, args.out_dir / "aging_cells.csv"),
        write_csv(summary, args.out_dir / "aging_selection.csv"),
        write_csv([chosen], args.out_dir / "selected_aging.csv"),
        _write_protocol(cfg, summary, chosen, args.out_dir / "aging_protocol.json"),
    ]
    provenance.write(
        args.out_dir,
        produced_by="scripts/select_aging.py",
        config_path=args.config,
        outputs=written,
        inputs=[
            *[
                args.overlay_dir / f"{args.pool}_rep{o}.npz"
                for o in (int(value) for value in args.overlays.split(","))
            ],
            args.scores,
        ],
        arguments={
            "pool": args.pool,
            "overlays": args.overlays,
            "levels": args.levels,
            "score": score_key,
        },
        notes={"guarantee": "none", "selected": chosen},
    )
    pinned = float(cfg["scheduling"]["aging_baseline"]["selected_credit_per_s"])
    status = "matches" if pinned == float(chosen["credit_per_s"]) else "MISMATCH"
    print(
        f"selected credit {chosen['credit_per_s']:.12g}; config {pinned:.12g} ({status}); "
        f"{time.time() - started:.0f} s",
        flush=True,
    )
    return 0 if status == "matches" else 1


if __name__ == "__main__":
    raise SystemExit(main())
