"""Stage 4: the neural predictors.

    N0   MLP on exactly M4's tabular columns (code + context + history).  The architecture
         control: it isolates "neural net vs gradient boosting" from "graph vs no graph".
    G0   the same network with every neighbour slot empty: root node states only, no edges.
    G0U  G0 with the assessment and class root nodes dropped as well, so the model sees
         exactly M4's information through the graph architecture.
    G1   heterogeneous relational network over the causal snapshots built by build_graph.
    G2   the same network on the shuffled-edge inputs (nb_g2).
    R1   per-user GRU over the submissions of that user whose results are available at the
         current arrival, concatenated with M4's tabular columns.

G1 / G2 network (research_plan.md 3.3): no node-id embeddings anywhere; a node enters only
through its own as-of statistics, so an unseen exercise or student is handled by the same
weights.  Hidden width 64, two propagation rounds, per-relation linear maps, aggregation
mean or sum chosen on the validation semester.

    h0[n]   = ReLU(P_type(n) [ state(n) , has_state ])                       n in roots and
                                                                             sampled nbrs
    h1[ex]  = ReLU(Ws_ex h0[ex] + W_RA agg h0[R_A] + W_RE agg h0[R_E] + W_eA h0[asm])
    h1[us]  = ReLU(Ws_us h0[us] + W_RC agg h0[R_C] + W_RU agg h0[R_U] + W_uC h0[cl])
    h1[asm] = ReLU(Ws_as h0[asm] + W_aE agg h0[R_A + ex])
    h1[cl]  = ReLU(Ws_cl h0[cl]  + W_cU agg h0[R_C + us])
    h2[ex]  = ReLU(V_ex h1[ex] + V_eA h1[asm] + V_eU h1[us])
    h2[us]  = ReLU(V_us h1[us] + V_uC h1[cl]  + V_uE h1[ex])
    out     = MLP([h2[us], h2[ex], submission-level features])

h2 reaches two hops (a classmate's statistics enter h1[us], which enters h2[ex]).  The
submission-level block is the static code features, the schedule/context block and the
user x exercise columns of the current submission -- the node statistics themselves are NOT
also fed as tabular columns, so the graph is the only route for exercise and user history.

Two output heads: log1p cost (MSE) and heavy (BCE, weight W_CLS).  The plan's loss is the
MSE alone; the heavy head is added so that the heavy AUROC / AUPRC comparison is against a
classifier, as it is for M4 (LightGBM fits a separate binary model).  Both heads share the
trunk and neither sees the other's target.

Training-time masking (plan 3.3): with probability P_MASK the model's own exercise-node
state and, independently, its own user-node state are blanked (zeros + has_state = 0), so
it has to learn to predict from neighbours alone; this is what makes the cold-start columns
meaningful.  Neighbour slots are additionally dropped with probability P_DROP.

Params are the CLI defaults below; seeds 3, 4, 5 as in the rest of the pre-check.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np
import torch
import torch.nn as nn

OUT = r"<cache-dir>\pn"
HERE = os.path.dirname(os.path.abspath(__file__))
TRAIN_CORE = ["2018-1", "2018-2", "2019-1", "2019-2"]
REMOTE = ["2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2"]
VALID = ["2022-1"]
TEST = ["2022-2"]
K = 16
H = 64
SEQ = 32
RELS = [("R_A", "asm", "ex"), ("R_C", "cl", "us"), ("R_U", "us", "ex"), ("R_E", "ex", "us")]
TYPES = ["us", "ex", "asm", "cl"]


def say(log, *a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


# --------------------------------------------------------------------------- #
class Net(nn.Module):
    def __init__(self, sdim, nsub, agg="mean", drop=0.1):
        super().__init__()
        self.agg = agg
        self.P = nn.ModuleDict({t: nn.Linear(sdim[t] + 1, H) for t in TYPES})
        self.W1 = nn.ModuleDict({k: nn.Linear(H, H, bias=False) for k in
                                 ["s_ex", "s_us", "s_as", "s_cl", "R_A", "R_E", "R_C", "R_U",
                                  "eA", "uC", "aE", "cU"]})
        self.b1 = nn.ParameterDict({t: nn.Parameter(torch.zeros(H)) for t in TYPES})
        self.W2 = nn.ModuleDict({k: nn.Linear(H, H, bias=False) for k in
                                 ["ex", "us", "eA", "eU", "uC", "uE"]})
        self.b2 = nn.ParameterDict({t: nn.Parameter(torch.zeros(H)) for t in ["ex", "us"]})
        self.head = nn.Sequential(nn.Linear(2 * H + nsub, 256), nn.ReLU(), nn.Dropout(drop),
                                  nn.Linear(256, 128), nn.ReLU(), nn.Dropout(drop),
                                  nn.Linear(128, 2))

    def pool(self, h, m):
        s = (h * m.unsqueeze(-1)).sum(1)
        if self.agg == "sum":
            return s
        return s / m.sum(1, keepdim=True).clamp(min=1.0)

    def forward(self, roots, rootm, nbr, nbrm, sub):
        h0 = {t: torch.relu(self.P[t](torch.cat([roots[t] * rootm[t].unsqueeze(-1),
                                                 rootm[t].unsqueeze(-1)], -1))) for t in TYPES}
        n0 = {}
        for nm, an, vn in RELS:
            x = torch.cat([nbr[nm] * nbrm[nm].unsqueeze(-1), nbrm[nm].unsqueeze(-1)], -1)
            n0[nm] = torch.relu(self.P[vn](x))
        pA = self.pool(n0["R_A"], nbrm["R_A"])
        pE = self.pool(n0["R_E"], nbrm["R_E"])
        pC = self.pool(n0["R_C"], nbrm["R_C"])
        pU = self.pool(n0["R_U"], nbrm["R_U"])
        aE = self.pool(torch.cat([n0["R_A"], h0["ex"].unsqueeze(1)], 1),
                       torch.cat([nbrm["R_A"], rootm["ex"].unsqueeze(1)], 1))
        cU = self.pool(torch.cat([n0["R_C"], h0["us"].unsqueeze(1)], 1),
                       torch.cat([nbrm["R_C"], rootm["us"].unsqueeze(1)], 1))
        h1ex = torch.relu(self.W1["s_ex"](h0["ex"]) + self.W1["R_A"](pA) + self.W1["R_E"](pE)
                          + self.W1["eA"](h0["asm"]) + self.b1["ex"])
        h1us = torch.relu(self.W1["s_us"](h0["us"]) + self.W1["R_C"](pC) + self.W1["R_U"](pU)
                          + self.W1["uC"](h0["cl"]) + self.b1["us"])
        h1as = torch.relu(self.W1["s_as"](h0["asm"]) + self.W1["aE"](aE) + self.b1["asm"])
        h1cl = torch.relu(self.W1["s_cl"](h0["cl"]) + self.W1["cU"](cU) + self.b1["cl"])
        h2ex = torch.relu(self.W2["ex"](h1ex) + self.W2["eA"](h1as) + self.W2["eU"](h1us)
                          + self.b2["ex"])
        h2us = torch.relu(self.W2["us"](h1us) + self.W2["uC"](h1cl) + self.W2["uE"](h1ex)
                          + self.b2["us"])
        z = torch.cat([h2us, h2ex, sub], -1)
        return self.head(z), z[:, :2 * H]


class MLP(nn.Module):
    def __init__(self, nin, drop=0.1):
        super().__init__()
        self.f = nn.Sequential(nn.Linear(nin, 256), nn.ReLU(), nn.Dropout(drop),
                               nn.Linear(256, 128), nn.ReLU(), nn.Dropout(drop),
                               nn.Linear(128, 2))

    def forward(self, x):
        return self.f(x), x[:, :0]


class GRUNet(nn.Module):
    def __init__(self, nstep, ntab, drop=0.1):
        super().__init__()
        self.g = nn.GRU(nstep, H, batch_first=True)
        self.f = nn.Sequential(nn.Linear(H + ntab, 256), nn.ReLU(), nn.Dropout(drop),
                               nn.Linear(256, 128), nn.ReLU(), nn.Dropout(drop),
                               nn.Linear(128, 2))

    def forward(self, seq, seqm, tab):
        o, _ = self.g(seq)                       # steps are oldest-first, padded in front
        last = o[:, -1, :] * (seqm[:, -1:].clamp(max=1.0))
        z = torch.cat([last, tab], -1)
        return self.f(z), last


# --------------------------------------------------------------------------- #
def standardise(X, mtr):
    mu = np.nanmean(X[mtr], 0)
    sd = np.nanstd(X[mtr], 0)
    sd = np.where((sd < 1e-6) | ~np.isfinite(sd), 1.0, sd)
    mu = np.where(np.isfinite(mu), mu, 0.0)
    Z = (X - mu) / sd
    miss = ~np.isfinite(Z)
    Z = np.where(miss, 0.0, np.clip(Z, -8, 8)).astype(np.float32)
    return Z, miss.astype(np.float32), mu, sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["N0", "G0", "G0U", "G1", "G2", "R1"])
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--agg", default="mean", choices=["mean", "sum"])
    ap.add_argument("--variant", default="core", choices=["core", "remote"])
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=4096)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--p_mask", type=float, default=0.15)
    ap.add_argument("--p_drop", type=float, default=0.1)
    ap.add_argument("--w_cls", type=float, default=0.5)
    ap.add_argument("--wd", type=float, default=0.0)
    ap.add_argument("--drop", type=float, default=0.1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--save_emb", action="store_true")
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    dev = "cuda"
    name = f"{a.model}_{a.variant}_lr{a.lr}_{a.agg}_wd{a.wd}_dr{a.drop}_s{a.seed}{a.tag}"
    log = open(os.path.join(HERE, f"out_train_{name}.txt"), "w", encoding="utf-8")
    say(log, f"{name}  params {vars(a)}")

    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    X = np.load(os.path.join(OUT, "X.npy"))
    xcols = open(os.path.join(OUT, "xcols.txt")).read().split("\n")
    sem = B["sem"]
    trsem = TRAIN_CORE if a.variant == "core" else TRAIN_CORE + REMOTE
    m_tr, m_va, m_te = np.isin(sem, trsem), np.isin(sem, VALID), np.isin(sem, TEST)
    y, hv = B["y"], B["hv"]

    M4 = [c for c in xcols if not c.endswith("_perm") and c not in
          ("r_ex_simuser_log", "r_ex_simuser_heavy", "r_ass_other_log",
           "r_ass_other_heavy", "r_ex_sameclass_log")]
    ci = [xcols.index(c) for c in M4]
    Ztab, Mtab, _, _ = standardise(X[:, ci], m_tr)
    TAB = np.hstack([Ztab, Mtab[:, [i for i, c in enumerate(M4) if Mtab[:, i].any()]]])
    # submission-level block for G1/G2: code + context + user x exercise, NOT ex_*/u_*
    SUBC = [c for c in M4 if not (c.startswith("ex_") or c.startswith("u_"))]
    si = [M4.index(c) for c in SUBC]
    SUB = np.hstack([Ztab[:, si], Mtab[:, si]])
    say(log, f"tabular block {TAB.shape}, submission-level block {SUB.shape}")

    keep = m_tr | m_va | m_te
    kidx = np.flatnonzero(keep)
    remap = -np.ones(len(sem), np.int64)
    remap[kidx] = np.arange(len(kidx))
    ytr = torch.tensor(y[kidx], device=dev)
    htr = torch.tensor(hv[kidx], device=dev)
    TABt = torch.tensor(TAB[kidx], device=dev)
    SUBt = torch.tensor(SUB[kidx], device=dev)
    itr = torch.tensor(remap[np.flatnonzero(m_tr)], device=dev)
    iva = torch.tensor(remap[np.flatnonzero(m_va)], device=dev)
    ite = torch.tensor(remap[np.flatnonzero(m_te)], device=dev)
    say(log, f"rows train {len(itr):,} valid {len(iva):,} test {len(ite):,}")

    graph = a.model in ("G0", "G0U", "G1", "G2")
    if graph:
        G = np.load(os.path.join(OUT, "graph.npz"), allow_pickle=False)
        nb = np.load(os.path.join(OUT, "nb_g2.npy" if a.model == "G2" else "nb_g1.npy"))[kidx]
        if a.model in ("G0", "G0U"):
            nb = np.full_like(nb, -1)      # ablation: root node states only, no edges
        root = G["root"][kidx].copy()
        if a.model == "G0U":
            root[:, 2:] = -1              # ablation: drop the assessment and class nodes too
        ST, sdim = {}, {}
        for t in TYPES:
            s = G[f"st_{t}"].astype(np.float32).copy()
            s[:, 0] = np.log1p(s[:, 0])                     # count -> log1p(count)
            mu, sd = s.mean(0), s.std(0)
            sd = np.where(sd < 1e-6, 1.0, sd)
            s = np.vstack([np.zeros((1, s.shape[1]), np.float32), (s - mu) / sd])  # row 0 = pad
            ST[t] = torch.tensor(s, device=dev)
            sdim[t] = s.shape[1]
        ROOT = torch.tensor(root + 1, device=dev, dtype=torch.long)
        NB = torch.tensor(nb.reshape(len(kidx), len(RELS), K) + 1, device=dev, dtype=torch.long)
        net = Net(sdim, SUB.shape[1], agg=a.agg, drop=a.drop).to(dev)
    elif a.model == "R1":
        r_avail, r_read = B["r_avail"], B["r_read"]
        us = B["us"].astype(np.int64)
        RSPAN = int(np.load(os.path.join(OUT, "graph.npz"))["RSPAN"])
        o = np.lexsort((r_avail, us))
        comp = us[o] * RSPAN + r_avail[o]
        ptr = np.searchsorted(us[o], np.arange(us.max() + 2))
        pos = np.searchsorted(comp, us * RSPAN + r_read, side="left")[kidx]
        lo = ptr[us][kidx]
        idx = pos[:, None] - 1 - np.arange(SEQ)[None, :]          # newest first
        ok = idx >= lo[:, None]
        rows = np.where(ok, o[np.maximum(idx, 0)], 0)
        nk = len(kidx)
        step = np.zeros((nk, SEQ, 9), np.float32)
        step[:, :, 0] = y[rows]
        step[:, :, 1] = B["errf"][rows]
        step[:, :, 2] = hv[rows]
        step[:, :, 3] = (B["ex"][rows] == B["ex"][kidx][:, None])
        step[:, :, 4] = (B["asm"][rows] == B["asm"][kidx][:, None])
        step[:, :, 5] = np.log1p(np.maximum(B["arr"][kidx][:, None] - B["avail"][rows], 0.0))
        step[:, :, 6] = np.log1p(np.maximum(B["avail"][rows] - B["arr"][rows], 0.0))
        step[:, :, 7] = np.log1p(np.maximum(B["ntc"][rows], 0.0))
        step[:, :, 8] = B["a_is_exam"][rows]
        step = step * ok[:, :, None]
        step = step[:, ::-1, :].copy()                            # oldest first for the GRU
        okr = ok[:, ::-1].copy().astype(np.float32)
        ktr = np.isin(sem[kidx], trsem)
        mu = step[ktr].reshape(-1, 9).mean(0); sd = step[ktr].reshape(-1, 9).std(0)
        sd = np.where(sd < 1e-6, 1.0, sd)
        step = (((step - mu) / sd) * okr[:, :, None]).astype(np.float32)
        SEQt = torch.tensor(step, device=dev)
        OKt = torch.tensor(okr, device=dev)
        say(log, f"sequence steps available: mean {okr.sum(1).mean():.2f} of {SEQ}")
        del step, okr, rows, ok
        net = GRUNet(9, TAB.shape[1], drop=a.drop).to(dev)
    else:
        net = MLP(TAB.shape[1], drop=a.drop).to(dev)
    say(log, f"parameters {sum(p.numel() for p in net.parameters()):,}")

    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    mse, bce = nn.MSELoss(), nn.BCEWithLogitsLoss()
    gen = torch.Generator(device=dev); gen.manual_seed(a.seed)

    def batch(ix, train):
        sub = SUBt[ix] if graph else None
        if graph:
            roots, rootm = {}, {}
            for i, t in enumerate(TYPES):
                j = ROOT[ix, i]
                roots[t] = ST[t][j]
                m = (j > 0).float()
                if train and a.p_mask > 0 and t in ("ex", "us"):
                    m = m * (torch.rand(len(ix), device=dev, generator=gen) >= a.p_mask).float()
                rootm[t] = m
            nbr, nbrm = {}, {}
            for r, (nm, an, vn) in enumerate(RELS):
                j = NB[ix, r]
                nbr[nm] = ST[vn][j]
                m = (j > 0).float()
                if train and a.p_drop > 0:
                    m = m * (torch.rand(m.shape, device=dev, generator=gen) >= a.p_drop).float()
                nbrm[nm] = m
            return net(roots, rootm, nbr, nbrm, sub)
        if a.model == "R1":
            return net(SEQt[ix], OKt[ix], TABt[ix])
        return net(TABt[ix])

    def evaluate(ix, bs=16384):
        net.eval()
        P, E = [], []
        with torch.no_grad():
            for s in range(0, len(ix), bs):
                o, e = batch(ix[s:s + bs], False)
                P.append(o); E.append(e)
        return torch.cat(P), torch.cat(E)

    best, bad, beststate = np.inf, 0, None
    t0 = time.time()
    for ep in range(a.epochs):
        net.train()
        perm = torch.randperm(len(itr), device=dev, generator=gen)
        tot = 0.0
        for s in range(0, len(itr), a.batch):
            ix = itr[perm[s:s + a.batch]]
            o, _ = batch(ix, True)
            loss = mse(o[:, 0], ytr[ix]) + a.w_cls * bce(o[:, 1], htr[ix])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(ix)
        P, _ = evaluate(iva)
        vl = float(mse(P[:, 0], ytr[iva]) + a.w_cls * bce(P[:, 1], htr[iva]))
        vr = float(torch.sqrt(((P[:, 0] - ytr[iva]) ** 2).mean()))
        say(log, f"  epoch {ep:2d} train {tot / len(itr):.5f} valid {vl:.5f} "
                 f"(rmse {vr:.4f}) {time.time() - t0:.0f}s")
        if vl < best - 1e-5:
            best, bad = vl, 0
            beststate = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= a.patience:
                say(log, f"  early stop at epoch {ep}")
                break
    net.load_state_dict(beststate)
    Pte, Ete = evaluate(ite)
    Pva, _ = evaluate(iva)
    out = dict(name=name, model=a.model, variant=a.variant, seed=a.seed, lr=a.lr, agg=a.agg,
               wd=a.wd, drop=a.drop, valid_loss=best,
               valid_rmse=float(torch.sqrt(((Pva[:, 0] - ytr[iva]) ** 2).mean())))
    np.savez(os.path.join(OUT, f"pred_{name}.npz"),
             yhat=Pte[:, 0].cpu().numpy(), hhat=torch.sigmoid(Pte[:, 1]).cpu().numpy(),
             yhat_va=Pva[:, 0].cpu().numpy(), hhat_va=torch.sigmoid(Pva[:, 1]).cpu().numpy())
    if a.save_emb and Ete.shape[1] > 0:
        Etr = evaluate(itr)[1].cpu().numpy()
        Eva = evaluate(iva)[1].cpu().numpy()
        np.savez(os.path.join(OUT, f"emb_{name}.npz"), tr=Etr, va=Eva, te=Ete.cpu().numpy())
    say(log, json.dumps(out))
    with open(os.path.join(HERE, "runs.jsonl"), "a") as f:
        f.write(json.dumps(out) + "\n")
    torch.save(net.state_dict(), os.path.join(OUT, f"net_{name}.pt"))


if __name__ == "__main__":
    main()
