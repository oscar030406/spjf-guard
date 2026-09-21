"""Stage 7: single-submission inference latency on the CPU, batch 1.

The scheduler has to produce a prediction before the job is enqueued, and the median
service time is 0.2 s, so anything above a few milliseconds is a deployment problem.  What
is timed here, per submission, is what a server would actually have to do on top of the
tabular features that every model needs anyway:

    graph lookup   4 x (binary search in the anchor's arrival list + scan back over the
                   last 96 records + collapse duplicates + 16 binary searches for the
                   neighbours' timeline entries) + 4 root timeline searches
    sequence lookup  1 binary search in the user's availability list + gather of 32 rows
    forward        one batch-1 forward pass of the network, torch on the CPU, no threads
                   beyond one

The LightGBM part of M4 / G3 / R1S is timed separately by latency_lgb.py (LightGBM is not
installed in the GPU environment).

Params: N_LAT = 2000 rows sampled from the test semester, seed 7, torch threads 1.
"""
from __future__ import annotations

import os
import sys
import time

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np
import torch

OUT = r"<cache-dir>\pn"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_neural as TN

N_LAT = 2000
SEED = 7
K, W = 16, 96
RELS = TN.RELS
TYPES = TN.TYPES

LOG = open(os.path.join(HERE, "out_latency.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def q(v):
    v = np.sort(np.asarray(v)) * 1e3
    return f"median {np.median(v):.3f} ms  mean {v.mean():.3f} ms  p99 {v[int(.99 * len(v))]:.3f} ms"


def main():
    torch.set_num_threads(1)
    rng = np.random.default_rng(SEED)
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    G = np.load(os.path.join(OUT, "graph.npz"), allow_pickle=False)
    RSPAN = int(G["RSPAN"])
    sem = B["sem"]
    te = np.flatnonzero(np.isin(sem, ["2022-2"]))
    rows = rng.choice(te, N_LAT, replace=False)
    NODES = {"ex": B["ex"], "us": B["us"], "asm": B["asm"], "cl": B["cl"]}
    r_read = B["r_read"]
    ST = {t: G[f"st_{t}"] for t in TYPES}
    SC = {t: G[f"sc_{t}"] for t in TYPES}
    SP = {t: G[f"sp_{t}"] for t in TYPES}
    LC = {nm: G[f"lc_{nm}"] for nm, _, _ in RELS}
    LV = {nm: G[f"lv_{nm}"] for nm, _, _ in RELS}
    LP = {nm: G[f"lp_{nm}"] for nm, _, _ in RELS}

    def graph_lookup(i):
        r = int(r_read[i])
        out = {}
        for t in TYPES:
            n = int(NODES[t][i])
            j = int(np.searchsorted(SC[t], n * RSPAN + r, side="left")) - 1
            out[t] = ST[t][j] if j >= SP[t][n] else None
        nb = {}
        for nm, an, vn in RELS:
            a_ = int(NODES[an][i])
            lo = int(LP[nm][a_])
            pos = int(np.searchsorted(LC[nm], a_ * RSPAN + r, side="left"))
            selfn = int(NODES[vn][i])
            seen, keep = set(), []
            for p in range(pos - 1, max(lo - 1, pos - 1 - W), -1):
                v = int(LV[nm][p])
                if v == selfn or v in seen:
                    continue
                seen.add(v)
                j = int(np.searchsorted(SC[vn], v * RSPAN + r, side="left")) - 1
                if j >= SP[vn][v]:
                    keep.append(ST[vn][j])
                if len(keep) == K:
                    break
            nb[nm] = keep
        return out, nb

    t = []
    for i in rows:
        t0 = time.perf_counter()
        graph_lookup(int(i))
        t.append(time.perf_counter() - t0)
    say(f"graph lookup (4 relations, K=16, W=96), pure python+numpy: {q(t)}")

    # sequence lookup for R1
    us = B["us"].astype(np.int64)
    o = np.lexsort((B["r_avail"], us))
    comp = us[o] * RSPAN + B["r_avail"][o]
    ptr = np.searchsorted(us[o], np.arange(us.max() + 2))
    y, hvv, errf, ntc = B["y"], B["hv"], B["errf"], B["ntc"]   # materialise: NpzFile
    t = []
    for i in rows:
        i = int(i)
        t0 = time.perf_counter()
        p = int(np.searchsorted(comp, us[i] * RSPAN + r_read[i], side="left"))
        lo = int(ptr[us[i]])
        idx = o[max(lo, p - TN.SEQ):p]
        step = np.stack([y[idx], hvv[idx], errf[idx], ntc[idx]], 1)
        t.append(time.perf_counter() - t0)
    say(f"sequence lookup (last 32 available results of the user):  {q(t)}")

    # batch-1 forward passes
    X = np.load(os.path.join(OUT, "X.npy"))
    xcols = open(os.path.join(OUT, "xcols.txt")).read().split("\n")
    M4 = [c for c in xcols if not c.endswith("_perm") and not c.startswith("r_")]
    ntab = len([c for c in M4]) + sum(1 for c in M4 if np.isnan(X[:, xcols.index(c)]).any())
    sdim = {t: ST[t].shape[1] for t in TYPES}
    nsub = 102
    nets = {"G1/G2/G0 (relational net)": (TN.Net(sdim, nsub, agg="mean"), "graph"),
            "N0 (MLP on M4 columns)": (TN.MLP(86), "tab"),
            "R1 (GRU + MLP)": (TN.GRUNet(9, 86), "seq")}
    for nm, (net, kind) in nets.items():
        net.eval()
        with torch.no_grad():
            if kind == "graph":
                roots = {t: torch.zeros(1, sdim[t]) for t in TYPES}
                rootm = {t: torch.ones(1) for t in TYPES}
                nbr = {r[0]: torch.zeros(1, K, sdim[r[2]]) for r in RELS}
                nbrm = {r[0]: torch.ones(1, K) for r in RELS}
                sub = torch.zeros(1, nsub)
                f = lambda: net(roots, rootm, nbr, nbrm, sub)
            elif kind == "tab":
                x = torch.zeros(1, 86)
                f = lambda: net(x)
            else:
                s_, m_, tb = torch.zeros(1, TN.SEQ, 9), torch.ones(1, TN.SEQ), torch.zeros(1, 86)
                f = lambda: net(s_, m_, tb)
            for _ in range(200):
                f()
            t = []
            for _ in range(N_LAT):
                t0 = time.perf_counter()
                f()
                t.append(time.perf_counter() - t0)
        say(f"forward batch 1, {nm}: {q(t)}")


if __name__ == "__main__":
    main()
