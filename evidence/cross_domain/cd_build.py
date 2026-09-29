"""Leak-free feature tables for the two non-education traces, plus two leak tests.

    uv run ... python cd_build.py azure
    uv run ... python cd_build.py netbatch

Visibility protocol (the same one the project uses on CodeBench, protocol A): a past job
j may enter the features of job i only once its RESULT exists, i.e. end[j] <= arrival[i].
Quantities that are observable at arrival without knowing any outcome (how many jobs of
the same entity are currently in flight, the gap since the previous arrival of the same
entity, the clock) are allowed.

Outputs: feature matrix + labels to the cache directory; out_leaktest_<trace>.txt here.
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np
import pandas as pd
from numba import njit

import cd_common as C

# ---- study parameters (frozen here; nothing below is tuned on the test window) ----
AZURE_MIN_ACTIVE_DAYS = 2      # drop one-day "flurry" apps, see out_flurry_azure.txt
AZURE_SPLIT_DAYS = (8, 10, 14)  # train < 8 d, valid [8,10), test [10,14)
NETBATCH_SPLIT_DAYS = (18, 22, 30)
EWM_ALPHA = 0.2
LEAK_TEST_ROWS = 2500
RNG_SEED = C.SEED

FEAT_ENT = ["e_n", "e_mean", "e_std", "e_last", "e_max", "e_min", "e_ewm", "e_heavy",
            "e_since_end", "a_n", "a_mean", "a_last", "a_ewm", "a_max"]
FEAT_STATIC = ["hour", "dow", "tod_sin", "tod_cos", "t_days", "gid"]
FEAT_ARR = ["e_inflight", "a_inflight", "g_inflight", "e_gap_arr", "e_new", "a_new",
            "g_n", "g_ewm"]
FEAT_ALL = FEAT_ENT + FEAT_STATIC + FEAT_ARR


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


STREAM_COLS = ["e_n", "e_mean", "e_std", "e_last", "e_max", "e_min", "e_ewm", "e_heavy",
               "e_since_end", "a_n", "a_mean", "a_last", "a_ewm", "a_max",
               "e_inflight", "a_inflight", "g_inflight", "e_gap_arr", "e_new", "a_new",
               "g_n", "g_ewm"]


def build_stream(arrival, end, dur, ent, ent2, heavy_thr):
    y = np.log1p(dur)
    order_end = np.argsort(end, kind="mergesort")
    out = np.zeros((len(arrival), len(STREAM_COLS)), np.float64)
    _stream(arrival, end, y, ent, ent2, order_end, int(ent.max()) + 1,
            int(ent2.max()) + 1, EWM_ALPHA, np.log1p(heavy_thr), out)
    return pd.DataFrame(out, columns=STREAM_COLS)


def brute_force_check(fh, arrival, end, dur, ent, feats, rows, tag=""):
    """Independent recomputation of the entity-history columns, from the definition.

    The per-entity index lists only avoid scanning the whole trace 2,500 times; the
    quantities themselves are recomputed from `(same entity) and (end <= arrival[i])`,
    with no state carried between rows.
    """
    y = np.log1p(dur)
    groups = pd.Series(np.arange(len(ent))).groupby(ent).apply(lambda s: s.values).to_dict()
    bad = 0
    for i in rows:
        g = groups[ent[i]]
        m = end[g] <= arrival[i]
        idx = g[m]
        n = int(idx.size)
        if n != int(round(feats["e_n"][i])):
            bad += 1
            continue
        if n == 0:
            continue
        ys = y[idx]
        ref_mean, ref_max, ref_min = ys.mean(), ys.max(), ys.min()
        ordr = np.argsort(end[idx], kind="mergesort")
        ref_last = ys[ordr][-1]
        for name, ref in (("e_mean", ref_mean), ("e_max", ref_max),
                          ("e_min", ref_min), ("e_last", ref_last)):
            if abs(feats[name][i] - ref) > 1e-9 * max(1.0, abs(ref)):
                bad += 1
                break
    C.log(fh, f"[leak test 1{tag}] brute-force recomputation of e_n/e_mean/e_max/e_min/"
              f"e_last on {len(rows)} sampled rows: mismatches = {bad}")
    return bad


def future_perturbation_check(fh, arrival, end, dur, ent, ent2, heavy_thr, feats, cutoff, rng):
    """Every job whose RESULT is not yet in (end > cutoff) gets a random duration.

    Rows that arrive at or before the cutoff must get byte-identical features.
    """
    d2 = dur.copy()
    e2 = end.copy()
    m = end > cutoff
    d2[m] = rng.uniform(0.0, float(np.percentile(dur, 99.99)) + 1.0, size=int(m.sum()))
    e2[m] = np.maximum(arrival[m] + d2[m], cutoff + 1.0)
    f2 = build_stream(arrival, e2, d2, ent, ent2, heavy_thr)
    pre = arrival <= cutoff
    diff = 0
    worst = ""
    for c in STREAM_COLS:
        d = np.abs(f2[c].values[pre] - feats[c].values[pre])
        if np.nanmax(d) > 0:
            diff += 1
            worst = c
    C.log(fh, f"[leak test 2] {int(m.sum())} jobs with end>cutoff given random durations; "
              f"{int(pre.sum())} rows arrive at or before the cutoff; feature columns that "
              f"changed: {diff}" + (f" (e.g. {worst})" if diff else ""))
    return diff


def prep_azure(fh):
    df = C.load_azure()
    df["day"] = (df.arrival.values / C.DAY).astype(int)
    act = df.groupby("app_id").day.nunique()
    keep = set(act.index[act >= AZURE_MIN_ACTIVE_DAYS])
    n0, w0 = len(df), df.duration.sum()
    df = df[df.app_id.isin(keep)].reset_index(drop=True)
    C.log(fh, f"flurry filter: kept apps active on >= {AZURE_MIN_ACTIVE_DAYS} distinct days "
              f"-> {len(keep)}/{len(act)} apps, {len(df)}/{n0} jobs "
              f"({len(df)/n0*100:.2f}%), work {df.duration.sum()/w0*100:.2f}% of the raw total")
    df["ent"] = pd.factorize(df.func_id)[0].astype(np.int64)
    df["ent2"] = pd.factorize(df.app_id)[0].astype(np.int64)
    df["gid"] = 0
    df["dur"] = np.maximum(df.duration.values, 0.001)   # 1 ms = the log's resolution
    df["end2"] = df.arrival.values + df.dur.values
    return df, "azure", AZURE_SPLIT_DAYS


def prep_netbatch(fh):
    df = C.load_netbatch()
    n0 = len(df)
    df = df[(df.nproc == 1) & (df.run > 0)].reset_index(drop=True)
    C.log(fh, f"kept serial jobs with run>0: {len(df)}/{n0} ({len(df)/n0*100:.2f}%)")
    df["arrival"] = df.submit.values.astype(np.float64)
    df["dur"] = df.run.values.astype(np.float64)
    df["end2"] = df.arrival.values + df.dur.values
    df["duration"] = df.dur
    df = df.sort_values(["arrival", "job"], kind="mergesort").reset_index(drop=True)
    df["ent"] = pd.factorize(df.exe)[0].astype(np.int64)
    df["ent2"] = pd.factorize(df.uid)[0].astype(np.int64)
    df["day"] = (df.arrival.values / C.DAY).astype(int)
    return df, "netbatch", NETBATCH_SPLIT_DAYS


def main(which):
    out = os.path.join(C.HERE, f"out_leaktest_{which}.txt")
    with open(out, "w", encoding="utf-8") as fh:
        df, name, split = (prep_azure(fh) if which == "azure" else prep_netbatch(fh))
        arrival = df.arrival.values.astype(np.float64)
        end = df.end2.values.astype(np.float64)
        dur = df.dur.values.astype(np.float64)
        ent = df.ent.values.astype(np.int64)
        ent2 = df.ent2.values.astype(np.int64)
        tr_d, va_d, te_d = split
        is_tr = df.day.values < tr_d
        heavy_thr = float(np.percentile(dur[is_tr], 95))
        C.log(fh, f"split (by arrival day): train < {tr_d} d ({int(is_tr.sum())} rows), "
                  f"valid [{tr_d},{va_d}) ({int(((df.day.values>=tr_d)&(df.day.values<va_d)).sum())}), "
                  f"test [{va_d},{te_d}) ({int((df.day.values>=va_d).sum())})")
        C.log(fh, f"heavy threshold = train p95 of the cost = {heavy_thr:.4f} s")
        L = float(np.percentile(dur[is_tr], 99.9))
        C.log(fh, f"service cap L = train p99.9 = {L:.4f} s "
                  f"(jobs capped in the whole trace: {int((dur>L).sum())}, "
                  f"{(dur>L).mean()*100:.4f}%; work removed by the cap "
                  f"{(np.sum(dur-np.minimum(dur,L))/dur.sum())*100:.2f}%)")

        feats = build_stream(arrival, end, dur, ent, ent2, heavy_thr)
        rng = np.random.default_rng(RNG_SEED)
        rows = rng.choice(len(df), size=LEAK_TEST_ROWS, replace=False)
        # brute force needs a per-entity scan; do it on the columns' definition directly
        bad = brute_force_check(fh, arrival, end, dur, ent, feats, rows)
        # the perturbation test runs on a prefix of the arrival order; features of a row
        # depend only on earlier arrivals, so the prefix reproduces them exactly.
        npre = min(len(df), 1_500_000)
        sl = slice(0, npre)
        pref = build_stream(arrival[sl], end[sl], dur[sl], ent[sl], ent2[sl], heavy_thr)
        same = max(np.abs(pref[c].values - feats[c].values[sl]).max() for c in STREAM_COLS)
        C.log(fh, f"[prefix check] features on the first {npre} rows reproduce the full-trace "
                  f"features exactly (max abs diff {same:.3g})")
        cutoff = float(np.percentile(arrival[sl], 60))
        diff = future_perturbation_check(fh, arrival[sl], end[sl], dur[sl], ent[sl],
                                         ent2[sl], heavy_thr, pref, cutoff, rng)
        C.log(fh, f"leak tests: {'PASS' if (bad == 0 and diff == 0) else 'FAIL'}")

        feats["hour"] = ((arrival / 3600.0) % 24).astype(np.float64)
        feats["dow"] = ((arrival / C.DAY) % 7).astype(np.float64)
        feats["tod_sin"] = np.sin(2 * np.pi * (arrival % C.DAY) / C.DAY)
        feats["tod_cos"] = np.cos(2 * np.pi * (arrival % C.DAY) / C.DAY)
        feats["t_days"] = arrival / C.DAY
        feats["gid"] = df.gid.values.astype(np.float64) if "gid" in df else 0.0
        feats["arrival"] = arrival
        feats["dur"] = dur
        feats["ent"] = ent
        feats["ent2"] = ent2
        feats["day"] = df.day.values
        feats["heavy"] = (dur >= heavy_thr).astype(np.int8)
        pq = os.path.join(C.SCRATCH, f"{name}_feats.parquet")
        feats.to_parquet(pq, index=False)
        meta = pd.DataFrame([{"trace": name, "n": len(df), "L": L, "heavy_thr": heavy_thr,
                              "train_day": tr_d, "valid_day": va_d, "end_day": te_d}])
        meta.to_csv(os.path.join(C.HERE, f"meta_{name}.csv"), index=False)
        C.log(fh, f"wrote {pq}  ({len(feats)} rows, {feats.shape[1]} columns)")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
