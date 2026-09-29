"""Shared setup for the cross-domain generality check (non-education workloads).

Traces
------
azure   : data/azure_functions_2021/AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt
          columns app, func, end_timestamp (s, relative to trace start), duration (s).
          Same semantics as the CodeBench log: the record carries the END time and the
          duration, so arrival = end_timestamp - duration.
netbatch: data/intel_netbatch_2012/Intel-NetbatchD-2012-1.swf.gz  (Standard Workload
          Format).  Fields used: submit time, run time, user id, executable number.

Nothing here reads or writes the education data; every output of this study stays in
evidence/cross_domain/ and every large intermediate array in the local cache directory.
"""
import os
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA = os.path.join(ROOT, "data")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.environ.get(
    "CD_SCRATCH",
    r"<cache-dir>"
    r"\cross_domain",
)
os.makedirs(SCRATCH, exist_ok=True)

AZURE_TXT = os.path.join(DATA, "azure_functions_2021",
                         "AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt")
NETBATCH_SWF = os.path.join(DATA, "intel_netbatch_2012", "Intel-NetbatchD-2012-1.swf.gz")

SEED = 20260919
HOUR = 3600.0
DAY = 86400.0

# service cap L per trace, decided in cd_audit and frozen here (see out_audit_*.txt)
L_AZURE = 60.0        # placeholder, overwritten below after the audit
L_NETBATCH = 3600.0   # placeholder, overwritten below after the audit


def log(fh, *parts):
    line = " ".join(str(p) for p in parts)
    print(line)
    if fh is not None:
        fh.write(line + "\n")
        fh.flush()


def load_azure(cache=True):
    """Return DataFrame with columns app, func (int codes), arrival, duration, end."""
    pq = os.path.join(SCRATCH, "azure.parquet")
    if cache and os.path.exists(pq):
        return pd.read_parquet(pq)
    df = pd.read_csv(AZURE_TXT, dtype={"app": "str", "func": "str"})
    df["end"] = df["end_timestamp"].astype("float64")
    df["duration"] = df["duration"].astype("float64")
    df["arrival"] = df["end"] - df["duration"]
    df["app_id"] = pd.factorize(df["app"])[0].astype("int32")
    # func ids are unique only inside an app
    df["func_id"] = pd.factorize(df["app"] + "/" + df["func"])[0].astype("int32")
    df = df[["app_id", "func_id", "arrival", "duration", "end"]]
    df = df.sort_values(["arrival", "end"], kind="mergesort").reset_index(drop=True)
    if cache:
        df.to_parquet(pq, index=False)
    return df


SWF_COLS = ["job", "submit", "wait", "run", "nproc", "cpu_used", "mem_used", "nproc_req",
            "time_req", "mem_req", "status", "uid", "gid", "exe", "queue", "part",
            "prev_job", "think"]


def load_netbatch(cache=True):
    """Return DataFrame with columns uid, exe, arrival(submit s), duration(run s)."""
    pq = os.path.join(SCRATCH, "netbatch.parquet")
    if cache and os.path.exists(pq):
        return pd.read_parquet(pq)
    df = pd.read_csv(NETBATCH_SWF, sep=r"\s+", comment=";", header=None,
                     names=SWF_COLS, engine="c",
                     usecols=["job", "submit", "wait", "run", "nproc", "status",
                              "uid", "gid", "exe", "queue"])
    for c in ["submit", "wait", "run", "nproc", "status", "uid", "gid", "exe", "queue"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(-1).astype("int64")
    if cache:
        df.to_parquet(pq, index=False)
    return df


def work_share_top(x, fracs=(0.001, 0.01, 0.05, 0.10)):
    """Share of total work carried by the largest jobs."""
    x = np.sort(np.asarray(x, dtype="float64"))[::-1]
    tot = x.sum()
    out = {}
    for f in fracs:
        m = max(1, int(round(f * x.size)))
        out[f] = x[:m].sum() / tot
    return out


def index_of_dispersion(counts):
    counts = np.asarray(counts, dtype="float64")
    m = counts.mean()
    return float(counts.var(ddof=1) / m) if m > 0 else float("nan")


def qtab(x, qs=(0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 99.9, 99.99, 100)):
    x = np.asarray(x, dtype="float64")
    return {q: float(np.percentile(x, q)) for q in qs}
