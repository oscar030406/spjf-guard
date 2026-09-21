"""Cross-domain comparison: education traces vs the two non-education traces.

    uv run ... python cd_table.py     ->  out_cross_domain_table.txt

The education numbers are quoted from files already in evidence/ (each one carries its
source below); nothing in the education pipeline is re-run and no education data is read.
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np
import pandas as pd

import cd_common as C

# --- education numbers, each with the file it is quoted from ------------------------ #
EDU = {
    "codebench": {
        "src_sched": "evidence/guard_variants/out_grid_rep0_L{0,1,2}_M4_1.txt "
                     "(rep0, M4 predictor) and evidence/ranking_score/out_table_primary_5reps.txt",
        "src_pred": "evidence/codebench_service_v2/out_service_v2.txt l.86-100 (M4 heavy AUROC) and "
                    "docs/research_plan.md 3.3 (AUROC 0.928-0.934)",
        "L": 60.0,
        "tail_top1": None,          # not tabulated in the quoted outputs
        "auroc": 0.9283, "spearman": None, "rmse_log": None,
        "levels": {
            # rho_busy: (FCFS p99_dl, SPJF gap_p99dl, SPJF max_excess_s,
            #            guard@5L gap, guard@5L max_excess_s)
            0.50: (22.170, 0.735, 1244.8, None, None),
            0.78: (109.708, 0.861, 3055.1, 0.705, 195.3),   # FIX-B600: guarantee 276 s = 4.6 L
            1.06: (263.120, 0.892, 5882.9, 0.429, 215.4),   # FIX-B600: guarantee 300 s = 5.0 L
        },
    },
    "accoding": {
        "src": "evidence/accoding_v2/out_accoding_v2.txt (audit l.114-120, prediction "
               "l.390-396, deadline_rho0.8_main l.899-911)",
        "L": 30.5,
        "tail_top1_runtime": 0.2905, "tail_top5_runtime": 0.6483,
        "tail_top1_service": 0.1224, "tail_top5_service": 0.2896,
        "auroc": 0.9266, "auprc": 0.5267, "spearman": 0.6924, "rmse_log": 0.2714,
        "gap_p99_rho08": 0.980, "spjf_max_excess_rho08": 601.7,
        "guard_B15_gap_p99": 0.739, "guard_B15_max_excess": 9.4,
    },
}

NEW = {"azure": dict(name="Azure Functions 2021 (serverless invocations)",
                     tail=(0.4429, 0.8787), mean_med=108.0),
       "netbatch": dict(name="Intel Netbatch pool D 2012 (EDA compute farm)",
                        tail=(0.3720, 0.6285), mean_med=14.15)}


def pick(sim, k_label, policy):
    r = sim[(sim.cap == k_label) & (sim.policy.str.startswith(policy))]
    return r.iloc[0] if len(r) else None


def main():
    out = os.path.join(C.HERE, "out_cross_domain_table.txt")
    with open(out, "w", encoding="utf-8") as fh:
        C.log(fh, "=" * 100)
        C.log(fh, "CROSS-DOMAIN CHECK OF THE SPJF + OVERTAKE-BUDGET-GUARD METHOD")
        C.log(fh, "=" * 100)
        C.log(fh, "Education side quoted from: " + EDU["codebench"]["src_sched"])
        C.log(fh, "                            " + EDU["accoding"]["src"])
        C.log(fh, "New side: evidence/cross_domain/out_audit_*.txt, out_predict_*.txt, "
                  "out_sim_*.txt (this study).\n")

        C.log(fh, "-- A. cost distribution (how heavy is the tail) " + "-" * 45)
        C.log(fh, f"{'trace':34s} {'unit':>8s} {'median':>10s} {'mean':>10s} "
                  f"{'p99':>10s} {'top1% work':>11s} {'top5% work':>11s} {'L used':>12s}")
        rowsA = [
            ("CodeBench (education)", "s", "~0.19", "-", "-", "n/a", "n/a", "60 (platform)"),
            ("ACcoding (education)", "s", "0.508", "0.834", "6.50", "0.122", "0.290",
             "30.5 (n_tests*limit)"),
        ]
        for w in ("azure", "netbatch"):
            a = pd.read_csv(os.path.join(C.HERE, f"meta_{w}.csv")).iloc[0]
            sim = pd.read_csv(os.path.join(C.HERE, f"sim_{w}.csv"))
            t = NEW[w]["tail"]
            if w == "azure":
                rowsA.append((NEW[w]["name"], "s", "0.031", "3.348", "72.2",
                              f"{t[0]:.3f}", f"{t[1]:.3f}", f"{a.L:.1f} (train p99.9)"))
            else:
                rowsA.append((NEW[w]["name"], "s", "486", "6875", "93482",
                              f"{t[0]:.3f}", f"{t[1]:.3f}", f"{a.L:.0f} (train p99.9)"))
        for r in rowsA:
            C.log(fh, f"{r[0]:34s} {r[1]:>8s} {r[2]:>10s} {r[3]:>10s} {r[4]:>10s} "
                      f"{r[5]:>11s} {r[6]:>11s} {r[7]:>12s}")
        C.log(fh, "\n  Azure is at least as heavy-tailed as the education traces (top 1% of "
                  "invocations = 44% of\n  the work, top 5% = 88%); Netbatch is comparable "
                  "(37% / 63%).  The tail assumption transfers.")

        C.log(fh, "\n-- B. predictability of the cost from information at arrival " + "-" * 31)
        C.log(fh, f"{'trace':34s} {'entity':>18s} {'RMSE log1p':>11s} {'Spearman':>10s} "
                  f"{'AUROC':>8s} {'AUPRC':>8s} {'eta^2 of identity':>18s}")
        C.log(fh, f"{'CodeBench (M4, dev test)':34s} {'user x exercise':>18s} "
                  f"{'n/a':>11s} {'n/a':>10s} {0.9283:8.4f} {'n/a':>8s} "
                  f"{'-':>18s}")
        C.log(fh, f"{'ACcoding (M4, dev test)':34s} {'user x problem':>18s} "
                  f"{0.2714:11.4f} {0.6924:10.4f} {0.9266:8.4f} {0.5267:8.4f} {'-':>18s}")
        for w, ent, eta in (("azure", "app/function", 0.8670), ("netbatch", "command (exe)", 0.6379)):
            p = pd.read_csv(os.path.join(C.HERE, f"pred_{w}.csv")).set_index("model")
            r = p.loc["ALL/log"]
            C.log(fh, f"{'  ' + w + ' ALL/log':34s} {ent:>18s} {r.rmse_log:11.4f} "
                      f"{r.spearman:10.4f} {r.auroc:8.4f} {r.auprc:8.4f} {eta:18.4f}")
            r = p.loc["ENT/log"]
            C.log(fh, f"{'  ' + w + ' ENT/log (history only)':34s} {ent:>18s} {r.rmse_log:11.4f} "
                      f"{r.spearman:10.4f} {r.auroc:8.4f} {r.auprc:8.4f} {'':>18s}")
            r = p.loc["STATIC/log"]
            C.log(fh, f"{'  ' + w + ' STATIC/log (no history)':34s} {ent:>18s} {r.rmse_log:11.4f} "
                      f"{r.spearman:10.4f} {r.auroc:8.4f} {r.auprc:8.4f} {'':>18s}")

        C.log(fh, "\n-- C. scheduling on the real arrival times " + "-" * 49)
        C.log(fh, "gap = (W_FCFS - W_policy) / (W_FCFS - W_SJF-true) on the p99 wait; "
                  "excess in units of L.")
        C.log(fh, f"{'trace / load':46s} {'k':>7s} {'FCFS p99':>10s} {'FCFS p99/L':>11s} "
                  f"{'gap SPJF':>9s} {'SPJF max excess':>16s}")
        for rho, lev in EDU["codebench"]["levels"].items():
            f99, gap, exc, _, _ = lev
            C.log(fh, f"{'CodeBench busy-hour rho=' + f'{rho:.2f}':46s} {'4-8':>7s} "
                      f"{f99:10.2f} {f99/60.0:11.2f} {gap:9.3f} "
                      f"{exc:10.1f} = {exc/60.0:4.0f} L")
        C.log(fh, f"{'ACcoding poisson rho=0.8 (synthetic arrivals)':46s} {'-':>7s} "
                  f"{0.648:10.3f} {0.648/30.5:11.4f} {0.980:9.3f} "
                  f"{601.7:10.1f} = {601.7/30.5:4.0f} L")
        for w in ("azure", "netbatch"):
            sim = pd.read_csv(os.path.join(C.HERE, f"sim_{w}.csv"))
            L = sim.L.iloc[0]
            for lab in sim.cap.unique():
                f = pick(sim, lab, "FCFS")
                s = pick(sim, lab, "SPJF-log")
                if f is None or f.p99_s <= 0:
                    continue
                C.log(fh, f"{w + ' ' + lab:46s} {int(f.k):7d} {f.p99_s:10.2f} "
                          f"{f.p99_s/L:11.4f} {s.gap_p99:9.3f} "
                          f"{s.max_excess_fcfs_s:10.1f} = {s.max_excess_fcfs_s/L:4.2f} L")

        C.log(fh, "\n-- D. what the guard costs and what it buys " + "-" * 48)
        C.log(fh, "The theorem's smallest expressible guarantee is (3-2/k) L ~ 3 L, so a "
                  "guarantee is only\nuseful when L is small next to the waits one cares "
                  "about.  FCFS p99 / L above is that ratio.")
        C.log(fh, f"{'trace / load':46s} {'policy':>22s} {'gap p99':>8s} {'max excess (L)':>15s} "
                  f"{'fire %':>8s}")
        C.log(fh, f"{'CodeBench busy-hour rho=1.06':46s} {'guard 5.0 L':>22s} {0.429:8.3f} "
                  f"{215.4/60.0:15.2f} {'0.38':>8s}")
        C.log(fh, f"{'CodeBench busy-hour rho=0.78':46s} {'guard 4.6 L':>22s} {0.705:8.3f} "
                  f"{195.3/60.0:15.2f} {'0.14':>8s}")
        for w in ("azure", "netbatch"):
            sim = pd.read_csv(os.path.join(C.HERE, f"sim_{w}.csv"))
            L = sim.L.iloc[0]
            for lab in sim.cap.unique():
                f = pick(sim, lab, "FCFS")
                if f is None or f.p99_s <= 0:
                    continue
                for pol, tag in (("guard G=5L", "guard 5 L"),
                                 ("guard B/k=0.001L", "guard B/k=0.001L"),
                                 ("guard B/k=0.01L", "guard B/k=0.01L"),
                                 ("guard B/k=0.1L", "guard B/k=0.1L")):
                    g = pick(sim, lab, pol)
                    if g is None:
                        continue
                    C.log(fh, f"{w + ' ' + lab:46s} {tag:>22s} {g.gap_p99:8.3f} "
                              f"{g.max_excess_fcfs_s/L:15.4f} {g.fire_rate*100:8.3f}")

        C.log(fh, "\n-- E. reading " + "-" * 78)
        for line in READING.strip().split("\n"):
            C.log(fh, line)
    print("wrote", out)


READING = """
1. Tail.  Both new traces are heavy-tailed in the same way the education traces are: on
   Azure the top 1% of invocations carry 0.44 of the work and the top 5% carry 0.88; on
   Netbatch 0.37 and 0.63.  Nothing about the method depended on education-specific tails.

2. Prediction.  The direction of the education result survives, and gets stronger where the
   entity is a program rather than a person.  On Azure a function's own recent history is
   almost the whole signal (identity alone explains eta^2 = 0.87 of the variance of
   log1p(duration); heavy-job AUROC 0.985, AUPRC 0.83, Spearman 0.93-0.95) while calendar
   features alone are worthless (Spearman 0.02).  On Netbatch the same features give
   AUROC 0.89-0.91 but AUPRC only 0.26-0.32 and RMSE(log1p) 1.35: which command will run
   long is predictable in rank order, how long it will run is not.  Note that the
   Netbatch STATIC set contains the group id, which is an identity, not a clock feature;
   its Spearman of 0.75 should not be read as "the calendar predicts".

3. Scheduling.  Azure behaves like the education traces: sizing k from the busiest hour,
   SPJF closes 0.85-0.87 of the FCFS -> true-SJF gap on p99 wait and 0.88-0.91 on the mean,
   and unguarded it delays some job by 2,900 s beyond FCFS (10 L).  The guard at a 5 L
   guarantee keeps 0.71 of the p99 gain and caps the observed harm at 2.5 L, firing on
   0.3% of dispatches.  This is the education result, on a different workload.

4. Where it does not transfer.  On Netbatch, sized for the busiest hour (k = 21,013
   servers) there is almost no queue at all: FCFS p99 wait is 34 s against service times
   of hours, so the ordering hardly matters.  Pushed into sustained overload (whole-window
   utilisation 0.8-0.95) SPJF improves the mean by 0.85 of the reference gap but makes the
   p99 wait WORSE than FCFS (gap -0.12 to -4.35): with a pool of ~16,000 servers and a
   service cap of 5.7 days, the jobs that lose are enormously starved (max wait 4.9 days
   against 18.7 h under FCFS).  And the guard's guarantee family cannot express a useful
   promise there, because its floor (3-2/k)L is 17 days while the FCFS p99 wait is 18.7 h;
   at G = 5 L the budget is so large the guard never fires.  The mechanism itself still
   works when the budget is set in absolute terms: B/k = 0.001 L = 494 s caps the observed
   harm at 5,953 s instead of 410,655 s and keeps a third of the mean gain.  The lesson is
   that the method needs L (the service cap) to be of the same order as the waits that
   matter; that holds for a judge with a 60 s timeout and for serverless functions, and
   fails for a farm whose jobs run for days.
"""

if __name__ == "__main__":
    main()
