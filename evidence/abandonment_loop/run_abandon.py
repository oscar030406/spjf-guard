"""Closed-loop replay with abandonment and resubmission (model in MODEL.md).

    python evidence/abandonment_loop/run_abandon.py validate
    python -u evidence/abandonment_loop/run_abandon.py run \
        [--reps 0,1,2,3,4] [--levels 0,1,2] [--combos inf:0,60:0,...] [--resume]

`validate` is check (a): on primary overlay 0, level 2, with infinite patience the new
kernel must reproduce `closed_kernel.simulate_closed` (gating on, late kept) and, with
gating off, `spjf_guard.sim.simulate`, job for job, for every policy.  `run` writes one
row per (overlay, level, patience, p_resubmit, policy) to out/cells.csv, rewriting it
after every policy.  Every guarded run asserts zero violations of the per-job bound
against reference R1 (FCFS without abandonment on the served attempts, MODEL.md
section 7); R2 is reported, not asserted.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "evidence" / "closed_loop"))

from abandon_kernel import (  # noqa: E402
    ERR_RANK_CAP,
    MODE_FCFS,
    STATUS_SERVED,
    STATUS_WITHDRAWN,
    simulate_abandon,
)
from closed_kernel import simulate_closed  # noqa: E402
from run_closed_loop import (  # noqa: E402
    SCORE_ARRAY,
    WINDOW,
    fcfs_open_on,
    kernel_args,
    load_cell,
)
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.sim import MICROS, Trace, simulate  # noqa: E402
from spjf_guard.sim.bounds import guard_upper_bound  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf, spjf  # noqa: E402

OUT = HERE / "out"
CFG = cfgmod.load(ROOT / "configs" / "main.yaml")
LIMIT_S = float(CFG.limit_s)
SEED_BASE = 20261001
MAX_RESUB = 3
POLICIES = ("FCFS", "SJF", "SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)")
COMBOS = ["inf:0"] + [f"{m}:{p}" for m in (60, 300, 1800) for p in (0, 0.5, 1)]


def policy_for(name: str, k: int):
    if name == "FCFS":
        return fcfs()
    if name == "SJF":
        return sjf()
    key = CFG["scheduling"]["ranking_score"]
    if name == "SPJF-E":
        return spjf(key, "SPJF-E")
    g = float(name[len("Guard("):-1])
    return CFG._guard_from(CFG.selected(g), g, k, name)


def score_for(cell: dict, policy) -> np.ndarray:
    """closed_loop's mapping: every learned score key ranks on the stored `tweedie`."""
    if policy.base == "fcfs":
        return np.zeros(len(cell["a_us"]), np.float64)
    if policy.score_key == "true_size":
        return cell["s_us"].astype(np.float64)
    return cell["tweedie"]


@njit(cache=True)
def _fcfs_sorted(a_us, s_us, k):
    """FCFS waits on arrivals sorted by (instant, input index): each job starts at the
    later of its arrival and the earliest instant a server is free (Kiefer-Wolfowitz)."""
    n = a_us.shape[0]
    free = np.full(k, -(np.int64(1) << 62), np.int64)  # min-heap of server free instants
    wait = np.empty(n, np.int64)
    for i in range(n):
        start = a_us[i] if a_us[i] > free[0] else free[0]
        wait[i] = start - a_us[i]
        free[0] = start + s_us[i]
        c = 0
        while True:
            left = 2 * c + 1
            if left >= k:
                break
            b = left
            if left + 1 < k and free[left + 1] < free[left]:
                b = left + 1
            if free[b] < free[c]:
                free[b], free[c] = free[c], free[b]
                c = b
            else:
                break
    return wait


def fcfs_r1(a_prime_us: np.ndarray, s_us: np.ndarray, k: int) -> np.ndarray:
    """Reference R1: the same waits as closed_loop's `fcfs_open_on` (stable sort, then
    FCFS), computed directly; `check-r1` asserts the two agree job for job."""
    order = np.argsort(a_prime_us, kind="stable")
    w = _fcfs_sorted(np.ascontiguousarray(a_prime_us[order]), np.ascontiguousarray(s_us[order]), k)
    out = np.empty(len(order), np.int64)
    out[order] = w
    return out


def parse_combo(text: str) -> tuple[float, float]:
    m, p = text.split(":")
    return (math.inf if m == "inf" else float(m)), float(p)


def run_kernel(cell, policy, closed, mean_s, p, a0=None, mode=None):
    m, b0, en, ed, bmax, gam = kernel_args(policy, cell["k"])
    n = len(cell["a_us"])
    cap = n if (p == 0 or math.isinf(mean_s)) else n + n // 4
    a0_us = cell["a_us"] if a0 is None else a0
    order = (
        np.argsort(a0_us, kind="stable").astype(np.int64)
        if closed == 0
        else np.empty(0, np.int64)
    )
    while True:
        out = simulate_abandon(
            a0_us,
            cell["s_us"],
            score_for(cell, policy),
            cell["succ"],
            cell["gate"],
            cell["delta_us"],
            cell["offset_us"],
            int(cell["k"]),
            m if mode is None else mode,
            b0,
            en,
            ed,
            bmax,
            WINDOW,
            gam,
            int(closed),
            SEED_BASE + int(cell["rep"]),
            0.0 if math.isinf(mean_s) else mean_s * MICROS,
            float(p),
            MAX_RESUB,
            cap,
            order,
        )
        if out[7] != ERR_RANK_CAP:
            break
        cap *= 2
    assert out[7] == 0, f"kernel error {out[7]}"
    status = out[4]
    assert int(((status == STATUS_SERVED) | (status == STATUS_WITHDRAWN)).sum()) == n, (
        "a job neither served nor withdrawn"
    )
    return out


# --------------------------------------------------------------------------- #
# check (a)
# --------------------------------------------------------------------------- #
def check_r1(rep: int = 0, level: int = 2, combo: str = "60:0.5") -> dict:
    """fcfs_r1 against closed_loop's fcfs_open_on (package FCFS), every non-FCFS policy."""
    cell = load_cell(rep, level)
    mean_s, p = parse_combo(combo)
    report = {"overlay": rep, "level": level, "combo": combo}
    for name in POLICIES[1:]:
        out = run_kernel(cell, policy_for(name, cell["k"]), 1, mean_s, p)
        served = out[4] == STATUS_SERVED
        t0 = time.time()
        fast = fcfs_r1(out[1][served], cell["s_us"][served], cell["k"])
        t1 = time.time()
        slow = fcfs_open_on(out[1][served], cell["s_us"][served], cell["k"])
        t2 = time.time()
        report[name] = {
            "n_served": int(served.sum()),
            "max_abs_diff_us": int(np.abs(fast - slow).max()),
            "fcfs_r1_s": round(t1 - t0, 1),
            "fcfs_open_on_s": round(t2 - t1, 1),
        }
        print(f"  {name}: {report[name]}", flush=True)
        assert report[name]["max_abs_diff_us"] == 0
        del out, fast, slow
    return report


def validate(rep: int = 0, level: int = 2) -> dict:
    cell = load_cell(rep, level)
    report = {"overlay": rep, "level": level, "k": int(cell["k"])}
    for name in POLICIES:
        policy = policy_for(name, cell["k"])
        m, b0, en, ed, bmax, gam = kernel_args(policy, cell["k"])
        t0 = time.time()
        mine = run_kernel(cell, policy, 1, math.inf, 0.0)
        t1 = time.time()
        theirs = simulate_closed(
            cell["a_us"], cell["s_us"], score_for(cell, policy), cell["succ"], cell["gate"],
            cell["delta_us"], cell["offset_us"], cell["deadline_us"], int(cell["k"]), m,
            b0, en, ed, bmax, WINDOW, gam, 1, 0,
        )
        assert theirs[10] == 0
        closed_wait = int(np.abs(mine[0] - theirs[0]).max())
        closed_arr = int(np.abs(mine[1] - theirs[1]).max())
        del theirs
        t2 = time.time()
        mine_open = run_kernel(cell, policy, 0, math.inf, 0.0)
        trace = Trace(
            cell["a_us"], cell["s_us"],
            {SCORE_ARRAY: cell["tweedie"], policy.score_key: cell["tweedie"]}
            if policy.base != "fcfs" and policy.score_key != "true_size"
            else {},
            limit_s=LIMIT_S,
        )
        pkg = simulate(trace, policy, cell["k"], window=WINDOW).wait_us
        open_wait = int(np.abs(mine_open[0] - pkg).max())
        report[name] = {
            "closed_max_abs_diff_wait_us": closed_wait,
            "closed_max_abs_diff_arrival_us": closed_arr,
            "open_max_abs_diff_wait_us": open_wait,
            "n_withdrawn": int(mine[6][6]) + int(mine_open[6][6]),
            "abandon_kernel_closed_s": round(t1 - t0, 1),
            "abandon_kernel_open_s": round(time.time() - t2, 1),
            "p99_dl_closed_s": float(np.quantile(mine[0][cell["dl"]] / MICROS, 0.99)),
        }
        print(f"  {name}: {report[name]}", flush=True)
        del mine, mine_open, pkg, trace
    return report


# --------------------------------------------------------------------------- #
# the experiment
# --------------------------------------------------------------------------- #
def q99(x: np.ndarray) -> float:
    return float(np.quantile(x, 0.99)) if x.size else float("nan")


def summarise(cell, name, policy, out, mean_s, p, elapsed) -> dict:
    wait_us, a_prime, a_first, end_us, status, att, ctr, _ = out
    k = int(cell["k"])
    served = status == STATUS_SERVED
    withdrawn = status == STATUS_WITHDRAWN
    dl = cell["dl"]
    w = wait_us[served]
    user = (end_us - a_first)[served]
    dl_s = dl[served]
    n = len(status)
    row = {
        "overlay": cell["rep"],
        "level": cell["level"],
        "k": k,
        "patience_mean_s": "inf" if math.isinf(mean_s) else mean_s,
        "p_resubmit": p,
        "policy": name,
        "n_jobs": n,
        "n_served": int(served.sum()),
        "n_withdrawn": int(withdrawn.sum()),
        "frac_withdrawn": float(withdrawn.mean()),
        "n_abandon_events": int(ctr[4]),
        "n_resubmissions": int(ctr[5]),
        "n_dl": int(dl.sum()),
        "n_dl_withdrawn": int((withdrawn & dl).sum()),
        "frac_dl_withdrawn": float((withdrawn & dl).sum() / max(int(dl.sum()), 1)),
        "p99_dl_s": q99(w[dl_s] / MICROS),
        "p99_dl_user_s": q99(user[dl_s] / MICROS),
        "mean_s": float(w.mean()) / MICROS,
        "p99_all_s": q99(w / MICROS),
        "max_s": float(w.max()) / MICROS,
        "fired_fraction_queue_weighted": int(ctr[3]) / max(int(ctr[2]), 1),
        "n_ranks": int(ctr[9]),
    }
    row.update({c: "" for c in (
        "max_excess_s", "bound_violations", "worst_ratio_to_bound",
        "max_excess_vs_fcfs_abandon_s", "n_over_bound_vs_fcfs_abandon",
    )})
    if name != "FCFS":
        # R1: FCFS, no abandonment, open-loop, on the served attempts' realised arrivals
        wf = fcfs_r1(a_prime[served], cell["s_us"][served], k)
        row["max_excess_s"] = float((w - wf).max()) / MICROS
        if policy.wrapper == "work":
            bound = guard_upper_bound(wf, policy, k, LIMIT_S)
            ws = w / MICROS
            viol = int((ws > bound).sum())
            row["bound_violations"] = viol
            row["worst_ratio_to_bound"] = float((ws / np.maximum(bound, 1e-12)).max())
            assert viol == 0, f"{name}: {viol} jobs above the R1 bound"
        del wf
        # R2: FCFS with the same abandonment, open-loop, on the first-attempt arrivals
        r2 = run_kernel(cell, fcfs(), 0, mean_s, p, a0=a_first, mode=MODE_FCFS)
        both = served & (r2[4] == STATUS_SERVED)
        d_p = (end_us - a_first)[both] / MICROS
        d_f = (r2[3] - r2[2])[both] / MICROS
        row["max_excess_vs_fcfs_abandon_s"] = float((d_p - d_f).max())
        if policy.wrapper == "work":
            add = d_f + policy.bmax_us / MICROS / k + (3.0 - 2.0 / k) * LIMIT_S
            row["n_over_bound_vs_fcfs_abandon"] = int((d_p > add).sum())
        del r2
    row["seconds"] = round(elapsed, 1)
    return row


def add_gaps(rows: list[dict]) -> None:
    ref = {}
    for r in rows:
        if r["policy"] in ("FCFS", "SJF"):
            ref[(r["overlay"], r["level"], str(r["patience_mean_s"]), r["p_resubmit"],
                 r["policy"])] = r
    for r in rows:
        key = (r["overlay"], r["level"], str(r["patience_mean_s"]), r["p_resubmit"])
        f, s = ref.get(key + ("FCFS",)), ref.get(key + ("SJF",))
        for col, src in (("gap_closed", "p99_dl_s"), ("gap_closed_user", "p99_dl_user_s")):
            if f is None or s is None:
                r[col] = ""
            else:
                den = float(f[src]) - float(s[src])
                r[col] = (float(f[src]) - float(r[src])) / den if den != 0 else ""


def write(rows: list[dict], path: Path) -> None:
    add_gaps(rows)
    fields = list(rows[0])
    for c in ("gap_closed", "gap_closed_user"):
        fields.remove(c)
        fields.insert(fields.index("p99_dl_user_s") + 1, c)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(reps, levels, combos, policies, resume: bool, path: Path) -> None:
    rows: list[dict] = []
    done = set()
    if resume and path.exists():
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            r["overlay"], r["level"] = int(r["overlay"]), int(r["level"])
            r["p_resubmit"] = float(r["p_resubmit"])
            pm = r["patience_mean_s"]
            r["patience_mean_s"] = pm if pm == "inf" else float(pm)
            done.add((r["overlay"], r["level"], str(r["patience_mean_s"]), r["p_resubmit"],
                      r["policy"]))
    for rep in reps:
        for level in levels:
            cell = None
            for combo in combos:
                mean_s, p = parse_combo(combo)
                for name in policies:
                    key = (rep, level, "inf" if math.isinf(mean_s) else str(mean_s), p, name)
                    if key in done:
                        continue
                    if cell is None:
                        cell = load_cell(rep, level)
                    policy = policy_for(name, cell["k"])
                    t0 = time.time()
                    out = run_kernel(cell, policy, 1, mean_s, p)
                    t1 = time.time()
                    row = summarise(cell, name, policy, out, mean_s, p, t1 - t0)
                    row["seconds_with_refs"] = round(time.time() - t0, 1)
                    del out
                    rows.append(row)
                    print(
                        f"rep{rep} L{level} k{cell['k']} {combo} {name}: "
                        f"p99_dl={row['p99_dl_s']:.3f} wd={row['frac_withdrawn']:.4f} "
                        f"resub={row['n_resubmissions']} exc={row['max_excess_s']} "
                        f"({row['seconds']}s / {row['seconds_with_refs']}s)",
                        flush=True,
                    )
                    write(rows, path)
            del cell


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["validate", "check-r1", "run"])
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--combos", default=",".join(COMBOS))
    ap.add_argument("--policies", default=",".join(POLICIES))
    ap.add_argument("--out", default="cells.csv")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "check-r1":
        report = check_r1()
        (OUT / "check_r1.json").write_text(json.dumps(report, indent=2))
        return
    if args.action == "validate":
        report = validate()
        (OUT / "validation.json").write_text(json.dumps(report, indent=2))
        return
    run(
        [int(x) for x in args.reps.split(",")],
        [int(x) for x in args.levels.split(",")],
        args.combos.split(","),
        args.policies.split(","),
        args.resume,
        OUT / args.out,
    )


if __name__ == "__main__":
    main()
