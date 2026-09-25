"""Head-of-line timeout against the guard at the same promise, on the development overlays.

Timeout(theta) serves the oldest waiting job once it has waited theta, and otherwise
the base policy's choice.  theory_check.py tests the bound
W <= W_FCFS + theta + (3 - 2/k) L, so theta = G - (3 - 2/k) L carries the same
promise G as Guard(G).  This script asks what the two rules do with that promise:
the deadline-window p99, the gap closed, the harm, and the per-job bound.

The timeout kernel below is a separate implementation.  Before it is trusted it must
reproduce the package kernel's FCFS waits (theta = 0) and SPJF-E waits (theta larger
than any wait) job for job; the script stops if either differs.

Scores: the stored expected-cost score ('tweedie', mapped to the key the policies ask
for), the same arrays envelope_bound_probe.py used.  Sealed data are not read.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment.metrics import deadline_window_p99, gap_closed, harm  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim.policy import MICROS, fixed  # noqa: E402
from spjf_guard.sim.runner import simulate  # noqa: E402

OVERLAYS = [ROOT / "data" / "derived" / "overlay_traces" / f"primary_rep{r}.npz" for r in range(5)]
LIMIT_S = 60.0
PROMISES = (300.0, 600.0, 1200.0)
THETA_GRID_S = (15.0, 30.0, 60.0, 120.0, 240.0, 480.0, 960.0)
HERE = Path(__file__).resolve().parent


@njit(cache=True)
def _push(key, idx, m, new_key, new_idx):
    key[m] = new_key
    idx[m] = new_idx
    c = m
    while c > 0:
        p = (c - 1) >> 1
        if key[p] > key[c] or (key[p] == key[c] and idx[p] > idx[c]):
            key[p], key[c] = key[c], key[p]
            idx[p], idx[c] = idx[c], idx[p]
            c = p
        else:
            break
    return m + 1


@njit(cache=True)
def _pop(key, idx, m):
    m -= 1
    key[0] = key[m]
    idx[0] = idx[m]
    c = 0
    while True:
        left = 2 * c + 1
        if left >= m:
            break
        b = left
        if left + 1 < m and (
            key[left + 1] < key[left] or (key[left + 1] == key[left] and idx[left + 1] < idx[left])
        ):
            b = left + 1
        if key[b] < key[c] or (key[b] == key[c] and idx[b] < idx[c]):
            key[b], key[c] = key[c], key[b]
            idx[b], idx[c] = idx[c], idx[b]
            c = b
        else:
            break
    return m


@njit(cache=True)
def timeout_kernel(a_us, s_us, score, k, theta_us):
    """Wait of every job under Timeout(theta).  Jobs are in rank order; int64 clock."""
    n = a_us.shape[0]
    wait = np.empty(n, np.int64)
    served = np.zeros(n, np.uint8)
    hk = np.empty(n + 1, np.float64)
    hi = np.empty(n + 1, np.int64)
    rk = np.empty(k + 1, np.float64)
    ri = np.empty(k + 1, np.int64)
    m = 0
    nrun = 0
    head = 0
    arrived = 0
    started = 0
    t = a_us[0]
    while started < n:
        while nrun > 0 and rk[0] <= t:
            nrun = _pop(rk, ri, nrun)
        while arrived < n and a_us[arrived] <= t:
            m = _push(hk, hi, m, score[arrived], arrived)
            arrived += 1
        if nrun < k and head < arrived:
            if t - a_us[head] >= theta_us:
                j = head
            else:
                while served[hi[0]] == 1:
                    m = _pop(hk, hi, m)
                j = hi[0]
                m = _pop(hk, hi, m)
            served[j] = 1
            wait[j] = t - a_us[j]
            started += 1
            while head < n and served[head] == 1:
                head += 1
            nrun = _push(rk, ri, nrun, float(t + s_us[j]), j)
            continue
        nxt = np.int64(1) << 62
        if nrun > 0:
            nxt = np.int64(rk[0])
        if arrived < n and a_us[arrived] < nxt:
            nxt = a_us[arrived]
        t = nxt
    return wait


def cross_check(trace, k, fcfs_wait, spjf_wait, score):
    """The separate kernel must reproduce both endpoints exactly before it is used."""
    at_zero = timeout_kernel(trace.arrival_us, trace.service_us, score, k, np.int64(0))
    at_inf = timeout_kernel(trace.arrival_us, trace.service_us, score, k, np.int64(1) << 60)
    if not np.array_equal(at_zero, fcfs_wait):
        raise SystemExit("timeout kernel at theta = 0 does not reproduce the package's FCFS")
    if not np.array_equal(at_inf, spjf_wait):
        raise SystemExit("timeout kernel at theta = inf does not reproduce the package's SPJF-E")


def row(overlay, level, k, name, promise, theta, wait_us, fcfs_us, ref, labels):
    wait_s = wait_us / MICROS
    fcfs_s = fcfs_us / MICROS
    excess = wait_s - fcfs_s
    p99 = deadline_window_p99(wait_s, labels["in_window"])
    out = {
        "overlay": overlay,
        "level": level,
        "k": k,
        "policy": name,
        "promise_s": promise,
        "theta_s": theta,
        "p99_dl_s": round(p99, 3),
        "gap_closed": round(gap_closed(p99, ref["FCFS"], ref["SJF"]), 4),
        "mean_s": round(float(wait_s.mean()), 3),
        "max_excess_s": round(float(excess.max()), 3),
        "harm_s": round(harm(excess, fcfs_s), 3),
        "max_wait_s": round(float(wait_s.max()), 3),
        "bound_violations": "",
    }
    if theta != "":
        bound = float(theta) + (3 - 2 / k) * LIMIT_S
        out["bound_violations"] = int((excess > bound + 1e-6).sum())
    return out


def run_cell(cfg, path, overlay, level, rows, grid):
    trace, k, labels = load_overlay(path, level, {"tweedie": "spjf_e"}, LIMIT_S)
    policies = {p.name: p for p in cfg.policies(k)}
    waits = {name: simulate(trace, policies[name], k).wait_us for name in ("FCFS", "SJF", "SPJF-E")}
    ref = {name: deadline_window_p99(w / MICROS, labels["in_window"]) for name, w in waits.items()}
    score = trace.score_for(policies["SPJF-E"].score_key)
    cross_check(trace, k, waits["FCFS"], waits["SPJF-E"], score)
    fcfs_us = waits["FCFS"]
    for name in ("FCFS", "SJF", "SPJF-E"):
        rows.append(row(overlay, level, k, name, "", "", waits[name], fcfs_us, ref, labels))
    slack = (3 - 2 / k) * LIMIT_S
    for promise in PROMISES:
        for name, policy in ((f"Guard({promise:g})", policies[f"Guard({promise:g})"]),
                             (f"Fixed({promise:g})", fixed(promise, k, LIMIT_S, "spjf_e"))):
            w = simulate(trace, policy, k).wait_us
            rows.append(row(overlay, level, k, name, promise, "", w, fcfs_us, ref, labels))
        theta = promise - slack
        w = timeout_kernel(trace.arrival_us, trace.service_us, score, k, np.int64(round(theta * MICROS)))
        rows.append(row(overlay, level, k, f"Timeout({promise:g})", promise, round(theta, 3), w,
                        fcfs_us, ref, labels))
    if grid:
        for theta in THETA_GRID_S:
            w = timeout_kernel(trace.arrival_us, trace.service_us, score, k,
                               np.int64(round(theta * MICROS)))
            rows.append(row(overlay, level, k, "Timeout-grid", round(theta + slack, 3), theta, w,
                            fcfs_us, ref, labels))


def main() -> None:
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    rows: list[dict] = []
    for overlay, path in enumerate(OVERLAYS):
        for level in (0, 1, 2):
            started = time.time()
            run_cell(cfg, path, overlay, level, rows, grid=(overlay == 0))
            print(f"overlay {overlay} level {level} done [{time.time() - started:.0f} s]", flush=True)
            for r in rows[-(12 if overlay else 19):]:
                print("  " + "  ".join(f"{key}={r[key]}" for key in (
                    "policy", "theta_s", "p99_dl_s", "gap_closed", "harm_s", "max_excess_s",
                    "bound_violations")), flush=True)
    with open(HERE / "timeout_overlays.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("EXIT 0")


if __name__ == "__main__":
    main()
