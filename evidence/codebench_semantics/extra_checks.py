"""Small extra checks: pairing sanity of T1, the lower edge of 'Killed' runs, feedback 'other'.

Usage: uv run --with pandas --with numpy --with pyarrow python extra_checks.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import CACHE, KEY, load_blocks, load_cm, q


def main():
    m = pd.read_parquet(os.path.join(CACHE, "t1_matched.parquet"))
    c = load_cm()
    fb = c[c.etype == "submit"]
    print("=== E1 T1 pairing sanity: verdict agreement vs |adj lag| ===")
    m = m.merge(fb.rename(columns={"ts": "cm_ts"})[["semester", "class", "user", "assessment", "exercise", "cm_ts", "fb"]],
                on=["semester", "class", "user", "assessment", "exercise", "cm_ts"], how="left")
    m["blk"] = np.where(m.grade == 100, "correct", np.where(m.grade > 0, "partial", "wrong"))
    m["agree"] = m.blk == m.fb.astype(str)
    m["abs_adj"] = pd.cut(m.adj.abs(), [0, 1, 3, 10, 60, 1e9], right=False)
    print(m.groupby("abs_adj", observed=True).agg(n=("agree", "size"), agree=("agree", "mean")).round(3).to_string())
    gp = m[m.grade == 100]
    print("  grade-100 blocks: share with 'wrong' feedback by semester:",
          gp.groupby("semester").apply(lambda x: round(float(np.mean(x.fb.astype(str) == "wrong")), 3),
                                       include_groups=False).to_dict())
    print("\n=== E2 lower edge of 'Killed' runs (2018-19) ===")
    b = load_blocks(["2018_1", "2018_2", "2019_1", "2019_2"])
    k = b[(b.kind == "submit") & (b.err_class == "Killed")]
    print("  smallest 10 exec_time:", np.sort(k.exec_time.to_numpy())[:10].round(1).tolist())
    print("  histogram [300,900) by 60 s:", np.histogram(k.exec_time, bins=np.arange(300, 901, 60))[0].tolist())
    print("  by semester:", k.semester.value_counts().to_dict())
    print("  histogram [0,3600) by 120 s:", np.histogram(k.exec_time, bins=np.arange(0, 3601, 120))[0].tolist())
    print("  exec_time mod 360 s (6 bins of 60 s), Killed runs >= 360 s:",
          np.histogram(np.mod(k.exec_time[k.exec_time >= 360], 360), bins=np.arange(0, 361, 60))[0].tolist())

    print("\n=== E4 T1 restricted to verdict-agreeing pairs (filters mismatched pairs without using lag) ===")
    a = m[m.agree]
    a = a.assign(bin=pd.cut(a.exec_time, [0, 1, 5, 10, 20, 40, 60, 1000, 1e5], right=False))
    t = a.groupby("bin", observed=True).agg(
        n=("adj", "size"), E_med=("exec_time", "median"), adj_med=("adj", "median"),
        lag_med=("lag", "median"),
        share_adj_within_3s_of_0=("adj", lambda x: np.mean(x.abs() <= 3)),
        share_adj_within_3s_of_E=("adj", lambda x: np.mean((x - a.loc[x.index, "exec_time"]).abs() <= 3)))
    print(t.round(3).to_string())
    print("\n=== E3 codemirror submit feedback classes by semester ===")
    print(fb.groupby(["semester", "fb"], observed=True).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
