"""Gate 1: delay_kernel.simulate_delay against sim_stale.sim_guard, job by job.

Random integer instances (k 1..4, n 2..40, L in {3,4,6,10}, delta 0..3L, constant or
shaped budget, six key rules, three delay rules, both server orders), models U, A1, A2.
Compared per job: start, server, dispatch position, and the dispatch count at which each
charge entered each view (sim_stale's appg / app2).  Each instance runs three times: with a
window of 64 ranks (no slide), 16 and 8 ranks (slides exercised; err = 1 runs skipped).
At delta = 0 every model is also compared with the production kernel
(src/spjf_guard/sim/kernel.py) on wait and dispatch position.

    python -u evidence/revision_r1/report_delay/check_reference.py [n_instances] [seed]
writes outputs/revision_r1/report_delay/gate1_check_reference.json
"""

from __future__ import annotations

import _setup  # noqa: F401  (threads, cache dir, paths)

import json
import sys
import time
from fractions import Fraction

import numpy as np

sys.path.insert(0, str(_setup.ROOT / "evidence" / "stale_charging"))
import sim_stale as ref  # noqa: E402
from delay_kernel import MODE_GUARD, MODEL_A1, MODEL_A2, MODEL_U, simulate_delay  # noqa: E402

from spjf_guard.sim.kernel import simulate_kernel  # noqa: E402

BIG = ref.BIG_KEY
REF_MODEL = {MODEL_U: ref.U, MODEL_A1: ref.A1, MODEL_A2: ref.A2}


def instance(rng):
    k = int(rng.integers(1, 5))
    n = int(rng.integers(2, 41))
    L = int(rng.choice([3, 4, 6, 10]))
    delta = int(rng.integers(0, 3 * L + 1)) if rng.random() < 0.85 else 0
    smode = rng.integers(0, 3)
    pL = rng.random()
    if smode == 0:
        C = rng.integers(1, L + 1, n)
    elif smode == 1:
        C = np.where(rng.random(n) < pL, L, 1)
    else:
        C = np.where(rng.random(n) < pL, L, rng.integers(1, 3, n))
    amode = rng.integers(0, 3)
    span = 0 if amode == 0 else (L if amode == 1 else n * L // 2 + 1)
    a = np.sort(rng.integers(0, span + 1, n))
    a -= a[0]
    kmode = rng.integers(0, 6)
    perm = rng.permutation(n)
    idx = np.arange(n)
    if kmode in (0, 5):
        key = perm.astype(np.float64)
    elif kmode == 1:
        key = (C * 64 - idx).astype(np.float64)
    elif kmode == 2:
        key = (-C * 64 - idx).astype(np.float64)
    else:
        key = (-idx).astype(np.float64)
    if kmode >= 4:
        key[rng.integers(0, n)] = BIG
    dmode = rng.integers(0, 3)
    if dmode == 0:
        d = np.full(n, delta)
    elif dmode == 1:
        d = rng.integers(0, delta + 1, n)
    else:
        d = np.where(rng.random(n) < 0.5, delta, 0)
    bmax = int(rng.integers(1, 6 * L + 1))  # 0 means "uncapped" to the kernel, budget 0 to sim_stale
    if rng.random() < 0.5:
        b0, gam, eta = bmax, 0, Fraction(0)
    else:
        b0 = int(rng.integers(0, bmax + 1))
        gam = int(rng.integers(0, 3))
        eta = Fraction(int(rng.integers(0, 4)), 4)
    model = int(rng.integers(0, 3))
    sorder = int(rng.integers(0, 2))
    return dict(k=k, n=n, L=L, delta=delta, a=a.astype(np.int64), C=C.astype(np.int64),
                key=key, d=d.astype(np.int64), bmax=bmax, b0=b0, gam=gam, eta=eta,
                model=model, sorder=sorder)


def run_ref(x):
    w, _ = ref.make_work_nb(x["n"], x["k"])
    ref.sim_guard(x["k"], x["a"], x["C"], x["key"], float(x["b0"]), float(x["gam"]),
                  float(x["eta"]), x["bmax"], REF_MODEL[x["model"]], x["d"], x["sorder"],
                  ref.INF, w)
    start, srv, seq, appg, app2 = w[0], w[2], w[3], w[10], w[11]
    rec = app2 if x["model"] == MODEL_A2 else appg[None, :]
    return start.copy(), srv.copy(), seq.copy(), rec.copy()


def run_mine(x, mslots):
    ek = x["eta"] * x["k"]
    out = simulate_delay(x["a"], x["C"], x["key"], x["k"], MODE_GUARD, x["b0"],
                         ek.numerator, ek.denominator, x["bmax"], mslots, x["gam"],
                         x["model"], x["d"], x["sorder"], True)
    wait, disp, start, srv, *_rest, nreb, _span, err, rec = out
    return start, srv, disp, rec, err, nreb, wait


def main():
    nrun = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261018
    rng = np.random.default_rng(seed)
    t0 = time.time()
    tally = {m: {"instances": 0, "delta_pos": 0, "compared": 0, "skipped_err": 0,
                 "with_rebuild": 0, "mismatch": 0, "charges_compared": 0}
             for m in ("U", "A1", "A2")}
    prod = {"compared": 0, "mismatch": 0}
    first_bad = []
    for _ in range(nrun):
        x = instance(rng)
        name = ("U", "A1", "A2")[x["model"]]
        tl = tally[name]
        tl["instances"] += 1
        tl["delta_pos"] += int(x["delta"] > 0)
        r_start, r_srv, r_seq, r_rec = run_ref(x)
        for mslots in (64, 16, 8):
            start, srv, disp, rec, err, nreb, wait = run_mine(x, mslots)
            if err:
                tl["skipped_err"] += 1
                continue
            tl["compared"] += 1
            tl["with_rebuild"] += int(nreb > 0)
            tl["charges_compared"] += int((r_rec >= 0).sum())
            ok = (np.array_equal(start, r_start) and np.array_equal(srv, r_srv)
                  and np.array_equal(disp, r_seq) and np.array_equal(rec, r_rec))
            if not ok:
                tl["mismatch"] += 1
                if len(first_bad) < 5:
                    first_bad.append({k: (v.tolist() if isinstance(v, np.ndarray) else str(v))
                                      for k, v in x.items()} | {"mslots": mslots})
            if x["delta"] == 0 and mslots == 64 and x["sorder"] == 0:
                ek = x["eta"] * x["k"]
                p = simulate_kernel(x["a"], x["C"], x["key"], x["k"], 2, x["b0"], ek.numerator,
                                    ek.denominator, x["bmax"], 0, mslots, x["gam"])
                prod["compared"] += 1
                if not (np.array_equal(p[0], wait) and np.array_equal(p[1], disp)):
                    prod["mismatch"] += 1
    total = sum(t["mismatch"] for t in tally.values()) + prod["mismatch"]
    report = {"instances": nrun, "seed": seed, "by_model": tally,
              "delta0_vs_production_kernel": prod, "total_mismatches": total,
              "first_mismatches": first_bad, "seconds": round(time.time() - t0, 1)}
    _setup.OUT.mkdir(parents=True, exist_ok=True)
    (_setup.OUT / "gate1_check_reference.json").write_text(json.dumps(report, indent=1))
    for m, t in tally.items():
        print(f"  {m}: {t}")
    print(f"  delta=0 vs production kernel: {prod}")
    print(f"GATE1 instances {nrun} total_mismatches {total} ({report['seconds']} s)")
    if total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
