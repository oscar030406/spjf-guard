"""The headline table, rebuilt from MY OWN simulations of the five overlays.

p99_dl / mean / p99_all / qw_fired are means over the five overlays, max_excess / harm /
max_heavy are the worst over them -- the report's own aggregation rule.  The last column
is the report's printed value, for eyeballing.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

from vsim import SCRATCH

MSIM = os.path.join(SCRATCH, "mv3_verify")
MAIN = r"<repo-root>\evidence\main_v3"
lev = int(sys.argv[1]) if len(sys.argv) > 1 else 2

cells = {r: pd.read_csv(os.path.join(MSIM, f"vcell_primary_rep{r}_L{lev}.csv"))
         .set_index("policy") for r in range(5)}
txt = open(os.path.join(MAIN, "out_main_v3.txt"), encoding="utf-8").read()
blk = re.search(rf"--- level {lev}: .*?\n(.*?)\n\n", txt, re.S).group(1)
rep = {l.split()[0]: l.split() for l in blk.splitlines()[1:]}

F = np.array([cells[r].loc["FCFS", "w_p99_dl"] for r in range(5)])
S = np.array([cells[r].loc["SJF-ref", "w_p99_dl"] for r in range(5)])
print(f"level {lev}, k = {int(cells[0].loc['FCFS', 'k'])}, five overlays, MY simulator")
print(f"{'policy':22s}{'p99_dl_s':>10s}{'gap':>8s}{'mean_s':>9s}{'max_exc':>10s}"
      f"{'harm':>9s}{'max_heavy':>11s}{'qw_fired':>10s}   report p99_dl")
for p in cells[0].index:
    if not all(p in cells[r].index for r in range(5)):
        continue
    g = lambda c: np.array([cells[r].loc[p, c] for r in range(5)])      # noqa: E731
    P = g("w_p99_dl")
    print(f"{p:22s}{P.mean():10.4f}{np.mean((F - P) / (F - S)):8.4f}"
          f"{g('w_mean').mean():9.4f}{g('max_excess').max():10.2f}"
          f"{g('harm_wf1s').max():9.2f}{g('max_heavy').max():11.2f}"
          f"{g('qw_forced_frac').mean():10.4f}   "
          f"{rep.get(p, ['', 'not in the report'])[1]}")
