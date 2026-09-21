"""T1: lag between a SUBMITION header timestamp and the codemirror "submit" event.

The codemirror "submit" line carries the judge's feedback message, so the client writes it after
the verdict has come back.  If the header time is when the server RECEIVED the code, then
lag = cm_submit_ts - header_ts grows about one-for-one with exec_time; if the header time is
when the RESULT was recorded, lag does not depend on exec_time.

Matching: inside one (semester, class, user, assessment, exercise) file pair the k-th SUBMITION
block is paired with the k-th codemirror submit event, only when both counts are equal
(order matching).  A nearest-neighbour matching is reported as a robustness check.
Clock offset: the client clock may differ from the server clock, so the median lag of short
jobs (exec_time < 1 s) of the same user and day is subtracted (adj_lag).

Usage: uv run --with pandas --with numpy --with scipy --with pyarrow python t1_lag.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import CACHE, KEY, load_blocks, load_cm, q

BINS = [0, 0.5, 1, 2, 5, 10, 20, 40, 60, 200, 1000, 1e5]


def order_match(b: pd.DataFrame, c: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = b.sort_values(KEY + ["seq"]).copy()
    c = c.sort_values(KEY + ["ts"]).copy()
    b["k"] = b.groupby(KEY, sort=False).cumcount()
    c["k"] = c.groupby(KEY, sort=False).cumcount()
    nb = b.groupby(KEY, sort=False).size().rename("nb")
    nc = c.groupby(KEY, sort=False).size().rename("nc")
    cnt = pd.concat([nb, nc], axis=1).fillna(0)
    eq = cnt[cnt.nb == cnt.nc].reset_index()[KEY]
    m = b.merge(eq, on=KEY).merge(c[KEY + ["k", "ts", "fb"]].rename(columns={"ts": "cm_ts"}), on=KEY + ["k"])
    m["lag"] = m["cm_ts"] - m["ts"]
    return m, cnt


def nearest_match(b: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """For every SUBMITION, the codemirror submit of the same file pair nearest in time."""
    b = b.sort_values("ts").copy()
    c = c.sort_values("ts").rename(columns={"ts": "cm_ts"})
    b["gid"] = b[KEY].astype(str).agg("|".join, axis=1)
    c["gid"] = c[KEY].astype(str).agg("|".join, axis=1)
    b["tsf"] = b["ts"].astype(float)
    m = pd.merge_asof(b, c[["gid", "cm_ts", "fb"]], left_on="tsf", right_on="cm_ts", by="gid",
                      direction="nearest", tolerance=3600.0)
    m["lag"] = m["cm_ts"] - m["ts"]
    return m.dropna(subset=["lag"])


def add_offset(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    m["day"] = (m["ts"] // 86400).astype(int)
    short = m[(m.exec_time < 1) & m.lag.abs().lt(6 * 3600)]
    off_ud = short.groupby(["semester", "user", "day"]).lag.agg(["median", "size"])
    off_ud = off_ud[off_ud["size"] >= 3]["median"].rename("off_ud")
    off_u = short.groupby(["semester", "user"]).lag.median().rename("off_u")
    m = m.merge(off_ud, on=["semester", "user", "day"], how="left").merge(off_u, on=["semester", "user"], how="left")
    m["offset"] = m["off_ud"].fillna(m["off_u"])
    m["adj"] = m["lag"] - m["offset"]
    return m


def bin_table(m: pd.DataFrame, col="adj") -> pd.DataFrame:
    m = m.dropna(subset=[col, "exec_time"])
    m = m.assign(bin=pd.cut(m.exec_time, BINS, right=False))
    g = m.groupby("bin", observed=True)
    t = pd.DataFrame({
        "n": g.size(),
        "exec_med": g.exec_time.median(),
        f"{col}_p10": g[col].quantile(0.10),
        f"{col}_p25": g[col].quantile(0.25),
        f"{col}_med": g[col].median(),
        f"{col}_p75": g[col].quantile(0.75),
        f"{col}_p90": g[col].quantile(0.90),
        "med(adj-exec)": g.apply(lambda x: (x[col] - x.exec_time).median(), include_groups=False),
        "share_adj>=0.5exec": g.apply(lambda x: (x[col] >= 0.5 * x.exec_time).mean(), include_groups=False),
    })
    return t.round(3)


def slope(m: pd.DataFrame, lo: float, hi: float, col="adj", trim=None) -> str:
    d = m[(m.exec_time >= lo) & (m.exec_time < hi)].dropna(subset=[col])
    if trim is not None:
        d = d[d[col].abs() < trim]
    if len(d) < 30:
        return f"[{lo},{hi}) n={len(d)}"
    x, y = d.exec_time.to_numpy(), d[col].to_numpy()
    b1, b0 = np.polyfit(x, y, 1)
    # bootstrap by user for a CI of the slope
    rng = np.random.default_rng(0)
    idx = d.reset_index(drop=True).groupby(["semester", "user"]).indices
    bs = []
    keys = list(idx.keys())
    for _ in range(200):
        pick = rng.integers(0, len(keys), size=len(keys))
        ii = np.concatenate([idx[keys[j]] for j in pick])
        if np.ptp(x[ii]) > 0:
            bs.append(np.polyfit(x[ii], y[ii], 1)[0])
    lo_ci, hi_ci = np.quantile(bs, [0.025, 0.975])
    return (f"exec in [{lo},{hi}) n={len(d):,} users={len(idx)}: OLS slope={b1:.3f} "
            f"[user-bootstrap 95% {lo_ci:.3f}, {hi_ci:.3f}] intercept={b0:.2f}")


def main():
    b_all = load_blocks()
    b = b_all[b_all.kind == "submit"].drop(columns=["kind"])
    c_all = load_cm()
    c = c_all[c_all.etype == "submit"].drop(columns=["etype"])

    print("=== T1 coverage: SUBMITION blocks vs codemirror submit events ===")
    m, cnt = order_match(b, c)
    cov = []
    for s, bb in b.groupby("semester", sort=False):
        cs = cnt.loc[s] if s in cnt.index.get_level_values(0) else cnt.iloc[:0]
        eq_blocks = cs[cs.nb == cs.nc].nb.sum()
        cov.append((s, len(bb), int((c.semester == s).sum()), int(cs.nb.gt(0).sum()),
                    int((cs.nb == cs.nc).sum()), round(eq_blocks / len(bb), 3),
                    int(bb["class"].nunique())))
    print(pd.DataFrame(cov, columns=["semester", "submit_blocks", "cm_submit", "file_pairs",
                                     "pairs_equal_count", "share_blocks_order_matched",
                                     "classes"]).to_string(index=False))

    print("\n=== T1 raw lag (cm_submit - header), order-matched, by semester ===")
    for s, d in m.groupby("semester", sort=False):
        print(f"  {s:9s} {q(d.lag)}")
    ml = m[m.lag.abs() < 6 * 3600]
    print(f"  share |lag|<10s: {np.mean(m.lag.abs() < 10):.3f}; within 6h kept for offset: {len(ml):,}")

    m = add_offset(ml)
    print("\n=== T1 estimated clock offset (median lag of exec<1s jobs per user-day, else per user) ===")
    print("  offset per user-semester:", q(m.groupby(["semester", "user"]).offset.first()))
    print("  lag of exec<1s jobs     :", q(m[m.exec_time < 1].lag))
    print("  adj of exec<1s jobs     :", q(m[m.exec_time < 1].adj))

    for era, d in m.groupby("era"):
        print(f"\n=== T1 adj lag by exec_time bin, era {era} (order-matched, offset removed) ===")
        print(bin_table(d).to_string())
    print("\n=== T1 raw lag (no offset removal) by exec_time bin, all DEV ===")
    print(bin_table(m, col="lag").to_string())

    print("\n=== T1 slope of adj lag on exec_time (1 = header is receipt time, 0 = result time) ===")
    for lo, hi in [(0, 60), (1, 60), (5, 60), (10, 60), (60, 1e5), (0, 1e5)]:
        print("  all   ", slope(m, lo, hi))
    for era, d in m.groupby("era"):
        print(f"  {era}", slope(d, 1, 60))
    print("  trimmed |adj|<600:", slope(m, 0, 1e5, trim=600))

    print("\n=== T1 short vs long: adj lag distribution ===")
    print("  exec < 1 s :", q(m[m.exec_time < 1].adj))
    print("  exec 1-10 s:", q(m[(m.exec_time >= 1) & (m.exec_time < 10)].adj))
    print("  exec > 10 s:", q(m[m.exec_time > 10].adj))
    print("  exec > 10 s, adj - exec:", q((m.adj - m.exec_time)[m.exec_time > 10]))
    print("  exec > 30 s, adj - exec:", q((m.adj - m.exec_time)[m.exec_time > 30]))

    print("\n=== T1 robustness: nearest-neighbour matching (all file pairs, |lag|<1h) ===")
    n = add_offset(nearest_match(b, c))
    print(bin_table(n).to_string())
    print("  ", slope(n, 1, 60))

    print("\n=== T1 feedback class of the matched cm event vs block (sanity of the pairing) ===")
    m["blk_ok"] = np.where(m.grade == 100, "grade100", np.where(m.grade > 0, "grade_partial",
                           np.where(m.grade == 0, "grade0", "no_grade")))
    print(pd.crosstab(m.blk_ok, m.fb.astype(str), margins=True).to_string())

    m[["semester", "class", "user", "assessment", "exercise", "seq", "ts", "exec_time", "n_tc",
       "grade", "err_class", "cm_ts", "lag", "offset", "adj"]].to_parquet(
        os.path.join(CACHE, "t1_matched.parquet"), index=False)


if __name__ == "__main__":
    main()
