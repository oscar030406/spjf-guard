"""Who makes the Azure trace's busiest hour, and how concentrated is the load overall.

Decides (and documents) the load-shaping choice used by cd_sim.py.
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np
import pandas as pd

import cd_common as C

out = os.path.join(C.HERE, "out_flurry_azure.txt")
with open(out, "w", encoding="utf-8") as fh:
    df = C.load_azure()
    d = df.duration.values
    hb = (df.arrival.values / 3600.0).astype(int)
    wk = np.bincount(hb, weights=d, minlength=336)
    order = np.argsort(wk)[::-1]
    C.log(fh, "hourly work (server-equivalents), sorted:")
    C.log(fh, "  top 12 hours: " + " ".join(f"h{h}={wk[h]/3600:.2f}" for h in order[:12]))
    C.log(fh, "  quantiles over 336 hours: " +
          " ".join(f"p{q}={np.percentile(wk,q)/3600:.3f}" for q in (50, 75, 90, 95, 99, 100)))
    C.log(fh, f"  share of all work in the single busiest hour: {wk.max()/wk.sum():.4f}")
    C.log(fh, f"  share of all work in the busiest 5 hours: {wk[order[:5]].sum()/wk.sum():.4f}")

    for h in order[:3]:
        m = hb == h
        sub = df[m]
        C.log(fh, f"\n-- hour {h}: jobs={m.sum()} work={d[m].sum():.0f}s "
                  f"({d[m].sum()/3600:.1f} server-equivalents)")
        by_app = sub.groupby("app_id").duration.agg(["sum", "size"]).sort_values("sum", ascending=False)
        C.log(fh, "   top apps by work: " +
              "  ".join(f"app{a}={r['sum']:.0f}s/{int(r['size'])}jobs" for a, r in by_app.head(4).iterrows()))
        by_f = sub.groupby("func_id").duration.agg(["sum", "size"]).sort_values("sum", ascending=False)
        C.log(fh, "   top funcs by work: " +
              "  ".join(f"f{a}={r['sum']:.0f}s/{int(r['size'])}jobs" for a, r in by_f.head(4).iterrows()))

    # how much of the whole-trace work does each app carry, and how peaked is each app
    app_w = df.groupby("app_id").duration.sum().sort_values(ascending=False)
    C.log(fh, "\n-- work share by app (whole trace), top 10:")
    C.log(fh, "   " + "  ".join(f"app{a}={v/app_w.sum():.4f}" for a, v in app_w.head(10).items()))
    top_app = app_w.index[0]
    m = df.app_id.values == top_app
    wk_top = np.bincount(hb[m], weights=d[m], minlength=336)
    C.log(fh, f"   app{top_app}: work={app_w.iloc[0]:.0f}s, its busiest hour={wk_top.max()/3600:.1f} "
              f"server-equivalents, hours with any job={int((wk_top>0).sum())}")

    # trace without the single heaviest app
    keep = ~m
    wk2 = np.bincount(hb[keep], weights=d[keep], minlength=336)
    C.log(fh, f"\n-- without app{top_app}: jobs={int(keep.sum())} "
              f"({keep.mean()*100:.2f}%), work={d[keep].sum():.0f}s")
    C.log(fh, "   hourly server-equivalents: " +
          " ".join(f"p{q}={np.percentile(wk2,q)/3600:.3f}" for q in (50, 90, 99, 100)) +
          f"  mean={wk2.mean()/3600:.3f}")
    ws = C.work_share_top(d[keep])
    C.log(fh, "   work share of largest jobs: " +
          "  ".join(f"top{f*100:g}%={v:.4f}" for f, v in ws.items()))
print("wrote", out)
