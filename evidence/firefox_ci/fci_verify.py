"""Verify the local k(t) kernel of fci_simval.py against the project kernel.

    uv run --with numpy --with numba --with pandas --with pyarrow --with requests \
        python fci_verify.py

With a constant capacity the two must agree job by job, on FCFS and on pure predicted
order; and a bucket with zero capacity must stall every dispatch until the next bucket.
Nothing in fci_simval.py may be trusted before this passes (writes out_verify.txt)."""
import sys, os
sys.dont_write_bytecode = True
import numpy as np
import guardkern_snapshot as GK
from fci_simval import simulate_kt

rng = np.random.default_rng(7)
bad = 0
for trial in range(30):
    n = rng.integers(20, 400)
    k = int(rng.integers(1, 8))
    a = np.sort(rng.exponential(3.0, n).cumsum())
    s = np.clip(rng.exponential(5.0, n), 1e-3, 60.0)
    nb = int(np.ceil((a.max() + s.sum() - a.min()) / 3600.0)) + 2
    kser = np.full(nb, k, np.int64)
    st = simulate_kt(a, s, np.arange(n, dtype=np.float64), kser, a.min(), 3600.0)
    w1 = st - a
    w2 = GK.run(a, s, k, policy="fcfs").w
    d = np.max(np.abs(w1 - w2))
    if d > 1e-9:
        bad += 1
        print("FCFS mismatch", trial, n, k, d)
    # pure-pred order
    pred = rng.random(n)
    st = simulate_kt(a, s, pred, kser, a.min(), 3600.0)
    w3 = st - a
    w4 = GK.run(a, s, k, policy="pri", pred=pred).w
    d = np.max(np.abs(w3 - w4))
    if d > 1e-9:
        bad += 1
        print("PRI mismatch", trial, n, k, d)
msg1 = ("kernel cross-check vs guardkern_snapshot.py on 30 random instances "
        "(FCFS and pure predicted order, constant capacity): "
        + ("PASS" if bad == 0 else f"FAIL {bad}"))
print(msg1)

# k(t) sanity: capacity 0 in a bucket must stall dispatch
a = np.array([0.0, 1.0, 2.0])
s = np.array([1.0, 1.0, 1.0])
kser = np.array([0, 2, 2], np.int64)
st = simulate_kt(a, s, np.arange(3, dtype=np.float64), kser, 0.0, 3600.0)
msg2 = (f"zero-capacity first hour -> starts {list(st)} (every start must be >= 3600): "
        + ("PASS" if st.min() >= 3600.0 else "FAIL"))
print(msg2)

import fci_common as C  # noqa: E402

with open(os.path.join(C.HERE, "out_verify.txt"), "w", encoding="utf-8") as fh:
    fh.write(msg1 + "\n" + msg2 + "\n")
