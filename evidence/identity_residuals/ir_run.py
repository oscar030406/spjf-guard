"""Stage 2: measure D_i on the real trace, one load level per invocation.

    D_i = k * ( W_P[i] - W_FCFS[i] ) - ( In_i - Out_i )

for the primary development trace, overlay rep 0, at the load level's k, for FCFS (as the
reference schedule) and the three policies of `ir_common.POLICIES`.  Every job of every
cell is checked against Theorem 1's bound 2(k-1)L, and the cell's row goes to `cells.csv`.

The waits come from `ir_kern.py`, which `ir_validate.py` has shown to be the project
kernel plus a recorder; `run_policy` re-checks that job for job here as well, on all
17.6 M jobs, by running `guardkern.run` beside it.

usage: ir_run.py --level {0,1,2} [--policies spjf,cap600,adv]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import ir_common as C
import ir_overtake as OV
from ir_common import V31

Q = (0.0, 0.001, 0.01, 0.5, 0.99, 0.999, 1.0)
QN = ("min", "p0.1", "p1", "p50", "p99", "p99.9", "max")


def r2(y, yhat):
    ss_res = float(np.square(y - yhat).sum())
    ss_tot = float(np.square(y - y.mean()).sum())
    return 1.0 - ss_res / ss_tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True)
    ap.add_argument("--policies", default=",".join(C.POLICIES))
    a_ = ap.parse_args()
    pols = a_.policies.split(",")

    lg = C.Log("run")
    Z = V31.load_trace(C.TRACE, C.REP)
    K = [int(x) for x in Z["K"]]
    k = K[a_.level]
    a = np.ascontiguousarray(Z["a"])
    svc = np.ascontiguousarray(Z["svc"])
    n = len(a)
    svc_us = C.us(svc)
    a_us = C.us(a)
    rho = float(Z["W"]) / (3600.0 * k)
    lg.el(f"{C.TRACE} rep{C.REP} level {a_.level}: k={k} (K={K}) n={n:,} "
          f"busy-hour rho={rho:.4f} L={C.L:g}s  total work={svc.sum() / 86400:.1f} d")

    rf = C.run_policy(a, svc, k, None, dict(policy="fcfs"))
    assert np.array_equal(rf.dord, np.arange(n)), "FCFS dispatch order is not rank order"
    wf_us = C.us(rf.dtime) - a_us
    wf = rf.w
    orderf = OV.dispatch_order(rf.dord)
    Inf_, Outf_ = OV.in_out_fenwick(svc_us, orderf)
    assert not Inf_.any() and not Outf_.any(), "FCFS has In != 0 or Out != 0"
    del Inf_, Outf_, orderf, rf
    lg.el(f"FCFS: dispatch order == rank order, In = Out = 0 on all {n:,} jobs; "
          f"mean wait {wf.mean():.3f} s, p99 {np.quantile(wf, 0.99):.3f} s")

    rows = []
    for tag in pols:
        pred, kw, desc = C.policy_spec(tag, k, Z)
        r = C.run_policy(a, svc, k, np.ascontiguousarray(pred), kw)
        lg.el(f"{tag}: {desc}")
        order = OV.dispatch_order(r.dord)
        In, Out = OV.in_out_fenwick(svc_us, order)
        same = OV.in_same_phase(svc_us, order, r.dtime)
        ph = OV.phase_id(order, r.dtime)
        del order
        w_us = C.us(r.dtime) - a_us
        net = In - Out
        D = k * (w_us - wf_us) - net                     # exact int64 microseconds
        bound = 2 * (k - 1) * C.L_US
        slack = 2 * k                                    # the two 0.5 us wait roundings
        viol = int((np.abs(D) > bound + slack).sum())
        assert viol == 0, f"{tag}: Theorem 1 violated on {viol} jobs"
        # the same residual computed entirely in float64 seconds, as a cross-check that
        # the microsecond quantisation of the waits is what the docstring claims
        Df = k * (r.w - wf) - net / 1e6
        dq = float(np.abs(Df - D / 1e6).max())

        ex = r.w - wf                                    # real excess, seconds
        pr = net / (1e6 * k)                             # what the identity predicts
        row = dict(
            trace=C.TRACE, rep=C.REP, level=a_.level, k=k, rho_busy=round(rho, 4),
            policy=tag, label=C.POLICY_LABEL[tag], spec=desc, n_jobs=n,
            n_phases=int(ph.max()) + 1,
            maxabsD_L=float(np.abs(D).max()) / C.L_US,
            bound_L=2.0 * (k - 1),
            ratio_to_bound=float(np.abs(D).max()) / bound,
            frac_D_zero=float((D == 0).mean()),
            frac_In_pos=float((In > 0).mean()), frac_Out_pos=float((Out > 0).mean()),
            samephase_share_sumIn=float(same.sum() / max(In.sum(), 1)),
            samephase_share_jobs=float((same > 0).sum() / max((In > 0).sum(), 1)),
            frac_In_all_samephase=float(((In > 0) & (same == In)).sum()
                                        / max((In > 0).sum(), 1)),
            mean_excess_s=float(ex.mean()), max_excess_s=float(ex.max()),
            mean_absD_L=float(np.abs(D).mean()) / C.L_US,
            r2_net_over_k=r2(ex, pr),
            max_abs_err_s=float(np.abs(ex - pr).max()),
            mean_abs_err_s=float(np.abs(ex - pr).mean()),
            med_abs_err_s=float(np.median(np.abs(ex - pr))),
            sum_In_s=float(In.sum() / 1e6), sum_Out_s=float(Out.sum() / 1e6),
            float_vs_int_max_diff_s=dq, bound_violations=viol,
            n_forced=int(r.n_forced), forced_frac=r.n_forced / max(r.n_disp, 1),
        )
        qs = np.quantile(D / C.L_US, Q)
        for nm, v in zip(QN, qs):
            row[f"D_L_{nm}"] = float(v)
        rows.append(row)
        lg.w(f"    n={n:,}  max|D| = {row['maxabsD_L']:.6f} L  "
             f"(bound 2(k-1)L = {row['bound_L']:.0f} L, "
             f"ratio {row['ratio_to_bound']:.5f})")
        lg.w(f"    D/L quantiles " + "  ".join(
            f"{nm}={row['D_L_' + nm]:+.6f}" for nm in QN))
        lg.w(f"    D_i = 0 on {row['frac_D_zero'] * 100:.4f}% of jobs;  In>0 on "
             f"{row['frac_In_pos'] * 100:.4f}%,  Out>0 on {row['frac_Out_pos'] * 100:.4f}%")
        lg.w(f"    same-phase share of sum In = "
             f"{row['samephase_share_sumIn'] * 100:.4f}%;  In_i entirely same-phase on "
             f"{row['frac_In_all_samephase'] * 100:.4f}% of the jobs with In>0")
        lg.w(f"    (In-Out)/k vs real excess:  R2 = {row['r2_net_over_k']:.6f}  "
             f"max abs err = {row['max_abs_err_s']:.4f} s  "
             f"mean {row['mean_abs_err_s']:.6f} s  median {row['med_abs_err_s']:.6f} s")
        lg.w(f"    float64-seconds D vs integer-microsecond D: max diff {dq:.3e} s")
        del In, Out, same, D, Df, net, ex, pr, r, ph

    p = os.path.join(C.HERE, "cells.csv")
    old = pd.read_csv(p).to_dict("records") if os.path.exists(p) else []
    t = pd.DataFrame(old + rows).drop_duplicates(subset=["level", "policy"], keep="last")
    t.sort_values(["level", "policy"]).to_csv(p, index=False)
    lg.el(f"wrote {p} ({len(t)} cells)")
    lg.close()


if __name__ == "__main__":
    main()
