"""Leak-free feature table for a Firefox CI pool window, plus two leak tests.

    uv run --with pandas --with numpy --with pyarrow --with numba python fci_build.py <pool-tag>

Visibility protocol (protocol A, the one the project uses on CodeBench and in
evidence/cross_domain): a past run j may enter the features of run i only once its
RESULT exists.  Here that is the RECORDED resolution time, `resolved[j] <= scheduled[i]`
-- stricter than cross_domain's `arrival + duration`, because the real system only knew
the outcome when the run actually finished.  Quantities observable at arrival without
any outcome (how many runs of the same label are in flight, the gap since the label's
previous arrival, the clock, the repository, the priority) are allowed.

Entities: e = the task label (job_type_name, e.g.
"test-macosx1500-aarch64-shippable/opt-talos-g1"), the analogue of a function in the
Azure trace and of an executable in Netbatch; a = the label's suite family (the label
with its trailing chunk number removed), the analogue of an app.
"""
import os
import re
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from numba import njit

import fci_common as C

EWM_ALPHA = 0.2
LEAK_TEST_ROWS = 2500

FEAT_ENT = ["e_n", "e_mean", "e_std", "e_last", "e_max", "e_min", "e_ewm", "e_heavy",
            "e_since_end", "a_n", "a_mean", "a_last", "a_ewm", "a_max"]
FEAT_STATIC = ["hour", "dow", "tod_sin", "tod_cos", "t_days", "gid", "prio", "tier"]
FEAT_ARR = ["e_inflight", "a_inflight", "g_inflight", "e_gap_arr", "e_new", "a_new",
            "g_n", "g_ewm"]
FEAT_ALL = FEAT_ENT + FEAT_STATIC + FEAT_ARR

STREAM_COLS = ["e_n", "e_mean", "e_std", "e_last", "e_max", "e_min", "e_ewm", "e_heavy",
               "e_since_end", "a_n", "a_mean", "a_last", "a_ewm", "a_max",
               "e_inflight", "a_inflight", "g_inflight", "e_gap_arr", "e_new", "a_new",
               "g_n", "g_ewm"]

PRIO_RANK = {"highest": 0, "very-high": 1, "high": 2, "medium": 3, "normal": 3,
             "low": 4, "very-low": 5, "lowest": 6}
CHUNK = re.compile(r"[-_]?\d+$")


@njit(cache=True)
def _stream(arrival, end, y, ent, ent2, order_end, n_ent, n_ent2, alpha, heavy_thr, out):
    n = arrival.shape[0]
    e_n = np.zeros(n_ent, np.float64)
    e_s = np.zeros(n_ent, np.float64)
    e_s2 = np.zeros(n_ent, np.float64)
    e_last = np.zeros(n_ent, np.float64)
    e_max = np.full(n_ent, -1.0, np.float64)
    e_min = np.full(n_ent, 1e18, np.float64)
    e_ewm = np.zeros(n_ent, np.float64)
    e_heavy = np.zeros(n_ent, np.float64)
    e_tend = np.full(n_ent, -1.0, np.float64)
    e_started = np.zeros(n_ent, np.int64)
    e_done = np.zeros(n_ent, np.int64)
    e_larr = np.full(n_ent, -1.0, np.float64)
    a_n = np.zeros(n_ent2, np.float64)
    a_s = np.zeros(n_ent2, np.float64)
    a_last = np.zeros(n_ent2, np.float64)
    a_ewm = np.zeros(n_ent2, np.float64)
    a_max = np.full(n_ent2, -1.0, np.float64)
    a_started = np.zeros(n_ent2, np.int64)
    a_done = np.zeros(n_ent2, np.int64)
    g_n = 0.0
    g_ewm = 0.0
    g_started = 0
    g_done = 0
    j = 0
    for i in range(n):
        t = arrival[i]
        while j < n:
            m = order_end[j]
            if end[m] > t:
                break
            e = ent[m]
            a = ent2[m]
            v = y[m]
            e_n[e] += 1.0
            e_s[e] += v
            e_s2[e] += v * v
            e_last[e] = v
            if v > e_max[e]:
                e_max[e] = v
            if v < e_min[e]:
                e_min[e] = v
            e_ewm[e] = v if e_n[e] == 1.0 else (1.0 - alpha) * e_ewm[e] + alpha * v
            if v >= heavy_thr:
                e_heavy[e] += 1.0
            e_tend[e] = end[m]
            e_done[e] += 1
            a_n[a] += 1.0
            a_s[a] += v
            a_last[a] = v
            if v > a_max[a]:
                a_max[a] = v
            a_ewm[a] = v if a_n[a] == 1.0 else (1.0 - alpha) * a_ewm[a] + alpha * v
            a_done[a] += 1
            g_n += 1.0
            g_ewm = v if g_n == 1.0 else (1.0 - alpha) * g_ewm + alpha * v
            g_done += 1
            j += 1
        e = ent[i]
        a = ent2[i]
        ne = e_n[e]
        out[i, 0] = ne
        out[i, 1] = e_s[e] / ne if ne > 0 else -1.0
        if ne > 1:
            var = e_s2[e] / ne - (e_s[e] / ne) ** 2
            out[i, 2] = np.sqrt(var) if var > 0 else 0.0
        else:
            out[i, 2] = -1.0
        out[i, 3] = e_last[e] if ne > 0 else -1.0
        out[i, 4] = e_max[e] if ne > 0 else -1.0
        out[i, 5] = e_min[e] if ne > 0 else -1.0
        out[i, 6] = e_ewm[e] if ne > 0 else -1.0
        out[i, 7] = e_heavy[e] / ne if ne > 0 else -1.0
        out[i, 8] = (t - e_tend[e]) if e_tend[e] >= 0 else -1.0
        na = a_n[a]
        out[i, 9] = na
        out[i, 10] = a_s[a] / na if na > 0 else -1.0
        out[i, 11] = a_last[a] if na > 0 else -1.0
        out[i, 12] = a_ewm[a] if na > 0 else -1.0
        out[i, 13] = a_max[a] if na > 0 else -1.0
        out[i, 14] = float(e_started[e] - e_done[e])
        out[i, 15] = float(a_started[a] - a_done[a])
        out[i, 16] = float(g_started - g_done)
        out[i, 17] = (t - e_larr[e]) if e_larr[e] >= 0 else -1.0
        out[i, 18] = 1.0 if ne == 0 else 0.0
        out[i, 19] = 1.0 if na == 0 else 0.0
        out[i, 20] = g_n
        out[i, 21] = g_ewm
        e_started[e] += 1
        a_started[a] += 1
        g_started += 1
        e_larr[e] = t
    return out


def build_stream(arrival, end, dur, ent, ent2, heavy_thr):
    y = np.log1p(dur)
    order_end = np.argsort(end, kind="mergesort")
    out = np.zeros((len(arrival), len(STREAM_COLS)), np.float64)
    _stream(arrival, end, y, ent, ent2, order_end, int(ent.max()) + 1,
            int(ent2.max()) + 1, EWM_ALPHA, np.log1p(heavy_thr), out)
    return pd.DataFrame(out, columns=STREAM_COLS)


def brute_force_check(fh, arrival, end, dur, ent, feats, rows):
    """Independent recomputation of the entity-history columns from the definition."""
    y = np.log1p(dur)
    groups = pd.Series(np.arange(len(ent))).groupby(ent).apply(lambda s: s.values).to_dict()
    bad = 0
    for i in rows:
        g = groups[ent[i]]
        idx = g[end[g] <= arrival[i]]
        n = int(idx.size)
        if n != int(round(feats["e_n"][i])):
            bad += 1
            continue
        if n == 0:
            continue
        ys = y[idx]
        ref_last = ys[np.argsort(end[idx], kind="mergesort")][-1]
        for name, ref in (("e_mean", ys.mean()), ("e_max", ys.max()),
                          ("e_min", ys.min()), ("e_last", ref_last)):
            if abs(feats[name][i] - ref) > 1e-9 * max(1.0, abs(ref)):
                bad += 1
                break
    C.log(fh, f"[leak test 1] brute-force recomputation of e_n/e_mean/e_max/e_min/e_last "
              f"on {len(rows)} sampled rows: mismatches = {bad}")
    return bad


def future_perturbation_check(fh, arrival, end, dur, ent, ent2, heavy_thr, feats, cutoff,
                              rng):
    """Every run whose RESULT is not yet in (end > cutoff) gets a random service time.

    Rows that arrive at or before the cutoff must get byte-identical features.
    """
    d2, e2 = dur.copy(), end.copy()
    m = end > cutoff
    d2[m] = rng.uniform(0.0, float(np.percentile(dur, 99.99)) + 1.0, size=int(m.sum()))
    e2[m] = np.maximum(arrival[m] + d2[m], cutoff + 1.0)
    f2 = build_stream(arrival, e2, d2, ent, ent2, heavy_thr)
    pre = arrival <= cutoff
    diff = sum(1 for c in STREAM_COLS
               if np.nanmax(np.abs(f2[c].values[pre] - feats[c].values[pre])) > 0)
    C.log(fh, f"[leak test 2] {int(m.sum())} runs with end>cutoff given random service; "
              f"{int(pre.sum())} rows arrive at or before the cutoff; feature columns "
              f"that changed: {diff}")
    return diff


def main(tag):
    out = os.path.join(C.HERE, f"out_leaktest_{tag}.txt")
    with open(out, "w", encoding="utf-8") as fh:
        df = pd.read_parquet(os.path.join(C.DATA, f"runs_{tag}.parquet"))
        n0 = len(df)
        df = df[np.isfinite(df.started) & np.isfinite(df.resolved)].copy()
        # A worker is not reusable the instant a task resolves: generic-worker tears
        # down and sets up.  Theory (research plan 5.4 / theory.md) says that time is
        # absorbed into the service.  The estimate is the median short inter-run gap on
        # the same worker, measured in fci_simval.py and frozen in keff_<tag>.csv; it is
        # also the setup that made the simulator reproduce the RECORDED waits.
        kp = os.path.join(C.HERE, f"keff_{tag}.csv")
        setup = float(pd.read_csv(kp).iloc[0].setup_s) if os.path.exists(kp) else 0.0
        df["service"] = (df.resolved - df.started).astype(float)
        df["dur"] = df.service + setup
        C.log(fh, f"occupancy = service + {setup:.1f} s of setup/teardown "
                  f"(from keff_{tag}.csv; 0 means fci_simval.py has not been run yet)")
        df["wait_rec"] = (df.started - df.scheduled).clip(lower=0.0)
        df = df[df.dur > 0].copy()
        df = df.sort_values(["scheduled", "task_id", "run_id"],
                            kind="mergesort").reset_index(drop=True)
        C.log(fh, f"=== {tag} ===")
        C.log(fh, f"runs with a service time: {len(df)}/{n0} "
                  f"({len(df)/n0*100:.2f}%); the rest never started")
        df["arrival"] = df.scheduled.values.astype(float)
        df["end2"] = df.resolved.values.astype(float)
        df["label"] = df.label.fillna("__unknown__")
        df["family"] = [CHUNK.sub("", x) for x in df.label.values]
        df["ent"] = pd.factorize(df.label)[0].astype(np.int64)
        df["ent2"] = pd.factorize(df.family)[0].astype(np.int64)
        C.log(fh, f"entities: {df.ent.nunique()} labels, {df.ent2.nunique()} families")

        w0iso, w1iso, split = C.window(C.pool_from_tag(tag))
        t0 = C.iso_to_epoch(w0iso)
        df["day"] = ((df.arrival.values - t0) / C.DAY).astype(int)
        tr_d, va_d, te_d = split
        is_tr = df.day.values < tr_d
        arrival = df.arrival.values
        end = df.end2.values
        dur = df.dur.values
        ent = df.ent.values
        ent2 = df.ent2.values
        heavy_thr = float(np.percentile(dur[is_tr], 95))
        C.log(fh, f"split (by arrival day from {w0iso}): train < {tr_d} d "
                  f"({int(is_tr.sum())} runs), valid [{tr_d},{va_d}) "
                  f"({int(((df.day.values>=tr_d)&(df.day.values<va_d)).sum())}), "
                  f"test [{va_d},{te_d}) ({int((df.day.values>=va_d).sum())})")
        C.log(fh, f"heavy threshold = train p95 of the service = {heavy_thr:.1f} s")

        L = float(np.percentile(dur[is_tr], 99.9))
        mrt = df.max_run_time.values
        C.log(fh, f"service cap L' = train p99.9 = {L:.1f} s "
                  f"(runs capped in the window: {int((dur>L).sum())}, "
                  f"{(dur>L).mean()*100:.4f}%; work removed by the cap "
                  f"{(np.sum(dur-np.minimum(dur,L))/dur.sum())*100:.3f}%)")
        C.log(fh, f"the platform's own per-task limits payload.maxRunTime: "
                  f"min={np.nanmin(mrt):.0f} median={np.nanmedian(mrt):.0f} "
                  f"max={np.nanmax(mrt):.0f} s over "
                  f"{len(pd.unique(mrt[np.isfinite(mrt)]))} distinct values; "
                  f"prefix-max of the realised service over the window = {dur.max():.1f} s")
        C.log(fh, "  (theory.md Prop 8 allows L to be the running prefix maximum, so the "
                  "theorem also holds with the heterogeneous maxRunTime; the frozen L' "
                  "above is used for the reported guarantees so that the numbers are "
                  "comparable with evidence/cross_domain, and every service is capped at "
                  "it, which makes the theorem apply verbatim.)")

        feats = build_stream(arrival, end, dur, ent, ent2, heavy_thr)
        rng = np.random.default_rng(C.SEED)
        rows = rng.choice(len(df), size=min(LEAK_TEST_ROWS, len(df)), replace=False)
        bad = brute_force_check(fh, arrival, end, dur, ent, feats, rows)
        cutoff = float(np.percentile(arrival, 60))
        diff = future_perturbation_check(fh, arrival, end, dur, ent, ent2, heavy_thr,
                                         feats, cutoff, rng)
        C.log(fh, f"leak tests: {'PASS' if (bad == 0 and diff == 0) else 'FAIL'}")

        feats["hour"] = ((arrival / 3600.0) % 24)
        feats["dow"] = ((arrival / C.DAY) % 7)
        feats["tod_sin"] = np.sin(2 * np.pi * (arrival % C.DAY) / C.DAY)
        feats["tod_cos"] = np.cos(2 * np.pi * (arrival % C.DAY) / C.DAY)
        feats["t_days"] = (arrival - t0) / C.DAY
        feats["gid"] = pd.factorize(df.repo.fillna("?"))[0].astype(float)
        feats["prio"] = df.priority.map(PRIO_RANK).fillna(3).values.astype(float)
        feats["tier"] = pd.to_numeric(df.tier, errors="coerce").fillna(-1).values
        feats["arrival"] = arrival
        feats["dur"] = dur
        feats["wait_rec"] = df.wait_rec.values
        feats["ent"] = ent
        feats["ent2"] = ent2
        feats["day"] = df.day.values
        feats["max_run_time"] = mrt
        feats["heavy"] = (dur >= heavy_thr).astype(np.int8)
        pq = os.path.join(C.SCRATCH, f"{tag}_feats.parquet")
        feats.to_parquet(pq, index=False)
        pd.DataFrame([{"pool_tag": tag, "n": len(df), "L": L, "heavy_thr": heavy_thr,
                       "train_day": tr_d, "valid_day": va_d, "end_day": te_d,
                       "mrt_max": float(np.nanmax(mrt)),
                       "serv_max": float(dur.max())}]).to_csv(
            os.path.join(C.HERE, f"meta_{tag}.csv"), index=False)
        C.log(fh, f"wrote {pq} ({len(feats)} rows, {feats.shape[1]} columns)")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
