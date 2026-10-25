"""Cold-task Spearman differences under resampling units that match the 'new task' claim.

evaluate.py resamples the 190 test users only, which treats the tested tasks as fixed. The
claim about newly released tasks generalises over tasks, so this reruns the same paired
differences on the cold-task rows (tasks with < 5 available results, test term 2022-2)
with four schemes: users, tasks, assignments, and users x tasks (pigeonhole: each row's
weight is the product of its user's and its task's multiplicity). Same predictions, same
three seeds, same weighted Spearman on fixed ranks as evaluate.py; 2,000 resamples, seed 3.

    uv run --no-sync python prechecks/predictor_neural/multiway_boot.py  -> out_multiway_boot.txt
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = "<cache-dir>"
OUT = os.path.join(SCRATCH, "pn")
CACHE = os.path.join(SCRATCH, "cb_v2_cache_r4")
SEEDS = (3, 4, 5)
N_BOOT = 2000
BOOT_SEED = 3
V = "core"
NEURAL = {"G0U": "G0U_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final",
          "G1": "G1_{v}_lr0.001_mean_wd0.0_dr0.1_s{s}_final"}
PAIRS = [("G1", "M4"), ("G0U", "M4"), ("G1", "G0U")]


def weighted_spearman(rx, ry, w):
    sw = w.sum()
    mx, my = (w * rx).sum() / sw, (w * ry).sum() / sw
    cx = np.sqrt((w * (rx - mx) ** 2).sum() / sw)
    cy = np.sqrt((w * (ry - my) ** 2).sum() / sw)
    return float((w * (rx - mx) * (ry - my)).sum() / sw / (cx * cy))


def main():
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    m_te = np.isin(B["sem"], ["2022-2"])
    cold = B["ex_nres"][m_te] < 5
    y = B["y"][m_te].astype("float64")[cold]
    units = {
        "user": np.unique(B["user_str"][m_te][cold], return_inverse=True)[1],
        "task": np.unique(B["ex"][m_te][cold], return_inverse=True)[1],
        "assignment": np.unique(B["asm"][m_te][cold], return_inverse=True)[1],
    }
    ref = pd.read_parquet(os.path.join(CACHE, f"p1pred_ires0_{V}.parquet"))
    P = {("M4", s): ref[f"{V}|M4|{s}|y"].values[cold] for s in SEEDS}
    for m, pat in NEURAL.items():
        for s in SEEDS:
            P[m, s] = np.load(os.path.join(OUT, f"pred_{pat.format(v=V, s=s)}.npz"))["yhat"].astype(
                "float64")[cold]
    lines = [f"cold-task rows {len(y)}; distinct users {units['user'].max() + 1}, tasks "
             f"{units['task'].max() + 1}, assignments {units['assignment'].max() + 1}"]
    point = {}
    for a, b in PAIRS:
        point[a, b] = np.mean([spearmanr(y, P[a, s]).statistic - spearmanr(y, P[b, s]).statistic
                               for s in SEEDS])
    ry = rankdata(y)
    rk = {k: rankdata(v) for k, v in P.items()}
    rows = []
    for scheme in ("user", "task", "assignment", "user x task"):
        rng = np.random.default_rng(BOOT_SEED)
        draws = {p: [] for p in PAIRS}
        for _ in range(N_BOOT):
            if scheme == "user x task":
                wu = np.bincount(rng.integers(0, units["user"].max() + 1, units["user"].max() + 1),
                                 minlength=units["user"].max() + 1)[units["user"]]
                wt = np.bincount(rng.integers(0, units["task"].max() + 1, units["task"].max() + 1),
                                 minlength=units["task"].max() + 1)[units["task"]]
                w = (wu * wt).astype(float)
            else:
                u = units[scheme]
                n = u.max() + 1
                w = np.bincount(rng.integers(0, n, n), minlength=n)[u].astype(float)
            if w.sum() == 0:
                continue
            for a, b in PAIRS:
                draws[a, b].append(np.mean([weighted_spearman(rk[a, s], ry, w)
                                            - weighted_spearman(rk[b, s], ry, w) for s in SEEDS]))
        for a, b in PAIRS:
            v = np.array(draws[a, b])
            v = v[np.isfinite(v)]
            lo, hi = np.quantile(v, [0.025, 0.975])
            rows.append(dict(scheme=scheme, pair=f"{a}-{b}", dSpear=point[a, b], lo=lo, hi=hi,
                             resamples=len(v)))
            lines.append(f"{scheme:12s} {a}-{b:4s} dSpear {point[a, b]:+.4f} [{lo:+.4f}, {hi:+.4f}]"
                         f"  ({len(v)} usable resamples)")
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "multiway_boot.csv"), index=False)
    with open(os.path.join(HERE, "out_multiway_boot.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
