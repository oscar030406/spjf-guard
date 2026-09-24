"""Referee round 4: two production-style starvation controls the manuscript names but does not run.

MaxWait(T): at every dispatch epoch serve the oldest waiting job if it has waited at
least T seconds, otherwise the waiting job with the smallest SPJF-E score (ties to the
smaller rank).  This is the "maximum waiting time" rule Section 2 of the manuscript says
production systems use without proofs.  It carries no per-job guarantee against FCFS.

Block(W): ranks are cut into consecutive blocks of W jobs; a job may be served only if
no waiting job belongs to an earlier block, and inside the eligible block the smallest
score goes first.  A rank-block stand-in for fixed-window ordering by predicted cost.

Both run in an independent numba kernel written here.  Before any new number is
reported, the kernel is run as FCFS (T = 0) and as SPJF-E (T = infinity) and its waits
are compared job by job with the package kernel, which must agree exactly.

Development overlay 0 only (data/derived/overlay_traces/primary_rep0.npz), original
archived Tweedie score, the three load levels.  Nothing is written outside this folder.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
      OMP_NUM_THREADS=4 uv run --no-sync python evidence/referee_round4/maxwait_baseline.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard.experiment.metrics import STARTS_IMMEDIATELY_S  # noqa: E402
from spjf_guard.experiment.reproduce import SCORE_KEY, load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf, spjf  # noqa: E402

OVERLAY = ROOT / "data" / "derived" / "overlay_traces" / "primary_rep0.npz"
LEVELS = (0, 1, 2)
MAXWAIT_T_S = (30, 60, 120, 300, 600, 1200, 2400)
BLOCK_W = (8, 32, 128, 512)
NEVER = 1 << 62
MICROS = 1_000_000


@njit(cache=False)
def _less(key_block, score, i, j):
    if key_block[i] != key_block[j]:
        return key_block[i] < key_block[j]
    if score[i] != score[j]:
        return score[i] < score[j]
    return i < j


@njit(cache=False)
def _push(heap, hn, x, key_block, score):
    heap[hn] = x
    c = hn
    while c > 0:
        p = (c - 1) // 2
        if _less(key_block, score, heap[c], heap[p]):
            heap[c], heap[p] = heap[p], heap[c]
            c = p
        else:
            break
    return hn + 1


@njit(cache=False)
def _pop(heap, hn, key_block, score):
    hn -= 1
    heap[0] = heap[hn]
    c = 0
    while True:
        l = 2 * c + 1
        r = l + 1
        m = c
        if l < hn and _less(key_block, score, heap[l], heap[m]):
            m = l
        if r < hn and _less(key_block, score, heap[r], heap[m]):
            m = r
        if m == c:
            break
        heap[c], heap[m] = heap[m], heap[c]
        c = m
    return hn


@njit(cache=False)
def _cpush(comp, cn, x):
    comp[cn] = x
    c = cn
    while c > 0:
        p = (c - 1) // 2
        if comp[c] < comp[p]:
            comp[c], comp[p] = comp[p], comp[c]
            c = p
        else:
            break
    return cn + 1


@njit(cache=False)
def _cpop(comp, cn):
    cn -= 1
    comp[0] = comp[cn]
    c = 0
    while True:
        l = 2 * c + 1
        r = l + 1
        m = c
        if l < cn and comp[l] < comp[m]:
            m = l
        if r < cn and comp[r] < comp[m]:
            m = r
        if m == c:
            break
        comp[c], comp[m] = comp[m], comp[c]
        c = m
    return cn


@njit(cache=False)
def simulate_rule(a, svc, score, key_block, k, t_max_wait):
    """Completions, then arrivals, then dispatches at each instant; int64 microseconds.

    The waiting job served is the oldest one when it has waited at least t_max_wait,
    and otherwise the minimum of (key_block, score, rank).  Returns start times and the
    number of dispatches the timer decided.
    """
    n = a.shape[0]
    start = np.full(n, -1, np.int64)
    dispatched = np.zeros(n, np.bool_)
    heap = np.empty(n, np.int64)
    hn = 0
    comp = np.empty(k, np.int64)
    cn = 0
    free = k
    nxt = 0
    head = 0
    nwait = 0
    ndisp = 0
    ntimer = 0
    while ndisp < n:
        t_arr = a[nxt] if nxt < n else NEVER
        t_cmp = comp[0] if cn > 0 else NEVER
        t = t_arr if t_arr < t_cmp else t_cmp
        while cn > 0 and comp[0] == t:
            cn = _cpop(comp, cn)
            free += 1
        while nxt < n and a[nxt] == t:
            hn = _push(heap, hn, nxt, key_block, score)
            nwait += 1
            nxt += 1
        while free > 0 and nwait > 0:
            while dispatched[head]:
                head += 1
            if t - a[head] >= t_max_wait:
                j = head
                ntimer += 1
            else:
                while dispatched[heap[0]]:
                    hn = _pop(heap, hn, key_block, score)
                j = heap[0]
                hn = _pop(heap, hn, key_block, score)
            dispatched[j] = True
            start[j] = t
            nwait -= 1
            free -= 1
            ndisp += 1
            cn = _cpush(comp, cn, t + svc[j])
    return start, ntimer


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def _metrics(wait_us, fcfs_us, in_window, fcfs_p99, sjf_p99):
    wait_s = wait_us / MICROS
    fcfs_s = fcfs_us / MICROS
    excess = wait_s - fcfs_s
    undelayed = fcfs_s <= STARTS_IMMEDIATELY_S
    p99 = float(np.quantile(wait_s[in_window], 0.99))
    return {
        "p99_dl_s": p99,
        "mean_s": float(wait_s.mean()),
        "max_excess_s": float(excess.max()),
        "harm_s": float(excess[undelayed].max()),
        "gap_closed": (fcfs_p99 - p99) / (fcfs_p99 - sjf_p99),
        "jobs_over_600s_excess": int((excess > 600.0).sum()),
    }


def main() -> None:
    t0 = time.time()
    rows = []
    checks = []
    for level in LEVELS:
        trace, k, labels = load_overlay(OVERLAY, level)
        a = np.ascontiguousarray(trace.arrival_us)
        svc = np.ascontiguousarray(trace.service_us)
        score = np.ascontiguousarray(trace.score_for(SCORE_KEY))
        zeros = np.zeros(len(a), np.int64)
        in_window = labels["in_window"]
        print(f"level {level}: k = {k}, {len(a):,} jobs", flush=True)

        ref = {p.name: simulate(trace, p, k).wait_us for p in (fcfs(), sjf(), spjf(SCORE_KEY, "SPJF-E"))}
        fcfs_us = ref["FCFS"]
        fcfs_p99 = float(np.quantile(fcfs_us[in_window] / MICROS, 0.99))
        sjf_p99 = float(np.quantile(ref["SJF"][in_window] / MICROS, 0.99))

        # Tool check: this kernel as FCFS and as SPJF-E must reproduce the package waits.
        mine_fcfs, _ = simulate_rule(a, svc, score, zeros, k, 0)
        mine_spjf, _ = simulate_rule(a, svc, score, zeros, k, NEVER)
        d_fcfs = int(((mine_fcfs - a) != fcfs_us).sum())
        d_spjf = int(((mine_spjf - a) != ref["SPJF-E"]).sum())
        checks.append({"level": level, "k": k, "fcfs_jobs_differing": d_fcfs, "spjf_jobs_differing": d_spjf})
        print(f"  tool check: FCFS differing {d_fcfs}, SPJF-E differing {d_spjf}", flush=True)
        if d_fcfs or d_spjf:
            raise SystemExit("independent kernel disagrees with the package kernel; no result reported")

        for name, w in (("FCFS", fcfs_us), ("SJF", ref["SJF"]), ("SPJF-E", ref["SPJF-E"])):
            rows.append({"level": level, "k": k, "policy": name, "timer_share": 0.0,
                         **_metrics(w, fcfs_us, in_window, fcfs_p99, sjf_p99)})
        for t_s in MAXWAIT_T_S:
            st, ntimer = simulate_rule(a, svc, score, zeros, k, t_s * MICROS)
            rows.append({"level": level, "k": k, "policy": f"MaxWait({t_s})",
                         "timer_share": ntimer / len(a),
                         **_metrics(st - a, fcfs_us, in_window, fcfs_p99, sjf_p99)})
            print(f"  MaxWait({t_s}) done", flush=True)
        for w_jobs in BLOCK_W:
            blocks = np.arange(len(a), dtype=np.int64) // w_jobs
            st, _ = simulate_rule(a, svc, score, blocks, k, NEVER)
            rows.append({"level": level, "k": k, "policy": f"Block({w_jobs})", "timer_share": 0.0,
                         **_metrics(st - a, fcfs_us, in_window, fcfs_p99, sjf_p99)})
            print(f"  Block({w_jobs}) done", flush=True)
        del trace, labels, ref, a, svc, score

    out_csv = OUT / "maxwait_overlay0.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    manifest = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": _sha256(Path(__file__)),
        "input": str(OVERLAY.relative_to(ROOT)),
        "input_sha256": _sha256(OVERLAY),
        "output": str(out_csv.relative_to(ROOT)),
        "output_sha256": _sha256(out_csv),
        "tool_checks": checks,
        "maxwait_T_s": list(MAXWAIT_T_S),
        "block_W": list(BLOCK_W),
        "score": SCORE_KEY,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (OUT / "maxwait_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
