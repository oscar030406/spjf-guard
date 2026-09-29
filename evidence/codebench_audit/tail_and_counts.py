"""同口径长尾表与规模核对（回应 2026-09-18、09-19 两次审计）。只读 parquet；封存学期只计数。

第二次审计指出旧版两处错误，本版已改：
1. 去重键写成了不存在的 "timestamp"（实际列名 ts），且缺列被静默丢掉；现在缺列直接报错，
   并且同秒同键的行只作为诊断计数，不当作重复删除（它们多数是 EXECUTION TIME 不同的两个块）。
2. “2018–2019”分组用了 semester < "2020"，把 2017-2（有部分执行时间）也算进去；现在用显式学期白名单。
"""
import glob
import os

import numpy as np
import pandas as pd

P = r"<repo-root>\data\codebench\parquet"
SEALED = {"2023-1", "2023-2", "2024-1"}
ERAS = {
    "2018-1..2019-2": ["2018-1", "2018-2", "2019-1", "2019-2"],
    "2020-ERE..2022-2": ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2"],
}
KEY = ["semester", "class", "user", "assessment", "exercise", "ts", "kind"]

ev = pd.concat([pd.read_parquet(f).assign(semester=os.path.basename(f)[:-8])
                for f in sorted(glob.glob(P + r"\events\*.parquet"))], ignore_index=True)
missing = [c for c in KEY + ["exec_time"] if c not in ev.columns]
if missing:
    raise KeyError(f"required columns missing: {missing}")
assert not (set(ERAS["2018-1..2019-2"]) & set(ERAS["2020-ERE..2022-2"]))
assert not (set(sum(ERAS.values(), [])) & SEALED)

print("columns:", list(ev.columns))
print("all events:", len(ev), "| submit:", int((ev.kind == "submit").sum()), "| test:", int((ev.kind == "test").sum()))
print("distinct user ids with events:", ev.user.nunique(),
      "| distinct (semester,user):", ev[["semester", "user"]].drop_duplicates().shape[0])
same = ev.duplicated(subset=KEY, keep=False)
print("rows sharing (semester,class,user,assessment,exercise,ts,kind) with another row:", int(same.sum()),
      "| extra rows beyond the first of each group:", int(ev.duplicated(subset=KEY).sum()),
      "(diagnostic only; not removed)")

print("\nexec_time availability on submits, per DEV semester:")
s_all = ev[(ev.kind == "submit") & ~ev.semester.isin(SEALED)]
avail = s_all.groupby("semester").exec_time.agg(n="size", with_exec=lambda x: int(x.notna().sum()))
avail["share"] = avail.with_exec / avail.n
print(avail.to_string())


def row(x):
    x = np.sort(x.to_numpy(float))
    n = len(x)
    tot = x.sum()
    return dict(n=n, mean=x.mean(), m2=(x ** 2).mean(), p50=np.quantile(x, .5), p95=np.quantile(x, .95),
                p99=np.quantile(x, .99), max=x.max(),
                top1_share=x[int(np.floor(n * .99)):].sum() / tot, top5_share=x[int(np.floor(n * .95)):].sum() / tot)


sub = s_all[s_all.exec_time.notna()]
rows = []
for era, sems in ERAS.items():
    g = sub[sub.semester.isin(sems)]
    assert set(g.semester.unique()) <= set(sems)
    print(f"\n{era}: n per semester {g.groupby('semester').size().to_dict()}")
    rows.append(dict(era=era, var="C raw", **row(g.exec_time)))
    rows.append(dict(era=era, var="C_cap=min(C,60)", **row(g.exec_time.clip(upper=60))))
pd.set_option("display.width", 250)
pd.set_option("display.float_format", lambda v: f"{v:.4g}")
print()
print(pd.DataFrame(rows).to_string(index=False))
other = sorted(set(sub.semester) - set(sum(ERAS.values(), [])))
print("\nDEV semesters with exec_time outside both eras (reported, not pooled):", other,
      {s: int((sub.semester == s).sum()) for s in other})
