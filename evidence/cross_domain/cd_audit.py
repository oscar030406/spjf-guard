"""Audit of the two non-education traces: fields, units, caps, tail, burstiness, entities.

    uv run ... python cd_audit.py azure
    uv run ... python cd_audit.py netbatch

Writes out_audit_<trace>.txt next to this file.  Read-only on data/.
"""
import sys

sys.dont_write_bytecode = True

import os
import numpy as np
import pandas as pd

import cd_common as C

pd.set_option("display.width", 200)


def eta2_by_entity(logx, ent, min_n=2):
    """Share of variance of log-cost explained by entity identity (one-way ANOVA eta^2).

    Uses only entities with at least min_n jobs; reports the coverage too.
    """
    df = pd.DataFrame({"y": logx, "e": ent})
    g = df.groupby("e")["y"]
    n = g.size()
    keep = n[n >= min_n].index
    d = df[df["e"].isin(keep)]
    if len(d) == 0:
        return float("nan"), 0.0
    gm = d["y"].mean()
    grp = d.groupby("e")["y"]
    ss_between = float((grp.count() * (grp.mean() - gm) ** 2).sum())
    ss_total = float(((d["y"] - gm) ** 2).sum())
    return ss_between / ss_total if ss_total > 0 else float("nan"), len(d) / len(df)


def tail_block(fh, x, label):
    q = C.qtab(x)
    C.log(fh, f"\n-- {label}: n={len(x)}  mean={np.mean(x):.4f}  sum={np.sum(x):.1f}")
    C.log(fh, "   percentiles: " + "  ".join(f"p{k}={v:.4f}" for k, v in q.items()))
    ws = C.work_share_top(x)
    C.log(fh, "   work share of largest: " +
          "  ".join(f"top{f*100:g}%={v:.4f}" for f, v in ws.items()))
    xs = np.sort(np.asarray(x, float))
    C.log(fh, f"   mean/median={np.mean(x)/max(1e-12,np.median(x)):.2f}  "
              f"cv={np.std(x)/max(1e-12,np.mean(x)):.2f}  "
              f"gini={(2*np.sum((np.arange(1,xs.size+1))*xs)/(xs.size*xs.sum())-(xs.size+1)/xs.size):.4f}")


def burstiness(fh, arrival, work, span_lo, span_hi, bin_s=3600.0, label="hour"):
    nb = int(np.ceil((span_hi - span_lo) / bin_s))
    idx = np.clip(((arrival - span_lo) / bin_s).astype(np.int64), 0, nb - 1)
    cnt = np.bincount(idx, minlength=nb).astype(float)
    wk = np.bincount(idx, weights=work, minlength=nb)
    C.log(fh, f"\n-- burstiness per {label} ({nb} bins of {bin_s:g}s)")
    C.log(fh, f"   count/bin: mean={cnt.mean():.1f} max={cnt.max():.0f} "
              f"peak/mean={cnt.max()/cnt.mean():.2f} IoD(var/mean)={C.index_of_dispersion(cnt):.1f}")
    C.log(fh, f"   work/bin (server-equivalents a[h]=work/{bin_s:g}): "
              f"mean={wk.mean()/bin_s:.3f} max={wk.max()/bin_s:.3f} "
              f"peak/mean={wk.max()/max(1e-12,wk.mean()):.2f} "
              f"p99={np.percentile(wk,99)/bin_s:.3f}")
    return cnt, wk


def diurnal(fh, arrival, work, period=86400.0, nb=24):
    ph = ((arrival % period) / (period / nb)).astype(int)
    cnt = np.bincount(ph, minlength=nb).astype(float)
    wk = np.bincount(ph, weights=work, minlength=nb)
    C.log(fh, "\n-- profile within a 24 h period (bin = 1 h of the period, origin = trace start)")
    C.log(fh, "   counts: " + " ".join(f"{v/cnt.sum()*100:.1f}" for v in cnt) + "   (% of jobs)")
    C.log(fh, "   work  : " + " ".join(f"{v/wk.sum()*100:.1f}" for v in wk) + "   (% of work)")
    C.log(fh, f"   peak/mean count = {cnt.max()/cnt.mean():.2f}, peak/mean work = {wk.max()/wk.mean():.2f}")


def audit_azure(fh):
    df = C.load_azure()
    C.log(fh, "=== Azure Functions invocation trace, two weeks from 2021-01-31 (pool: all) ===")
    C.log(fh, f"file: {C.AZURE_TXT}")
    C.log(fh, f"rows={len(df)}  columns of raw file: app, func, end_timestamp (s), duration (s)")
    C.log(fh, f"arrival = end_timestamp - duration  (the record carries the END time)")
    C.log(fh, f"span: arrival min={df.arrival.min():.3f}  max={df.arrival.max():.3f}  "
              f"end max={df.end.max():.3f}  -> {(df.end.max()-df.arrival.min())/86400:.3f} days")
    neg = int((df.arrival < 0).sum())
    C.log(fh, f"rows with arrival<0 (job started before trace start): {neg} "
              f"({neg/len(df)*100:.4f}%)  min arrival={df.arrival.min():.3f}")
    C.log(fh, f"zero-duration rows: {int((df.duration<=0).sum())}  "
              f"({(df.duration<=0).mean()*100:.4f}%)")
    d = df.duration.values
    C.log(fh, f"duration granularity: unique values={len(np.unique(d))}; "
              f"values*1000 integral for {np.mean(np.abs(d*1000-np.round(d*1000))<1e-6)*100:.2f}% of rows"
              " -> recorded in milliseconds")
    C.log(fh, f"max duration={d.max():.3f}s; rows at >= 600s: {int((d>=600).sum())}; "
              f">=300s: {int((d>=300).sum())}; >=60s: {int((d>=60).sum())}")
    top = pd.Series(d).round(3).value_counts().head(12)
    C.log(fh, "most frequent duration values (s -> count):\n" + top.to_string())
    tail_block(fh, d, "duration (s), all rows")

    C.log(fh, f"\n-- entities: apps={df.app_id.nunique()}  functions (app/func)={df.func_id.nunique()}")
    per_f = df.groupby("func_id").size()
    C.log(fh, "invocations per function: " +
          "  ".join(f"p{q}={np.percentile(per_f,q):.0f}" for q in (50, 90, 99, 100)) +
          f"  mean={per_f.mean():.1f}")
    wf = df.groupby("func_id").duration.sum().sort_values(ascending=False)
    C.log(fh, f"work share of top 1% of functions: {wf.head(max(1,len(wf)//100)).sum()/wf.sum():.4f}; "
              f"top 10: {wf.head(10).sum()/wf.sum():.4f}")
    ly = np.log1p(d)
    e_f, cov_f = eta2_by_entity(ly, df.func_id.values)
    e_a, cov_a = eta2_by_entity(ly, df.app_id.values)
    C.log(fh, f"variance of log1p(duration) explained by identity: "
              f"function eta^2={e_f:.4f} (coverage {cov_f:.4f}), app eta^2={e_a:.4f}")
    cvf = df.groupby("func_id").duration.agg(["mean", "std", "size"])
    cvf = cvf[cvf["size"] >= 10]
    C.log(fh, f"within-function CV of duration (functions with >=10 calls, n={len(cvf)}): "
              f"median={np.nanmedian(cvf['std']/cvf['mean']):.3f}  "
              f"p90={np.nanpercentile(cvf['std']/cvf['mean'],90):.3f}")

    lo, hi = 0.0, df.end.max()
    burstiness(fh, df.arrival.values, d, lo, hi, 3600.0, "hour")
    burstiness(fh, df.arrival.values, d, lo, hi, 60.0, "minute")
    burstiness(fh, df.arrival.values, d, lo, hi, 1.0, "second")
    diurnal(fh, df.arrival.values, d)
    hb = np.clip((df.arrival.values / 3600.0).astype(int), 0, None)
    wk = np.bincount(hb, weights=d)
    C.log(fh, f"\nbusiest hour: index={int(np.argmax(wk))} work={wk.max():.1f}s "
              f"-> {wk.max()/3600:.3f} server-equivalents; whole-trace mean "
              f"{wk.mean()/3600:.3f}")
    C.log(fh, "L (service cap) candidates: p99.9=%.2f  p99.99=%.2f  max=%.2f" %
          (np.percentile(d, 99.9), np.percentile(d, 99.99), d.max()))


def audit_netbatch(fh):
    df = C.load_netbatch()
    C.log(fh, "=== Intel Netbatch pool D, Oct 31 - Nov 30 2012 (SWF conversion 1) ===")
    C.log(fh, f"file: {C.NETBATCH_SWF}")
    C.log(fh, f"rows={len(df)}")
    C.log(fh, "SWF fields used: submit (s from UnixStartTime 1351728003), wait (s), "
              "run (s), nproc, status, uid, gid, exe (anonymised command), queue")
    for c in ["nproc", "status", "queue", "gid"]:
        vc = df[c].value_counts().head(6)
        C.log(fh, f"{c}: n_unique={df[c].nunique()} top -> {dict(vc)}")
    C.log(fh, f"uid: n_unique={df.uid.nunique()}   exe: n_unique={df.exe.nunique()}")
    C.log(fh, f"run<=0: {int((df.run<=0).sum())}  run<0: {int((df.run<0).sum())}  "
              f"wait<0: {int((df.wait<0).sum())}")
    C.log(fh, f"submit span: {df.submit.min()} .. {df.submit.max()} s "
              f"= {(df.submit.max()-df.submit.min())/86400:.2f} days")
    ser = df[(df.nproc == 1)]
    C.log(fh, f"serial jobs (nproc==1): {len(ser)} ({len(ser)/len(df)*100:.2f}%)")
    use = ser[(ser.run > 0)].copy()
    C.log(fh, f"serial with run>0: {len(use)} ({len(use)/len(ser)*100:.2f}% of serial)")
    C.log(fh, f"real system wait: mean={ser.wait.mean():.1f}s p50={ser.wait.median():.0f} "
              f"p99={np.percentile(ser.wait,99):.0f} max={ser.wait.max()}")
    tail_block(fh, use.run.values.astype(float), "run time (s), serial jobs with run>0")
    d = use.run.values.astype(float)
    C.log(fh, f"granularity: integer seconds; rows at run==1: {int((d==1).sum())}; "
              f"max={d.max():.0f}s ({d.max()/3600:.2f} h)")
    for cap in (3600, 7200, 86400, 172800):
        C.log(fh, f"  rows with run>={cap}s: {int((d>=cap).sum())} ({(d>=cap).mean()*100:.4f}%), "
                  f"share of work {d[d>=cap].sum()/d.sum():.4f}")
    ly = np.log1p(d)
    e_e, cov_e = eta2_by_entity(ly, use.exe.values)
    e_u, cov_u = eta2_by_entity(ly, use.uid.values)
    e_ue, cov_ue = eta2_by_entity(ly, (use.uid.values.astype(np.int64) * 100000 + use.exe.values))
    C.log(fh, f"variance of log1p(run) explained by identity: exe eta^2={e_e:.4f}, "
              f"uid eta^2={e_u:.4f}, uid x exe eta^2={e_ue:.4f}")
    per_e = use.groupby("exe").size()
    C.log(fh, "jobs per exe: " + "  ".join(f"p{q}={np.percentile(per_e,q):.0f}" for q in (50, 90, 99, 100)))
    per_u = use.groupby("uid").size()
    C.log(fh, "jobs per uid: " + "  ".join(f"p{q}={np.percentile(per_u,q):.0f}" for q in (50, 90, 99, 100)))
    a = use.submit.values.astype(float)
    burstiness(fh, a, d, a.min(), a.max() + 1, 3600.0, "hour")
    burstiness(fh, a, d, a.min(), a.max() + 1, 60.0, "minute")
    diurnal(fh, a - a.min(), d)
    hb = ((a - a.min()) / 3600.0).astype(int)
    wk = np.bincount(hb, weights=d)
    C.log(fh, f"\nbusiest hour: index={int(np.argmax(wk))} work={wk.max():.0f}s "
              f"-> {wk.max()/3600:.1f} server-equivalents; whole-trace mean {wk.mean()/3600:.1f}")
    C.log(fh, "L (service cap) candidates: p99=%.0f p99.9=%.0f  p99.99=%.0f  max=%.0f" %
          (np.percentile(d, 99), np.percentile(d, 99.9), np.percentile(d, 99.99), d.max()))


if __name__ == "__main__":
    which = sys.argv[1]
    out = os.path.join(C.HERE, f"out_audit_{which}.txt")
    with open(out, "w", encoding="utf-8") as fh:
        if which == "azure":
            audit_azure(fh)
        else:
            audit_netbatch(fh)
    print("wrote", out)
