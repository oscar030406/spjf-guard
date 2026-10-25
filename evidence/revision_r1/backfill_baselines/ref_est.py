"""Brute-force reference for bf_kernel.py with per-job runtime estimates (unit widths).

Extends evidence/llm_batching/backfill/backfill_ref.py in the same style (a dict of
intervals, usage summed on every query, earliest fit tried point by point) to
  - a per-job estimate est[j] instead of one D (slack shifts by the inserted job's est);
  - overrun: a job still running at s + est gets estimate L; then CBF re-runs its
    compression and SLACK re-places every waiting job in ascending (te, index) at its
    earliest fit with slack max(s - delay, 0);
  - earliest fit without an upper bound;
  - SLACK insert falls back to plain insertion at the anchor when no candidate is
    feasible (counted in .fallbacks).
With est[j] = D for every j and L = D it is backfill_ref.py's rules with M = k, w = 1.
Driven by check_prefix_refund.run (integer time).  Small instances only.
"""
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evidence" / "llm_batching"))
from check_prefix_refund import Observer  # noqa: E402


class CBFEst(Observer):
    def __init__(self, est, k, L):
        super().__init__()
        self.est, self.k, self.L = list(est), k, L
        self.iv = {}
        self.te, self.r0 = {}, {}
        self.overruns = 0

    def usage(self, u, iv):
        return sum(1 for x, e in iv.values() if x <= u < e)

    def fits(self, x, d, iv):
        return all(self.usage(u, iv) + 1 <= self.k for u in range(x, x + d))

    def earliest(self, t, d, iv):
        x = t
        while not self.fits(x, d, iv):
            x += 1
        return x

    def observe(self, t, alive):
        alive = set(alive)
        for j in sorted(self.alive - alive):
            self.d[j] = t - self.s[j]
            self.alive.discard(j)
            del self.iv[j]
            if self.s[j] + self.est[j] > t:
                self.on_early(t)
        for j in sorted(self.alive):
            if self.s[j] + self.est[j] == t:
                self.overruns += 1
                self.est[j] = self.L
                self.iv[j] = (self.s[j], self.s[j] + self.L)
                self.on_overrun(t)

    def compress(self, t):
        for j in sorted(self.te):
            del self.iv[j]
            self.te[j] = self.earliest(t, self.est[j], self.iv)
            self.iv[j] = (self.te[j], self.te[j] + self.est[j])

    def on_early(self, t):
        self.compress(t)

    def on_overrun(self, t):
        self.compress(t)

    def on_arrival(self, t, j):
        self.te[j] = self.r0[j] = self.earliest(t, self.est[j], self.iv)
        self.iv[j] = (self.te[j], self.te[j] + self.est[j])

    def choose(self, t, waiting, free, reqs, running):
        for j in waiting:
            if j not in self.te:
                self.on_arrival(t, j)
        for j in waiting:
            if self.te[j] == t:
                del self.te[j]
                self.admitted(t, j)
                return j
        return None


class SlackEst(CBFEst):
    def __init__(self, est, k, L, G):
        super().__init__(est, k, L)
        self.G = G
        self.sl, self.te0 = {}, {}
        self.fallbacks = 0

    def try_slot(self, t, ts, j):
        iv = dict(self.iv)
        delayed = sorted((self.te[i], i) for i in self.te if self.te[i] >= ts)
        if j is not None:
            sh = self.est[j]
            for x, i in delayed:
                iv[i] = (x + sh, x + sh + self.est[i])
            if not self.fits(ts, self.est[j], iv):
                return None
            iv[j] = (ts, ts + self.est[j])
        new = {}
        for _, i in delayed:
            del iv[i]
            new[i] = self.earliest(t, self.est[i], iv)
            iv[i] = (new[i], new[i] + self.est[i])
        total = Fraction(0 if j is None else ts - t)
        neg, moved = False, 0
        for i in new:
            delay = new[i] - self.te[i]
            if delay > self.sl[i]:
                return None
            if delay != 0:
                moved += 1
                if self.sl[i] > 0:
                    total += Fraction(delay * self.G, self.sl[i])
                else:
                    neg = True
        key = (0, 0, moved, ts) if neg else (1, total, moved, ts)
        return key, iv, new

    def pick(self, t, j, candidates):
        options = [o for o in (self.try_slot(t, ts, j) for ts in candidates) if o is not None]
        if not options:
            assert j is not None
            self.fallbacks += 1
            x = candidates[-1]
            self.iv[j] = (x, x + self.est[j])
            self.te[j] = self.te0[j] = x
            self.sl[j] = self.G
            return
        key, iv, new = min(options, key=lambda o: o[0])
        self.iv = iv
        for i in new:
            self.sl[i] -= new[i] - self.te[i]
            self.te[i] = new[i]
        if j is not None:
            self.te[j] = self.te0[j] = key[3]
            self.sl[j] = self.G

    def on_early(self, t):
        self.pick(t, None, [t])

    def on_overrun(self, t):
        for _, i in sorted((self.te[i], i) for i in self.te):
            del self.iv[i]
            y = self.earliest(t, self.est[i], self.iv)
            self.sl[i] = max(self.sl[i] - (y - self.te[i]), 0)
            self.te[i] = y
            self.iv[i] = (y, y + self.est[i])

    def on_arrival(self, t, j):
        anchor = self.earliest(t, self.est[j], self.iv)
        self.pick(t, j, sorted({t, anchor}))
