"""The k = 2 and k = 3 traces: 3 busy-hour loads x 5 repetitions on the primary pool.

    python build_traces.py [--ks 2,3] [--reps 0,1,2,3,4] [--listings N] [--skip-gate]

The pipeline of evidence/latency_steady_online/g18b/build_k1_grid.py, which built the
k = 1 grid this experiment reads: prepare_everything on the pool of overlay.single_server,
single_server_pool, then build_overlay with the selected copies at a fixed server count.
Two changes for k servers, both stated in REPORT.md section 2:

  load     single_server_pool compares the busiest-hour work / 3600 s with its target, so
           the target and the window are multiplied by k: per-server load 0.50, 0.80, 0.95,
           window half-width 0.02 per server.
  listing  the pool is listed 16k times instead of 8, so the random phase reaches the
           target by itself.  This is asserted for every trace.

`--listings N` lists the pool N times for every k given, and names the files
k<k>L<N>u<load>_rep<rep>.npz so they never collide with the default ones.  It exists for
the k = 1 sensitivity traces built like k = 2, 3 (`--ks 1 --listings 16`, REPORT.md 6).

Seeds are overlay.seed * 100 + single_server.seed_offset + rep, as for k = 1.

Gate, before anything is written: the same code at k = 1 with 8 listings rebuilds the 15
G18 B traces, and each must equal its file in outputs/steady_online_g18b/overlays on all 13
trace arrays; k1u80_rep0 must also equal data/derived/overlay_traces/k1_rep0.npz.

Files are k<k>u<load>_rep<rep>.npz in outputs/revision_r1/small_k_shapes/overlays, without
stored scores (run_cells.py attaches them by job_row).  An existing file is kept.
"""

import common

import argparse
import csv
import time

import numpy as np
from build_overlays import pool_terms, prepare_everything
from spjf_guard import config as cfgmod
from spjf_guard.experiment.overlay import (
    REFERENCE_MONDAY_S,
    WEEK_S,
    _k1_candidates,
    _SingleServerState,
    build_overlay,
    single_server_pool,
    superpose,
)

HALF_WIDTH = 0.02
TRACE_ARRAYS = ("a", "svc", "dl", "exam", "hvt", "wk", "weeks", "K", "W", "copies", "job_row",
                "copy_entry", "copy_round")


def listings(k: int) -> int:
    return 8 if k == 1 else 16 * k


def random_phase_reaches(inputs, seed: int, target: float, window, repeats: int) -> bool:
    """Phase 1 of single_server_pool, replayed: does it reach the target on its own?"""
    state = _SingleServerState(inputs.per_term, "arr")
    for term, weeks in _k1_candidates(inputs.pool, seed, repeats):
        peak = state.peak_after(term, weeks)
        if peak / 3600.0 > window[1]:
            continue
        state.add(term, weeks, peak)
        if state.utilisation >= target:
            return True
    return False


def trace_for(cfg, inputs, k: int, load: float, rep: int, listed: int):
    section = cfg["overlay"]["single_server"]
    seed = int(cfg["overlay"]["seed"]) * 100 + int(section["seed_offset"]) + rep
    target, window = k * load, (k * (load - HALF_WIDTH), k * (load + HALF_WIDTH))
    entries, rho = single_server_pool(
        inputs.pool, inputs.per_term, "arr", seed, target, window, listed
    )
    arrival, _, _, _ = superpose(entries, inputs.per_term, "arr")
    weeks = np.array(sorted(set(np.unique(
        np.floor((arrival - REFERENCE_MONDAY_S) / WEEK_S).astype(np.int64)).tolist())), np.int64)
    del arrival
    arrays = build_overlay(inputs, inputs.pool, len(entries), 0, seed, weeks,
                           cfg["overlay"]["target_busy_hour_utilisation"],
                           entries=entries, servers=[k])
    info = {"k": k, "load": load, "rep": rep, "seed": seed, "listings": listed,
            "copies": len(entries), "rho_per_server": rho / k, "jobs": len(arrays["a"]),
            "weeks": len(weeks)}
    return arrays, info, (seed, target, window)


def equal_arrays(arrays: dict, path) -> list[str]:
    with np.load(path) as ref:
        return [n for n in TRACE_ARRAYS if not np.array_equal(arrays[n], ref[n])]


def gate_k1(cfg, inputs) -> None:
    for stem, load in common.LOADS.items():
        for rep in common.REPS:
            arrays, info, _ = trace_for(cfg, inputs, 1, load, rep, listings(1))
            name = f"k1{stem}_rep{rep}.npz"
            unequal = equal_arrays(arrays, common.K1_DIR / name)
            if stem == "u80" and rep == 0:
                unequal += [f"k1_rep0:{n}" for n in equal_arrays(
                    arrays, cfg.data_path("overlay_dir") / "k1_rep0.npz")]
            print(f"gate k = 1 {name}: {info['copies']} copies, {info['jobs']:,} jobs: "
                  f"{'all 13 arrays equal' if not unequal else f'DIFFERENT {unequal}'}",
                  flush=True)
            if unequal:
                raise AssertionError(f"{name} differs in {unequal}")
            del arrays


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ks", default="2,3")
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--listings", type=int, default=None)
    ap.add_argument("--skip-gate", action="store_true")
    args = ap.parse_args()
    cfg = cfgmod.load(common.ROOT / "configs" / "main.yaml")
    started = time.time()
    _, inputs = prepare_everything(cfg, pool_terms(cfg, cfg["overlay"]["single_server"]["pool"]),
                                   False)
    print(f"pool: {len(inputs.pool)} class-terms, {inputs.info} ({time.time() - started:.0f} s)",
          flush=True)
    if not args.skip_gate:
        gate_k1(cfg, inputs)
    common.OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    log = common.OVERLAY_DIR / "build_log.csv"
    for k in (int(x) for x in args.ks.split(",")):
        for stem, load in common.LOADS.items():
            for rep in (int(x) for x in args.reps.split(",")):
                listed = listings(k) if args.listings is None else args.listings
                tag = "" if args.listings is None else f"L{args.listings}"
                path = common.OVERLAY_DIR / f"k{k}{tag}{stem}_rep{rep}.npz"
                if path.exists():
                    print(f"{path.name}: exists, kept", flush=True)
                    continue
                t0 = time.time()
                arrays, info, (seed, target, window) = trace_for(cfg, inputs, k, load, rep, listed)
                if not random_phase_reaches(inputs, seed, target, window, listed):
                    raise AssertionError(f"{path.name}: the random phase did not reach "
                                         f"{target} with {listed} listings")
                partial = path.with_name(path.stem + ".part.npz")
                np.savez(partial, **arrays)
                partial.replace(path)
                info["seconds"] = round(time.time() - t0, 1)
                new = not log.exists()
                with open(log, "a", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=list(info))
                    if new:
                        writer.writeheader()
                    writer.writerow(info)
                print(f"{path.name}: {info}", flush=True)
                del arrays
    print(f"peak commit {common.peak_commit_gb():.2f} GB, {time.time() - started:.0f} s",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
