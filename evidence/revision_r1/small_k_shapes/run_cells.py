"""Run the shape ablation policies on one stored trace, one cell per load level.

    python run_cells.py --trace <npz> --overlay <rep> --out-dir <dir> [--levels 0]
        [--policies FCFS,SJF,...] [--workers 1] [--no-bootstrap]

A thin wrapper around scripts/run_main.py: the same overlay loading, score attachment by
job_row, `run_cell` (FCFS reference, per-job bound assertion, summary) and `cell_rows`.
Two things differ.  The policy set is FCFS, SJF, SPJF-E and, per promise G, the three
family winners of the selection, Fixed(G), and the pre-registered no-grid default
Guard-default(G) = constant budget B_max/2 (REPORT.md section 1).  And nothing is written
to the sealed ledger: this reads development pools only, as run_main's development runs do.

Per cell it writes, under --out-dir, <stem>_l<level>.csv (the run_main main_cells columns),
<stem>_l<level>_bounds.csv, <stem>_l<level>_params.csv, <stem>_l<level>_replicates.npz and
<stem>_l<level>_cost.json.  A cell whose .csv exists is skipped, so a rerun resumes.
"""

import common  # noqa: F401  (thread caps, priority and job object before numpy)

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import run_main
from spjf_guard import config as cfgmod
from spjf_guard.experiment import bootstrap as bs
from spjf_guard.experiment.report import write_csv
from spjf_guard.experiment.reproduce import load_overlay
from spjf_guard.sim.policy import bmax_for_promise, fixed

SHAPES = ("Guard-fixed(", "Guard-age(", "Guard-queue(", "Fixed(")
UNGUARDED = ("FCFS", "SJF", "SPJF-E")


def default_policy(cfg, promise: float, servers: int):
    """The no-grid default: constant budget B0 = B_max / 2, written down before any run."""
    bmax = bmax_for_promise(promise, servers, cfg.limit_s)
    return fixed(
        promise,
        servers,
        cfg.limit_s,
        cfg["scheduling"]["ranking_score"],
        b0_s=bmax / 2.0,
        name=f"Guard-default({promise:g})",
    )


def install_policy_set(cfg, keep: set | None) -> None:
    """Replace cfg.policies on this instance, so run_cell and parameter_rows both see it."""
    original = cfgmod.Config.policies

    def policies(servers, include_log_control=False, selection=None, include_family_bests=True):
        out = []
        for p in original(cfg, servers, False, selection):
            if p.name in UNGUARDED or p.name.startswith(SHAPES):
                out.append(p)
            if p.name.startswith("Fixed("):
                promise = float(p.name[len("Fixed(") : -1])
                out.append(default_policy(cfg, promise, servers))
        return [p for p in out if keep is None or p.name in keep]

    object.__setattr__(cfg, "policies", policies)


def run_one(cfg, args, selection, external, level: int) -> None:
    stem = f"{args.trace.stem}_l{level}"
    target = args.out_dir / f"{stem}.csv"
    if target.exists():
        print(f"{stem}: done already, skipped", flush=True)
        return
    started = time.time()
    trace, servers, labels = load_overlay(args.trace, level, {}, cfg.limit_s)
    with np.load(args.trace) as store:
        labels["week"] = store["wk"].astype(np.int64)
        n_weeks = len(store["weeks"])
        work_s = float(store["W"])
        rho_target = run_main.level_utilisation(cfg, level, servers, work_s, len(store["K"]))
        trace = run_main.attach_scores(trace, external, store["job_row"])
    multiplicities = None
    if not args.no_bootstrap:
        multiplicities = bs.with_point_estimate(
            bs.week_multiplicities(
                n_weeks, int(cfg["bootstrap"]["resamples"]), int(cfg["bootstrap"]["seed"])
            )
        )
    scratch = Path(tempfile.mkdtemp(prefix="small_k_shapes_"))
    results = run_main.run_cell(
        cfg, trace, servers, labels, args.overlay, level, scratch, args.workers,
        multiplicities, selection, False,
    )
    shutil.rmtree(scratch, ignore_errors=True)
    rows = run_main.cell_rows(cfg, results, args.overlay, level, servers, rho_target, work_s)
    bounds = [
        {"overlay": args.overlay, "level": level, "k": servers, "policy": tag, **p["bound"]}
        for tag, p in results.items()
        if "bound" in p
    ]
    params = run_main.parameter_rows(cfg, selection, args.overlay, level, servers)
    write_csv(bounds, args.out_dir / f"{stem}_bounds.csv")
    write_csv(params, args.out_dir / f"{stem}_params.csv")
    if multiplicities is not None:
        np.savez(
            args.out_dir / f"{stem}_replicates.npz",
            **{
                f"{tag}|{stat}": p["replicates"][stat]
                for tag, p in results.items()
                for stat in ("p99_dl", "mean")
            },
        )
    cost = {
        "trace": str(args.trace),
        "level": level,
        "k": servers,
        "jobs": int(len(trace.arrival_us)),
        "policies": len(results),
        "workers": args.workers,
        "bootstrap": multiplicities is not None,
        "wall_s": round(time.time() - started, 1),
        "peak_commit_gb_so_far": round(common.peak_commit_gb(), 2),
    }
    (args.out_dir / f"{stem}_cost.json").write_text(json.dumps(cost, indent=1), encoding="utf-8")
    partial = target.with_suffix(".csv.part")
    write_csv(rows, partial)
    partial.replace(target)
    violations = sum(b["violations"] for b in bounds)
    print(
        f"{stem}: k = {servers}, {cost['jobs']:,} jobs, {len(results)} policies, "
        f"bound violations {violations}, {cost['wall_s']} s, peak commit "
        f"{cost['peak_commit_gb_so_far']} GB",
        flush=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--overlay", type=int, required=True, help="the rep index, for the rows")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--levels", default="0")
    ap.add_argument("--policies", default=None, help="comma list; default: the full set")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--no-bootstrap", action="store_true")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cfg = cfgmod.load(common.CONFIG)
    selection = run_main.read_selection(common.SELECTION)
    if not selection:
        raise SystemExit(f"no selection at {common.SELECTION}")
    keep = None if args.policies is None else set(args.policies.split(","))
    install_policy_set(cfg, keep)
    score_key = cfg["scheduling"]["ranking_score"]
    external = {score_key: run_main.read_external_scores(common.SCORES)[score_key]}
    print(f"{args.trace.name}: scores {score_key} by job_row from {common.SCORES.name}; "
          f"selection {common.SELECTION.relative_to(common.ROOT)}", flush=True)
    for level in (int(x) for x in args.levels.split(",")):
        run_one(cfg, args, selection, external, level)
    print(f"peak commit of this process and its workers: {common.peak_commit_gb():.2f} GB",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
