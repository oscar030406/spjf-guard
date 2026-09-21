"""T2: server-side ordering test for the header timestamp (no client clock involved).

For a SUBMITION with a long exec_time E and header time t:
  * if t is the RECEIPT time, the job ran over [t, t+E]; a student whose UI waits for the verdict
    cannot start the next execution before t+E, so post_gap = t_next - t should be >= E;
  * if t is the RESULT time, the job ran over [t-E, t]; the previous execution must lie before
    t-E, so pre_gap = t - t_prev should be >= E.
The share of post_gap < E versus pre_gap < E tells the two apart.

Also:
  T2b  kill clustering: for runs >= 100 s, do many users share the same header time (batch kill at
       the result time) or the same header-minus-exec time?
  T2c  distance from the header time of long runs to the same user's login/logout records.

Usage: uv run --with pandas --with numpy --with pyarrow python t2_gaps.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import KEY, load_blocks, q

ROOT = r"<repo-root>"
BINS = [0, 1, 5, 10, 20, 40, 60, 200, 1000, 1e5]


def neighbours(b: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    b = b.sort_values(by + ["ts", "seq"]).copy()
    g = b.groupby(by, sort=False)
    b["ts_prev"] = g.ts.shift(1)
    b["ts_next"] = g.ts.shift(-1)
    b["kind_prev"] = g.kind.shift(1)
    b["kind_next"] = g.kind.shift(-1)
    b["pre_gap"] = b.ts - b.ts_prev
    b["post_gap"] = b.ts_next - b.ts
    return b


def table(s: pd.DataFrame) -> pd.DataFrame:
    s = s.assign(bin=pd.cut(s.exec_time, BINS, right=False))
    g = s.groupby("bin", observed=True)
    return pd.DataFrame({
        "n": g.size(),
        "exec_med": g.exec_time.median(),
        "pre_gap_med": g.pre_gap.median(),
        "post_gap_med": g.post_gap.median(),
        "share_pre<exec": g.apply(lambda x: (x.pre_gap < x.exec_time).sum() / x.pre_gap.notna().sum(), include_groups=False),
        "share_post<exec": g.apply(lambda x: (x.post_gap < x.exec_time).sum() / x.post_gap.notna().sum(), include_groups=False),
        "share_pre<0.5exec": g.apply(lambda x: (x.pre_gap < 0.5 * x.exec_time).sum() / x.pre_gap.notna().sum(), include_groups=False),
        "share_post<0.5exec": g.apply(lambda x: (x.post_gap < 0.5 * x.exec_time).sum() / x.post_gap.notna().sum(), include_groups=False),
    }).round(3)


def main():
    b = load_blocks()
    b = b.drop_duplicates(subset=KEY + ["kind", "ts", "exec_time", "n_tc", "grade"])  # exact repeats
    for scope, by in [("same user, same exercise file (task definition)", KEY),
                      ("same user, any exercise", ["semester", "user"])]:
        nb = neighbours(b, by)
        s = nb[nb.kind == "submit"]
        for era, d in s.groupby("era"):
            print(f"\n=== T2 {scope}; SUBMITION blocks, era {era} ===")
            print(table(d).to_string())
        if by == KEY:
            long = s[s.exec_time > 10]
            gap = long.ts_next - long.ts - long.exec_time
            print("\n  gap = t_next - t_this - exec_this for exec_this > 10 s (same file):", q(gap))
            print(f"  share gap < 0: {np.mean(gap.dropna() < 0):.3f}  (n={gap.notna().sum():,})")
            for era, d in long.groupby("era"):
                gg = (d.ts_next - d.ts - d.exec_time).dropna()
                gp = (d.ts - d.ts_prev - d.exec_time).dropna()
                print(f"  {era}: share(t_next - t - E < 0)={np.mean(gg < 0):.3f} (n={len(gg)}), "
                      f"share(t - t_prev - E < 0)={np.mean(gp < 0):.3f} (n={len(gp)})")
            for k in ("submit", "test"):
                d = long[long.kind_next == k]
                gg = (d.ts_next - d.ts - d.exec_time).dropna()
                print(f"  next block is {k:6s}: n={len(gg):,} share(t_next - t - E < 0)={np.mean(gg < 0):.3f}")
                d = long[long.kind_prev == k]
                gp = (d.ts - d.ts_prev - d.exec_time).dropna()
                print(f"  prev block is {k:6s}: n={len(gp):,} share(t - t_prev - E < 0)={np.mean(gp < 0):.3f}")

    # ---- T2b: clustering of long runs ------------------------------------------------------ #
    print("\n=== T2b clustering of long runs (exec >= 100 s): distinct users sharing a 10-s window ===")
    s = b[(b.kind == "submit") & (b.exec_time >= 100)].copy()
    s["start_if_result"] = s.ts - s.exec_time      # start time if header = result time
    s["end_if_receipt"] = s.ts + s.exec_time       # end time if header = receipt time
    rng = np.random.default_rng(0)
    for col in ("ts", "start_if_result", "end_if_receipt"):
        w = (s[col] // 10).astype(np.int64)
        cnt = s.assign(w=w).groupby("w").user.nunique()
        top = cnt.sort_values(ascending=False).head(5)
        print(f"  {col:16s}: windows with >=3 distinct users: {int((cnt >= 3).sum())}, "
              f"with >=5: {int((cnt >= 5).sum())}; top counts {top.tolist()}")
    # null: shuffle exec_time among the long runs of the same semester
    null3 = []
    for _ in range(20):
        ex = s.groupby("semester").exec_time.transform(lambda x: rng.permutation(x.to_numpy()))
        for col, v in (("start", s.ts - ex), ("end", s.ts + ex)):
            w = (v // 10).astype(np.int64)
            null3.append((col, int((s.assign(w=w).groupby("w").user.nunique() >= 3).sum())))
    nd = pd.DataFrame(null3, columns=["col", "n3"]).groupby("col").n3.agg(["mean", "max"])
    print("  null (exec_time permuted within semester, 20 draws), windows with >=3 users:")
    print(nd.to_string())

    # ---- T2c: relation to login / logout ---------------------------------------------------- #
    print("\n=== T2c distance from header time to the same user's nearest logout / login record ===")
    lg = []
    for sem in b.semester.unique():
        p = os.path.join(ROOT, "data", "codebench", "parquet", "logins", sem.replace("_", "-") + ".parquet")
        d = pd.read_parquet(p, columns=["user", "ts", "kind"])
        d["semester"] = sem
        lg.append(d)
    lg = pd.concat(lg, ignore_index=True)
    lg["user"] = lg.user.astype(str)
    lg["tsf"] = (lg.ts - pd.Timestamp("1970-01-01")).dt.total_seconds()
    s = b[b.kind == "submit"].copy()
    s["tsf"] = s.ts.astype(float)
    s["cls"] = pd.cut(s.exec_time, [0, 1, 10, 60, 1000, 1e5], right=False)
    s = s.dropna(subset=["cls"]).sort_values("tsf")
    for kind in ("logout", "login"):
        L = lg[lg.kind.astype(str) == kind].sort_values("tsf")[["semester", "user", "tsf"]].rename(columns={"tsf": "t_l"})
        for direction in ("forward", "backward"):
            m = pd.merge_asof(s[["semester", "user", "tsf", "exec_time", "cls"]], L, left_on="tsf", right_on="t_l",
                              by=["semester", "user"], direction=direction)
            m["d"] = (m.t_l - m.tsf).abs()
            t = m.groupby("cls", observed=True).d.agg(
                n="size", med="median", share_le60s=lambda x: np.mean(x <= 60), share_le10s=lambda x: np.mean(x <= 10))
            print(f"  nearest {kind} {'after' if direction == 'forward' else 'before'} the header:")
            print(t.round(3).to_string())


if __name__ == "__main__":
    main()
