"""Follow-up checks after T1-T5.

R1  Client-only clock: for submissions with a kill_program event near the header, time from that
    kill_program to the next codemirror "submit" feedback in the same file.  If the kill is the
    student's stop button ending a running submission (header = result time), the feedback follows
    within a second whatever exec_time is.  If the kill were the IDE stopping a console program at
    the submit click (header = receipt time), the feedback would come about exec_time later.
R2  exec_time == 0 runs (2020-22): are they the runs that hit a 60 s limit?  Compare the gap to the
    previous execution (pre_gap = header - previous header) with runs of known exec_time.
R3  Sealed-safe counts only: none.  (No sealed data is read.)

Usage: uv run --with pandas --with numpy --with pyarrow python refine_checks.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import CACHE, KEY, load_blocks, load_cm, q


def r1(b: pd.DataFrame, c: pd.DataFrame):
    print("=== R1 kill_program -> next codemirror submit feedback (both client clock) ===")
    off = pd.read_parquet(os.path.join(CACHE, "t1_matched.parquet"), columns=["semester", "user", "offset"]) \
        .groupby(["semester", "user"]).offset.median()
    off = off[off.abs() < 30].rename("off")
    s = b[b.kind == "submit"].join(off, on=["semester", "user"], how="inner")
    s = s.assign(gid=s[KEY].astype(str).agg("|".join, axis=1), tsf=s.ts.astype(float)).sort_values("tsf")
    k = c[c.etype == "kill_program"].join(off, on=["semester", "user"], how="inner")
    k = k.assign(gid=k[KEY].astype(str).agg("|".join, axis=1), kraw=k.ts, kts=k.ts - k.off).sort_values("kts")
    m = pd.merge_asof(s, k[["gid", "kts", "kraw"]], left_on="tsf", right_on="kts", by="gid",
                      direction="nearest", tolerance=3.0).dropna(subset=["kts"])
    cs = c[c.etype == "submit"]
    cs = cs.assign(gid=cs[KEY].astype(str).agg("|".join, axis=1), cm_ts=cs.ts).sort_values("cm_ts")
    m = m.sort_values("kraw")
    m2 = pd.merge_asof(m, cs[["gid", "cm_ts"]], left_on="kraw", right_on="cm_ts", by="gid",
                       direction="forward", tolerance=600.0)
    m2["kill_to_fb"] = m2.cm_ts - m2.kraw
    m2["cls"] = pd.cut(m2.exec_time, [0, 1, 5, 20, 60, 1e5], right=False)
    t = m2.groupby(["era", "cls"], observed=True).agg(
        n=("kill_to_fb", "size"), has_fb=("kill_to_fb", lambda x: x.notna().mean()),
        p25=("kill_to_fb", lambda x: x.quantile(0.25)), med=("kill_to_fb", "median"),
        p75=("kill_to_fb", lambda x: x.quantile(0.75)), E_med=("exec_time", "median"),
        share_fb_within_2s=("kill_to_fb", lambda x: np.mean(x <= 2)))
    print(t.round(3).to_string())
    print("  (result reading: med ~ latency, flat in E; receipt reading: med ~ E_med)")


def r2(b: pd.DataFrame):
    print("\n=== R2 exec_time == 0 runs in 2020-22 ===")
    s = b[b.era == "2020-22"].sort_values(["semester", "user", "ts", "seq"])
    g = s.groupby(["semester", "user"], sort=False)
    s = s.assign(pre=s.ts - g.ts.shift(1), post=g.ts.shift(-1) - s.ts)
    sub = s[s.kind == "submit"]
    groups = {
        "exec==0": sub[sub.exec_time == 0],
        "exec in (0,1) grade0": sub[(sub.exec_time > 0) & (sub.exec_time < 1) & (sub.grade == 0)],
        "exec in [20,40)": sub[(sub.exec_time >= 20) & (sub.exec_time < 40)],
        "exec in [40,60)": sub[(sub.exec_time >= 40) & (sub.exec_time < 60)],
    }
    rows = []
    for name, d in groups.items():
        rows.append((name, len(d), d.user.nunique(),
                     round(float(np.mean((d.n_tc_empty_out == d.n_tc) & (d.n_tc > 0))), 3),
                     round(float(d.pre.median()), 1), round(float(np.mean(d.pre >= 60)), 3),
                     round(float(np.mean(d.pre >= 55)), 3), round(float(d.post.median()), 1)))
    print(pd.DataFrame(rows, columns=["group", "n", "users", "all_out_empty", "pre_gap_med",
                                      "share_pre>=60", "share_pre>=55", "post_gap_med"]).to_string(index=False))
    z = groups["exec==0"]
    print("  exec==0: pre_gap quantiles:", q(z.pre, ps=(0.1, 0.25, 0.5, 0.75, 0.9)))
    print("  exec==0: pre_gap histogram 0-120 s by 10 s:",
          np.histogram(z.pre.dropna(), bins=np.arange(0, 130, 10))[0].tolist())
    same = z.merge(s[s.kind == "submit"][KEY + ["ts"]].rename(columns={"ts": "ts_other"}), on=KEY)
    same = same[same.ts_other < same.ts]
    last = same.groupby(KEY + ["ts"]).ts_other.max()
    print("  exec==0: time since the previous SUBMITION of the same exercise:",
          q((last.index.get_level_values("ts") - last.values), ps=(0.1, 0.25, 0.5, 0.75, 0.9)))
    print("  exec==0 by month:", pd.to_datetime(z.ts, unit="s").dt.strftime("%Y-%m").value_counts().sort_index().to_dict())


def main():
    b = load_blocks()
    b = b.drop_duplicates(subset=KEY + ["kind", "ts", "exec_time", "n_tc", "grade"])
    c = load_cm()
    r1(b, c)
    r2(b)


if __name__ == "__main__":
    main()
