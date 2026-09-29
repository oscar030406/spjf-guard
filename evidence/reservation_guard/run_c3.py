"""C3.  Positioning: with enforced caps the promise is denominated in the caps
of the admitted overtakers, not in the global L.

Two cap classes: a short class with cap ell (sizes <= ell) and a long class with
cap L.  Only short-class jobs are ever proposed out of turn, so every overtaker
comes from the short class.  Designed worst-case family plus a random search,
for k = 1, 2, 4, at a fixed allowance B.

Designed family: k long victims of size L at t = 0 (ranks 0..k-1) followed by a
stream of short jobs of size ell; the base policy always prefers the shorts.
Predicted maximum In of the rank-0 victim:
    rule R  In = ell * floor(B/ell)                      <= B
    rule C  In = ell * (floor((B-1)/ell) + 1) + (k-1)*ell if B >= 1
            (the completed-work rule admits one more short per server, the
             overshoot term, which is k*ell here and k*L in the uniform bound)

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-project --with numpy python run_c3.py
"""
import sys
from fractions import Fraction

import numpy as np

sys.dont_write_bytecode = True
import rguard  # noqa: E402
import sim_core  # noqa: E402


def prefer_short(nlong):
    def f(t, waiting, state):
        for c, q in enumerate(waiting):
            if q >= nlong:
                return c
        return 0
    return f


def family(k, L, ell, B, nshort):
    jobs = [(0, L)] * k + [(0, ell)] * nshort
    caps = [L] * k + [ell] * nshort
    base = prefer_short(k)
    out = {}
    for rule, wrap in (('R', rguard.make_rguard(base, B, caps)),
                       ('C', rguard.make_cguard(base, B))):
        sP, oP, _ = sim_core.simulate(jobs, k, wrap)
        In, Out, W, WF, exc = rguard.metrics(jobs, k, oP, sP)
        out[rule] = (max(In), max(exc))
    return out


def randsearch(k, L, ell, B, trials, rng):
    best = {'R': (0, 0), 'C': (0, 0)}
    n = 9
    for _ in range(trials):
        nlong = int(rng.integers(1, 4))
        a = np.sort(rng.integers(0, 2 * L, size=n)).tolist()
        x = []
        caps = []
        for i in range(n):
            if i < nlong:
                x.append(int(rng.integers(1, L + 1)))
                caps.append(L)
            else:
                x.append(int(rng.integers(1, ell + 1)))
                caps.append(ell)
        jobs = list(zip(a, x))
        base = prefer_short(nlong)
        for rule, wrap in (('R', rguard.make_rguard(base, B, caps)),
                           ('C', rguard.make_cguard(base, B))):
            sP, oP, _ = sim_core.simulate(jobs, k, wrap)
            In, Out, W, WF, exc = rguard.metrics(jobs, k, oP, sP)
            best[rule] = (max(best[rule][0], max(In)),
                          max(best[rule][1], max(exc)))
    return best


def main():
    L = 12
    B = 10
    rng = np.random.default_rng(20260923)
    print("=" * 78)
    print("C3  two cap classes, L = %d, allowance B = %d, only short-class "
          "jobs overtake" % (L, B))
    print("=" * 78)
    for k in (1, 2, 4):
        print()
        print("k = %d   uniform bounds: rule R  k*exc <= B+(2k-2)L = %d ;  "
              "rule C  k*exc < B+(3k-2)L = %d"
              % (k, B + (2 * k - 2) * L, B + (3 * k - 2) * L))
        print("  %-6s %-22s %-22s %-22s %s"
              % ("ell", "family In (R / C)", "family exc (R / C)",
                 "random In (R / C)", "pred In (R / C)"))
        for ell in (1, 2, 3, 4, 6, 12):
            fam = family(k, L, ell, B, nshort=6 * k + 8)
            rnd = randsearch(k, L, ell, B, 400, rng)
            pr = ell * (B // ell)
            pc = ell * ((B - 1) // ell + 1) + (k - 1) * ell if B >= 1 else 0
            print("  %-6d %-22s %-22s %-22s %s"
                  % (ell,
                     "%d / %d" % (fam['R'][0], fam['C'][0]),
                     "%s / %s" % (Fraction(fam['R'][1]),
                                  Fraction(fam['C'][1])),
                     "%d / %d" % (rnd['R'][0], rnd['C'][0]),
                     "%d / %d" % (pr, pc)))
    print()
    print("Reading: rule R's In never exceeds B for any cap profile, so its "
          "promise at k=1 is B and never mentions L.")
    print("Rule C's In exceeds B by up to k*ell on the same instances; the "
          "L-scale term of the published bound is the ell = L corner.")


if __name__ == "__main__":
    main()
