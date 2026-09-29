"""Timing probe: how long one full-trace run of each policy takes, and whether the
segment-tree window (Mslots) is large enough.  usage: probe_speed.py"""
import sys
sys.dont_write_bytecode = True
import os
import time
import numpy as np
import guardkern as G

SCRATCH = r"<cache-dir>"
IN = SCRATCH + "/gv_inputs"
T0 = time.time()

G.run(np.zeros(2), np.ones(2), 1, "guard", pred=np.zeros(2), B=1.0, eps=0.5, Mslots=4)
print(f"[{time.time()-T0:5.1f}s] kernel compiled", flush=True)
Z = np.load(os.path.join(IN, "rep0.npz"))
a, svc, M4, K = Z["a"], Z["svc"], Z["M4"], Z["K"]
k = int(K[2])
print(f"[{time.time()-T0:5.1f}s] loaded n={len(a):,} k={k}", flush=True)
for nm, kw in (("fcfs", dict(policy="fcfs")),
               ("spjf", dict(policy="pri", pred=M4)),
               ("guard B=600", dict(policy="guard", pred=M4, B=600.0)),
               ("guard B0=0 eps=2", dict(policy="guard", pred=M4, B=0.0, eps=2.0))):
    t = time.time()
    r = G.run(a, svc, k, **kw)
    print(f"[{time.time()-T0:5.1f}s] {nm:18s} {time.time()-t:6.1f}s  mean={r.w.mean():.4f} "
          f"max={r.w.max():.1f} forced={r.n_forced:,}/{r.n_disp:,} "
          f"rebuilds={r.n_rebuild} max_span={r.max_span:,} err={r.err}", flush=True)
    del r
