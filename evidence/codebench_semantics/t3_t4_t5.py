"""T3 / T4 / T5 and the logout check.

T3  exec_time against the number of test cases in the block; floor of exec_time for trivial
    correct programs (is it CPU time of the program, or wall clock including process start?);
    exec_time of correct submissions against concurrent load (does it include contention?).
T4  2020-1 .. 2022-2: density of exec_time just below 60 s, date of the last run >= 60 s,
    how the slowest runs look; 2018-19: what the >= 1000 s runs look like.
T5  TEST blocks: any timing?  Codemirror "saida_testar" / "kill_program" events against TEST
    headers of the same file pair.
L   distance from the header of long runs to the same user's logout record (signed).

Usage: uv run --with pandas --with numpy --with pyarrow python t3_t4_t5.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import KEY, load_blocks, load_cm, q

ROOT = r"<repo-root>"


def t3(b: pd.DataFrame):
    s = b[(b.kind == "submit") & b.exec_time.notna()]
    ok = s[(s.grade == 100) & ~s.has_error]
    print("=== T3a exec_time of correct submissions (grade 100, no error) by number of test cases ===")
    t = ok.groupby(["era", "n_tc"]).exec_time.agg(
        n="size", p1=lambda x: x.quantile(0.01), p10=lambda x: x.quantile(0.1),
        med="median", p90=lambda x: x.quantile(0.9)).round(3)
    t = t[t.n >= 200]
    print(t.to_string())
    for era, d in ok[ok.exec_time < 5].groupby("era"):
        d = d[d.n_tc.between(1, 15)]
        med = d.groupby("n_tc").exec_time.median()
        p10 = d.groupby("n_tc").exec_time.quantile(0.10)
        cnt = d.groupby("n_tc").size()
        keep = cnt[cnt >= 200].index
        s1 = np.polyfit(keep, med[keep], 1)
        s2 = np.polyfit(keep, p10[keep], 1)
        print(f"  {era}: median exec = {s1[1]:.3f} + {s1[0]:.3f} * n_tc ; p10 exec = {s2[1]:.3f} + {s2[0]:.3f} * n_tc "
              f"(n_tc 1..15 with >=200 runs)")

    print("\n=== T3b load dependence: correct runs, log(exec) vs number of submissions in the same "
          "10-min window (all users), exercise-demeaned ===")
    s = s.copy()
    s["win"] = (s.ts // 600).astype(np.int64)
    load = s.groupby(["semester", "win"]).size().rename("load")
    ok = ok.assign(win=(ok.ts // 600).astype(np.int64)).merge(load.reset_index(), on=["semester", "win"])
    ok = ok[ok.exec_time > 0]
    ok["lx"] = np.log(ok.exec_time)
    ok["lx_dm"] = ok.lx - ok.groupby(["semester", "exercise", "n_tc"]).lx.transform("median")
    ok["load_bin"] = pd.cut(ok.load, [0, 5, 10, 20, 40, 80, 160, 1e6], right=False)
    for era, d in ok.groupby("era"):
        t = d.groupby("load_bin", observed=True).agg(n=("lx", "size"), load_med=("load", "median"),
                                                     exec_med=("exec_time", "median"),
                                                     rel_exec=("lx_dm", lambda x: float(np.exp(x.median()))))
        print(f"-- era {era} (rel_exec = median exec relative to the same exercise and n_tc)")
        print(t.round(3).to_string())


def t4(b: pd.DataFrame):
    s = b[(b.kind == "submit") & b.exec_time.notna()].copy()
    s["date"] = pd.to_datetime(s.ts, unit="s")
    print("\n=== T4a last runs >= 60 s and first date after which none reach 60 s ===")
    big = s[s.exec_time >= 60]
    print("  last five runs >= 60 s (date, exec):",
          [(str(d)[:16], round(e, 1)) for d, e in big.sort_values("ts").tail(5)[["date", "exec_time"]].itertuples(index=False)])
    s["ym"] = s.date.dt.strftime("%Y-%m")
    m = s[s.semester == "2019_2"].groupby("ym").exec_time.agg(n="size", mx="max", n_ge60=lambda x: int((x >= 60).sum()))
    print("  2019-2 by month:", m.round(2).to_dict("index"))

    late = s[s.era == "2020-22"]
    print("\n=== T4b 2020-22: counts per 1-s bin of exec_time in [40, 62) ===")
    h = np.histogram(late.exec_time, bins=np.arange(40, 63, 1))[0]
    print("  " + " ".join(f"{int(lo)}:{c}" for lo, c in zip(np.arange(40, 62, 1), h)))
    h = np.histogram(late.exec_time, bins=np.arange(59, 60.01, 0.1))[0]
    print("  [59,60) by 0.1 s:", h.tolist())
    print("  counts in [10,20) [20,30) [30,40) [40,50) [50,55) [55,58) [58,59) [59,60) [60,inf):",
          np.histogram(late.exec_time, bins=[10, 20, 30, 40, 50, 55, 58, 59, 60, 1e9])[0].tolist())
    top = late[late.exec_time >= 50]
    print(f"  runs >= 50 s: n={len(top)}, users={top.user.nunique()}; err_class={top.err_class.astype(str).value_counts().to_dict()}; "
          f"grade recorded={top.grade.notna().mean():.3f}; grade>0={np.mean(top.grade > 0):.3f}; "
          f"all outputs empty={np.mean((top.n_tc_empty_out == top.n_tc) & (top.n_tc > 0)):.3f}")
    print("  runs >= 50 s, exec_time / n_tc:", q(top.exec_time / top.n_tc.replace(0, np.nan)))
    print("  exec digits after the point, 2020-22:", late.exec_ndec.value_counts().sort_index().to_dict())
    z = late[late.exec_ndec == 0]
    print("  integer-valued exec_time values (2020-22):", z.exec_time.value_counts().head(8).to_dict(),
          "err:", z.err_class.astype(str).value_counts().head(5).to_dict())
    print("  exec_time == 0 by era:", s.groupby("era").exec_time.apply(lambda x: int((x == 0).sum())).to_dict())
    print(f"    exec==0 runs: grade={z.grade.value_counts(dropna=False).head(4).to_dict()} "
          f"n_tc={z.n_tc.value_counts().head(4).to_dict()} semesters={z.semester.value_counts().to_dict()}")

    print("\n=== T4d runs whose test-case outputs are all empty (likely non-terminating), grade 0, "
          "exec_time by number of test cases ===")
    hung = s[(s.n_tc > 0) & (s.n_tc_empty_out == s.n_tc) & (s.grade == 0) & (s.exec_time >= 5)]
    for era, d in hung.groupby("era"):
        t = d.groupby("n_tc").exec_time.agg(n="size", p10=lambda x: x.quantile(0.1), p25=lambda x: x.quantile(0.25),
                                            med="median", p75=lambda x: x.quantile(0.75), p90=lambda x: x.quantile(0.9),
                                            mx="max")
        print(f"-- {era}")
        print(t[t.n >= 10].round(2).to_string())
    for era, d in s[(s.n_tc > 0) & (s.grade == 0)].groupby("era"):
        frac = d.n_tc_empty_out / d.n_tc
        print(f"  {era}: share of grade-0 runs with exec>=5 s among all-empty-output runs "
              f"{np.mean(d.exec_time[frac == 1] >= 5):.3f} vs runs with some output {np.mean(d.exec_time[frac < 1] >= 5):.3f}")

    early = s[s.era == "2018-19"]
    print("\n=== T4c 2018-19: runs >= 1000 s ===")
    v = early[early.exec_time >= 1000]
    print(f"  n={len(v)} users={v.user.nunique()} err_class={v.err_class.astype(str).value_counts().to_dict()}")
    print(f"  grade recorded={v.grade.notna().mean():.3f} grade>0={np.mean(v.grade > 0):.3f} n_tc dist={v.n_tc.value_counts().to_dict()}")
    k = early[early.err_class == "Killed"]
    print("  all 'Killed' runs 2018-19:", q(k.exec_time, ps=(0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)))
    print("  'Killed' runs, n_tc distribution:", k.n_tc.value_counts().head(5).to_dict())
    k2 = late[late.err_class == "Killed"]
    print("  'Killed' runs 2020-22:", q(k2.exec_time, ps=(0.01, 0.1, 0.5, 0.9, 0.99)))
    for era, d in s.groupby("era"):
        print(f"  {era}: has_error & n_tc==0 (run aborted before test cases were listed): "
              f"{int(((d.n_tc == 0) & d.has_error).sum()):,}; n_tc==0 & no error: {int(((d.n_tc == 0) & ~d.has_error).sum()):,}")


def t5(b: pd.DataFrame, c: pd.DataFrame):
    print("\n=== T5a TEST blocks: exec_time present? ===")
    t = b[b.kind == "test"]
    print("  share of TEST blocks with an EXECUTION TIME value:", round(float(t.exec_time.notna().mean()), 6),
          " n=", f"{len(t):,}")
    print("\n=== T5b codemirror events per semester vs TEST / SUBMITION blocks ===")
    cc = c.groupby(["semester", "etype"], observed=True).size().unstack(fill_value=0)
    cc.columns = [f"cm_{x}" for x in cc.columns]
    bb = b.groupby(["semester", "kind"]).size().unstack(fill_value=0)
    bb.columns = [f"blocks_{x}" for x in bb.columns]
    print(cc.join(bb).to_string())
    print("\n=== T5c saida_testar vs TEST header, same file pair (nearest event within 1 h) ===")
    tt = t.sort_values("ts").copy()
    st = c[c.etype == "saida_testar"].sort_values("ts").rename(columns={"ts": "cm_ts"})
    tt["gid"] = tt[KEY].astype(str).agg("|".join, axis=1)
    st["gid"] = st[KEY].astype(str).agg("|".join, axis=1)
    tt["tsf"] = tt.ts.astype(float)
    for direction in ("nearest", "forward", "backward"):
        m = pd.merge_asof(tt, st[["gid", "cm_ts"]], left_on="tsf", right_on="cm_ts", by="gid",
                          direction=direction, tolerance=3600.0).dropna(subset=["cm_ts"])
        m["lag"] = m.cm_ts - m.ts
        print(f"  {direction:8s} lag = cm_saida_testar - TEST_header:", q(m.lag))
    m = pd.merge_asof(tt, st[["gid", "cm_ts"]], left_on="tsf", right_on="cm_ts", by="gid",
                      direction="nearest", tolerance=3600.0).dropna(subset=["cm_ts"])
    m["lag"] = m.cm_ts - m.ts
    m["has_err"] = m.has_error
    print("  nearest lag by whether the TEST produced an ERROR section:")
    for k, d in m.groupby("has_err"):
        print(f"    error={k}: {q(d.lag, ps=(0.1, 0.25, 0.5, 0.75, 0.9))}")
    # the same comparison for SUBMITION vs cm submit, as a reference for the client clock offset
    ss = b[b.kind == "submit"].sort_values("ts").copy()
    cs = c[c.etype == "submit"].sort_values("ts").rename(columns={"ts": "cm_ts"})
    ss["gid"] = ss[KEY].astype(str).agg("|".join, axis=1)
    cs["gid"] = cs[KEY].astype(str).agg("|".join, axis=1)
    ss["tsf"] = ss.ts.astype(float)
    ms = pd.merge_asof(ss[ss.semester.isin(m.semester.unique())], cs[["gid", "cm_ts"]], left_on="tsf",
                       right_on="cm_ts", by="gid", direction="nearest", tolerance=3600.0).dropna(subset=["cm_ts"])
    print("  reference, same semesters: cm_submit - SUBMITION header (exec<1 s):",
          q((ms.cm_ts - ms.ts)[ms.exec_time < 1], ps=(0.1, 0.25, 0.5, 0.75, 0.9)))


def logout_check(b: pd.DataFrame):
    print("\n=== L: signed time from the same user's nearest logout record to the header (header - logout) ===")
    lg = []
    for sem in b.semester.unique():
        d = pd.read_parquet(os.path.join(ROOT, "data", "codebench", "parquet", "logins",
                                         sem.replace("_", "-") + ".parquet"), columns=["user", "ts", "kind"])
        d["semester"] = sem
        lg.append(d)
    lg = pd.concat(lg, ignore_index=True)
    lg = lg[lg.kind.astype(str) == "logout"]
    lg["user"] = lg.user.astype(str)
    lg["t_l"] = (lg.ts - pd.Timestamp("1970-01-01")).dt.total_seconds()
    s = b[b.kind == "submit"].copy()
    s["tsf"] = s.ts.astype(float)
    s = s.sort_values("tsf")
    m = pd.merge_asof(s, lg.sort_values("t_l")[["semester", "user", "t_l"]], left_on="tsf", right_on="t_l",
                      by=["semester", "user"], direction="nearest")
    m["d"] = m.tsf - m.t_l
    m["cls"] = pd.cut(m.exec_time, [0, 1, 10, 60, 1000, 1e5], right=False)
    t = m.groupby(["era", "cls"], observed=True).d.agg(
        n="size",
        share_abs_le2=lambda x: np.mean(x.abs() <= 2),
        share_abs_le10=lambda x: np.mean(x.abs() <= 10),
        share_0_to_10=lambda x: np.mean((x >= 0) & (x <= 10)),
        share_m10_to_0=lambda x: np.mean((x < 0) & (x >= -10)))
    print(t.round(4).to_string())
    near = m[(m.exec_time >= 60) & (m.d.abs() <= 10)]
    print(f"  long runs (>=60 s) with a logout within 10 s: n={len(near)}; header - logout:",
          q(near.d, ps=(0.1, 0.25, 0.5, 0.75, 0.9)))
    print("   their err_class:", near.err_class.astype(str).value_counts().to_dict())
    print("   runs sharing that logout (same user, |header - logout| <= 10 s), per logout:",
          q(near.groupby(["semester", "user", "t_l"]).size(), ps=(0.5, 0.9, 0.99)))
    print("   does the run start (header - exec) precede the logout?  share:",
          round(float(np.mean(near.tsf - near.exec_time < near.t_l)), 3))


def kill_check(b: pd.DataFrame, c: pd.DataFrame):
    """kill_program (client) near the header (result reading) or near header+E (receipt reading)?"""
    print("\n=== K: codemirror kill_program events around submissions (client clock offset removed) ===")
    off = pd.read_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "t1_matched.parquet"),
                          columns=["semester", "user", "offset"]).groupby(["semester", "user"]).offset.median()
    off = off[off.abs() < 30].rename("off")          # users whose clock is within 30 s of the server
    s = b[(b.kind == "submit")].join(off, on=["semester", "user"], how="inner")
    k = c[c.etype == "kill_program"].join(off, on=["semester", "user"], how="inner")
    k = k.assign(kts=k.ts - k.off).sort_values("kts")
    s = s.assign(gid=s[KEY].astype(str).agg("|".join, axis=1))
    k = k.assign(gid=k[KEY].astype(str).agg("|".join, axis=1))
    s["cls"] = pd.cut(s.exec_time, [0, 1, 5, 20, 60, 1e5], right=False)
    for anchor in ("header", "header+E", "header-E"):
        a = s.ts + (s.exec_time if anchor == "header+E" else (-s.exec_time if anchor == "header-E" else 0))
        ss = s.assign(anc=a.astype(float)).dropna(subset=["anc"]).sort_values("anc")
        m = pd.merge_asof(ss, k[["gid", "kts"]], left_on="anc", right_on="kts", by="gid",
                          direction="nearest", tolerance=600.0)
        m["d"] = m.kts - m.anc
        t = m.groupby(["era", "cls"], observed=True).d.agg(
            n="size", share_kill_within_3s=lambda x: np.mean(x.abs() <= 3),
            share_kill_within_10s=lambda x: np.mean(x.abs() <= 10))
        print(f"-- anchor = {anchor}")
        print(t.round(4).to_string())


def main():
    b = load_blocks()
    b = b.drop_duplicates(subset=KEY + ["kind", "ts", "exec_time", "n_tc", "grade"])
    c = load_cm()
    t3(b)
    t4(b)
    t5(b, c)
    logout_check(b)
    kill_check(b, c)


if __name__ == "__main__":
    main()
