"""Envelope bound: an absolute per-job wait bound from the fluid rate-k backlog.

Claim under test (derived by hand, not in the paper):
  (1) FCFS on k identical non-preemptive servers: W_FCFS[i] <= U_{<i}(a_i) / k.
  (2) Any work-conserving k-server system: U(t) <= V(t) + (k-1) L, with V the backlog of
      one fluid server of rate k fed the same work.  Hence, with V_i the fluid backlog
      just after job i arrives, W_FCFS[i] <= (V_i - C_i + (k-1) L) / k.
  (3) Theorem 2 of the paper (Guard bound) then gives, for a wrapper with promise G,
      W[i] < (V_i - C_i + (k-1) L) / k + G, and with sigma = max_t V(t) every job waits
      less than sigma/k + (1 - 1/k) L + G.  At k = 1 step (1) is an equality.

Parts, in the order they run:
  b. sigma on the primary and validation overlays at the primary k of each level (and at
     the validation overlay's own k), so an advance quote can be compared with the
     realised one.
  k1. the k = 1 overlay: FCFS waits against V_i - C_i, exactly, in microseconds; then the
     per-job bound for every policy the configuration builds at k = 1.
  a. five primary overlays x three levels x every policy of cfg.policies(k).

Every comparison is in int64 microseconds, as the simulator's clock is, so no
floating-point rounding decides a violation.  A single job above its bound refutes (2)
or (3) on this input.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
      OMP_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=<scratch> \
      uv run --no-sync python evidence/envelope_bound/envelope_bound.py \
      > evidence/envelope_bound/out_envelope_bound.txt
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim.policy import (  # noqa: E402
    MICROS,
    TRUE_SIZE,
    WRAP_NONE,
    WRAP_SKIP,
    WRAP_WORK,
)
from spjf_guard.sim.runner import Trace, simulate  # noqa: E402

CONFIG = ROOT / "configs" / "main.yaml"
OVERLAYS = ROOT / "data" / "derived" / "overlay_traces"
OUT = Path(__file__).resolve().parent
PRIMARY = [OVERLAYS / f"primary_rep{r}.npz" for r in range(5)]
VALIDATION = [OVERLAYS / f"validation_rep{r}.npz" for r in range(5)]
K1 = OVERLAYS / "k1_rep0.npz"
LEVELS = (0, 1, 2)
# Stored score array -> the key the policies ask for.  'tweedie' -> 'spjf_e' is the
# probe's map; 'tweedie_conservative' feeds Aging(600), whose configured score it is
# (configs/main.yaml scheduling.aging_baseline.ranking_score).
SCORE_MAP = {"tweedie": "spjf_e", "tweedie_conservative": "spjf_e_conservative"}
PROMISE_IN_NAME = re.compile(r"\((\d+(?:\.\d+)?)\)$")

BOUND_FIELDS = [
    "overlay", "level", "k", "policy", "n", "sigma_s", "bound_abs_s", "bound_prearrival_s",
    "max_wait_s", "ratio_max_wait_over_bound_abs", "per_job_violations", "ties",
    "min_slack_s", "promise_named_s", "promise_own_s", "violations_own_constant",
    "bound_kind", "sim_seconds",
]
SIGMA_FIELDS = [
    "overlay", "level", "k_primary", "sigma_primary_s", "sigma_validation_s",
    "ratio_validation_over_primary", "k_validation_own", "sigma_validation_own_k_s",
    "prearrival_primary_s", "prearrival_validation_s",
]


def fluid_backlog_us(arrival_us: np.ndarray, service_us: np.ndarray, k: int) -> np.ndarray:
    """V_n = max(0, V_{n-1} - k (a_n - a_{n-1})) + C_n, closed form, exact int64."""
    prefix = np.concatenate(([0], np.cumsum(service_us, dtype=np.int64)))
    drain = np.int64(k) * arrival_us
    floor = np.minimum.accumulate(prefix[:-1] - drain)
    return prefix[1:] - drain - floor


@njit(cache=True)
def fluid_backlog_loop(arrival_us, service_us, k):
    """The same recursion step by step: the independent implementation of the check."""
    out = np.empty(len(arrival_us), np.int64)
    v = np.int64(0)
    last = arrival_us[0]
    for n in range(len(arrival_us)):
        v = max(np.int64(0), v - np.int64(k) * (arrival_us[n] - last)) + service_us[n]
        last = arrival_us[n]
        out[n] = v
    return out


def checked_backlog(trace: Trace, k: int) -> np.ndarray:
    """Fluid backlog after each arrival, cross-checked against the loop, with the model's
    two preconditions asserted on the trace itself."""
    limit_us = round(trace.limit_s * MICROS)
    assert int(trace.service_us.max()) <= limit_us, "a service time exceeds L"
    assert bool(np.all(np.diff(trace.arrival_us) >= 0)), "arrivals are not in rank order"
    v = fluid_backlog_us(trace.arrival_us, trace.service_us, k)
    assert np.array_equal(v, fluid_backlog_loop(trace.arrival_us, trace.service_us, k))
    return v


def k_times_promise_us(policy, k: int, limit_us: int) -> tuple[int | None, int | None]:
    """(k * G named, k * the policy's own constant), in microseconds; (None, None) when the
    policy claims no guarantee.  FCFS is the wrapper-free policy with G = 0."""
    if policy.name == "FCFS":
        return 0, 0
    if policy.wrapper == WRAP_NONE:
        return None, None
    named = round(float(PROMISE_IN_NAME.search(policy.name).group(1)) * MICROS) * k
    if policy.wrapper == WRAP_WORK:
        return named, policy.bmax_us + (3 * k - 2) * limit_us
    assert policy.wrapper == WRAP_SKIP
    return named, (policy.skip_count + 2 * k - 2) * limit_us


def bound_row(wait_us, v_us, service_us, policy, k, limit_us) -> dict:
    """Per-job and absolute bound for one policy run.  Units: seconds in the output."""
    named, own = k_times_promise_us(policy, k, limit_us)
    max_wait = int(wait_us.max())
    row = {"max_wait_s": max_wait / MICROS, "bound_kind": "none"}
    if named is None:
        return row
    base = v_us - service_us + (k - 1) * limit_us  # k * the FCFS per-job bound
    slack = base + named - np.int64(k) * wait_us  # k * (bound - wait)
    strict = policy.wrapper == WRAP_WORK
    bound_abs = (int(v_us.max()) + (k - 1) * limit_us + named) / k / MICROS
    row.update(
        bound_abs_s=bound_abs,
        bound_prearrival_s=(int(base.max()) + named) / k / MICROS,
        ratio_max_wait_over_bound_abs=max_wait / MICROS / bound_abs,
        per_job_violations=int((slack < 0).sum()),
        ties=int((slack == 0).sum()),
        min_slack_s=int(slack.min()) / k / MICROS,
        promise_named_s=named / k / MICROS,
        promise_own_s=own / k / MICROS,
        violations_own_constant=int((base + own - np.int64(k) * wait_us < 0).sum()),
        bound_kind="strict" if strict else "non-strict",
    )
    return row


def unique_runs(policies):
    """Policies that differ only in their label are simulated once."""
    seen: dict = {}
    for policy in policies:
        seen.setdefault(dataclasses.replace(policy, name=""), []).append(policy)
    return seen.values()


def run_cell(trace, k, policies, overlay, level, writer, handle) -> list[dict]:
    limit_us = round(trace.limit_s * MICROS)
    v_us = checked_backlog(trace, k)
    rows = []
    for group in unique_runs(policies):
        started = time.time()
        wait_us = simulate(trace, group[0], k).wait_us
        elapsed = time.time() - started
        for policy in group:
            row = {"overlay": overlay, "level": level, "k": k, "policy": policy.name,
                   "n": len(trace), "sigma_s": int(v_us.max()) / MICROS,
                   "sim_seconds": round(elapsed, 1)}
            row.update(bound_row(wait_us, v_us, trace.service_us, policy, k, limit_us))
            writer.writerow(row)
            rows.append(row)
            print(format_row(row), flush=True)
        handle.flush()
    return rows


def format_row(row: dict) -> str:
    head = f"  {row['policy']:18s} max wait {row['max_wait_s']:9.1f} s"
    if row["bound_kind"] == "none":
        return head + "  (no bound claimed)"
    return (head + f"  abs bound {row['bound_abs_s']:9.1f} s"
            f"  ratio {row['ratio_max_wait_over_bound_abs']:.3f}"
            f"  violations {row['per_job_violations']} (own constant "
            f"{row['violations_own_constant']})  ties {row['ties']}"
            f"  min slack {row['min_slack_s']:8.2f} s")


def arrival_service(path: Path) -> tuple[Trace, list[int]]:
    with np.load(path) as z:
        return Trace.from_seconds(z["a"], z["svc"], {}, limit_s=60.0), z["K"].tolist()


def sigma_table(limit_s: float) -> list[dict]:
    """Part b: sigma per overlay and level, primary against validation at the same k."""
    rows = []
    for rep, (prim_path, val_path) in enumerate(zip(PRIMARY, VALIDATION)):
        prim, k_prim = arrival_service(prim_path)
        val, k_val = arrival_service(val_path)
        for level in LEVELS:
            k = k_prim[level]
            vp = checked_backlog(prim, k)
            vv = checked_backlog(val, k)
            vv_own = fluid_backlog_us(val.arrival_us, val.service_us, k_val[level])
            row = {
                "overlay": rep, "level": level, "k_primary": k,
                "sigma_primary_s": int(vp.max()) / MICROS,
                "sigma_validation_s": int(vv.max()) / MICROS,
                "ratio_validation_over_primary": int(vv.max()) / int(vp.max()),
                "k_validation_own": k_val[level],
                "sigma_validation_own_k_s": int(vv_own.max()) / MICROS,
                "prearrival_primary_s": int((vp - prim.service_us).max()) / MICROS,
                "prearrival_validation_s": int((vv - val.service_us).max()) / MICROS,
            }
            rows.append(row)
            print(f"  overlay {rep} level {level} k={k}: sigma primary "
                  f"{row['sigma_primary_s']:9.1f} s, validation {row['sigma_validation_s']:9.1f} s,"
                  f" ratio {row['ratio_validation_over_primary']:.3f}; validation at its own "
                  f"k={k_val[level]}: {row['sigma_validation_own_k_s']:9.1f} s", flush=True)
    return rows


def k1_check(cfg, writer, handle) -> list[dict]:
    """k = 1: FCFS wait must equal V_i - C_i exactly (Lindley)."""
    with np.load(K1) as z:
        stored = {key: val for key, val in SCORE_MAP.items() if key in z.files}
    trace, k, _ = load_overlay(K1, 0, stored, cfg.limit_s)
    assert k == 1
    v_us = checked_backlog(trace, 1)
    fcfs = next(p for p in cfg.policies(1) if p.name == "FCFS")
    diff = simulate(trace, fcfs, 1).wait_us - (v_us - trace.service_us)
    print(f"k1_rep0: n={len(trace):,}, sigma={int(v_us.max()) / MICROS:,.1f} s; "
          f"FCFS wait - (V_i - C_i): max |diff| = {int(np.abs(diff).max())} us, "
          f"nonzero jobs {int((diff != 0).sum())}", flush=True)
    runnable = [p for p in cfg.policies(1) if not p.needs_score or p.score_key in
                set(trace.scores) | {TRUE_SIZE}]
    skipped = sorted({p.name for p in cfg.policies(1)} - {p.name for p in runnable})
    print(f"  k1 policies skipped for want of their score array: {skipped}", flush=True)
    return run_cell(trace, 1, runnable, "k1_rep0", 0, writer, handle)


def primary_runs(cfg, writer, handle) -> list[dict]:
    rows = []
    for rep, path in enumerate(PRIMARY):
        trace, _, _ = load_overlay(path, 0, SCORE_MAP, cfg.limit_s)
        with np.load(path) as z:
            ks = z["K"].tolist()
        for level in LEVELS:
            k = ks[level]
            print(f"primary overlay {rep} level {level}: k={k}, n={len(trace):,}", flush=True)
            rows += run_cell(trace, k, cfg.policies(k), rep, level, writer, handle)
    return rows


def advance_quote(sigma_rows: list[dict], bound_rows: list[dict], limit_s: float) -> None:
    """Would the bound quoted from validation alone have covered the realised waits?"""
    print("\nadvance quote from validation sigma (paired overlay, and max over the five):")
    for level in LEVELS:
        cells = [r for r in sigma_rows if r["level"] == level]
        worst_val = max(r["sigma_validation_s"] for r in cells)
        for r in cells:
            k = r["k_primary"]
            for rb in bound_rows:
                if (rb["overlay"], rb["level"]) != (r["overlay"], level):
                    continue
                if rb["bound_kind"] == "none" or not rb["policy"].startswith(("FCFS", "Guard(")):
                    continue
                g = rb["promise_named_s"]
                paired = (r["sigma_validation_s"] + (k - 1) * limit_s) / k + g
                pooled = (worst_val + (k - 1) * limit_s) / k + g
                print(f"  overlay {r['overlay']} level {level} {rb['policy']:12s} realised max "
                      f"{rb['max_wait_s']:8.1f} s | primary bound {rb['bound_abs_s']:8.1f} | "
                      f"validation-quoted {paired:8.1f} (off {paired - rb['bound_abs_s']:+8.1f},"
                      f" covers {rb['max_wait_s'] < paired}) | max-of-5 quote {pooled:8.1f}"
                      f" (covers {rb['max_wait_s'] < pooled})")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 23), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(outputs: list[Path]) -> None:
    manifest_path = ROOT / "outputs" / "dev_tables" / "manifest.json"
    recorded = {}
    for item in json.loads(manifest_path.read_text(encoding="utf-8")).get("inputs", []):
        if isinstance(item, dict) and "path" in item:
            recorded[item["path"]] = item.get("sha256")
    inputs = {}
    for path in [*PRIMARY, *VALIDATION, K1]:
        rel = path.relative_to(ROOT).as_posix()
        inputs[rel] = {"sha256": sha256(path), "manifest_sha256": recorded.get(rel)}
    doc = {
        "script": {"path": Path(__file__).name, "sha256": sha256(Path(__file__))},
        "config": {"path": "configs/main.yaml", "sha256": sha256(CONFIG)},
        "inputs": inputs,
        "outputs": {p.name: sha256(p) for p in outputs},
    }
    (OUT / "run_manifest.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    for rel, item in inputs.items():
        print(f"  {rel}: {item['sha256'][:16]}  manifest {str(item['manifest_sha256'])[:16]}")


def main() -> None:
    started = time.time()
    cfg = cfgmod.load(CONFIG)
    print(f"L = {cfg.limit_s} s; promises {cfg.promises_s}", flush=True)
    print("\n[b] sigma, primary against validation, at the primary k of each level", flush=True)
    sigma_rows = sigma_table(cfg.limit_s)
    with open(OUT / "envelope_sigma_validation.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SIGMA_FIELDS)
        writer.writeheader()
        writer.writerows(sigma_rows)
    with open(OUT / "envelope_bound.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BOUND_FIELDS)
        writer.writeheader()
        print("\n[k1] single server", flush=True)
        k1_check(cfg, writer, fh)
        print("\n[a] primary overlays", flush=True)
        rows = primary_runs(cfg, writer, fh)
    checked = [r for r in rows if r["bound_kind"] != "none"]
    print(f"\n[a] summary: {len(checked)} checked (cell, policy) rows, per-job violations "
          f"{sum(r['per_job_violations'] for r in checked)}, own-constant violations "
          f"{sum(r['violations_own_constant'] for r in checked)}, ties "
          f"{sum(r['ties'] for r in checked)}; max ratio "
          f"{max(r['ratio_max_wait_over_bound_abs'] for r in checked):.4f}; min slack "
          f"{min(r['min_slack_s'] for r in checked):.3f} s", flush=True)
    advance_quote(sigma_rows, rows, cfg.limit_s)
    print("\ninput hashes (this run / outputs/dev_tables/manifest.json):", flush=True)
    write_manifest([OUT / "envelope_bound.csv", OUT / "envelope_sigma_validation.csv"])
    print(f"\ntotal {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
