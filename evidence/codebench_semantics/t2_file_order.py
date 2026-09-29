"""T2-order: are header timestamps monotone in file order?

A block contains the verdict and the program output, so it can only be appended to
executions/<a>_<e>.log after the run.  If the header time were the RECEIPT time, a long job
received before a short one but finishing after it would be appended later with an EARLIER
header time, i.e. out of order.  If the header time is the RESULT time, file order and header
order agree.  Counts adjacent pairs (block k, block k+1) in file order with ts[k+1] < ts[k],
and checks what they look like.

Also prints the gap tables that separate the two readings in 2020-22 at a finer exec_time grid:
median of (t - t_prev - E) and (t_next - t - E).

Usage: uv run --with pandas --with numpy --with pyarrow python t2_file_order.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import KEY, load_blocks, q


def main():
    b = load_blocks().sort_values(KEY + ["seq"])
    g = b.groupby(KEY, sort=False)
    b["ts_next_file"] = g.ts.shift(-1)
    b["exec_next_file"] = g.exec_time.shift(-1)
    b["kind_next_file"] = g.kind.shift(-1)
    d = b.dropna(subset=["ts_next_file"])
    dt = d.ts_next_file - d.ts
    print("=== adjacent blocks in file order: sign of header-time difference ===")
    t = pd.DataFrame({"pairs": d.groupby("era").size(),
                      "share_dt<0": (dt < 0).groupby(d.era).mean(),
                      "n_dt<0": (dt < 0).groupby(d.era).sum(),
                      "share_dt==0": (dt == 0).groupby(d.era).mean()})
    print(t.round(5).to_string())
    neg = d[dt < 0].assign(dt=dt[dt < 0])
    if len(neg):
        print("  out-of-order pairs: size of the backwards step:", q(-neg.dt))
        print("  kinds (this -> next):", neg.groupby(["kind", "kind_next_file"], observed=True).size().to_dict())
        print("  exec_time of the LATER-appended block (receipt reading predicts it is long):",
              q(neg.exec_next_file))
        print("  exec_time of the earlier block:", q(neg.exec_time))
    # how many out-of-order pairs we would expect if header = receipt time: count pairs of
    # submissions in the same file where the later-received one finishes first
    s = b[b.kind == "submit"].sort_values(KEY + ["ts", "seq"])
    gs = s.groupby(KEY, sort=False)
    s = s.assign(ts_nx=gs.ts.shift(-1))
    s = s.dropna(subset=["ts_nx", "exec_time"])
    would = (s.ts + s.exec_time > s.ts_nx + 1)   # this run still running when the next one arrived (+1 s)
    print("\n=== receipt reading: submissions still running when the next one of the same file arrived ===")
    print(would.groupby(s.era).agg(["sum", "mean"]).round(5).to_string())

    print("\n=== finer gap table, SUBMITION blocks, same user any exercise (seconds) ===")
    b2 = b.drop_duplicates(subset=KEY + ["kind", "ts", "exec_time", "n_tc", "grade"]) \
          .sort_values(["semester", "user", "ts", "seq"])
    g2 = b2.groupby(["semester", "user"], sort=False)
    b2 = b2.assign(pre=b2.ts - g2.ts.shift(1), post=g2.ts.shift(-1) - b2.ts)
    s = b2[(b2.kind == "submit") & (b2.exec_time >= 5)]
    s = s.assign(bin=pd.cut(s.exec_time, [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 200, 1000, 1e5], right=False))
    for era, d in s.groupby("era"):
        gg = d.groupby("bin", observed=True)
        t = pd.DataFrame({"n": gg.size(), "E_med": gg.exec_time.median(),
                          "med(pre-E)": gg.apply(lambda x: (x.pre - x.exec_time).median(), include_groups=False),
                          "med(post-E)": gg.apply(lambda x: (x.post - x.exec_time).median(), include_groups=False),
                          "med(pre)": gg.pre.median(), "med(post)": gg.post.median(),
                          "share pre>=E": gg.apply(lambda x: np.mean(x.pre.dropna() >= x.exec_time[x.pre.notna()]), include_groups=False),
                          "share post>=E": gg.apply(lambda x: np.mean(x.post.dropna() >= x.exec_time[x.post.notna()]), include_groups=False)})
        print(f"-- era {era}")
        print(t.round(2).to_string())
        # median regression proxy: OLS of bin medians on E_med
        tt = t[t.n >= 20]
        if len(tt) >= 3:
            sp = np.polyfit(tt.E_med, tt["med(pre)"], 1)[0]
            so = np.polyfit(tt.E_med, tt["med(post)"], 1)[0]
            print(f"   slope of median pre-gap on E = {sp:.2f}; slope of median post-gap on E = {so:.2f} "
                  f"(result reading predicts ~1 and ~0; receipt reading ~0 and ~1)")


if __name__ == "__main__":
    main()
