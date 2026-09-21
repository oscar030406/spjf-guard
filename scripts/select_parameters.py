"""Choose the guard's budget shape and parameters on the validation overlays.

    uv run python scripts/select_parameters.py --overlay-dir <dir> \
        [--pool validation] [--overlays 0,1,2,3,4] [--levels 0,1,2] [--workers 3] \
        [--part i --nparts n] [--force] [--from-grid]

Runs the three pre-stated grids (fixed, capped, hybrid) in every (overlay, load level)
cell of the validation trace, applies the rule of ADR 0003, and writes the per-cell grid,
the worst-cell summary, the feasible frontier and the selection: one row per family per
promise (the ablation rows) and one joint winner per promise (the paper's Guard(G)).

A cell is ~250 simulations and takes tens of minutes, so every cell is written the moment
it is measured and a rerun of the identical command skips what is already on disk;
`--part i --nparts n` splits one cell's policies across several runs.  The
development-test term is not in this pool and no sealed term can be.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import grids, parallel, provenance  # noqa: E402
from spjf_guard.experiment import select as sel  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, summarise  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf, spjf  # noqa: E402

SCORE = cfgmod.SCORE_KEY
REFERENCES = ("FCFS", "SJF", "SPJF-E")


def cell_policies(cfg, servers: int):
    """(point, policy) for every distinct schedule of the three grids at this k."""
    points = grids.grid_points(cfg["scheduling"]["selection"]["grids"], cfg.promises_s)
    seen: dict[tuple, str] = {}
    out = []
    for point in points:
        key = grids.schedule_key(point, servers, cfg.limit_s, cfg.promises_s)
        if key in seen:
            out.append((point, None))
            continue
        seen[key] = point.name
        out.append(
            (point, grids.policy_for(point, servers, cfg.limit_s, SCORE, cfg.promises_s))
        )
    return out, seen


def run_cell(cfg, trace, servers, labels, overlay, level, scratch, workers, part, nparts):
    """Every distinct schedule of the grid in one cell, plus the two references.

    Returns the rows of this cell and whether the cell is complete.
    """
    window = int(cfg["run"]["segment_tree_window_ranks"])
    reference = simulate(trace, fcfs(), servers, window=window)
    fcfs_wait = reference.wait_us
    base = summarise(reference, fcfs_wait, labels["in_window"], labels["is_heavy"])
    del reference
    pairs, distinct = cell_policies(cfg, servers)
    simulated = [(p, pol) for p, pol in pairs if pol is not None]
    chunk = [
        (p, pol) for i, (p, pol) in enumerate(simulated) if i % nparts == (part - 1) % nparts
    ]
    cell_dir = parallel.write_cell(
        scratch / f"cell_{overlay}_{level}",
        trace,
        labels,
        fcfs_wait,
        {SCORE: trace.scores[SCORE]},
    )
    tasks = [
        {
            "tag": "SJF",
            "policy": sjf(),
            "servers": servers,
            "window": window,
            "limit_s": cfg.limit_s,
            "assert_bounds": False,
        },
        {
            "tag": "SPJF-E",
            "policy": spjf(SCORE, "SPJF-E"),
            "servers": servers,
            "window": window,
            "limit_s": cfg.limit_s,
            "assert_bounds": False,
        },
    ]
    tasks += [
        {
            "tag": point.name,
            "policy": policy,
            "servers": servers,
            "window": window,
            "limit_s": cfg.limit_s,
            "assert_bounds": bool(cfg["run"]["assert_per_job_bounds"]),
        }
        for point, policy in chunk
    ]
    stats = {
        tag: payload["summary"]
        for tag, payload in parallel.map_policies(
            cell_dir, tasks, cfg.limit_s, (SCORE,), workers
        )
    }
    shutil.rmtree(cell_dir, ignore_errors=True)
    target = stats["SJF"].p99_dl_s
    rows = [
        {
            "overlay": overlay,
            "level": level,
            "k": servers,
            "policy": name,
            "family": "reference",
            "promise_s": -1.0,
            "b0_base_s": -1.0,
            "eta": -1.0,
            "gam_base_s": -1.0,
            "realised_promise_s": float("inf"),
            "p99_dl_s": stats[name].p99_dl_s,
            "harm_s": stats[name].harm_s,
            "gap_closed": gap_closed(stats[name].p99_dl_s, base.p99_dl_s, target),
            "fcfs_p99_dl_s": base.p99_dl_s,
            "sjf_p99_dl_s": target,
        }
        for name in ("SJF", "SPJF-E")
    ]
    for point, _ in chunk:
        summary = stats[point.name]
        rows.append(
            {
                "overlay": overlay,
                "level": level,
                "k": servers,
                "policy": point.name,
                "family": point.family,
                "promise_s": point.promise_s,
                "b0_base_s": point.b0_base_s,
                "eta": point.eta,
                "gam_base_s": point.gam_base_s,
                "realised_promise_s": grids.realised_promise(point, servers, cfg.limit_s),
                "p99_dl_s": summary.p99_dl_s,
                "harm_s": summary.harm_s,
                "gap_closed": gap_closed(summary.p99_dl_s, base.p99_dl_s, target),
                "fcfs_p99_dl_s": base.p99_dl_s,
                "sjf_p99_dl_s": target,
            }
        )
    return rows, len(simulated), len(pairs)


def expand_duplicates(cfg, rows: list[dict]) -> list[sel.Cell]:
    """Give every grid point its measured numbers, including the ones that share a
    schedule with a point already simulated."""
    by_cell: dict[tuple[int, int], dict] = {}
    servers: dict[tuple[int, int], int] = {}
    for row in rows:
        cell = (int(row["overlay"]), int(row["level"]))
        by_cell.setdefault(cell, {})[row["policy"]] = row
        servers[cell] = int(row["k"])
    points = grids.grid_points(cfg["scheduling"]["selection"]["grids"], cfg.promises_s)
    out: list[sel.Cell] = []
    for cell, measured in sorted(by_cell.items()):
        k = servers[cell]
        seen: dict[tuple, str] = {}
        for point in points:
            key = grids.schedule_key(point, k, cfg.limit_s, cfg.promises_s)
            source = seen.setdefault(key, point.name)
            row = measured.get(source)
            if row is None:
                raise KeyError(
                    f"cell {cell} is missing the policy {source!r} that {point.name} "
                    "shares a schedule with; the cell is incomplete"
                )
            out.append(
                sel.Cell(
                    overlay=cell[0],
                    level=cell[1],
                    family=point.family,
                    promise_s=point.promise_s,
                    b0_base_s=point.b0_base_s,
                    eta=point.eta,
                    gam_base_s=point.gam_base_s,
                    gap_closed=float(row["gap_closed"]),
                    harm_s=float(row["harm_s"]),
                    realised_promise_s=grids.realised_promise(point, k, cfg.limit_s),
                )
            )
    return out


def write(rows, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_protocol(cfg, chosen, grid_rows, path: Path) -> Path:
    """The exact expanded grids and every count behind the selection table."""
    points = grids.grid_points(cfg["scheduling"]["selection"]["grids"], cfg.promises_s)
    servers = sorted({int(row["k"]) for row in grid_rows})
    schedules = {}
    for k in servers:
        pairs, distinct = cell_policies(cfg, k)
        schedules[str(k)] = {
            "expanded_points": len(pairs),
            "distinct_schedules": len(distinct),
        }
    document = {
        "definition": cfg["scheduling"]["selection"]["grids"],
        "expanded_points": [
            {
                "name": point.name,
                "family": point.family,
                "promise_s": point.promise_s,
                "b0_base_s": point.b0_base_s,
                "eta": point.eta,
                "gam_base_s": point.gam_base_s,
            }
            for point in points
        ],
        "counts": [
            {
                "family": item.family,
                "promise_s": item.promise_s,
                "n_candidates": item.n_candidates,
                "n_feasible": item.n_feasible,
            }
            for item in chosen
        ],
        "per_server_count": schedules,
        "explanation": (
            "Expanded points include schedules shared across promises. Candidate counts "
            "apply the realised-promise filter at each G; distinct schedules deduplicate "
            "points that dispatch identically at one server count."
        ),
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_cells(paths) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def measure(cfg, args, out_dir: Path, scratch: Path) -> list[Path]:
    """Every requested cell, one file each, skipping the ones already on disk."""
    cell_dir = out_dir / "cells"
    cell_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for overlay in (int(x) for x in args.overlays.split(",")):
        path = args.overlay_dir / f"{args.pool}_rep{overlay}.npz"
        for level in (int(x) for x in args.levels.split(",")):
            target = cell_dir / f"grid_o{overlay}_l{level}.csv"
            if target.is_file() and not args.force:
                print(f"overlay {overlay} level {level}: already measured, kept", flush=True)
                written.append(target)
                continue
            started = time.time()
            trace, servers, labels = load_overlay(
                path, level, {args.score_array: SCORE}, cfg.limit_s
            )
            if args.external_score is not None:
                from spjf_guard.sim import Trace

                with np.load(path) as store:
                    rows = store["job_row"].astype(np.int64)
                trace = Trace(
                    trace.arrival_us,
                    trace.service_us,
                    {SCORE: args.external_score[rows]},
                    trace.limit_s,
                )
            rows, n_distinct, n_points = run_cell(
                cfg,
                trace,
                servers,
                labels,
                overlay,
                level,
                scratch,
                args.workers,
                args.part,
                args.nparts,
            )
            if args.nparts > 1:
                target = cell_dir / f"grid_o{overlay}_l{level}_part{args.part}.csv"
            written.append(write(rows, target))
            print(
                f"overlay {overlay} level {level}: k = {servers}, {n_points} points -> "
                f"{n_distinct} distinct schedules, {len(rows)} rows this part, "
                f"{time.time() - started:.0f} s",
                flush=True,
            )
            del trace, labels
    return written


def selection_rows(chosen, cells, harm_fraction) -> list[dict]:
    return [
        {
            "family": c.family,
            "from_family": c.from_family,
            "promise_s": c.promise_s,
            "b0_base_s": c.b0_base_s,
            "eta": c.eta,
            "gam_base_s": c.gam_base_s,
            "worst_gap_closed": c.worst_gap_closed,
            "worst_harm_s": c.worst_harm_s,
            "worst_promise_s": c.worst_promise_s,
            "harm_limit_s": c.harm_limit_s,
            "harm_slack_s": c.harm_limit_s - c.worst_harm_s,
            "n_feasible": c.n_feasible,
            "n_candidates": c.n_candidates,
            "next_better_point": sel.next_better_point(cells, c, harm_fraction),
            "note": c.note,
        }
        for c in chosen
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--overlay-dir", type=Path, default=None)
    ap.add_argument("--pool", default="validation")
    ap.add_argument("--overlays", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--score-array", default="tweedie")
    ap.add_argument(
        "--score-parquet",
        type=Path,
        default=None,
        help="attach one regenerated score column by job_row instead of a stored array",
    )
    ap.add_argument("--score-column", default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--scratch", type=Path, default=None)
    ap.add_argument("--part", type=int, default=1)
    ap.add_argument("--nparts", type=int, default=1)
    ap.add_argument("--force", action="store_true", help="measure every cell again")
    ap.add_argument(
        "--from-grid", action="store_true", help="apply the rule to the cell files on disk"
    )
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    args.external_score = None
    if args.score_parquet is not None:
        import pandas as pd

        column = args.score_column or str(cfg["scheduling"]["ranking_score"])
        args.external_score = pd.read_parquet(args.score_parquet, columns=[column])[
            column
        ].to_numpy("float64")
    out_dir = args.out_dir or (ROOT / cfg["run"]["output_dir"] / "selection")
    harm_fraction = float(cfg["scheduling"]["selection"]["harm_fraction"])
    scratch = args.scratch or Path(tempfile.mkdtemp(prefix="spjf_select_"))
    if args.from_grid:
        cell_files = sorted((out_dir / "cells").glob("grid_o*_l*.csv"))
        if not cell_files:
            ap.error(f"--from-grid was given but {out_dir / 'cells'} holds no cell file")
    else:
        if args.overlay_dir is None:
            args.overlay_dir = cfg.data_path("overlay_dir")
        cell_files = measure(cfg, args, out_dir, scratch)
    if args.scratch is None:
        shutil.rmtree(scratch, ignore_errors=True)
    if args.nparts > 1:
        print("parts are incomplete on their own; rerun with --from-grid to apply the rule")
        return 0

    grid_rows = read_cells(cell_files)
    cells = expand_duplicates(cfg, grid_rows)
    written = [write(grid_rows, out_dir / "selection_grid.csv")]
    written.append(
        write(
            [
                {
                    "family": k[0],
                    "promise_s": k[1],
                    "b0_base_s": k[2],
                    "eta": k[3],
                    "gam_base_s": k[4],
                    **v,
                }
                for k, v in sorted(sel.summarise(cells, harm_fraction).items(), key=str)
            ],
            out_dir / "selection_worst.csv",
        )
    )
    written.append(
        write(sel.frontier(cells, harm_fraction), out_dir / "selection_frontier.csv")
    )
    chosen = sel.choose(cells, harm_fraction)
    written.append(
        write(selection_rows(chosen, cells, harm_fraction), out_dir / "selected_parameters.csv")
    )
    written.append(write_protocol(cfg, chosen, grid_rows, out_dir / "selection_protocol.json"))
    provenance.write(
        out_dir,
        produced_by="scripts/select_parameters.py",
        config_path=args.config,
        outputs=written,
        inputs=(
            ([args.score_parquet] if args.score_parquet is not None else [])
            + (
                []
                if args.overlay_dir is None
                else [
                    args.overlay_dir / f"{args.pool}_rep{o}.npz"
                    for o in (int(x) for x in args.overlays.split(","))
                ]
            )
        ),
        arguments={
            "pool": args.pool,
            "overlays": args.overlays,
            "levels": args.levels,
            "score_array": args.score_array,
            "score_parquet": (
                provenance.relative_path(args.score_parquet)
                if args.score_parquet is not None
                else None
            ),
            "score_column": args.score_column,
        },
        notes={
            "harm_fraction": harm_fraction,
            "n_cells": len({(c.overlay, c.level) for c in cells}),
            "n_points": len({c.key for c in cells}),
        },
    )
    print(
        f"\ncells: {len({(c.overlay, c.level) for c in cells})}, "
        f"grid points: {len({c.key for c in cells})}"
    )
    for c in chosen:
        print(
            f"  [{c.family:7s}] G = {c.promise_s:6.0f}: B0 = {c.b0_base_s:g} k/4 s, "
            f"eta = {c.eta:g}, gam = {c.gam_base_s:g} k/4 s"
            + (f" (from {c.from_family})" if c.family == sel.JOINT else "")
            + f"; worst-cell gap {c.worst_gap_closed:.4f}, worst-cell harm "
            f"{c.worst_harm_s:.2f} s of {c.harm_limit_s:.0f} s "
            f"({c.n_feasible}/{c.n_candidates} feasible) {c.note}"
        )
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
