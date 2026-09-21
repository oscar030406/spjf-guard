"""Stage 2: causal node-state timelines and sampled neighbour sets for G1 / G2.

GRAPH.  Node types user, exercise, assessment (class|assessment), class (semester|class).
No node-id embeddings anywhere: a node enters the model only through its statistics.

NODE INPUT = that node's statistics over the results AVAILABLE at the query time.  The
statistics are materialised as a TIMELINE per node: one entry per availability event of
that node, carrying the running (count, mean, sd, p50, p90, max, error rate, heavy rate,
mean test-case count) of log1p(C) over the results available up to and including that
event.  The state of node n as of a read with event rank r is the last timeline entry with
rank_avail < r.  Because every entry only summarises results that were available strictly
before r, the state is exactly the "as-of" state the verified feature pipeline would build.
(build_base.py proves this: replaying the same stream reproduces feat_ires0's ex_*/u_*
columns bit for bit.)

NEIGHBOURS (cap K = 16 per relation, drawn from the last W = 96 records):
    R_A  exercise <- assessment -> exercise   other exercises recently active in the
                                              same assessment
    R_C  user     <- class      -> user       other users recently active in the same class
    R_U  user     -> submit     -> exercise   the user's other recently used exercises
    R_E  exercise <- submit     <- user       other users who recently used this exercise
Each candidate list is the arrival-ordered list of submissions attached to the anchor node;
only entries whose REGISTER rank is < the read rank are visible (i.e. arrival[j] <
arrival[i] strictly, the arrival-only half of the availability rule).  The most recent W
visible entries are scanned back, the self node is removed, duplicates collapse to their
most recent occurrence, and the first K distinct neighbours are kept.  Each kept neighbour
is then resolved to its own timeline entry as of the read rank.  Nothing else about the
neighbour enters the model.

G2 (shuffled-edge control) rewires the edges within a semester x time block: rows are
grouped by semester and then into blocks of BLK = 20,000 consecutive rows (the rows are in
event order), and inside each block a random permutation reassigns whole neighbour SETS
from one row to another.  The borrowed node ids are then resolved to their own timelines at
the BORROWING row's query time, so G2 is exactly as causal as G1 and its neighbours are
nodes that were active in the same semester at about the same time -- what changes is only
WHICH node each edge points at.  (A plain global permutation of node ids was tried first
and rejected: it halves the number of neighbours that have any state yet, so G1 would win
on neighbour count rather than on relation identity.)

Params: K = 16, W = 96, PERM_SEED = 3, BLK = 20,000.  Deterministic.
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
K = 16
W = 96
PERM_SEED = 3
BLK = 20_000
CHUNK = 120_000

# relation -> (anchor node type, neighbour node type)
RELS = [("R_A", "asm", "ex"), ("R_C", "cl", "us"), ("R_U", "us", "ex"), ("R_E", "ex", "us")]
STATE_DIM = {"ex": 9, "us": 8, "asm": 5, "cl": 5}

LOG = open(os.path.join(HERE, "out_build_graph.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def build_timelines(node, r_avail, lg, hv, errf, ntc, nnode, with_q, with_ntc):
    """One pass in availability-rank order; returns (comp, feat, ptr) for this node type.
    comp = node * R + rank_avail (globally sorted), feat = running statistics after the
    event, ptr[n] = first entry of node n."""
    o = np.argsort(r_avail, kind="stable")
    d = 3 + (3 if with_q else 0) + 2 + (1 if with_ntc else 0)
    feat = np.zeros((len(o), d), np.float32)
    nodes_o = node[o]
    st = {}
    lgl, hvl, erl, ntl = lg.tolist(), hv.tolist(), errf.tolist(), ntc.tolist()
    nl = nodes_o.tolist()
    ol = o.tolist()
    for pos, (n, j) in enumerate(zip(nl, ol)):
        x, h_, er = lgl[j], hvl[j], erl[j]
        S = st.get(n)
        if S is None:
            S = st[n] = [0, 0.0, 0.0, 0.0, 0.0, 0.0, deque(maxlen=120) if with_q else None]
        S[0] += 1; S[1] += x; S[2] += x * x; S[3] += er; S[4] += h_
        if with_ntc:
            S[5] += ntl[j]
        nn = S[0]
        m = S[1] / nn
        row = [nn, m, sqrt(max(S[2] / nn - m * m, 0.0))]
        if with_q:
            S[6].append(x)
            s = sorted(S[6]); L = len(s) - 1
            row += [s[min(L, int(.5 * L + .5))], s[min(L, int(.9 * L + .5))], s[-1]]
        row += [S[3] / nn, S[4] / nn]
        if with_ntc:
            row.append(S[5] / nn)
        feat[pos] = row
    # sort globally by (node, rank)
    r_sorted = r_avail[o]
    o2 = np.lexsort((r_sorted, nodes_o))
    feat = feat[o2]
    comp = nodes_o[o2].astype(np.int64) * RSPAN + r_sorted[o2]
    ptr = np.searchsorted(nodes_o[o2], np.arange(nnode + 1))
    return comp, feat, ptr.astype(np.int64)


def build_lists(anchor, value, r_reg, nnode):
    """CSR of (anchor node -> arrival-ordered neighbour values)."""
    o = np.lexsort((r_reg, anchor))
    comp = anchor[o].astype(np.int64) * RSPAN + r_reg[o]
    val = value[o].astype(np.int32)
    ptr = np.searchsorted(anchor[o], np.arange(nnode + 1)).astype(np.int64)
    return comp, val, ptr


def neighbours(anchor_ids, self_ids, r_read, lcomp, lval, lptr):
    """Most recent K distinct neighbour node ids strictly before r_read (K columns, -1 pad).
    Also returns the number of visible candidate records (the anchor's causal degree)."""
    n = len(r_read)
    pos = np.searchsorted(lcomp, anchor_ids.astype(np.int64) * RSPAN + r_read, side="left")
    lo = lptr[anchor_ids]
    deg = pos - lo
    idx = pos[:, None] - 1 - np.arange(W)[None, :]
    ok = idx >= lo[:, None]
    idx = np.where(ok, idx, 0)
    v = np.where(ok, lval[idx], -1)
    v = np.where(v == self_ids[:, None], -1, v)          # drop the self node
    keep = v >= 0
    # collapse repeats to their most recent occurrence: sort each row by value (stable, so
    # the earliest column of each equal run comes first), keep the run's first member
    so = np.argsort(v, axis=1, kind="stable")
    vs = np.take_along_axis(v, so, axis=1)
    first = np.ones_like(vs, bool)
    first[:, 1:] = vs[:, 1:] != vs[:, :-1]
    firstback = np.empty_like(first)
    np.put_along_axis(firstback, so, first, axis=1)
    keep &= firstback
    order = np.argsort(~keep, axis=1, kind="stable")
    v = np.take_along_axis(v, order, axis=1)[:, :K]
    keep = np.take_along_axis(keep, order, axis=1)[:, :K]
    return np.where(keep, v, -1).astype(np.int32), deg.astype(np.int32)


def state_index(node_ids, r_read, scomp, sptr):
    """Timeline entry of each node as of r_read (last entry with rank < r_read), -1 if none.
    node_ids may be -1 (absent neighbour)."""
    nid = np.maximum(node_ids, 0).astype(np.int64)
    j = np.searchsorted(scomp, nid * RSPAN + r_read, side="left") - 1
    ok = (node_ids >= 0) & (j >= sptr[nid])
    return np.where(ok, j, -1).astype(np.int32)


def main():
    global RSPAN, LOG
    LOG = open(os.path.join(HERE, "out_build_graph.txt"), "w", encoding="utf-8")
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    ex, us, cl, asm = B["ex"], B["us"], B["cl"], B["asm"]
    r_avail, r_read, r_reg = B["r_avail"], B["r_read"], B["r_reg"]
    lg, hv, errf, ntc = B["lg"].astype("float64"), B["hv"].astype("float64"), \
        B["errf"].astype("float64"), B["ntc"].astype("float64")
    NE, NU, NC, NA = int(B["NE"]), int(B["NU"]), int(B["NC"]), int(B["NA"])
    ns = len(ex)
    RSPAN = int(max(r_avail.max(), r_read.max(), r_reg.max())) + 2
    say(f"rows {ns:,}  rank span {RSPAN:,}  K={K} W={W} perm_seed={PERM_SEED}")

    NODES = {"ex": (ex, NE), "us": (us, NU), "asm": (asm, NA), "cl": (cl, NC)}
    S = {}
    for t, (node, nn) in NODES.items():
        c, f, p = build_timelines(node, r_avail, lg, hv, errf, ntc, nn,
                                  with_q=(t in ("ex", "us")), with_ntc=(t == "ex"))
        S[t] = (c, f, p)
        say(f"timeline {t}: entries {len(c):,} dim {f.shape[1]} nodes {nn:,}")
        assert f.shape[1] == STATE_DIM[t]

    L = {}
    for nm, an, vn in RELS:
        L[nm] = build_lists(NODES[an][0], NODES[vn][0], r_reg, NODES[an][1])
        say(f"list {nm}: anchor {an} value {vn} entries {len(L[nm][0]):,}")

    rng = np.random.default_rng(PERM_SEED)
    PERM = {t: rng.permutation(nn).astype(np.int32) for t, (_, nn) in NODES.items()}

    # block permutation used by G2: within each semester, blocks of BLK consecutive rows
    sem = B["sem"]
    shuf = np.arange(ns)
    rng2 = np.random.default_rng(PERM_SEED)
    for s_ in np.unique(sem):
        idx = np.flatnonzero(sem == s_)
        for a in range(0, len(idx), BLK):
            blk = idx[a:a + BLK]
            shuf[blk] = blk[rng2.permutation(len(blk))]
    say(f"G2 block permutation: BLK={BLK}, moved rows {float((shuf != np.arange(ns)).mean()):.4f}")

    nb1 = np.full((ns, len(RELS) * K), -1, np.int32)
    nb2 = np.full((ns, len(RELS) * K), -1, np.int32)
    deg = np.zeros((ns, len(RELS)), np.int32)
    for ri, (nm, an, vn) in enumerate(RELS):
        lcomp, lval, lptr = L[nm]
        scomp, _, sptr = S[vn]
        anch_all, self_all = NODES[an][0], NODES[vn][0]
        nodes_col = np.full((ns, K), -1, np.int32)
        for a in range(0, ns, CHUNK):
            b = min(a + CHUNK, ns)
            nb, dg = neighbours(anch_all[a:b], self_all[a:b], r_read[a:b], lcomp, lval, lptr)
            nodes_col[a:b] = nb
            deg[a:b, ri] = dg
        nodes_sh = nodes_col[shuf]
        for a in range(0, ns, CHUNK):
            b = min(a + CHUNK, ns)
            rr = np.repeat(r_read[a:b], K).reshape(-1, K)
            nb1[a:b, ri * K:(ri + 1) * K] = state_index(nodes_col[a:b], rr, scomp, sptr)
            nb2[a:b, ri * K:(ri + 1) * K] = state_index(nodes_sh[a:b], rr, scomp, sptr)
        sl = slice(ri * K, (ri + 1) * K)
        say(f"  {nm}: neighbours with state/row  G1 {float((nb1[:, sl] >= 0).sum(1).mean()):.2f} "
            f"G2 {float((nb2[:, sl] >= 0).sum(1).mean()):.2f}  "
            f"visible candidate records {float(deg[:, ri].mean()):.1f}")
        del nodes_col, nodes_sh
    np.save(os.path.join(OUT, "nb_g1.npy"), nb1)
    np.save(os.path.join(OUT, "nb_g2.npy"), nb2)
    np.save(os.path.join(OUT, "deg.npy"), deg)

    root = np.full((ns, 4), -1, np.int32)
    rootdeg = np.zeros((ns, 4), np.int32)
    for i, t in enumerate(["us", "ex", "asm", "cl"]):
        scomp, _, sptr = S[t]
        root[:, i] = state_index(NODES[t][0], r_read, scomp, sptr)
        nm = {"us": "R_U", "ex": "R_E", "asm": "R_A", "cl": "R_C"}[t]
        lcomp, _, lptr = L[nm]
        pos = np.searchsorted(lcomp, NODES[t][0].astype(np.int64) * RSPAN + r_read, side="left")
        rootdeg[:, i] = pos - lptr[NODES[t][0]]
        say(f"root {t}: with state {float((root[:, i] >= 0).mean()):.4f}  "
            f"mean prior arrivals {float(rootdeg[:, i].mean()):.1f}")

    np.savez(os.path.join(OUT, "graph.npz"), root=root, rootdeg=rootdeg,
             **{f"st_{t}": S[t][1] for t in S},
             **{f"sp_{t}": S[t][2] for t in S},
             **{f"sc_{t}": S[t][0] for t in S},
             **{f"lc_{nm}": L[nm][0] for nm, _, _ in RELS},
             **{f"lv_{nm}": L[nm][1] for nm, _, _ in RELS},
             **{f"lp_{nm}": L[nm][2] for nm, _, _ in RELS},
             RSPAN=np.int64(RSPAN), K=np.int64(K), W=np.int64(W))
    say("wrote graph.npz, nb_g1.npy, nb_g2.npy, deg.npy")


if __name__ == "__main__":
    main()
