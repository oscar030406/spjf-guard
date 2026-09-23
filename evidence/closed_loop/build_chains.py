"""Per-user submission chains and the recorded think time, on a development overlay.

Writes one npz per overlay into out/chains/: for every job of the overlay, the index of
the same user's (same copy's) previous submission, the recorded offset

    delta_i = a_i - done_pred,   done_pred = a_pred + C_pred

and the assignment deadline of the job on the overlay's own calendar.  Nothing here
simulates; this is the observational half of the study.

Run from the repository root:

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
        OMP_NUM_THREADS=4 uv run --no-sync python evidence/closed_loop/build_chains.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CHAINS = OUT / "chains"


def load_row_tables():
    """(user, deadline, arrival) per submission row of the development cache."""
    from build_overlays import clock_from  # noqa: E402
    from spjf_guard import config as cfgmod  # noqa: E402
    from spjf_guard.data import sealed  # noqa: E402
    from spjf_guard.data.events import (  # noqa: E402
        arrival_and_availability,
        load_events,
        prepare,
        static_submission_columns,
    )

    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    terms = list(cfg["overlay"]["pools"]["primary"])
    sealed.guard_semesters(terms, ROOT, unseal=False)
    events = load_events(cfg.data_path("cache_dir"), cfg["data"]["events_file"], None)
    prepared = prepare(
        events,
        seed=int(cfg["predictor"]["seed"]),
        limit_s=cfg.limit_s,
        train_terms=cfg["semesters"]["train"],
        zero_cost_drop_terms=cfg["clock"]["drop_zero_cost_terms"],
        jitter_key=cfg["clock"]["jitter"]["key"],
    )
    static = static_submission_columns(events, prepared)
    arrival, _ = arrival_and_availability(prepared, clock_from(cfg))
    del events
    rows = prepared.submission_rows
    return {
        "user": prepared.user[rows].astype(np.int64),
        "a_end": np.asarray(static["a_end"], np.float64),
        "a_start": np.asarray(static["a_start"], np.float64),
        "arr": arrival[rows].astype(np.float64),
        "terms": terms,
        "limit_s": float(cfg.limit_s),
        "deadline_window_s": float(cfg["metrics"]["deadline_window_s"]),
    }


def chains_for(path: Path, tables: dict) -> dict:
    with np.load(path) as z:
        a = z["a"].astype(np.float64)
        svc = z["svc"].astype(np.float64)
        job_row = z["job_row"].astype(np.int64)
        copy_entry = z["copy_entry"].astype(np.int64)
        dl = z["dl"].astype(bool)
    n = len(a)
    user = tables["user"][job_row]
    n_users = int(tables["user"].max()) + 1
    group = copy_entry * n_users + user
    order = np.argsort(group, kind="stable")  # groups, members in arrival order
    g = group[order]
    first = np.empty(len(g), bool)
    first[0] = True
    first[1:] = g[1:] != g[:-1]
    pred = np.full(n, -1, np.int64)
    pred[order[1:]] = np.where(first[1:], -1, order[:-1])
    del order, g, first, group

    has = pred >= 0
    delta = np.full(n, np.nan)
    done_pred = a[pred[has]] + svc[pred[has]]
    delta[has] = a[has] - done_pred
    c_pred = np.full(n, np.nan)
    c_pred[has] = svc[pred[has]]

    # the assignment deadline on the overlay's calendar: the same rigid shift the copy got
    shift = a - tables["arr"][job_row]
    deadline = tables["a_end"][job_row] + shift
    return {
        "pred": pred,
        "delta": delta,
        "c_pred": c_pred,
        "deadline": deadline,
        "dl": dl,
        "a": a,
        "svc": svc,
        "user": user,
        "copy_entry": copy_entry,
    }


def quantiles(x: np.ndarray, qs) -> dict:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    return {f"q{q}": float(np.quantile(x, q)) for q in qs}


def describe(ch: dict, limit_s: float) -> dict:
    delta, c_pred, dl = ch["delta"], ch["c_pred"], ch["dl"]
    has = np.isfinite(delta)
    gated = delta >= 0
    qs = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    out = {
        "n_jobs": int(len(delta)),
        "n_first_submissions": int((~has).sum()),
        "n_with_predecessor": int(has.sum()),
        "share_result_gated": float(gated[has].mean()),
        "share_submission_gated": float((~gated[has]).mean()),
        "delta_all_s": quantiles(delta, qs),
        "delta_result_gated_s": quantiles(np.where(gated, delta, np.nan), qs),
        "delta_in_window": {
            "n_with_predecessor": int((has & dl).sum()),
            "share_result_gated": float(gated[has & dl].mean()),
            "quantiles_s": quantiles(np.where(dl, delta, np.nan), qs),
        },
        "delta_outside_window": {
            "n_with_predecessor": int((has & ~dl).sum()),
            "share_result_gated": float(gated[has & ~dl].mean()),
            "quantiles_s": quantiles(np.where(~dl, delta, np.nan), qs),
        },
    }
    # does the think time depend on the previous job's own cost?
    edges = np.array([0.0, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 15.0, 60.0001])
    rows = []
    for mask, label in ((np.ones(len(delta), bool), "all"), (dl, "deadline_window")):
        sel = has & mask
        idx = np.digitize(c_pred[sel], edges) - 1
        d = delta[sel]
        g = gated[sel]
        cp = c_pred[sel]
        for b in range(len(edges) - 1):
            m = idx == b
            if not m.any():
                continue
            rows.append(
                {
                    "subset": label,
                    "c_pred_bin_lo_s": float(edges[b]),
                    "c_pred_bin_hi_s": float(edges[b + 1]),
                    "n": int(m.sum()),
                    "mean_c_pred_s": float(cp[m].mean()),
                    "share_result_gated": float(g[m].mean()),
                    "delta_p10_s": float(np.quantile(d[m], 0.10)),
                    "delta_median_s": float(np.quantile(d[m], 0.50)),
                    "delta_p90_s": float(np.quantile(d[m], 0.90)),
                    "median_delta_given_gated_s": (
                        float(np.quantile(d[m & g], 0.50)) if (m & g).any() else float("nan")
                    ),
                }
            )
    out["delta_vs_c_pred"] = rows
    # rank correlation of delta on C_pred among result-gated pairs (subsample for speed)
    rng = np.random.default_rng(0)
    sel = np.flatnonzero(has & gated)
    take = sel if sel.size <= 2_000_000 else rng.choice(sel, 2_000_000, replace=False)
    x, y = c_pred[take], delta[take]
    out["spearman_delta_vs_c_pred_result_gated"] = float(
        np.corrcoef(
            np.argsort(np.argsort(x)).astype(np.float64),
            np.argsort(np.argsort(y)).astype(np.float64),
        )[0, 1]
    )
    out["n_sampled_for_correlation"] = int(take.size)
    out["limit_s"] = limit_s
    return out


def main() -> None:
    CHAINS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    tables = load_row_tables()
    print(f"row tables in {time.time() - t0:.1f} s", flush=True)
    overlay_dir = ROOT / "data" / "derived" / "overlay_traces"
    summary = {}
    for rep in (0, 1, 2, 3, 4):
        path = overlay_dir / f"primary_rep{rep}.npz"
        t1 = time.time()
        ch = chains_for(path, tables)
        np.savez(
            CHAINS / f"chain_rep{rep}.npz",
            pred=ch["pred"],
            delta=ch["delta"],
            deadline=ch["deadline"],
        )
        summary[f"rep{rep}"] = describe(ch, tables["limit_s"])
        print(f"rep{rep} in {time.time() - t1:.1f} s", flush=True)
        del ch
    (OUT / "think_time.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    import csv

    with (OUT / "delta_vs_cpred.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = None
        for rep, block in summary.items():
            for row in block["delta_vs_c_pred"]:
                row = {"overlay": rep, **row}
                if writer is None:
                    writer = csv.DictWriter(fh, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
    print(f"total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
