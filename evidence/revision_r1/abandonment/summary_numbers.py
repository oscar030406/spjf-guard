"""Print the ranges that the manuscript and the Supplementary quote from the abandonment
grid (evidence/abandonment_loop/out/cells.csv) and write them to
outputs/revision_r1/abandonment/summary_numbers.txt. Gap closed and withdrawn fraction are
means over the five overlays; the largest excess and the share of the bound are the worst
overlay; withdrawal ratios are per (overlay, level, patience, coin) group.

    python evidence/revision_r1/abandonment/summary_numbers.py
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[3]
CELLS = ROOT / "evidence/abandonment_loop/out/cells.csv"
OUT = ROOT / "outputs/revision_r1/abandonment/summary_numbers.txt"
GUARDS = ["Guard(300)", "Guard(600)", "Guard(1200)"]
KEY = ["overlay", "level", "patience_mean_s", "p_resubmit"]


def main():
    c = pd.read_csv(CELLS)
    lines = []
    out = lines.append
    g = c[c.policy.isin(GUARDS)]
    out(f"rows {len(c)}; guarded rows {len(g)}; jobs per run {sorted(c.n_jobs.unique())}")
    out(f"R1 bound violations {int(g.bound_violations.sum())}; worst W/bound {g.worst_ratio_to_bound.max():.4f}")
    over = g.n_over_bound_vs_fcfs_abandon
    out(f"R2 (descriptive) runs with a job over the bound {int((over > 0).sum())}; jobs {int(over.sum())}; "
        f"by p_resubmit {g.groupby('p_resubmit').n_over_bound_vs_fcfs_abandon.sum().astype(int).to_dict()}")

    p99 = c.pivot_table(index=KEY, columns="policy", values="p99_dl_s")
    out(f"groups {len(p99)}; FCFS highest p99 in {int((p99['FCFS'] >= p99.max(axis=1)).sum())}; "
        f"SJF lowest in {int((p99['SJF'] <= p99.min(axis=1)).sum())}")

    m = c.groupby(["level", "patience_mean_s", "p_resubmit", "policy"]).agg(
        gap=("gap_closed", "mean"), gap_user=("gap_closed_user", "mean"),
        excess=("max_excess_s", "max")).reset_index()
    for pol in ["SPJF-E", "Guard(600)"]:
        for pat in [float("inf"), 1800.0, 300.0, 60.0]:
            s = m[(m.policy == pol) & (m.patience_mean_s == pat)]
            s2 = s[s.level == 2]
            out(f"{pol} patience {pat}: gap {s.gap.min():.3f}-{s.gap.max():.3f}; "
                f"gap from first submission {s.gap_user.min():.3f}-{s.gap_user.max():.3f}; "
                f"largest excess all loads {s.excess.min():.1f}-{s.excess.max():.1f}, "
                f"heaviest load {s2.excess.min():.1f}-{s2.excess.max():.1f}")

    w = c.pivot_table(index=KEY, columns="policy", values="n_withdrawn")
    big = w[w["SPJF-E"] >= 1000]
    for num, den in [("SPJF-E", "FCFS"), ("Guard(600)", "FCFS"), ("Guard(600)", "SPJF-E")]:
        r = big[num] / big[den]
        out(f"withdrawn {num}/{den} on {len(big)} groups with >= 1000 SPJF-E withdrawals: {r.min():.3f}-{r.max():.3f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
