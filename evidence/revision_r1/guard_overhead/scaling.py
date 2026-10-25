"""Part 2: cost of the guard's three operations against the number n of waiting jobs.

    python scaling.py [--exps 2,3,4,5,6] [--geometries queue,production]
                      [--min-seconds 1.0] [--repeats 5] [--out scaling.json]

The loops below call the production kernel's own data-structure functions
(src/spjf_guard/sim/kernel.py) inside @njit drivers, so no Python call sits inside a
timed operation.  The state is n waiting jobs, ranks base .. base+n-1, in one of two
geometries:

    queue       Fenwick tree over the n ranks, segment-tree window = next power of 2 >= n
                (structures sized to the queue: the O(log n) of the paper)
    production  Fenwick tree over all N = 17,634,760 ranks of overlay 0 with the n live
                ranks in the middle, segment-tree window 2^22 (what simulate_kernel
                allocates for the main table: depth log W + log N whatever the queue)

Positions are drawn by an in-loop xorshift generator; the loop "rng" times it alone and
is subtracted in the derived numbers.

    arrival     _fen_pref(rank) + _st_set(leaf)              (kernel: _admit_arrivals)
    completion  _fen_add(rank) + _st_add_suffix(leaf)        (kernel: _apply_completions)
    query       _fen_pref(head) + _st_leftmost(threshold)    (kernel: _fired_member)
    remove      _st_set(leaf, NEG)                           (kernel: _choose)
    dispatch    = query + remove                              (derived)
    heap        _score_pop + _score_push over n entries      (the base SPJF order, context)

Leaf values increase with the position, so a threshold equal to a random leaf's value
sends _st_leftmost down a uniformly random root-to-leaf path (its full-depth branch,
never the early exit).  The iteration count is set so the slowest loop (completion) runs
about --min-seconds; the faster loops run proportionally shorter.  Results are per
operation.  Wall time is the primary number: thread CPU time on Windows ticks in 15.6 ms
steps, which is coarse for the shorter loops.
"""

from __future__ import annotations

import argparse
import statistics
import time

import common
import numpy as np
from numba import njit

from spjf_guard.sim.kernel import (
    NEG,
    _fen_add,
    _fen_pref,
    _score_pop,
    _score_push,
    _st_add_suffix,
    _st_clear,
    _st_leftmost,
    _st_set,
)

ED = 4  # eta denominator of the selected guards (eta = 0.5 / 0.75 -> ed in {2, 4})
STEP = 64_000_000  # spacing of leaf values; exceeds ED times any single charge below
PRODUCTION_N = 17_634_760  # jobs in overlay 0
PRODUCTION_WINDOW = 1 << 22  # configs/main_frozen_1289aa2.yaml run.segment_tree_window_ranks
OPS = ("rng", "arrival", "completion", "query", "remove", "heap")


@njit(cache=True, inline="always")
def _rand(x):
    x ^= x << np.uint64(13)
    x ^= x >> np.uint64(7)
    x ^= x << np.uint64(17)
    return x


@njit(cache=True, inline="always")
def _below(x, n):
    return np.int64((x >> np.uint64(32)) * np.uint64(n) >> np.uint64(32))


@njit(cache=True)
def build(n, size, fen_n, base, seed):
    """Random completed work (< 2^20 us) on every rank, built in O(fen_n); leaf p of the
    window holds STEP * p, so the leftmost leaf >= STEP * t is leaf t."""
    fen = np.zeros(fen_n + 1, np.int64)
    x = np.uint64(seed)
    for i in range(1, fen_n + 1):
        x = _rand(x)
        fen[i] += np.int64(x >> np.uint64(44))
        j = i + (i & -i)
        if j <= fen_n:
            fen[j] += fen[i]
    tre = np.empty(2 * size, np.int64)
    lz = np.empty(size, np.int64)
    _st_clear(tre, lz, size)
    for p in range(n):
        _st_set(tre, lz, size, p, STEP * p)
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    m = 0
    for p in range(n):
        x = _rand(x)
        m = _score_push(hk, hi, m, np.float64(x >> np.uint64(11)), base + p)
    return fen, tre, lz, hk, hi, m


@njit(cache=True)
def loop_rng(n, iters, seed):
    x = np.uint64(seed)
    acc = np.int64(0)
    for _ in range(iters):
        x = _rand(x)
        acc += _below(x, n)
    return acc


@njit(cache=True)
def loop_arrival(fen, tre, lz, n, size, fen_n, base, iters, seed):
    x = np.uint64(seed)
    acc = np.int64(0)
    for _ in range(iters):
        x = _rand(x)
        p = _below(x, n)
        f = _fen_pref(fen, base + p)
        _st_set(tre, lz, size, p, STEP * p - ED * f)
        acc += f
    return acc


@njit(cache=True)
def loop_completion(fen, tre, lz, n, size, fen_n, base, iters, seed):
    x = np.uint64(seed)
    acc = np.int64(0)
    for _ in range(iters):
        x = _rand(x)
        p = _below(x, n)
        w = np.int64(x & np.uint64(0xFFFFF))
        _fen_add(fen, fen_n, base + p, w)
        _st_add_suffix(tre, lz, size, p, -ED * w)
        acc += w
    return acc


@njit(cache=True)
def loop_query(fen, tre, lz, n, size, fen_n, base, iters, seed):
    """Firing test: the cap check at a random head and a threshold on a random leaf."""
    x = np.uint64(seed)
    acc = np.int64(0)
    total = _fen_pref(fen, fen_n - 1)
    for _ in range(iters):
        x = _rand(x)
        over = total - _fen_pref(fen, base + _below(x, n))
        pos = _st_leftmost(tre, lz, size, STEP * _below(_rand(x), n))
        acc += pos + (over & 1)
    return acc


@njit(cache=True)
def loop_remove(tre, lz, n, size, iters, seed):
    x = np.uint64(seed)
    for _ in range(iters):
        x = _rand(x)
        _st_set(tre, lz, size, _below(x, n), NEG)
    return tre[1]


@njit(cache=True)
def loop_heap(hk, hi, m, base, iters, seed):
    x = np.uint64(seed)
    acc = np.int64(0)
    for _ in range(iters):
        acc += hi[0]
        m = _score_pop(hk, hi, m)
        x = _rand(x)
        m = _score_push(hk, hi, m, np.float64(x >> np.uint64(11)), base + _below(x, m + 1))
    return acc


def geometry(name, n):
    """(window size, Fenwick length, first live rank)."""
    if name == "queue":
        size = 1
        while size < n:
            size *= 2
        return size, n, 0
    return PRODUCTION_WINDOW, PRODUCTION_N, PRODUCTION_N // 2


def run_op(op, n, geo, iters, seed):
    """Fresh state, then one timed loop; returns (wall_ns, cpu_ns) for the loop."""
    size, fen_n, base = geo
    fen, tre, lz, hk, hi, m = build(n, size, fen_n, base, 12345)
    fns = {
        "rng": lambda: loop_rng(n, iters, seed),
        "arrival": lambda: loop_arrival(fen, tre, lz, n, size, fen_n, base, iters, seed),
        "completion": lambda: loop_completion(fen, tre, lz, n, size, fen_n, base, iters, seed),
        "query": lambda: loop_query(fen, tre, lz, n, size, fen_n, base, iters, seed),
        "remove": lambda: loop_remove(tre, lz, n, size, iters, seed),
        "heap": lambda: loop_heap(hk, hi, m, base, iters, seed),
    }
    c0, w0 = time.thread_time_ns(), time.perf_counter_ns()
    fns[op]()
    return time.perf_counter_ns() - w0, time.thread_time_ns() - c0


def measure(exps, geometries, min_seconds, repeats, log=print):
    for op in OPS:  # compile every driver once on a tiny state
        run_op(op, 64, (64, 64, 0), 1000, 7)
    rows = []
    for name in geometries:
        for e in exps:
            n = 10**e
            geo = geometry(name, n)
            iters = 100_000
            while True:  # calibrate on the slowest loop
                wall, _ = run_op("completion", n, geo, iters, 99)
                if wall >= 0.25e9 * min_seconds:
                    break
                iters *= 4
            iters = int(iters * max(1.0, min_seconds * 1e9 / wall))
            for op in OPS:
                walls, cpus = [], []
                for r in range(repeats):
                    wall, cpu = run_op(op, n, geo, iters, 1000 + r)
                    walls.append(wall / iters)
                    cpus.append(cpu / iters)
                row = {"geometry": name, "n": n, "log2_window": geo[0].bit_length() - 1,
                       "fenwick_n": geo[1], "op": op, "iters": iters, "repeats": repeats,
                       "wall_ns_median": statistics.median(walls), "wall_ns_min": min(walls),
                       "wall_ns_max": max(walls), "cpu_ns_median": statistics.median(cpus),
                       "cpu_ns_min": min(cpus), "cpu_ns_max": max(cpus)}
                rows.append(row)
                log(f"{name:10s} n=10^{e} {op:10s} {row['wall_ns_median']:8.1f} ns wall "
                    f"[{row['wall_ns_min']:.1f}, {row['wall_ns_max']:.1f}]  "
                    f"{row['cpu_ns_median']:8.1f} ns cpu  ({iters:,} iters x {repeats})")
    return {"rows": rows, "derived": derive(rows)}


def derive(rows):
    """Per (geometry, n): dispatch = query + remove; guard per job = arrival + completion
    + dispatch (each job has one of each); rng loop subtracted from every operation."""
    by = {(r["geometry"], r["n"], r["op"]): r["wall_ns_median"] for r in rows}
    out = []
    for geo, n in sorted({(r["geometry"], r["n"]) for r in rows}):
        rng = by[(geo, n, "rng")]
        net = {op: by[(geo, n, op)] - rng for op in OPS if op != "rng"}
        net["dispatch"] = net["query"] + net["remove"]
        net["guard_per_job"] = net["arrival"] + net["completion"] + net["dispatch"]
        out.append({"geometry": geo, "n": n, "rng_ns": rng,
                    **{f"{k}_ns": v for k, v in net.items()}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exps", default="2,3,4,5,6")
    ap.add_argument("--geometries", default="queue,production")
    ap.add_argument("--min-seconds", type=float, default=1.0)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default="scaling.json")
    a = ap.parse_args()
    t0 = time.time()
    result = measure([int(x) for x in a.exps.split(",")], a.geometries.split(","),
                     a.min_seconds, a.repeats)
    result["machine"] = common.machine_info()
    result["elapsed_s"] = round(time.time() - t0, 1)
    common.write_json(common.OUT / a.out, result)
    for d in result["derived"]:
        print(f"{d['geometry']:10s} n={d['n']:>9,}: arrival {d['arrival_ns']:6.1f}  "
              f"completion {d['completion_ns']:6.1f}  dispatch {d['dispatch_ns']:6.1f}  "
              f"guard/job {d['guard_per_job_ns']:6.1f}  heap {d['heap_ns']:6.1f} ns")
    print(f"elapsed {result['elapsed_s']} s -> {common.OUT / a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
