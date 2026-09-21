"""C7 (and the manifest part of C1): is every reported cell complete, under one manifest,
and produced after the 20:25 incident?

Checks, all from the artefacts:
  * sha256 of every mv3_*.py and the combined manifest hash, against the report header;
  * every '## ... manifest=' line of every stage log carries that hash, and its timestamp
    is after the incident; every invocation is closed by a '## done' line;
  * the 16 main cells and the 3 selection cells exist, with the expected policy count,
    job count, zero bound violations and a finite used/allowed ratio for guarded rows;
  * the bootstrap replicate files hold 2,000 finite replicates per policy and metric, and
    how many replicates the gain stage silently drops as non-finite;
  * the report's own count of per-job bound checks.
"""
from __future__ import annotations

import hashlib
import os
import re

import numpy as np
import pandas as pd

from vsim import SCRATCH

MAIN = r"<repo-root>\evidence\main_v3"
BSIM = os.path.join(SCRATCH, "mv3", "sim")
INCIDENT = "2026-09-19 20:25:00"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    txt = open(os.path.join(MAIN, "out_main_v3.txt"), encoding="utf-8").read()
    rep_man = re.search(r"manifest of the scripts that produced every number below: "
                        r"([0-9a-f]{64})", txt).group(1)
    files = sorted(f for f in os.listdir(MAIN)
                   if f.startswith("mv3_") and f.endswith(".py") and f != "mv3_report.py")
    h = hashlib.sha256()
    print("=" * 90)
    print("1. MANIFEST")
    for f in files:
        s = sha(os.path.join(MAIN, f))
        h.update(f.encode() + b"\0" + s.encode() + b"\0")
        want = re.search(rf"{re.escape(f)}\s+([0-9a-f]{{64}})", txt)
        ok = want and want.group(1) == s
        print(f"  {f:22s} {s[:16]}...  {'matches the report' if ok else 'DIFFERS'}")
    mine = h.hexdigest()
    print(f"  combined: report {rep_man[:24]}...  recomputed {mine[:24]}...  "
          f"{'MATCH' if mine == rep_man else 'MISMATCH'}")
    for f in ("mv3_report.py",):
        print(f"  {f}: {sha(os.path.join(MAIN, f))[:16]}... (formats only, not in the manifest)")
    for p, nm in ((r"<repo-root>\evidence\guard_variants\guardkern.py",
                   "guardkern.py (the simulator kernel)"),
                  (r"<repo-root>\evidence\codebench_service_v2"
                   r"\service_precheck_v2.py", "service_precheck_v2.py (pipeline)")):
        st = os.stat(p)
        import time as _t
        print(f"  OUTSIDE the manifest: {nm} sha {sha(p)[:16]}... "
              f"last written (local) {_t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(st.st_mtime))}")

    print("=" * 90)
    print("2. STAGE LOGS")
    for f in sorted(os.listdir(MAIN)):
        if not (f.startswith("out_") and f.endswith(".txt")) or f == "out_main_v3.txt":
            continue
        lines = open(os.path.join(MAIN, f), encoding="utf-8").read().splitlines()
        heads = [l for l in lines if l.startswith("## ") and "manifest=" in l]
        dones = [l for l in lines if l.startswith("## done")]
        mans = {re.search(r"manifest=([0-9a-f]{64})", l).group(1) for l in heads}
        ts = [l[3:22] for l in heads]
        claimed = re.search(rf"{re.escape(f)}\s+(\d+) lines", txt)
        print(f"  {f:18s} invocations {len(heads):2d}  done {len(dones):2d}  "
              f"manifests {'one, matching' if mans == {rep_man} else mans}  "
              f"first {min(ts)}  last {max(ts)}  "
              f"after the incident: {all(t > INCIDENT for t in ts)}  "
              f"lines {len(lines)} (report says {claimed.group(1) if claimed else '-'})")

    print("=" * 90)
    print("3. CELLS")
    tot = 0
    for trace, reps, levs, pset in (("primary", range(5), range(3), "main"),
                                    ("k1", [0], [0], "main"),
                                    ("valid", [0], range(3), "grid")):
        for r in reps:
            for l in levs:
                p = os.path.join(BSIM, f"{trace}_rep{r}_L{l}_{pset}.csv")
                if not os.path.exists(p):
                    print(f"  MISSING {p}")
                    continue
                d = pd.read_csv(p)
                g = d[d.guard != "-"] if "guard" in d.columns else d.iloc[0:0]
                nb = -1
                bp = os.path.join(BSIM, f"bw_{trace}_rep{r}_L{l}_{pset}.npz")
                if os.path.exists(bp):
                    z = np.load(bp)
                    shapes = {v.shape for v in (z[k] for k in z.files)}
                    nfin = min(int(np.isfinite(z[k]).sum()) for k in z.files)
                    nb = f"{sorted(shapes)} min finite {nfin}"
                tot += int(g.n_jobs.sum()) if len(g) else 0
                print(f"  {trace} rep{r} L{l} {pset}: policies {len(d):2d} guarded {len(g):2d} "
                      f"n_jobs {int(d.n_jobs.iloc[0]):,} k {int(d.k.iloc[0])} "
                      f"bound_viol max {int(d.bound_viol.max())} "
                      f"used<=1 {bool((d.used_over_allowed.dropna() <= 1).all())} boot {nb}")
    print(f"  per-job bound checks over the guarded runs: {tot:,}")
    m = re.search(r"guarded runs checked: ([\d,]+) .*?([\d,]+) per-job bound checks, "
                  r"violations: (\d+)", txt)
    print(f"  the report claims: {m.group(1)} guarded runs, {m.group(2)} checks, "
          f"{m.group(3)} violations")

    print("=" * 90)
    print("4. HOW MANY BOOTSTRAP REPLICATES THE GAIN STAGE DROPS")
    for l in range(3):
        drop = {}
        for r in range(5):
            z = np.load(os.path.join(BSIM, f"primary_rep{r}_L{l}_main.npz")
                        .replace("primary_rep", "bw_primary_rep"))
            F, S = z["p99dl|FCFS"], z["p99dl|SJF-ref"]
            bad = int((~np.isfinite((F - F) / (F - S))).sum())
            drop[r] = bad
        print(f"  level {l}: non-finite gap replicates per overlay {drop} of 2000")


if __name__ == "__main__":
    main()
