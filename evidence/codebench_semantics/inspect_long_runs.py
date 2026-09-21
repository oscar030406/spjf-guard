"""Inspect the time structure around long runs (exec_time >= 60 s), timestamps and kinds only.

For a few randomly chosen users with long runs (fixed seed) prints, relative to the first long
run's header time, every execution block (kind, exec_time, grade, error class, #test cases,
#empty user outputs), codemirror submit / kill_program events and login / logout records in a
window around it.  Users are shown by an index, never by id.  Also quantifies, for bursts of
long runs by one user, whether header+exec (common end if header = receipt time) or the
header itself (common end if header = result time) is what coincides.

Usage: uv run --with pandas --with numpy --with pyarrow python inspect_long_runs.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import load_blocks, load_cm, q

ROOT = r"<repo-root>"


def logins(sems) -> pd.DataFrame:
    out = []
    for sem in sems:
        d = pd.read_parquet(os.path.join(ROOT, "data", "codebench", "parquet", "logins",
                                         sem.replace("_", "-") + ".parquet"), columns=["user", "ts", "kind"])
        d["semester"] = sem
        out.append(d)
    d = pd.concat(out, ignore_index=True)
    d["user"] = d.user.astype(str)
    d["tsf"] = (d.ts - pd.Timestamp("1970-01-01")).dt.total_seconds()
    return d


def bursts(s: pd.DataFrame, gap: float = 120.0) -> pd.DataFrame:
    """Group long runs of one user whose header times are within `gap` s of each other."""
    s = s.sort_values(["semester", "user", "ts"]).copy()
    new = (s.user != s.user.shift()) | (s.semester != s.semester.shift()) | (s.ts - s.ts.shift() > gap)
    s["burst"] = new.cumsum()
    return s


def main():
    b = load_blocks()
    b = b.drop_duplicates(subset=["semester", "class", "user", "assessment", "exercise", "kind", "ts",
                                  "exec_time", "n_tc", "grade"])
    c = load_cm()
    lg = logins(b.semester.unique())
    long = b[(b.kind == "submit") & (b.exec_time >= 60)]

    print("=== long runs (>=60 s): error class, grade, empty outputs ===")
    long2 = long.assign(all_empty=(long.n_tc_empty_out == long.n_tc) & (long.n_tc > 0))
    print(long2.groupby("era").agg(n=("ts", "size"), users=("user", "nunique"),
                                   killed=("err_class", lambda x: np.mean(x == "Killed")),
                                   has_error=("has_error", "mean"),
                                   grade_recorded=("grade", lambda x: x.notna().mean()),
                                   grade_pos=("grade", lambda x: np.mean(x > 0)),
                                   all_outputs_empty=("all_empty", "mean")).round(3).to_string())

    print("\n=== bursts of long runs by one user (header gaps <= 120 s), bursts with >= 3 runs ===")
    s = bursts(long)
    g = s.groupby("burst")
    st = pd.DataFrame({
        "n": g.size(),
        "era": g.era.first(),
        "spread_header": g.ts.agg(np.ptp),
        "spread_header_plus_exec": g.apply(lambda x: np.ptp(x.ts + x.exec_time), include_groups=False),
        "spread_header_minus_exec": g.apply(lambda x: np.ptp(x.ts - x.exec_time), include_groups=False),
    })
    st = st[st.n >= 3]
    print(f"  bursts: {len(st)}  runs in them: {int(st.n.sum())}")
    for col in ("spread_header", "spread_header_plus_exec", "spread_header_minus_exec"):
        print(f"  {col:26s}", q(st[col], ps=(0.1, 0.25, 0.5, 0.75, 0.9)))
    print("  share of bursts where spread(header+exec) < spread(header-exec):",
          round(float(np.mean(st.spread_header_plus_exec < st.spread_header_minus_exec)), 3))

    print("\n=== example timelines (relative seconds; B=block, C=codemirror, L=login record) ===")
    # examples: runs >= 60 s in 2018-19, runs in [40, 60) s in 2020-22 (none reach 60 s there)
    ex = b[(b.kind == "submit") & (((b.era == "2018-19") & (b.exec_time >= 60))
                                   | ((b.era == "2020-22") & (b.exec_time >= 40)))]
    users = ex[["semester", "user", "era"]].drop_duplicates()
    picks = pd.concat([users[users.era == e].sample(4, random_state=1) for e in ("2018-19", "2020-22")])
    for i, (sem, uid, era) in enumerate(picks.itertuples(index=False)):
        lr = ex[(ex.semester == sem) & (ex.user == uid)].sort_values("ts").iloc[0]
        t0, E = lr.ts, lr.exec_time
        lo, hi = t0 - max(E, 60) - 120, t0 + max(E, 60) + 120
        rows = []
        bb = b[(b.semester == sem) & (b.user == uid) & b.ts.between(lo, hi)]
        for r in bb.itertuples():
            same = "*" if (r.assessment, r.exercise) == (lr.assessment, lr.exercise) else " "
            rows.append((r.ts - t0, f"B{same}{r.kind:6s} exec={r.exec_time:9.2f} grade={r.grade} "
                                    f"err={r.err_class} tc={r.n_tc} empty_out={r.n_tc_empty_out}"))
        cc = c[(c.semester == sem) & (c.user == uid) & c.ts.between(lo - 7200, hi + 7200)]
        for r in cc.itertuples():
            if lo - 5 <= r.ts <= hi + 5:
                same = "*" if (r.assessment, r.exercise) == (lr.assessment, lr.exercise) else " "
                rows.append((r.ts - t0, f"C{same}{r.etype} {r.fb}"))
        ll = lg[(lg.semester == sem) & (lg.user == uid) & lg.tsf.between(lo, hi)]
        for r in ll.itertuples():
            rows.append((r.tsf - t0, f"L {r.kind}"))
        print(f"\n-- user #{i} ({era}), first long run exec={E:.2f}s; * = same exercise")
        for dt, txt in sorted(rows, key=lambda x: x[0])[:45]:
            print(f"   {dt:+10.2f}  {txt}")


if __name__ == "__main__":
    main()
