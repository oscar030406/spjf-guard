"""Late completion reports on the development overlays (reviewer 2, comment 4).

    python -u evidence/revision_r1/report_delay/run_delay.py gate2
    python -u evidence/revision_r1/report_delay/run_delay.py run --overlay 0 --level 2 \
        [--models U,A1,A2] [--laws const,unif] [--deltas 0,0.1,1,5,30,60,300] \
        [--policies "Guard(300),Guard(600),Guard(1200)"] [--out-dir cells] [--resume]

`gate2` runs the three guards of the main table at delta = 0 on overlay 0, every level,
through delay_kernel with each model, compares the waits job by job with the production
`spjf_guard.sim.simulate`, and compares p99, gap closed and max excess with
outputs/dev_tables/main_cells.csv (exact float equality).  `run` writes one row per
(policy, model, law, delta) of one cell to <out-dir>/rep<o>_L<l>.csv, rewritten after every
row; --resume skips the rows already there.  FCFS, SJF and SPJF-E come from the production
simulator (delta does not change them).  delta = 0 is one run per guard (model "all", law
"all"): every model is Algorithm 1 there.
"""

from __future__ import annotations

import _setup

import argparse
import csv
import importlib.util
import json
import os
import time

import numpy as np

from delay_kernel import MODE_GUARD, MODEL_A1, MODEL_A2, MODEL_U, simulate_delay
from spjf_guard import config as cfgmod
from spjf_guard.experiment.metrics import gap_closed, reduction_percent, summarise
from spjf_guard.experiment.reproduce import load_overlay
from spjf_guard.sim import simulate
from spjf_guard.sim.bounds import guard_upper_bound
from spjf_guard.sim.policy import MICROS, eta_fraction
from spjf_guard.sim.runner import JobResults

ROOT = _setup.ROOT
OUT = _setup.OUT
CONFIG = ROOT / "configs" / "main_frozen_1289aa2.yaml"
SELECTION = ROOT / "outputs" / "selection_v4" / "selected_parameters.csv"
MAIN_CELLS = ROOT / "outputs" / "dev_tables" / "main_cells.csv"
PARAMS = ROOT / "outputs" / "dev_tables" / "policy_parameters.csv"
OVERLAYS = ROOT / "data" / "derived" / "overlay_traces"
GUARDS = ("Guard(300)", "Guard(600)", "Guard(1200)")
REFS = ("FCFS", "SJF", "SPJF-E")
MODELS = {"U": MODEL_U, "A1": MODEL_A1, "A2": MODEL_A2}
LAWS = ("const", "unif")
DELTAS_S = (0.0, 0.1, 1.0, 5.0, 30.0, 60.0, 300.0)
DELAY_SEED = 20261018
"""The uniform law: u_c = default_rng(DELAY_SEED + overlay).random(n), d_c = floor(u_c (delta+1)) us,
the same draw for every policy, model and delta of an overlay."""

CFG = cfgmod.load(CONFIG)
LIMIT_S = float(CFG.limit_s)
L_US = int(round(LIMIT_S * MICROS))
WINDOW = int(CFG["run"]["segment_tree_window_ranks"])


def _read_selection():
    spec = importlib.util.spec_from_file_location("run_main", ROOT / "scripts" / "run_main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.read_selection(SELECTION)


SEL = _read_selection()


def policies_at(k: int, overlay: int, level: int) -> dict:
    """The main table's policy objects at this k, checked against policy_parameters.csv."""
    pols = {p.name: p for p in CFG.policies(k, False, SEL)}
    with PARAMS.open(encoding="utf-8") as fh:
        rows = {r["policy"]: r for r in csv.DictReader(fh)
                if int(r["overlay"]) == overlay and int(r["level"]) == level}
    for name in GUARDS:
        p, r = pols[name], rows[name]
        got = (p.b0_us / MICROS, p.eta_k / k, p.gam_us / MICROS, p.bmax_us / MICROS, k)
        want = (float(r["b0_s"]), float(r["eta"]), float(r["gam_s"]), float(r["bmax_s"]), int(r["k"]))
        assert got == want, f"{name} at overlay {overlay} level {level}: {got} != {want}"
    return pols


def load_cell(overlay: int, level: int) -> dict:
    path = OVERLAYS / f"primary_rep{overlay}.npz"
    trace, k, labels = load_overlay(path, level, {"tweedie": cfgmod.SCORE_KEY}, LIMIT_S)
    return {"overlay": overlay, "level": level, "k": k, "trace": trace, **labels}


def run_guard(cell, policy, model: int, delay_us: np.ndarray) -> JobResults:
    tr = cell["trace"]
    en, ed = eta_fraction(policy.eta_k)
    out = simulate_delay(
        tr.arrival_us, tr.service_us, tr.score_for(policy.score_key), int(cell["k"]),
        MODE_GUARD, int(policy.b0_us), int(en), int(ed), int(policy.bmax_us), WINDOW,
        int(policy.gam_us), model, delay_us, 0, False,
    )
    wait, disp, start, _srv, nd, nf, qw, qwf, _nreb, _span, err, _rec = out
    assert err == 0, f"{policy.name}: window of {WINDOW} ranks too small"
    return JobResults(policy.name, int(cell["k"]), wait, start, disp, int(nd), int(nf), int(qw), int(qwf))


def late_extra_us(model: str, k: int, delta_us: int) -> int:
    """X of sim_stale.py: k(L+delta) for U, (k-1)(L+delta) for A2, 0 for A1 and at delta 0."""
    if delta_us == 0 or model in ("A1", "all"):
        return 0
    return (k if model == "U" else k - 1) * (L_US + delta_us)


def row_for(cell, res: JobResults, refs: dict, policy, model: str, law: str, delta_s: float,
            seconds: float) -> dict:
    k = int(cell["k"])
    fw = refs["fcfs_wait"]
    stats = summarise(res, fw, cell["in_window"], cell["is_heavy"])
    row = {
        "overlay": cell["overlay"], "level": cell["level"], "k": k, "policy": res.policy,
        "model": model, "law": law, "delta_s": delta_s,
        "delay_seed": DELAY_SEED + cell["overlay"] if law == "unif" else "",
        **{c: v for c, v in stats.as_row().items() if c not in ("policy", "servers")},
        "fired_pct": 100.0 * stats.fired_fraction_queue_weighted,
        "gap_closed": gap_closed(stats.p99_dl_s, refs["FCFS"], refs["SJF"]),
        "reduction_pct": reduction_percent(stats.p99_dl_s, refs["FCFS"]),
    }
    if policy is not None:
        delta_us = int(round(delta_s * MICROS))
        exc = res.wait_us - fw
        kb = int(policy.bmax_us) + (3 * k - 2) * L_US + late_extra_us(model, k, delta_us)
        bound = guard_upper_bound(fw, policy, k, LIMIT_S)
        allowed = bound - fw / MICROS
        used = exc / MICROS
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(allowed > 0, used / allowed, 0.0)
        worst = int(np.argmax(exc))
        row.update({
            "worst_job": worst,
            "worst_job_wait_s": res.wait_us[worst] / MICROS,
            "worst_job_fcfs_wait_s": fw[worst] / MICROS,
            "late_bound_excess_s": kb / k / MICROS,
            "viol_late": int((k * exc >= kb).sum()),
            "worst_ratio_late": float((k * exc).max() / kb),
            "viol_orig": int((res.wait_us / MICROS > bound).sum()),
            "worst_ratio_orig": float(np.nanmax(ratio)),
        })
    else:
        row.update({c: "" for c in ("worst_job", "worst_job_wait_s", "worst_job_fcfs_wait_s",
                                    "late_bound_excess_s", "viol_late", "worst_ratio_late",
                                    "viol_orig", "worst_ratio_orig")})
    row["seconds"] = round(seconds, 1)
    return row


def reference_runs(cell, pols: dict) -> tuple[dict, list]:
    """FCFS, SJF, SPJF-E from the production simulator; returns the p99s, FCFS waits, rows."""
    tr, k = cell["trace"], int(cell["k"])
    res = {}
    secs = {}
    for name in REFS:
        t0 = time.time()
        res[name] = simulate(tr, pols[name], k, window=WINDOW)
        secs[name] = time.time() - t0
    fw = res["FCFS"].wait_us
    refs = {"fcfs_wait": fw}
    for name in REFS:
        refs[name] = summarise(res[name], fw, cell["in_window"], cell["is_heavy"]).p99_dl_s
    rows = [row_for(cell, res[name], refs, None, "", "", "", secs[name]) for name in REFS]
    return refs, rows


def delays(n: int, overlay: int, law: str, delta_s: float, u_cache: dict) -> np.ndarray:
    d_us = int(round(delta_s * MICROS))
    if law == "const" or d_us == 0:
        return np.full(n, d_us, np.int64)
    if "u" not in u_cache:
        u_cache["u"] = np.random.default_rng(DELAY_SEED + overlay).random(n)
    return np.minimum(np.floor(u_cache["u"] * (d_us + 1)).astype(np.int64), d_us)


def write_rows(rows: list[dict], path) -> None:
    fields = list(rows[0])
    for r in rows:
        fields += [c for c in r if c not in fields]
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def run(overlay, level, models, laws, deltas, policies, resume, out_dir) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"rep{overlay}_L{level}.csv"
    rows: list[dict] = []
    if resume and path.exists():
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    done = {(r["policy"], r["model"], r["law"], str(r["delta_s"])) for r in rows}
    plan = []
    for law in laws:
        for d in deltas:
            for name in policies:
                for m in models:
                    if d == 0:
                        key = (name, "all", "all", str(0.0))
                    else:
                        key = (name, m, law, str(d))
                    if key not in done and key not in [p[0] for p in plan]:
                        plan.append((key, law, d, name, m))
    if not plan and all((r, "", "", "") in done for r in REFS):
        print(f"rep{overlay} L{level}: complete, {len(rows)} rows", flush=True)
        return
    t_cell = time.time()
    cell = load_cell(overlay, level)
    k = int(cell["k"])
    pols = policies_at(k, overlay, level)
    refs, ref_rows = reference_runs(cell, pols)
    for r in ref_rows:
        if (r["policy"], "", "", "") not in done:
            rows.append(r)
    write_rows(rows, path)
    print(f"rep{overlay} L{level} k{k}: refs FCFS {refs['FCFS']:.3f} SJF {refs['SJF']:.3f} "
          f"SPJF-E {refs['SPJF-E']:.3f} ({time.time() - t_cell:.0f} s)", flush=True)
    u_cache: dict = {}
    n = len(cell["trace"])
    for key, law, d, name, m in plan:
        model = "all" if d == 0 else m
        dly = delays(n, overlay, law, d, u_cache)
        t0 = time.time()
        res = run_guard(cell, pols[name], MODEL_U if d == 0 else MODELS[m], dly)
        row = row_for(cell, res, refs, pols[name], model, key[2], d, time.time() - t0)
        del res, dly
        rows.append(row)
        write_rows(rows, path)
        print(f"rep{overlay} L{level} {name} {model} {key[2]} delta={d}: p99={row['p99_dl_s']:.3f} "
              f"gap={row['gap_closed']:.4f} exc={row['max_excess_s']:.1f} "
              f"viol_late={row['viol_late']} viol_orig={row['viol_orig']} ({row['seconds']} s)",
              flush=True)
    log = {"overlay": overlay, "level": level, "k": k, "rows": len(rows),
           "wall_s": round(time.time() - t_cell, 1), "peak_commit_gb": round(_setup.peak_commit_gb(), 2)}
    (out_dir / f"rep{overlay}_L{level}.log.json").write_text(json.dumps(log, indent=1))
    print(f"rep{overlay} L{level}: done {log}", flush=True)


def gate2() -> None:
    with MAIN_CELLS.open(encoding="utf-8") as fh:
        main = {(int(r["overlay"]), int(r["level"]), r["policy"]): r for r in csv.DictReader(fh)}
    cols = ("p99_dl_s", "gap_closed", "max_excess_s", "harm_s", "mean_s")
    report = {"cells": [], "mismatches": 0}
    t_all = time.time()
    for level in (0, 1, 2):
        cell = load_cell(0, level)
        k = int(cell["k"])
        pols = policies_at(k, 0, level)
        refs, ref_rows = reference_runs(cell, pols)
        zero = np.zeros(len(cell["trace"]), np.int64)
        for r in ref_rows:
            m = main[(0, level, r["policy"])]
            diffs = {c: (float(r[c]), float(m[c])) for c in cols if float(r[c]) != float(m[c])}
            report["mismatches"] += len(diffs)
            report["cells"].append({"level": level, "k": k, "policy": r["policy"], "model": "production",
                                    "main_cells_diffs": diffs})
        for name in GUARDS:
            prod = simulate(cell["trace"], pols[name], k, window=WINDOW)
            for mname, model in MODELS.items():
                t0 = time.time()
                res = run_guard(cell, pols[name], model, zero)
                secs = time.time() - t0
                wdiff = int(np.abs(res.wait_us - prod.wait_us).max())
                same_disp = bool(np.array_equal(res.dispatch_index, prod.dispatch_index))
                forced_same = (res.n_forced, res.queue_weighted_forced) == (prod.n_forced, prod.queue_weighted_forced)
                r = row_for(cell, res, refs, pols[name], "all", "all", 0.0, secs)
                m = main[(0, level, name)]
                diffs = {c: (float(r[c]), float(m[c])) for c in cols if float(r[c]) != float(m[c])}
                bad = len(diffs) + int(wdiff != 0) + int(not same_disp) + int(not forced_same) \
                    + int(r["viol_orig"] != 0) + int(r["viol_late"] != 0)
                report["mismatches"] += bad
                entry = {"level": level, "k": k, "policy": name, "model": mname,
                         "max_abs_wait_diff_vs_simulate_us": wdiff, "dispatch_order_equal": same_disp,
                         "forced_counts_equal": forced_same, "main_cells_diffs": diffs,
                         "p99_dl_s": r["p99_dl_s"], "gap_closed": r["gap_closed"],
                         "max_excess_s": r["max_excess_s"], "viol_orig": r["viol_orig"],
                         "viol_late": r["viol_late"], "seconds": round(secs, 1)}
                report["cells"].append(entry)
                print(f"  L{level} k{k} {name} {mname}: wait diff {wdiff} us, order equal {same_disp}, "
                      f"p99 {r['p99_dl_s']!r} gap {r['gap_closed']!r} exc {r['max_excess_s']!r}, "
                      f"main_cells diffs {diffs or 'none'} ({secs:.1f} s)", flush=True)
                del res
            del prod
        del cell
    report["wall_s"] = round(time.time() - t_all, 1)
    report["peak_commit_gb"] = round(_setup.peak_commit_gb(), 2)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gate2_delta0.json").write_text(json.dumps(report, indent=1))
    print(f"GATE2 mismatches {report['mismatches']} wall {report['wall_s']} s "
          f"peak commit {report['peak_commit_gb']} GB", flush=True)
    if report["mismatches"]:
        raise SystemExit(1)


def main() -> None:
    _setup.below_normal()
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["gate2", "run"])
    ap.add_argument("--overlay", type=int, default=0)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--models", default="U,A1,A2")
    ap.add_argument("--laws", default=",".join(LAWS))
    ap.add_argument("--deltas", default=",".join(str(d) for d in DELTAS_S))
    ap.add_argument("--policies", default=",".join(GUARDS))
    ap.add_argument("--out-dir", default="cells")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    if a.action == "gate2":
        gate2()
        return
    run(a.overlay, a.level, a.models.split(","), a.laws.split(","),
        [float(x) for x in a.deltas.split(",")], a.policies.split(","), a.resume, OUT / a.out_dir)


if __name__ == "__main__":
    main()
