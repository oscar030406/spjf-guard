"""Rebuild the primary overlay inputs (rep 0, rep 1) and the single-server configuration
from the verified project module, and save them for the guard runs.

Nothing here is new: it calls service_precheck_v2's own p2_inputs / ms_entries / overlay /
rebase / level_ks / k1_select (imported read-only, byte-compilation off) so the traces are
the same ones the project's tables are computed on.  Only the arrays needed by the
scheduler are kept.

output (cache directory, not the project tree):
    <SCRATCH>/gv_inputs/rep0.npz, rep1.npz  -- a, svc, M4, in_dl, in_exam, hvt, K, W
    <SCRATCH>/gv_inputs/k1rep0.npz          -- the same for the k = 1 configuration
usage:  build_inputs.py
"""
import sys
sys.dont_write_bytecode = True
import os
import time
import numpy as np

V2 = r"<repo-root>/evidence/codebench_service_v2"
SCRATCH = r"<cache-dir>"
CACHE = SCRATCH + "/cb_v2_cache_r4"
OUT = SCRATCH + "/gv_inputs"
CFG = "ires0"
COPIES = 44
T0 = time.time()


def log(*a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    sys.path.insert(0, V2)
    import service_precheck_v2 as b
    log("module loaded; reading the cache")
    ev = b.load_events(CACHE)
    D = b.prep(ev)
    S = b.static_sub(ev, D)
    I = b.p2_inputs(D, S, CFG, CACHE)
    key = b.trace_key(CFG)
    log(f"p2_inputs {CFG}: {I['info']}, pool {len(I['pool'])} class-semesters, key={key}")

    for rep in (0, 1):
        ent = b.ms_entries(I["pool"], COPIES, rep)
        a, svc, jidx, _ = b.overlay(ent, I["per_cs"], key)
        comp, W = b.busy_comp(a, svc, jidx, D, S)
        K = b.level_ks(W)
        a = b.rebase(a)
        assert np.all(np.diff(a) >= 0)
        np.savez(os.path.join(OUT, f"rep{rep}.npz"), a=a, svc=svc,
                 M4=I["P"]["M4"][jidx].astype(np.float64),
                 dl=I["in_dl"][jidx], exam=I["in_exam"][jidx], hvt=I["hvt"][jidx],
                 K=np.array(K), W=np.float64(W))
        log(f"rep{rep}: n={len(a):,}  busy-hour work W={W:.3f}s  k={K}  "
            f"rho={[round(W/(3600*k), 4) for k in K]}  "
            f"deadline-window jobs {int(I['in_dl'][jidx].sum()):,}  "
            f"heavy {int(I['hvt'][jidx].sum()):,}  span={a.max()/86400:.1f} d")
        del a, svc, jidx

    rep = 0
    sel, rho_p = b.k1_select(I["pool"], I["per_cs"], b.SEED * 100 + 50 + rep, key)
    a, svc, jidx, _ = b.overlay(sel, I["per_cs"], key)
    comp, W = b.busy_comp(a, svc, jidx, D, S)
    a = b.rebase(a)
    assert abs(W / 3600.0 - rho_p) < 1e-9
    np.savez(os.path.join(OUT, "k1rep0.npz"), a=a, svc=svc,
             M4=I["P"]["M4"][jidx].astype(np.float64),
             M1=I["P"]["M1"][jidx].astype(np.float64),
             dl=I["in_dl"][jidx], exam=I["in_exam"][jidx], hvt=I["hvt"][jidx],
             K=np.array([1]), W=np.float64(W))
    log(f"k1 rep0: {len(sel)} class-semester copies, n={len(a):,}, busy-hour rho at k=1 "
        f"= {W/3600.0:.4f}, deadline-window jobs {int(I['in_dl'][jidx].sum()):,}")
    log("done")


if __name__ == "__main__":
    main()
