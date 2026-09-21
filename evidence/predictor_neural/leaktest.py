"""Stage 3: leak tests for the causal graph construction.

T1  GLOBAL INDEX ASSERTION.  Every stored timeline index (root and neighbour, G1 and G2)
    must point at an entry whose availability rank is strictly below the row's read rank.
    Checked on all 863,149 rows x (4 roots + 4 relations x 16 slots).

T2  BRUTE-FORCE RECOMPUTATION on N_BRUTE >= 500 random rows.  Written from the definitions
    in research_plan.md 2.3, on the raw float clocks, with no reference to the rank
    machinery or the CSR arrays of build_graph:
        record j's existence is usable by i   iff  arrival[j] <  arrival[i]
        record j's result    is usable by i   iff  available[j] < arrival[i], or
                                                   available[j] == arrival[i] and
                                                   available[j] > arrival[j]
    For each sampled row it rebuilds the four root node states and the four neighbour sets
    (last 96 visible records of the anchor node, self dropped, duplicates collapsed to their
    most recent occurrence, first 16 kept) together with each neighbour's node state, and
    compares them with what the built arrays resolve to.

T3  TWO-EVENT / FUTURE PERTURBATION on a closed sub-dataset (all rows of a few classes).
    (a) the recorded OUTCOME (cost, error flag, heavy flag, test-case count) of every record
        arriving after a cut time T is replaced by noise;
    (b) every record arriving after T is deleted outright.
    In both cases every graph input of every row arriving at or before T must be unchanged,
    bit for bit.  A positive control perturbs a record BEFORE T and checks that the inputs
    of later rows do move, so the test cannot pass vacuously.

Params: N_BRUTE = 600, SEED = 7, K = 16, W = 96 (must match build_graph).
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from collections import deque
from math import sqrt

import numpy as np

OUT = r"<cache-dir>\pn"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_graph as BG            # reuse the construction under test (T3 rebuilds with it)

N_BRUTE = 600
SEED = 7
K, W = 16, 96
RELS = BG.RELS

LOG = open(os.path.join(HERE, "out_leaktest.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def stats_from(lg, hv, er, nt, order, with_q, with_ntc):
    """The node-state vector produced by build_timelines from the visible records of one
    node, given their indices in availability order."""
    n = len(order)
    if n == 0:
        return None
    x = lg[order]
    m = x.mean()
    row = [float(n), float(m), float(sqrt(max((x * x).mean() - m * m, 0.0)))]
    if with_q:
        s = sorted(x[-120:].tolist())
        L = len(s) - 1
        row += [s[min(L, int(.5 * L + .5))], s[min(L, int(.9 * L + .5))], s[-1]]
    row += [float(er[order].mean()), float(hv[order].mean())]
    if with_ntc:
        row.append(float(nt[order].mean()))
    return np.array(row, np.float32)


def main():
    rng = np.random.default_rng(SEED)
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    G = np.load(os.path.join(OUT, "graph.npz"), allow_pickle=False)
    nb1 = np.load(os.path.join(OUT, "nb_g1.npy"))
    nb2 = np.load(os.path.join(OUT, "nb_g2.npy"))
    ns = len(B["ex"])
    RSPAN = int(G["RSPAN"])
    r_read = B["r_read"]
    NODES = {"ex": B["ex"], "us": B["us"], "asm": B["asm"], "cl": B["cl"]}
    ST = {t: G[f"st_{t}"] for t in NODES}
    SC = {t: G[f"sc_{t}"] for t in NODES}
    root = G["root"]

    # ---------------- T1 ----------------
    say(f"T1  global index assertion over {ns:,} rows")
    bad = 0
    for i, t in enumerate(["us", "ex", "asm", "cl"]):
        j = root[:, i]
        m = j >= 0
        rk = SC[t][j[m]] % RSPAN
        nd = SC[t][j[m]] // RSPAN
        bad += int((rk >= r_read[m]).sum()) + int((nd != NODES[t][m]).sum())
    for tag, nb in (("G1", nb1), ("G2", nb2)):
        for ri, (nm, an, vn) in enumerate(RELS):
            j = nb[:, ri * K:(ri + 1) * K]
            rr = np.repeat(r_read, K).reshape(-1, K)
            m = j >= 0
            rk = SC[vn][j[m]] % RSPAN
            b = int((rk >= rr[m]).sum())
            bad += b
            if b:
                say(f"   {tag} {nm}: {b} entries at or after the read rank")
    say(f"T1  entries pointing at or after the read: {bad}  -> {'PASS' if bad == 0 else 'FAIL'}")

    # ---------------- T2 ----------------
    say(f"\nT2  brute-force recomputation on {N_BRUTE} random rows (raw float clocks)")
    arr, avail = B["arr"], B["avail"]
    lg, hv, errf, ntc = B["lg"].astype("float64"), B["hv"].astype("float64"), \
        B["errf"].astype("float64"), B["ntc"].astype("float64")
    ty_av = np.where(avail == arr, 3, 0)
    idx_all = np.arange(ns)

    byn = {}
    for t, node in NODES.items():
        o = np.argsort(node, kind="stable")
        ptr = np.searchsorted(node[o], np.arange(node.max() + 2))
        byn[t] = (o, ptr)

    rows = rng.choice(ns, N_BRUTE, replace=False)
    # only sample rows that have some history, so the test is not dominated by empty sets
    rows = rows[B["ex_nres"][rows] > 0]
    say(f"    sampled {len(rows)} rows with at least one available exercise result")

    nfail_state = nfail_set = ncmp_state = ncmp_set = 0
    for i in rows:
        ti = arr[i]
        for ti_, t in enumerate(["us", "ex", "asm", "cl"]):
            o, ptr = byn[t]
            cand = o[ptr[NODES[t][i]]:ptr[NODES[t][i] + 1]]
            vis = cand[(avail[cand] < ti) | ((avail[cand] == ti) & (ty_av[cand] == 0))]
            order = vis[np.lexsort((vis, ty_av[vis], avail[vis]))]
            want = stats_from(lg, hv, errf, ntc, order,
                              with_q=(t in ("ex", "us")), with_ntc=(t == "ex"))
            j = root[i, ti_]
            got = ST[t][j] if j >= 0 else None
            ncmp_state += 1
            if (want is None) != (got is None) or (
                    want is not None and not np.allclose(want, got, rtol=1e-5, atol=1e-6)):
                nfail_state += 1
                if nfail_state <= 3:
                    say(f"    root mismatch row {i} type {t}: want {want} got {got}")
        for ri, (nm, an, vn) in enumerate(RELS):
            o, ptr = byn[an]
            cand = o[ptr[NODES[an][i]]:ptr[NODES[an][i] + 1]]
            vis = cand[arr[cand] < ti]
            vis = vis[np.lexsort((vis, arr[vis]))][-W:][::-1]
            seen, keep = set(), []
            selfn = NODES[vn][i]
            for j_ in vis:
                v = int(NODES[vn][j_])
                if v == selfn or v in seen:
                    continue
                seen.add(v)
                keep.append(v)
                if len(keep) == K:
                    break
            want_states = []
            for v in keep:
                o2, ptr2 = byn[vn]
                c2 = o2[ptr2[v]:ptr2[v + 1]]
                v2 = c2[(avail[c2] < ti) | ((avail[c2] == ti) & (ty_av[c2] == 0))]
                od = v2[np.lexsort((v2, ty_av[v2], avail[v2]))]
                want_states.append(stats_from(lg, hv, errf, ntc, od,
                                              with_q=(vn in ("ex", "us")), with_ntc=(vn == "ex")))
            want_states = [w for w in want_states if w is not None]
            got_j = nb1[i, ri * K:(ri + 1) * K]
            got_states = [ST[vn][j_] for j_ in got_j if j_ >= 0]
            ncmp_set += 1
            ok = len(want_states) == len(got_states) and all(
                np.allclose(a, b, rtol=1e-5, atol=1e-6) for a, b in zip(want_states, got_states))
            if not ok:
                nfail_set += 1
                if nfail_set <= 3:
                    say(f"    neighbour mismatch row {i} {nm}: {len(want_states)} vs "
                        f"{len(got_states)} states")
    say(f"T2  root states compared {ncmp_state}, mismatches {nfail_state}")
    say(f"T2  neighbour sets compared {ncmp_set}, mismatches {nfail_set}  "
        f"-> {'PASS' if nfail_state == 0 and nfail_set == 0 else 'FAIL'}")

    # ---------------- T3 ----------------
    say("\nT3  future-perturbation on a closed sub-dataset")
    cls = B["cl"]
    pick = np.isin(cls, np.unique(cls)[:6])
    sub = np.flatnonzero(pick)
    say(f"    sub-dataset: {len(sub):,} rows from 6 classes")
    d = {k: B[k][sub] if B[k].shape[:1] == (ns,) else B[k] for k in
         ("ex", "us", "cl", "asm", "arr", "avail", "lg", "hv", "errf", "ntc")}

    def rebuild(dd, mask=None):
        """Run the construction of build_graph on a sub-dataset and return, for every row,
        the concatenation of its root state vectors and its G1 neighbour state vectors."""
        sel = np.arange(len(dd["arr"])) if mask is None else np.flatnonzero(mask)
        a, av = dd["arr"][sel], dd["avail"][sel]
        ty = np.where(av == a, 3, 0).astype(np.int64)
        n = len(sel)
        T = np.concatenate([av, a, a])
        TY = np.concatenate([ty, np.ones(n, np.int64), np.full(n, 2, np.int64)])
        o = np.lexsort((TY, T))
        Ts, TYs = T[o], TY[o]
        grp = np.cumsum(np.r_[True, (Ts[1:] != Ts[:-1]) | (TYs[1:] != TYs[:-1])]) - 1
        rk = np.empty(len(T), np.int64); rk[o] = grp
        ra, rd, rg = rk[:n], rk[n:2 * n], rk[2 * n:]
        BG.RSPAN = int(rk.max()) + 2
        ids = {t: dd[t][sel] for t in ("ex", "us", "asm", "cl")}
        rmap = {t: {v: i2 for i2, v in enumerate(np.unique(ids[t]))} for t in ids}
        ids = {t: np.array([rmap[t][v] for v in ids[t]], np.int32) for t in ids}
        NN = {t: len(rmap[t]) for t in ids}
        S = {}
        for t in ids:
            S[t] = BG.build_timelines(ids[t], ra, dd["lg"][sel].astype("float64"),
                                      dd["hv"][sel].astype("float64"),
                                      dd["errf"][sel].astype("float64"),
                                      dd["ntc"][sel].astype("float64"), NN[t],
                                      with_q=(t in ("ex", "us")), with_ntc=(t == "ex"))
        out = []
        for ti_, t in enumerate(["us", "ex", "asm", "cl"]):
            j = BG.state_index(ids[t], rd, S[t][0], S[t][2])
            F = np.where(j[:, None] >= 0, S[t][1][np.maximum(j, 0)], np.nan)
            out.append(F)
        for nm, an, vn in RELS:
            L = BG.build_lists(ids[an], ids[vn], rg, NN[an])
            nb, _ = BG.neighbours(ids[an], ids[vn], rd, L[0], L[1], L[2])
            jj = BG.state_index(nb, np.repeat(rd, K).reshape(-1, K), S[vn][0], S[vn][2])
            F = np.where(jj[:, :, None] >= 0, S[vn][1][np.maximum(jj, 0)], np.nan)
            out.append(F.reshape(n, -1))
        return sel, np.concatenate(out, axis=1)

    sel0, base0 = rebuild(d)
    T = float(np.quantile(d["arr"], 0.6))
    early = d["arr"] <= T
    say(f"    cut time T at the 60th percentile of arrivals; {int(early.sum()):,} rows at or before T")

    d1 = {k: v.copy() for k, v in d.items()}
    later = d["arr"] > T
    r2 = np.random.default_rng(11)
    d1["lg"][later] = r2.random(int(later.sum())).astype(d1["lg"].dtype) * 4.0
    d1["hv"][later] = (r2.random(int(later.sum())) < .5).astype(d1["hv"].dtype)
    d1["errf"][later] = (r2.random(int(later.sum())) < .5).astype(d1["errf"].dtype)
    d1["ntc"][later] = (r2.random(int(later.sum())) * 20).astype(d1["ntc"].dtype)
    _, pert = rebuild(d1)
    same = np.array_equal(np.nan_to_num(base0[early], nan=-9e9),
                          np.nan_to_num(pert[early], nan=-9e9))
    moved_late = not np.array_equal(np.nan_to_num(base0[~early], nan=-9e9),
                                    np.nan_to_num(pert[~early], nan=-9e9))
    say(f"T3a outcome of every record after T replaced by noise: early rows unchanged = {same}; "
        f"later rows did move = {moved_late}")

    keep = d["arr"] <= T
    sel2, del_ = rebuild(d, mask=keep)
    same2 = np.array_equal(np.nan_to_num(base0[keep], nan=-9e9), np.nan_to_num(del_, nan=-9e9))
    say(f"T3b every record after T deleted: early rows unchanged = {same2}")

    d2 = {k: v.copy() for k, v in d.items()}
    j0 = int(np.flatnonzero(d["arr"] <= np.quantile(d["arr"], 0.05))[-1])
    d2["lg"][j0] += 3.0
    d2["hv"][j0] = 1.0 - d2["hv"][j0]
    _, ctrl = rebuild(d2)
    aftr = d["arr"] > d["avail"][j0]
    moved = not np.array_equal(np.nan_to_num(base0[aftr], nan=-9e9),
                               np.nan_to_num(ctrl[aftr], nan=-9e9))
    before = d["arr"] < d["arr"][j0]
    stayed = np.array_equal(np.nan_to_num(base0[before], nan=-9e9),
                            np.nan_to_num(ctrl[before], nan=-9e9))
    say(f"T3c positive control (one record at the 5th percentile perturbed): later rows moved "
        f"= {moved}; strictly earlier rows unchanged = {stayed}")
    ok = (bad == 0 and nfail_state == 0 and nfail_set == 0 and same and same2 and moved
          and stayed and moved_late)
    say(f"\nALL LEAK TESTS {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
