"""C1 extra: the guard-parameter choice, redone on the validation overlay the builder
built but never used (valid rep 1), with my own simulator.

Limitation (2) of out_main_v3.txt says the choice was made on ONE validation overlay and
its overlay-to-overlay stability was never checked.  This script runs the same 15-point
grid (B0 in {30,120,600} x k/4, eta in {0,0.25,0.5,0.75,0.9}) plus the fixed-budget guard
at each of the three G on valid rep 1, applies the report's own rule (feasible = worst
harm over the three load levels <= G/2; objective = worst-level deadline-window p99 gap
closed) and prints what it would have selected.

usage: vselect2.py [--rep 1]
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np
import pandas as pd

import vsim
from vsim import WORK

GS = (300.0, 600.0, 1200.0)
B0B = (30.0, 120.0, 600.0)
ETAS = (0.0, 0.25, 0.5, 0.75, 0.9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--trace", default="valid")
    a = ap.parse_args()
    z = np.load(os.path.join(vsim.BUILDER_TRACES, f"{a.trace}_rep{a.rep}.npz"))
    Z = {q: z[q] for q in ("a", "svc", "dl", "hvt", "K", "W", "tweedie")}
    dl = Z["dl"].astype(bool)
    rows = []
    t0 = time.time()
    for lev, k in enumerate(list(Z["K"])):
        k = int(k)
        wf = vsim.run(Z["a"], Z["svc"], k, policy="fcfs")["w"]
        q1 = wf <= 1.0
        ws = vsim.run(Z["a"], Z["svc"], k, policy="pri", pred=Z["svc"])["w"]
        f99 = float(np.quantile(wf[dl], .99))
        s99 = float(np.quantile(ws[dl], .99))
        print(f"[{time.time() - t0:5.0f}s] level {lev} k={k}: FCFS p99dl {f99:.3f}, "
              f"SJF-ref {s99:.3f}", flush=True)
        for G in GS:
            Bmax = vsim.gmax(G, k)
            cfgs = [("fix", Bmax, 0.0)] + [("cap", b, e) for b in B0B for e in ETAS]
            for tag, b0b, eta in cfgs:
                B0 = Bmax if tag == "fix" else min(b0b * k / 4.0, Bmax)
                r = vsim.run(Z["a"], Z["svc"], k, policy="cap", pred=Z["tweedie"],
                             B0=B0, eta=eta, Bmax=Bmax)
                w = r["w"]
                ub = vsim.bound(wf, k, B0=B0, eta=eta, Bmax=Bmax)
                rows.append(dict(level=lev, k=k, G=G, guard=tag,
                                 B0_base=np.nan if tag == "fix" else b0b, eta=eta,
                                 p99dl=float(np.quantile(w[dl], .99)),
                                 gap=(f99 - float(np.quantile(w[dl], .99))) / (f99 - s99),
                                 harm=float((w - wf)[q1].max()),
                                 max_excess=float((w - wf).max()),
                                 viol=int((w > ub + 1e-6).sum())))
                print(f"[{time.time() - t0:5.0f}s]   G{G:g} {tag} B0={b0b:g} eta={eta:g}: "
                      f"gap {rows[-1]['gap']:.4f} harm {rows[-1]['harm']:.1f} "
                      f"viol {rows[-1]['viol']}", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(WORK, f"vgrid_{a.trace}_rep{a.rep}.csv"), index=False)
    assert d.viol.sum() == 0, "per-job bound violated on my own waits"
    print("\n=== the rule, applied to this overlay ===")
    sel = pd.read_csv(r"<repo-root>\evidence\main_v3"
                      r"\selected_params.csv")
    for G in GS:
        sub = d[(d.G == G) & (d.guard == "cap")]
        agg = (sub.groupby(["B0_base", "eta"])
               .agg(worst_gap=("gap", "min"), worst_harm=("harm", "max")).reset_index())
        ok = agg[agg.worst_harm <= G / 2.0]
        row = sel[sel.G == G].iloc[0]
        if not len(ok):
            print(f"  G={G:g}: NO feasible configuration on this overlay")
            continue
        best = ok.sort_values(["worst_gap", "worst_harm", "B0_base", "eta"],
                              ascending=[False, True, True, True]).iloc[0]
        cur = agg[(agg.B0_base == row.B0_base) & (agg.eta == row.eta)].iloc[0]
        print(f"  G={G:6g}: this overlay picks B0={best.B0_base:g} eta={best.eta:g} "
              f"(worst gap {best.worst_gap:.4f}, harm {best.worst_harm:.1f}); "
              f"the reported choice B0={row.B0_base:g} eta={row.eta:g} scores "
              f"gap {cur.worst_gap:.4f}, harm {cur.worst_harm:.1f}, "
              f"feasible={bool(cur.worst_harm <= G / 2)} -> "
              f"{'SAME' if (best.B0_base == row.B0_base and best.eta == row.eta) else 'DIFFERENT'}")


if __name__ == "__main__":
    main()
