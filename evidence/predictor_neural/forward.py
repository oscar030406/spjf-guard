"""Stage 8: forward (rolling-origin) predictions for the 60 s-limit development semesters,
so that a neural predictor can be run through the scheduler exactly like M4's
forward_ires0.parquet.

For each target semester s the model is trained on the submissions of the semesters whose
first event precedes s, minus every record whose assumed availability time is at or after
s's first arrival -- the rule service_precheck_v2.stage_forward uses.  The network needs an
inner validation set for early stopping, and it must not be allowed to peek: the latest
VAL_FRAC of the TRAINING rows by arrival time is held out for that, so the stopping
decision is made on data that is still strictly older than the target.  Seed 3 only, as in
the pre-check's forward stage.

Output: forward_neural.parquet, one row per submission in the same order as
forward_ires0.parquet (the sidx order of the v2 cache), NaN outside the six target
semesters.  The stored value is the regression head's log1p prediction, the same quantity
forward_ires0.parquet stores, so the scheduler can use it unchanged.

Params: TARGETS below, VAL_FRAC = 0.1, seed 3, same hyper-parameters as the frozen runs.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_neural as TN

OUT = TN.OUT
TARGETS = ["2020-ERE", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2"]
VAL_FRAC = 0.10
SEED = 3
HP = {"G1": dict(lr=1e-3, epochs=30), "R1": dict(lr=3e-4, epochs=30)}
K = TN.K
RELS = TN.RELS
TYPES = TN.TYPES


def say(log, *a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="G1,R1")
    ap.add_argument("--targets", default=",".join(TARGETS))
    ap.add_argument("--save_emb", action="store_true")
    a = ap.parse_args()
    targets = a.targets.split(",")
    log = open(os.path.join(HERE, f"out_forward_{'_'.join(targets)}.txt"), "w", encoding="utf-8")
    dev = "cuda"
    B = np.load(os.path.join(OUT, "base.npz"), allow_pickle=False)
    X = np.load(os.path.join(OUT, "X.npy"))
    xcols = open(os.path.join(OUT, "xcols.txt")).read().split("\n")
    sem, y, hv = B["sem"], B["y"], B["hv"]
    arr, avail = B["arr"], B["avail"]
    ns = len(sem)
    allsem = sorted(set(sem.tolist()))
    first = {s: float(arr[sem == s].min()) for s in allsem}
    order = sorted(allsem, key=first.get)
    say(log, "semester order by first arrival: " + ", ".join(order))

    M4 = [c for c in xcols if not c.endswith("_perm") and not c.startswith("r_")]
    ci = [xcols.index(c) for c in M4]
    SUBC = [c for c in M4 if not (c.startswith("ex_") or c.startswith("u_"))]

    G = np.load(os.path.join(OUT, "graph.npz"), allow_pickle=False)
    RSPAN = int(G["RSPAN"])
    nb_all = np.load(os.path.join(OUT, "nb_g1.npy"))
    root_all = G["root"]
    ST, sdim = {}, {}
    for t in TYPES:
        s_ = G[f"st_{t}"].astype(np.float32).copy()
        s_[:, 0] = np.log1p(s_[:, 0])
        mu, sd = s_.mean(0), s_.std(0)
        sd = np.where(sd < 1e-6, 1.0, sd)
        ST[t] = torch.tensor(np.vstack([np.zeros((1, s_.shape[1]), np.float32),
                                        (s_ - mu) / sd]), device=dev)
        sdim[t] = s_.shape[1]

    us = B["us"].astype(np.int64)
    o = np.lexsort((B["r_avail"], us))
    compseq = us[o] * RSPAN + B["r_avail"][o]
    ptrseq = np.searchsorted(us[o], np.arange(us.max() + 2))

    outf = os.path.join(HERE, "forward_neural.parquet")
    res = (pd.read_parquet(outf).to_dict("series") if os.path.exists(outf)
           else {m: pd.Series(np.full(ns, np.nan)) for m in a.models.split(",")})
    res = {m: np.array(v, dtype="float64", copy=True) for m, v in res.items()}
    for m in a.models.split(","):
        res.setdefault(m, np.full(ns, np.nan))

    rows = []
    for s in targets:
        prior = [q for q in order if first[q] < first[s]]
        m_prior = np.isin(sem, prior)
        m_tr_all = m_prior & (avail < first[s])
        m_te = sem == s
        cut = np.quantile(arr[m_tr_all], 1 - VAL_FRAC)
        m_va = m_tr_all & (arr >= cut)
        m_tr = m_tr_all & (arr < cut)
        say(log, f"\ntarget {s}: prior {prior[0]}..{prior[-1]}  rows {int(m_prior.sum()):,} "
                 f"-> usable {int(m_tr_all.sum()):,} (dropped "
                 f"{int(m_prior.sum() - m_tr_all.sum()):,} not yet available)  "
                 f"inner train {int(m_tr.sum()):,} / valid {int(m_va.sum()):,}  "
                 f"target {int(m_te.sum()):,}")
        keep = m_tr | m_va | m_te
        kidx = np.flatnonzero(keep)
        remap = -np.ones(ns, np.int64); remap[kidx] = np.arange(len(kidx))
        Ztab, Mtab, _, _ = TN.standardise(X[:, ci], m_tr)
        TAB = np.hstack([Ztab, Mtab[:, [i for i, c in enumerate(M4) if Mtab[:, i].any()]]])
        si = [M4.index(c) for c in SUBC]
        SUB = np.hstack([Ztab[:, si], Mtab[:, si]])
        TABt = torch.tensor(TAB[kidx], device=dev)
        SUBt = torch.tensor(SUB[kidx], device=dev)
        yt = torch.tensor(y[kidx], device=dev); ht = torch.tensor(hv[kidx], device=dev)
        itr = torch.tensor(remap[np.flatnonzero(m_tr)], device=dev)
        iva = torch.tensor(remap[np.flatnonzero(m_va)], device=dev)
        ite = torch.tensor(remap[np.flatnonzero(m_te)], device=dev)
        ROOT = torch.tensor(root_all[kidx] + 1, device=dev, dtype=torch.long)
        NB = torch.tensor(nb_all[kidx].reshape(len(kidx), len(RELS), K) + 1,
                          device=dev, dtype=torch.long)

        pos = np.searchsorted(compseq, us * RSPAN + B["r_read"], side="left")[kidx]
        lo = ptrseq[us][kidx]
        sidx_ = pos[:, None] - 1 - np.arange(TN.SEQ)[None, :]
        okm = sidx_ >= lo[:, None]
        srow = np.where(okm, o[np.maximum(sidx_, 0)], 0)
        step = np.zeros((len(kidx), TN.SEQ, 9), np.float32)
        step[:, :, 0] = y[srow]; step[:, :, 1] = B["errf"][srow]; step[:, :, 2] = hv[srow]
        step[:, :, 3] = (B["ex"][srow] == B["ex"][kidx][:, None])
        step[:, :, 4] = (B["asm"][srow] == B["asm"][kidx][:, None])
        step[:, :, 5] = np.log1p(np.maximum(arr[kidx][:, None] - avail[srow], 0.0))
        step[:, :, 6] = np.log1p(np.maximum(avail[srow] - arr[srow], 0.0))
        step[:, :, 7] = np.log1p(np.maximum(B["ntc"][srow], 0.0))
        step[:, :, 8] = B["a_is_exam"][srow]
        step = (step * okm[:, :, None])[:, ::-1, :].copy()
        okr = okm[:, ::-1].copy().astype(np.float32)
        ktr = m_tr[kidx]
        mu = step[ktr].reshape(-1, 9).mean(0); sd = step[ktr].reshape(-1, 9).std(0)
        sd = np.where(sd < 1e-6, 1.0, sd)
        SEQt = torch.tensor((((step - mu) / sd) * okr[:, :, None]).astype(np.float32), device=dev)
        OKt = torch.tensor(okr, device=dev)
        del step, okr, srow, okm

        for mname in a.models.split(","):
            torch.manual_seed(SEED); np.random.seed(SEED)
            gen = torch.Generator(device=dev); gen.manual_seed(SEED)
            hp = HP[mname]
            net = (TN.Net(sdim, SUB.shape[1], agg="mean") if mname == "G1"
                   else TN.GRUNet(9, TAB.shape[1])).to(dev)
            opt = torch.optim.AdamW(net.parameters(), lr=hp["lr"], weight_decay=0.0)
            mse, bce = nn.MSELoss(), nn.BCEWithLogitsLoss()

            def batch(ix, train):
                if mname == "G1":
                    roots, rootm = {}, {}
                    for i, t in enumerate(TYPES):
                        j = ROOT[ix, i]
                        roots[t] = ST[t][j]
                        mm = (j > 0).float()
                        if train and t in ("ex", "us"):
                            mm = mm * (torch.rand(len(ix), device=dev, generator=gen)
                                       >= 0.15).float()
                        rootm[t] = mm
                    nbr, nbrm = {}, {}
                    for r, (nm, an, vn) in enumerate(RELS):
                        j = NB[ix, r]
                        nbr[nm] = ST[vn][j]
                        mm = (j > 0).float()
                        if train:
                            mm = mm * (torch.rand(mm.shape, device=dev, generator=gen)
                                       >= 0.1).float()
                        nbrm[nm] = mm
                    return net(roots, rootm, nbr, nbrm, SUBt[ix])
                return net(SEQt[ix], OKt[ix], TABt[ix])

            def ev(ix, bs=16384):
                net.eval(); P, E = [], []
                with torch.no_grad():
                    for st_ in range(0, len(ix), bs):
                        p_, e_ = batch(ix[st_:st_ + bs], False)
                        P.append(p_); E.append(e_)
                return torch.cat(P), torch.cat(E)

            best, bad, bstate, t0 = np.inf, 0, None, time.time()
            for ep in range(hp["epochs"]):
                net.train()
                perm = torch.randperm(len(itr), device=dev, generator=gen)
                for st_ in range(0, len(itr), 4096):
                    ix = itr[perm[st_:st_ + 4096]]
                    p_, _ = batch(ix, True)
                    loss = mse(p_[:, 0], yt[ix]) + 0.5 * bce(p_[:, 1], ht[ix])
                    opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
                P, _ = ev(iva)
                vl = float(mse(P[:, 0], yt[iva]) + 0.5 * bce(P[:, 1], ht[iva]))
                if vl < best - 1e-5:
                    best, bad = vl, 0
                    bstate = {k_: v_.detach().clone() for k_, v_ in net.state_dict().items()}
                else:
                    bad += 1
                    if bad >= 5:
                        break
            net.load_state_dict(bstate)
            P, E = ev(ite)
            res[mname][np.flatnonzero(m_te)] = P[:, 0].cpu().numpy().astype("float64")
            yy, hh = y[m_te], hv[m_te]
            pp = P[:, 0].cpu().numpy()
            from scipy.stats import spearmanr
            rm = float(np.sqrt(np.mean((yy - pp) ** 2)))
            sp = float(spearmanr(yy, pp).statistic)
            rows.append(dict(target=s, model=mname, n_train=int(m_tr.sum()),
                             n_target=int(m_te.sum()), epochs=ep + 1, valid=best,
                             rmse=round(rm, 4), spearman=round(sp, 4),
                             sec=round(time.time() - t0)))
            say(log, f"  {mname}: epochs {ep + 1}  rmse {rm:.4f}  spearman {sp:.4f}  "
                     f"{time.time() - t0:.0f}s")
            if a.save_emb and mname == "R1":
                np.savez(os.path.join(OUT, f"fwdemb_R1_{s}.npz"),
                         tr=ev(itr)[1].cpu().numpy(), te=E.cpu().numpy(),
                         itr=np.flatnonzero(m_tr), ite=np.flatnonzero(m_te))
    pd.DataFrame(res).to_parquet(outf, index=False)
    t = pd.DataFrame(rows)
    p = os.path.join(HERE, "fwdtab_neural.csv")
    if os.path.exists(p):
        t = pd.concat([pd.read_csv(p), t], ignore_index=True)
    t.to_csv(p, index=False)
    say(log, "\n" + t.to_string(index=False))


if __name__ == "__main__":
    main()
