"""Collect results/grid_*.csv into the Pareto tables.

Two robustness axes are reported for every design, because they are not the same thing:
  guar_excess_max  the GUARANTEED worst-case excess over FCFS on this trace,
                   max_i (bound_i - W_fcfs[i]); flat for a constant or capped budget,
                   proportional to W_fcfs for an uncapped relative budget;
  max_excess_wf0   the OBSERVED worst excess among jobs FCFS would have started within
                   1 s, i.e. the harm done to submissions that were not going to wait.
and the gain axis is the fraction of the FCFS -> true-size-SJF gap closed on the
deadline-window p99 wait.

usage:  pareto.py      (writes pareto_main.csv, pareto_adv.csv, pareto_tables.txt)
"""
import sys
sys.dont_write_bytecode = True
import os
import glob
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
COLS = ["policy", "k", "guar_excess_max", "guar_excess_at0", "gap_p99dl", "gap_mean",
        "w_p99_dl", "max_excess", "max_excess_wf0", "max_heavy", "qw_forced_frac",
        "used_over_allowed", "bound_viol"]


def pareto_flag(df, xcol, ycol):
    """1 if no other row has x <= and y >= with one strict (minimise x, maximise y)."""
    out = []
    for _, r in df.iterrows():
        dom = ((df[xcol] <= r[xcol] + 1e-9) & (df[ycol] >= r[ycol] - 1e-12) &
               ((df[xcol] < r[xcol] - 1e-9) | (df[ycol] > r[ycol] + 1e-12)))
        out.append(0 if dom.any() else 1)
    return out


def main():
    frames = []
    for p in sorted(glob.glob(os.path.join(RES, "grid_*.csv"))):
        d = pd.read_csv(p)
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["rep", "level", "predictor", "policy"], keep="last")
    assert (df["bound_viol"] <= 0).all(), "a bound violation reached the CSV"
    df.to_csv(os.path.join(HERE, "all_runs.csv"), index=False)
    out = open(os.path.join(HERE, "pareto_tables.txt"), "w", encoding="utf-8")

    def emit(s=""):
        print(s, flush=True)
        out.write(s + "\n")

    emit("guar = guaranteed worst-case per-job excess over FCFS on this trace "
         "(max_i bound_i - W_fcfs[i]);")
    emit("guar@0 = the same bound for a job FCFS would not have delayed; "
         "harm = observed max excess over")
    emit("FCFS among jobs with W_fcfs <= 1 s; gap = fraction of the FCFS->true-SJF gap "
         "closed on deadline-window p99;")
    emit("qwF = share of queue-weighted dispatches forced to a guarded job; "
         "used = observed excess / allowed excess.")
    emit("P1 marks the Pareto front on (guar, gap), P2 on (harm, gap).")

    main_df = df[(df.rep == "rep0") & (df.predictor == "M4")]
    rows = []
    for lev, g in main_df.groupby("level"):
        g = g.copy()
        gg = g[g.guar_excess_max < 1e30].copy()
        gg["P1"] = pareto_flag(gg, "guar_excess_max", "gap_p99dl")
        gg["P2"] = pareto_flag(gg, "max_excess_wf0", "gap_p99dl")
        g = g.merge(gg[["policy", "P1", "P2"]], on="policy", how="left").fillna({"P1": 0, "P2": 0})
        g = g.sort_values(["guar_excess_max", "gap_p99dl"])
        k = int(g.k.iloc[0])
        rho = float(g.rho_busy.iloc[0])
        emit(f"\n=== rep0, predictor M4, level {lev}: k = {k}, busy-hour rho = {rho:.4f}, "
             f"FCFS p99_dl = {g.fcfs_p99dl.iloc[0]:.1f} s, true-SJF p99_dl = "
             f"{g.sjf_p99dl.iloc[0]:.1f} s ===")
        emit(f"{'policy':22s} {'guar':>8s} {'guar@0':>8s} {'gap':>6s} {'gapMean':>7s} "
             f"{'p99_dl':>8s} {'maxExc':>8s} {'harm':>7s} {'maxHeavy':>8s} {'qwF%':>6s} "
             f"{'used':>5s}  P1 P2")
        for _, r in g.iterrows():
            gu = "-" if r.guar_excess_max > 1e30 else f"{r.guar_excess_max:8.1f}"
            g0 = "-" if r.guar_excess_at0 > 1e30 else f"{r.guar_excess_at0:8.1f}"
            us = "-" if pd.isna(r.used_over_allowed) else f"{r.used_over_allowed:5.3f}"
            emit(f"{r.policy:22s} {gu:>8s} {g0:>8s} {r.gap_p99dl:6.3f} {r.gap_mean:7.3f} "
                 f"{r.w_p99_dl:8.2f} {r.max_excess:8.1f} {r.max_excess_wf0:7.1f} "
                 f"{r.max_heavy:8.1f} {r.qw_forced_frac*100:6.2f} {us:>5s}  "
                 f"{int(r.P1)}  {int(r.P2)}")
            rows.append(dict(level=lev, **{c: r[c] for c in COLS}, P1=int(r.P1), P2=int(r.P2)))
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "pareto_main.csv"), index=False)

    # ------------------------------------------------------------------ adversarial
    adv = df[(df.rep == "rep0") & (df.predictor != "M4")]
    keep = sorted(set(adv.policy))
    emit("\n\n=== rep0, adversarial predictors (selected designs) ===")
    arows = []
    for (lev, pn), g in adv.groupby(["level", "predictor"]):
        k = int(g.k.iloc[0])
        emit(f"\n-- level {lev} (k={k}), predictor {pn}: FCFS p99_dl "
             f"{g.fcfs_p99dl.iloc[0]:.1f} s --")
        emit(f"{'policy':22s} {'guar':>8s} {'gap':>7s} {'p99_dl':>8s} {'maxExc':>8s} "
             f"{'harm':>8s} {'maxHeavy':>8s} {'qwF%':>6s} {'used':>5s}")
        for _, r in g.sort_values("guar_excess_max").iterrows():
            gu = "-" if r.guar_excess_max > 1e30 else f"{r.guar_excess_max:8.1f}"
            us = "-" if pd.isna(r.used_over_allowed) else f"{r.used_over_allowed:5.3f}"
            emit(f"{r.policy:22s} {gu:>8s} {r.gap_p99dl:7.3f} {r.w_p99_dl:8.2f} "
                 f"{r.max_excess:8.1f} {r.max_excess_wf0:8.1f} {r.max_heavy:8.1f} "
                 f"{r.qw_forced_frac*100:6.2f} {us:>5s}")
            arows.append(dict(level=lev, predictor=pn, **{c: r[c] for c in COLS}))
    pd.DataFrame(arows).to_csv(os.path.join(HERE, "pareto_adv.csv"), index=False)

    # ------------------------------------------------------------------ other traces
    for rep in ("rep1", "k1rep0"):
        sub = df[df.rep == rep]
        if not len(sub):
            continue
        emit(f"\n\n=== {rep} ===")
        for (lev, pn), g in sub.groupby(["level", "predictor"]):
            emit(f"\n-- level {lev} (k={int(g.k.iloc[0])}), predictor {pn}: FCFS p99_dl "
                 f"{g.fcfs_p99dl.iloc[0]:.1f} s, true-SJF {g.sjf_p99dl.iloc[0]:.1f} s --")
            emit(f"{'policy':22s} {'guar':>8s} {'gap':>7s} {'p99_dl':>8s} {'maxExc':>8s} "
                 f"{'harm':>8s} {'maxHeavy':>8s} {'used':>5s}")
            for _, r in g.sort_values("guar_excess_max").iterrows():
                gu = "-" if r.guar_excess_max > 1e30 else f"{r.guar_excess_max:8.1f}"
                us = "-" if pd.isna(r.used_over_allowed) else f"{r.used_over_allowed:5.3f}"
                emit(f"{r.policy:22s} {gu:>8s} {r.gap_p99dl:7.3f} {r.w_p99_dl:8.2f} "
                     f"{r.max_excess:8.1f} {r.max_excess_wf0:8.1f} {r.max_heavy:8.1f} "
                     f"{us:>5s}")
    emit(f"\n\ntotal runs collected: {len(df)}; bound violations: "
         f"{int((df.bound_viol > 0).sum())}")
    out.close()


if __name__ == "__main__":
    main()
