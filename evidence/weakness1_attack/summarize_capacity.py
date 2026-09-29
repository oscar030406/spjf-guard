"""Summarise the frozen capacity sweep after all 156 cells are complete.

This script is intentionally independent of the project package.  It reads only the
JSON/NPZ cell products, refuses a partial or mixed-protocol run, and writes aggregate
tables, coverage metadata, selected numbers, and (when matplotlib is available) a
four-panel figure.  It does not run a queue simulation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np


HERE = Path(__file__).resolve().parent
MPLCONFIG = HERE / "cache" / "matplotlib"
MPLCONFIG.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(MPLCONFIG)
CELLS = HERE / "cells"
COMMON_K = list(range(1, 21))
EXTENSION_K = list(range(21, 77))
REPS = list(range(5))
RESAMPLES = 2000
LIMIT_S = 60.0
WEEK_S = 7.0 * 24.0 * 3600.0
COMMON_POLICIES = ["FCFS", "SJF", "SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)"]
EXTENSION_POLICIES = ["FCFS", "SJF", "SPJF-E", "Guard(600)"]
INFERENCE_POLICIES = ["SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)"]
PROMISE = {"Guard(300)": 300.0, "Guard(600)": 600.0, "Guard(1200)": 1200.0}
METRICS = ("q99", "mean", "max_excess", "harm")

# Kept byte-for-byte equivalent to capacity_sweep.py's JSON-hashed parameter object.
PARAMETERS = {
    "reps": list(range(5)),
    "common_k": list(range(1, 21)),
    "extension_rep": 0,
    "extension_k": list(range(21, 77)),
    "resamples": 2000,
    "seed": 20260921,
    "score": "tweedie",
    "limit_s": 60.0,
    "window": 1 << 22,
    "guard_settings": [
        [300.0, 15.0, 0.5, 0.0],
        [600.0, 30.0, 0.75, 0.0],
        [1200.0, 0.0, 0.0, 4.0],
    ],
}
EXPECTED_PROTOCOL = hashlib.sha256(
    json.dumps(PARAMETERS, sort_keys=True).encode()
).hexdigest()
EXPECTED_CELLS = {(rep, k) for rep in REPS for k in COMMON_K} | {
    (0, k) for k in EXTENSION_K
}


def _finite(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return value
    return x if math.isfinite(x) else None


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return _finite(value)
    return value


def _atomic_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def _write_json(path: Path, value) -> None:
    _atomic_text(path, json.dumps(_json_safe(value), indent=2, allow_nan=False) + "\n")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty table {path}")
    fields = list(rows[0])
    if any(list(row) != fields for row in rows):
        raise AssertionError(f"rows of {path.name} do not have one stable schema")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if _finite(v) is None else v for k, v in row.items()})
    tmp.replace(path)


def _point_interval(draws: np.ndarray) -> tuple[float, float]:
    finite = np.asarray(draws[1:], dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return float("nan"), float("nan")
    lo, hi = np.percentile(finite, [2.5, 97.5])
    return float(lo), float(hi)


def _ratio_interval(draws: np.ndarray) -> tuple[float, float, bool]:
    """A ratio interval exists only when its point and all declared draws exist."""
    point = float(draws[0])
    replicates = np.asarray(draws[1:], dtype=np.float64)
    complete = bool(np.isfinite(point) and np.isfinite(replicates).all())
    if not complete:
        return float("nan"), float("nan"), False
    lo, hi = np.percentile(replicates, [2.5, 97.5])
    return float(lo), float(hi), True


def _ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    out = np.full_like(numerator, np.nan, dtype=np.float64)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (denominator > 0.0)
    out[valid] = numerator[valid] / denominator[valid]
    return out


def _cell_paths(rep: int, k: int) -> tuple[Path, Path]:
    stem = CELLS / f"rep{rep}_k{k}"
    return stem.with_suffix(".json"), stem.with_suffix(".npz")


def load_cell(rep: int, k: int) -> dict:
    json_path, npz_path = _cell_paths(rep, k)
    if not json_path.is_file() or not npz_path.is_file():
        missing = [str(p) for p in (json_path, npz_path) if not p.is_file()]
        raise RuntimeError(f"partial sweep: missing {missing}")
    try:
        document = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable cell metadata {json_path}: {exc}") from exc
    if document.get("protocol") != EXPECTED_PROTOCOL:
        raise RuntimeError(
            f"mixed protocol in {json_path}: {document.get('protocol')} != {EXPECTED_PROTOCOL}"
        )
    if document.get("parameters") != PARAMETERS:
        raise RuntimeError(f"parameter object changed in {json_path}")
    expected_policies = COMMON_POLICIES if k <= 20 else EXTENSION_POLICIES
    rows = document.get("rows", [])
    if [row.get("policy") for row in rows] != expected_policies:
        raise RuntimeError(
            f"policy order in {json_path} is {[r.get('policy') for r in rows]}, "
            f"expected {expected_policies}"
        )
    for row in rows:
        if int(row.get("rep", -1)) != rep or int(row.get("k", -1)) != k:
            raise RuntimeError(f"cell coordinates disagree inside {json_path}")
        if int(row.get("n", 0)) <= 0:
            raise RuntimeError(f"nonpositive job count in {json_path}")
    expected_arrays = {
        f"{policy}_{metric}" for policy in expected_policies for metric in METRICS
    }
    with np.load(npz_path, allow_pickle=False) as store:
        if set(store.files) != expected_arrays:
            missing = sorted(expected_arrays - set(store.files))
            extra = sorted(set(store.files) - expected_arrays)
            raise RuntimeError(f"array schema in {npz_path}: missing={missing}, extra={extra}")
        draws = {name: np.asarray(store[name], dtype=np.float64).copy() for name in store.files}
    expected_shape = (RESAMPLES + 1,)
    wrong = {name: value.shape for name, value in draws.items() if value.shape != expected_shape}
    if wrong:
        raise RuntimeError(f"draw shapes in {npz_path}: {wrong}, expected {expected_shape}")
    if any(not np.isfinite(value).all() for value in draws.values()):
        raise RuntimeError(f"nonfinite primitive draws in {npz_path}")
    by_policy = {row["policy"]: row for row in rows}
    for policy in expected_policies:
        if not np.isclose(
            draws[f"{policy}_q99"][0], by_policy[policy]["p99_deadline_s"], atol=1e-7
        ):
            raise RuntimeError(f"point q99 does not match its draw in {json_path}, {policy}")
        if not np.isclose(
            draws[f"{policy}_mean"][0], by_policy[policy]["mean_s"], atol=1e-9
        ):
            raise RuntimeError(f"point mean does not match its draw in {json_path}, {policy}")
    return {"document": document, "rows": by_policy, "draws": draws}


def _aggregate_metric(cells: list[dict], policy: str, metric: str) -> np.ndarray:
    values = np.stack([cell["draws"][f"{policy}_{metric}"] for cell in cells])
    if metric in ("max_excess", "harm"):
        return np.max(values, axis=0)
    return np.mean(values, axis=0)


def aggregate_capacity(k: int, cells: list[dict], scope: str) -> tuple[list[dict], dict]:
    policies = COMMON_POLICIES if k <= 20 else EXTENSION_POLICIES
    q = {p: _aggregate_metric(cells, p, "q99") for p in policies}
    means = {p: _aggregate_metric(cells, p, "mean") for p in policies}
    max_excess = {p: _aggregate_metric(cells, p, "max_excess") for p in policies}
    harm = {p: _aggregate_metric(cells, p, "harm") for p in policies}
    fcfs_q, sjf_q, spjf_q = q["FCFS"], q["SJF"], q["SPJF-E"]
    denominator = fcfs_q - sjf_q
    max_wait_all = max(float(cell["rows"][p]["max_wait_s"]) for cell in cells for p in policies)
    rows = []
    derived = {}
    for policy in policies:
        source = [cell["rows"][policy] for cell in cells]
        improvement = fcfs_q - q[policy]
        gap = _ratio(improvement, denominator)
        reduction = 100.0 * _ratio(improvement, fcfs_q)
        promise_cost = q[policy] - spjf_q if policy in PROMISE else np.full_like(q[policy], np.nan)
        derived[policy] = {
            "improvement": improvement,
            "gap": gap,
            "reduction": reduction,
            "promise_cost": promise_cost,
        }
        p99_lo, p99_hi = _point_interval(q[policy])
        mean_lo, mean_hi = _point_interval(means[policy])
        excess_stability_lo, excess_stability_hi = _point_interval(max_excess[policy])
        harm_stability_lo, harm_stability_hi = _point_interval(harm[policy])
        imp_lo, imp_hi = _point_interval(improvement)
        gap_lo, gap_hi, gap_interval_available = _ratio_interval(gap)
        red_lo, red_hi, reduction_interval_available = _ratio_interval(reduction)
        cost_lo, cost_hi = _point_interval(promise_cost)
        promise = PROMISE.get(policy, float("nan"))
        floor_s = float(source[0]["floor_s"])
        fcfs_point = float(fcfs_q[0])
        simulated = sum(row.get("execution", "simulated") == "simulated" for row in source)
        certified = sum(
            row.get("execution", "simulated") == "certified_identical" for row in source
        )
        validations = sum(bool(row.get("certificate_checked_against_kernel")) for row in source)
        is_guard = policy in PROMISE
        row = {
            "scope": scope,
            "policy": policy,
            "k": k,
            "n_overlays": len(cells),
            "n_jobs_per_overlay": int(source[0]["n"]),
            "p99_deadline_s": float(q[policy][0]),
            "p99_deadline_lo": p99_lo,
            "p99_deadline_hi": p99_hi,
            "mean_wait_s": float(means[policy][0]),
            "mean_wait_lo": mean_lo,
            "mean_wait_hi": mean_hi,
            "p99_all_s_mean_across_overlays": float(np.mean([r["p99_all_s"] for r in source])),
            "max_wait_s_across_overlays": float(max(r["max_wait_s"] for r in source)),
            "max_wait_s_across_policies": max_wait_all,
            "max_wait_plus_L_weeks": (float(max(r["max_wait_s"] for r in source)) + LIMIT_S) / WEEK_S,
            "max_wait_across_policies_plus_L_weeks": (max_wait_all + LIMIT_S) / WEEK_S,
            "max_excess_s": float(max_excess[policy][0]),
            "max_excess_resample_stability_lo": excess_stability_lo,
            "max_excess_resample_stability_hi": excess_stability_hi,
            "harm_s": float(harm[policy][0]),
            "harm_resample_stability_lo": harm_stability_lo,
            "harm_resample_stability_hi": harm_stability_hi,
            "absolute_p99_improvement_s": float(improvement[0]),
            "absolute_p99_improvement_lo": imp_lo,
            "absolute_p99_improvement_hi": imp_hi,
            "simultaneous_improvement_lo": float("nan"),
            "simultaneous_improvement_hi": float("nan"),
            "gap_closed": float(gap[0]) if np.isfinite(gap[0]) else float("nan"),
            "gap_closed_lo": gap_lo,
            "gap_closed_hi": gap_hi,
            "gap_valid_bootstrap_draws": int(np.isfinite(gap[1:]).sum()),
            "gap_total_bootstrap_draws": RESAMPLES,
            "gap_interval_all_draws_valid": gap_interval_available,
            "reduction_pct": float(reduction[0]) if np.isfinite(reduction[0]) else float("nan"),
            "reduction_pct_lo": red_lo,
            "reduction_pct_hi": red_hi,
            "reduction_valid_bootstrap_draws": int(np.isfinite(reduction[1:]).sum()),
            "reduction_total_bootstrap_draws": RESAMPLES,
            "reduction_interval_all_draws_valid": reduction_interval_available,
            "promise_cost_vs_SPJF_s": (
                float(promise_cost[0]) if np.isfinite(promise_cost[0]) else float("nan")
            ),
            "promise_cost_lo": cost_lo,
            "promise_cost_hi": cost_hi,
            "positive_wait_probability_mean": float(
                np.mean([r["positive_wait_jobs"] / r["n"] for r in source])
            ),
            "guard_forced_dispatches_total": (
                int(sum(r["forced_dispatches"] for r in source)) if is_guard else 0
            ),
            "guard_fired_fraction_mean": (
                float(np.mean([r["fired_fraction"] for r in source])) if is_guard else 0.0
            ),
            "guard_fired_queue_weighted_mean": (
                float(np.mean([r["fired_queue_weighted"] for r in source]))
                if is_guard
                else 0.0
            ),
            "bound_checks_total": int(sum(r["bound_checks"] for r in source)),
            "bound_violations_total": int(sum(r["bound_violations"] for r in source)),
            "max_bound_violation_s": float(max(r["max_bound_violation_s"] for r in source)),
            "max_fraction_of_allowed_excess": float(
                max(r["max_fraction_of_allowed_excess"] for r in source)
            ),
            "simulated_overlay_cells": simulated,
            "certified_identical_overlay_cells": certified,
            "certificate_kernel_validations": validations,
            "certificate_max_in_us": max(
                (
                    int(r["certificate_max_in_us"])
                    for r in source
                    if r.get("certificate_max_in_us") is not None
                ),
                default=0,
            ),
            "theorem_floor_s": floor_s,
            "fcfs_p99_deadline_s": fcfs_point,
            "fcfs_p99_div_floor": fcfs_point / floor_s if floor_s > 0 else float("nan"),
            "floor_eligible_mean_fcfs_p99_gt_floor": bool(fcfs_point > floor_s),
            "overlays_fcfs_p99_gt_floor": sum(float(cell['rows']['FCFS']['p99_deadline_s']) > floor_s for cell in cells),
            "overlays_in_scope": len(cells),
            "promise_G_s": promise,
            "fcfs_p99_div_G": fcfs_point / promise if np.isfinite(promise) else float("nan"),
            "G_below_fcfs_p99": bool(fcfs_point > promise) if np.isfinite(promise) else False,
            "busy_hour_offered_load_mean": float(
                np.mean([r["busy_hour_offered_load"] for r in source])
            ),
            "b0_s": float(source[0]["b0_s"]),
            "eta": float(source[0]["eta"]),
            "gamma_s": float(source[0]["gamma_s"]),
            "bmax_s": float(source[0]["bmax_s"]),
        }
        rows.append(row)
    return rows, derived


def simultaneous_band(common_rows: list[dict], derived_by_k: dict) -> dict:
    coordinates = []
    samples = []
    for k in COMMON_K:
        for policy in INFERENCE_POLICIES:
            coordinates.append((k, policy))
            samples.append(derived_by_k[k][policy]["improvement"])
    matrix = np.stack(samples, axis=1)
    if matrix.shape != (RESAMPLES + 1, 80):
        raise AssertionError(f"simultaneous family is {matrix.shape}, expected {(RESAMPLES + 1, 80)}")
    estimate = matrix[0]
    star = matrix[1:]
    se = np.std(star, axis=0, ddof=1)
    positive_scale = se > 0.0
    if not positive_scale.any():
        critical = 0.0
    else:
        t = np.max(np.abs((star[:, positive_scale] - estimate[positive_scale]) / se[positive_scale]), axis=1)
        critical = float(np.percentile(t, 95.0))
    low = estimate - critical * se
    high = estimate + critical * se
    low[~positive_scale] = estimate[~positive_scale]
    high[~positive_scale] = estimate[~positive_scale]
    bands = {(k, p): (float(lo), float(hi), float(scale)) for (k, p), lo, hi, scale in zip(coordinates, low, high, se)}
    for row in common_rows:
        key = (int(row["k"]), row["policy"])
        if key in bands:
            row["simultaneous_improvement_lo"] = bands[key][0]
            row["simultaneous_improvement_hi"] = bands[key][1]
    return {
        "method": "centered coordinate-standardized single-bootstrap max-|t| band",
        "level": 0.95,
        "critical_value": critical,
        "coordinates": len(coordinates),
        "bootstrap_draws": RESAMPLES,
        "zero_variance_coordinates": [
            {"k": k, "policy": p} for (k, p), scale in zip(coordinates, se) if scale == 0.0
        ],
        "coverage_scope": (
            "conditional calendar-week uncertainty on the five constructed development overlays; "
            "no semester, predictor-fit, structural queue-model, or demand-feedback uncertainty"
        ),
    }


def _selected_numbers(common_rows: list[dict], extension_rows: list[dict], band: dict) -> dict:
    by_policy = {p: [r for r in common_rows if r["policy"] == p] for p in INFERENCE_POLICIES}
    support = {}
    for policy, rows in by_policy.items():
        support[policy] = {
            "simultaneous_positive_k": [
                int(r["k"]) for r in rows if r["simultaneous_improvement_lo"] > 0.0
            ],
            "simultaneous_not_positive_k": [
                int(r["k"]) for r in rows if r["simultaneous_improvement_lo"] <= 0.0
            ],
            "min_point_improvement_s": min(r["absolute_p99_improvement_s"] for r in rows),
            "min_simultaneous_lower_s": min(r["simultaneous_improvement_lo"] for r in rows),
            "max_point_improvement_s": max(r["absolute_p99_improvement_s"] for r in rows),
        }
    all_rows = common_rows + extension_rows
    return {
        "protocol": EXPECTED_PROTOCOL,
        "five_overlay_capacity_range": [1, 20],
        "overlay0_capacity_range": [1, 76],
        "simultaneous_band": band,
        "support_by_policy": support,
        "largest_observed_wait_s": max(r["max_wait_s_across_overlays"] for r in all_rows),
        "largest_wait_plus_L_weeks": max(r["max_wait_plus_L_weeks"] for r in all_rows),
        "note": (
            "The wait-plus-L/week quantity is a conservative diagnostic for possible "
            "cross-week dependence. The reported bootstrap resamples realised outcomes; "
            "it is not a queue-process bootstrap."
        ),
    }


def make_figure(common_rows: list[dict], extension_rows: list[dict], log: list[str]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # optional output; tables remain the acceptance artefacts
        log.append(f"figure skipped: matplotlib unavailable ({exc})")
        return []

    colors = {
        "FCFS": "#313638",
        "SJF": "#6c757d",
        "SPJF-E": "#0077b6",
        "Guard(300)": "#d62828",
        "Guard(600)": "#f77f00",
        "Guard(1200)": "#2a9d8f",
    }

    def shade_integer_runs(ax, x, selected) -> None:
        """Shade complete integer-capacity runs without implying continuity in k."""
        runs = []
        start = None
        previous = None
        for k, keep in zip(x, selected):
            if keep and start is None:
                start = previous = k
            elif keep and k == previous + 1:
                previous = k
            elif keep:
                runs.append((start, previous))
                start = previous = k
            elif start is not None:
                runs.append((start, previous))
                start = previous = None
        if start is not None:
            runs.append((start, previous))
        for index, (left, right) in enumerate(runs):
            ax.axvspan(
                left - 0.5,
                right + 0.5,
                color="#8ecae6",
                alpha=0.16,
                lw=0,
                label=("Mean FCFS p99 > theorem floor (feasibility screen)" if index == 0 else None),
            )

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    ax = axes[0, 0]
    p99_rows = {}
    for policy in COMMON_POLICIES:
        rows = [r for r in common_rows if r["policy"] == policy]
        p99_rows[policy] = rows
        ax.plot([r["k"] for r in rows], [r["p99_deadline_s"] for r in rows], marker="o", ms=3, label=policy, color=colors[policy])
    for policy in ("FCFS", "Guard(600)"):
        rows = p99_rows[policy]
        x = np.array([r["k"] for r in rows])
        lo = np.array([r["p99_deadline_lo"] for r in rows])
        hi = np.array([r["p99_deadline_hi"] for r in rows])
        ax.fill_between(
            x,
            lo,
            hi,
            color=colors[policy],
            alpha=0.14,
            linewidth=0,
            label=f"{policy}: 95% pointwise resampling",
        )
    fcfs_rows = p99_rows["FCFS"]
    x_common = np.array([r["k"] for r in fcfs_rows])
    floor = np.array([r["theorem_floor_s"] for r in fcfs_rows])
    eligible = np.array([r["floor_eligible_mean_fcfs_p99_gt_floor"] for r in fcfs_rows])
    shade_integer_runs(ax, x_common, eligible)
    ax.plot(
        x_common,
        floor,
        color="#6a4c93",
        ls="--",
        lw=1.4,
        label="theorem floor (not the promise G)",
    )
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set(title="Deadline-window p99 wait, five-overlay mean", xlabel="servers k", ylabel="seconds")
    ax.set_xlim(0.5, 20.5)
    ax.grid(alpha=0.25)
    ax.legend(ncol=2, fontsize=7)

    ax = axes[0, 1]
    for policy in INFERENCE_POLICIES:
        rows = [r for r in common_rows if r["policy"] == policy]
        ax.plot([r["k"] for r in rows], [r["gap_closed"] for r in rows], marker="o", ms=3, label=policy, color=colors[policy])
    guard600 = [r for r in common_rows if r["policy"] == "Guard(600)"]
    gx = np.array([r["k"] for r in guard600])
    valid = np.array(
        [
            r["gap_valid_bootstrap_draws"] == RESAMPLES
            and np.isfinite(r["gap_closed_lo"])
            and np.isfinite(r["gap_closed_hi"])
            for r in guard600
        ]
    )
    glo = np.array([r["gap_closed_lo"] if ok else np.nan for r, ok in zip(guard600, valid)])
    ghi = np.array([r["gap_closed_hi"] if ok else np.nan for r, ok in zip(guard600, valid)])
    ax.fill_between(
        gx,
        glo,
        ghi,
        where=valid,
        color=colors["Guard(600)"],
        alpha=0.18,
        linewidth=0,
        label="Guard(600): 95% resampling; all 2,000 ratios valid",
    )
    ax.axhline(0.0, color="black", lw=0.8)
    ax.set(title="FCFS-to-SJF p99 gap closed", xlabel="servers k", ylabel="fraction")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)

    ax = axes[1, 0]
    for policy in ["SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)"]:
        rows = [r for r in common_rows if r["policy"] == policy]
        color = colors[policy]
        ax.plot([r["k"] for r in rows], [r["max_excess_s"] for r in rows], label=f"{policy} max excess", color=color)
        ax.plot([r["k"] for r in rows], [r["harm_s"] for r in rows], ls="--", label=f"{policy} harm", color=color, alpha=0.8)
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set(
        title="Realised worst excess and harm\n(points; no population-maximum interval)",
        xlabel="servers k",
        ylabel="seconds",
    )
    ax.grid(alpha=0.25)
    ax.legend(ncol=2, fontsize=7)

    ax = axes[1, 1]
    for policy in ["FCFS", "SJF", "SPJF-E", "Guard(600)"]:
        rows = [r for r in extension_rows if r["policy"] == policy]
        ax.plot([r["k"] for r in rows], [r["positive_wait_probability_mean"] for r in rows], label=policy, color=colors[policy])
    ax.set_yscale("symlog", linthresh=1e-8)
    ax.set(title="Positive-wait probability, overlay 0", xlabel="servers k", ylabel="share of jobs")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)

    fig.suptitle(
        "Capacity envelope — development conditional paired-week resampling\n"
        "95% intervals; shading compares mean FCFS p99 with the floor, not the chosen promise G\n"
        "SPJF-E and Guard use the archived embedded Tweedie fit",
        fontsize=12,
    )
    svg = HERE / "capacity_envelope.svg"
    png = HERE / "capacity_envelope.png"
    fig.savefig(svg)
    fig.savefig(png, dpi=180)
    plt.close(fig)
    log.append(f"wrote {svg.name} and {png.name}")

    band_fig, band_axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for ax, policy in zip(band_axes.flat, INFERENCE_POLICIES):
        rows = [r for r in common_rows if r["policy"] == policy]
        x = np.array([r["k"] for r in rows])
        estimate = np.array([r["absolute_p99_improvement_s"] for r in rows])
        low = np.array([r["simultaneous_improvement_lo"] for r in rows])
        high = np.array([r["simultaneous_improvement_hi"] for r in rows])
        ax.fill_between(
            x,
            low,
            high,
            color=colors[policy],
            alpha=0.20,
            linewidth=0,
            label="95% simultaneous resampling band (80 comparisons)",
        )
        ax.plot(x, estimate, color=colors[policy], marker="o", ms=3, label="D = FCFS p99 - policy p99")
        ax.axhline(0.0, color="black", lw=1.0, label="zero effect")
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_xlim(0.5, 20.5)
        ax.set(title=policy, xlabel="servers k", ylabel="absolute p99 improvement D (s)")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7)
    band_fig.suptitle(
        "Capacity-wide p99 improvement — development conditional paired-week resampling\n"
        "One simultaneous 95% family: 20 capacities × SPJF-E / Guard(300) / Guard(600) / Guard(1200)\n"
        "SPJF-E and Guard use the archived embedded Tweedie fit",
        fontsize=12,
    )
    band_svg = HERE / "capacity_improvement_bands.svg"
    band_png = HERE / "capacity_improvement_bands.png"
    band_fig.savefig(band_svg)
    band_fig.savefig(band_png, dpi=180)
    plt.close(band_fig)
    log.append(f"wrote {band_svg.name} and {band_png.name}")
    return [svg.name, png.name, band_svg.name, band_png.name]


def main() -> int:
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    log = [f"protocol {EXPECTED_PROTOCOL}", f"required cells {len(EXPECTED_CELLS)}"]

    missing = []
    for rep, k in sorted(EXPECTED_CELLS):
        for path in _cell_paths(rep, k):
            if not path.is_file():
                missing.append(str(path.relative_to(HERE)))
    if missing:
        raise RuntimeError(
            f"refusing a partial summary: {len(missing)} required files are missing; "
            f"first entries: {missing[:10]}"
        )

    cells = {(rep, k): load_cell(rep, k) for rep, k in sorted(EXPECTED_CELLS)}
    if len(cells) != 156:
        raise AssertionError(f"loaded {len(cells)} cells, expected 156")
    log.append("all 156 JSON/NPZ pairs passed protocol, parameter, policy, shape, and point checks")

    common_rows = []
    common_derived = {}
    for k in COMMON_K:
        rows, derived = aggregate_capacity(
            k, [cells[(rep, k)] for rep in REPS], "five_overlay_mean_or_worst"
        )
        common_rows.extend(rows)
        common_derived[k] = derived
    band = simultaneous_band(common_rows, common_derived)
    log.append(
        f"simultaneous 95% max-|t| band: {band['coordinates']} coordinates, "
        f"critical={band['critical_value']:.6g}"
    )

    extension_rows = []
    for k in COMMON_K + EXTENSION_K:
        rows, _ = aggregate_capacity(k, [cells[(0, k)]], "overlay0_full_envelope")
        extension_rows.extend(rows)

    _write_csv(HERE / "capacity_curve.csv", common_rows)
    _write_csv(HERE / "extension_curve.csv", extension_rows)
    numbers = _selected_numbers(common_rows, extension_rows, band)

    guarded_source_rows = [
        row
        for cell in cells.values()
        for row in cell["rows"].values()
        if row["policy"] in PROMISE
    ]
    guard_execution = {
        "source_guard_policy_cells": len(guarded_source_rows),
        "simulated": sum(
            r.get("execution", "simulated") == "simulated" for r in guarded_source_rows
        ),
        "certified_identical": sum(
            r.get("execution", "simulated") == "certified_identical"
            for r in guarded_source_rows
        ),
        "kernel_validations": sum(
            bool(r.get("certificate_checked_against_kernel")) for r in guarded_source_rows
        ),
        "bound_checks": sum(int(r["bound_checks"]) for r in guarded_source_rows),
        "bound_violations": sum(int(r["bound_violations"]) for r in guarded_source_rows),
        "max_reported_bound_violation_s": max(
            float(r["max_bound_violation_s"]) for r in guarded_source_rows
        ),
    }
    numbers["guard_execution"] = guard_execution
    coverage = {
        "protocol": EXPECTED_PROTOCOL,
        "parameters": PARAMETERS,
        "complete_cells": len(cells),
        "expected_cells": 156,
        "source_json_files": 156,
        "source_npz_files": 156,
        "common_scope": {"overlays": REPS, "capacities": [1, 20], "policies": COMMON_POLICIES},
        "extension_scope": {"overlay": 0, "capacities": [1, 76], "policies_above_20": EXTENSION_POLICIES},
        "simultaneous_band": band,
        "ratio_validity": {
            "gap_min_valid_bootstrap_draws": min(r["gap_valid_bootstrap_draws"] for r in common_rows),
            "reduction_min_valid_bootstrap_draws": min(r["reduction_valid_bootstrap_draws"] for r in common_rows),
            "gap_rows_with_interval": sum(bool(r["gap_interval_all_draws_valid"]) for r in common_rows),
            "reduction_rows_with_interval": sum(
                bool(r["reduction_interval_all_draws_valid"]) for r in common_rows
            ),
            "interval_rule": (
                "a ratio interval is reported only when the observed ratio and all "
                "2,000 declared bootstrap ratios are finite with positive denominators; "
                "otherwise lo/hi are missing"
            ),
            "invalid_draws_are_never_conditioned_away": True,
        },
        "realised_maximum_resampling": {
            "point_fields": ["max_excess_s", "harm_s"],
            "stability_fields": [
                "max_excess_resample_stability_lo",
                "max_excess_resample_stability_hi",
                "harm_resample_stability_lo",
                "harm_resample_stability_hi",
            ],
            "interpretation": (
                "conditional empirical week-resampling stability ranges for realised "
                "trace maxima; they are not confidence intervals for population maxima"
            ),
        },
        "guard_execution": guard_execution,
        "simultaneous_positive_support": numbers["support_by_policy"],
        "cross_week_diagnostic": {
            "max_wait_s": numbers["largest_observed_wait_s"],
            "max_wait_plus_L_weeks": numbers["largest_wait_plus_L_weeks"],
            "interpretation": (
                "upper diagnostic for how many week lengths one realised wait plus one "
                "job limit spans; it reveals potential cross-week dependence but does not "
                "turn the outcome-resampling procedure into a queue-process bootstrap"
            ),
        },
        "firing_field_note": (
            "All non-guard fired/forced fields in the summary are defined as zero. The "
            "production kernel's raw FCFS forced flag marks FIFO selection, not a guard "
            "override, and is therefore not a guard firing statistic."
        ),
        "limitations": [
            "development data only; no held-out, structural, or predictor-fit uncertainty",
            "the five overlays reuse the same source jobs and are not independent datasets",
            "week multiplicities resample realised outcomes without rerunning queue state",
            "k=21..76 is overlay 0 only, and above k=20 only Guard(600) is present",
            "ratios are undefined whenever their resampled denominator is nonpositive",
        ],
    }
    figures = make_figure(common_rows, extension_rows, log)
    coverage["figures"] = figures
    elapsed = {
        "wall_s": time.perf_counter() - started_wall,
        "cpu_s": time.process_time() - started_cpu,
    }
    coverage["summary_timing"] = elapsed
    numbers["summary_timing"] = elapsed
    _write_json(HERE / "coverage.json", coverage)
    _write_json(HERE / "summary_numbers.json", numbers)
    log.extend(
        [
            f"wrote capacity_curve.csv ({len(common_rows)} rows)",
            f"wrote extension_curve.csv ({len(extension_rows)} rows)",
            "wrote coverage.json and summary_numbers.json",
            f"timing wall_s={elapsed['wall_s']:.6f} cpu_s={elapsed['cpu_s']:.6f}",
            (
                "interval scope: conditional paired-week outcome resampling; not a "
                "queue-process bootstrap and not structural uncertainty"
            ),
            (
                "ratio intervals require 2,000/2,000 finite draws; maximum resampling "
                "ranges are stability diagnostics, not population-maximum confidence intervals"
            ),
        ]
    )
    _atomic_text(HERE / "out_summarize_capacity.txt", "\n".join(log) + "\n")
    print("\n".join(log), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
