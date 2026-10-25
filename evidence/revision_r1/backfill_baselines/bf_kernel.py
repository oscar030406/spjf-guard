"""Conservative and slack-based backfilling on the paper's model, in int64 microseconds.

k identical servers, every job has width 1, non-preemptive.  Each job j carries a runtime
estimate est[j] (the limit L for every job, or the stored SPJF-E prediction clipped to
[1 us, L]).  The rules are those of evidence/llm_batching/backfill/backfill.py with M = k
and w = 1, event-driven instead of stepping one time unit:

  instant t:  1. completions, in job-index order; an early one (s + est > t) drops the
                 rest of its estimate and triggers the rule's compression;
              2. overruns (job still running at s + est < s + actual), in job-index
                 order: the estimate becomes L (Tsafrir, Etsion, Feitelson 2007) and the
                 waiting jobs are re-placed (see repair below); never happens when
                 est = L, because every service time is at most L;
              3. arrivals, in index order, each inserted by the rule;
              4. every waiting job whose scheduled time is t starts, in arrival order.

  CBF   insert: earliest fit from t.  compress: every waiting job, in arrival order, is
        removed and re-inserted at its earliest fit from t, the others staying in place.
  SLACK insert(j): candidates ts in sorted({t, anchor}) ("now+anchor" of backfill.py).
        For each: delay every waiting job with te >= ts by est[j], put j at ts (skip if
        it does not fit), compress the delayed jobs in ascending (te, index), price
            (ts - t) + sum_i d_i G / s_i   (infinite if some d_i > s_i; -inf class when a
                                            moved job has s_i = 0)
        and keep the smallest (class, price, moved, ts).  Then s_i -= d_i; j gets te0 = ts
        and slack G.  remove (early completion): the same with no job and ts = t only.
        The price is summed in float64 and prices within 1e-9 relative count as equal;
        such ties with a non-integer term are counted (C_NEARTIE).

  repair after an overrun (only with predicted estimates; no reference rule exists):
        CBF: the CBF compression.  SLACK: compression in ascending (te, index) with no
        pricing; s_i = max(s_i - d_i, 0).
  Earliest fit is computed without an upper bound.  Whenever the current place is
  feasible it returns the same point as backfill.py's bounded search.

The profile is a sorted breakpoint list T[h:P] with usage U on [T[i], T[i+1]); adjacent
equal usages are merged, the last segment has usage 0.
"""

from __future__ import annotations

import numpy as np
from numba import njit

RULE_CBF = 0
RULE_SLACK = 1

C_ERR = 0
C_OVERRUN = 1
C_FALLBACK = 2
C_NEARTIE = 3
C_MAXP = 4
C_MAXW = 5
C_MOVES = 6
C_NOWTRIALS = 7
C_INSTANTS = 8
C_COMPRESS = 9
C_LEN = 10

ERR_PROFILE_FULL = 1
ERR_NO_SERVER = 2
ERR_PAST_RESERVATION = 3
ERR_NO_CANDIDATE = 4

NEG_INF_T = -(np.int64(1) << 62)
POS_INF_T = np.int64(1) << 62


# --------------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _seg(T, h, P, x):
    lo = h
    hi = P - 1
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if T[mid] <= x:
            lo = mid
        else:
            hi = mid - 1
    return lo


@njit(cache=True)
def _ensure(T, U, pm, x):
    h = pm[0]
    P = pm[1]
    i = _seg(T, h, P, x)
    if T[i] == x:
        return i
    for q in range(P, i + 1, -1):
        T[q] = T[q - 1]
        U[q] = U[q - 1]
    T[i + 1] = x
    U[i + 1] = U[i]
    pm[1] = P + 1
    return i + 1


@njit(cache=True)
def _drop(T, U, pm, i):
    P = pm[1]
    for q in range(i, P - 1):
        T[q] = T[q + 1]
        U[q] = U[q + 1]
    pm[1] = P - 1


@njit(cache=True)
def _add(T, U, pm, x, e, delta, cnt):
    """usage += delta on [x, e); x >= T[h]."""
    if pm[1] + 2 >= T.shape[0]:
        h = pm[0]
        if h == 0:
            cnt[C_ERR] = ERR_PROFILE_FULL
            return
        P = pm[1]
        for q in range(h, P):
            T[q - h] = T[q]
            U[q - h] = U[q]
        pm[0] = 0
        pm[1] = P - h
    ix = _ensure(T, U, pm, x)
    ie = _ensure(T, U, pm, e)
    for q in range(ix, ie):
        U[q] += delta
    if U[ie] == U[ie - 1]:
        _drop(T, U, pm, ie)
    if ix > pm[0] and U[ix] == U[ix - 1]:
        _drop(T, U, pm, ix)
    if pm[1] - pm[0] > cnt[C_MAXP]:
        cnt[C_MAXP] = pm[1] - pm[0]


@njit(cache=True)
def _earliest(T, U, pm, x, d, k):
    """Smallest y >= x with usage < k on all of [y, y + d)."""
    P = pm[1]
    j = _seg(T, pm[0], P, x)
    while True:
        q = j
        hit = -1
        while q < P and T[q] < x + d:
            if U[q] >= k:
                hit = q
                break
            q += 1
        if hit < 0:
            return x
        x = T[hit + 1]
        j = hit + 1


@njit(cache=True)
def _fits(T, U, pm, x, d, k):
    P = pm[1]
    q = _seg(T, pm[0], P, x)
    while q < P and T[q] < x + d:
        if U[q] >= k:
            return False
        q += 1
    return True


@njit(cache=True)
def _copy_profile(T, U, pm, T2, U2, pm2):
    h = pm[0]
    P = pm[1]
    for q in range(h, P):
        T2[q - h] = T[q]
        U2[q - h] = U[q]
    pm2[0] = 0
    pm2[1] = P - h


# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #
@njit(cache=True)
def _cbf_compress(t, T, U, pm, wl, wh, wt, state, te, est, k, cnt):
    cnt[C_COMPRESS] += 1
    for p in range(wh, wt):
        j = wl[p]
        if state[j] != 1:
            continue
        x = te[j]
        e = est[j]
        _add(T, U, pm, x, x + e, -1, cnt)
        y = _earliest(T, U, pm, t, e, k)
        _add(T, U, pm, y, y + e, 1, cnt)
        if y != x:
            cnt[C_MOVES] += 1
        te[j] = y


@njit(cache=True)
def _sorted_waiting(wl, wh, wt, state, te, buf_idx, buf_te):
    """Waiting jobs sorted by (te, index); returns their count."""
    m = 0
    for p in range(wh, wt):
        j = wl[p]
        if state[j] == 1:
            buf_idx[m] = j
            buf_te[m] = te[j]
            m += 1
    if m > 1:
        order = np.argsort(buf_te[:m], kind="mergesort")
        tmp = buf_idx[:m].copy()
        for q in range(m):
            buf_idx[q] = tmp[order[q]]
            buf_te[q] = te[buf_idx[q]]
    return m


@njit(cache=True)
def _slack_repair(t, T, U, pm, m, buf_idx, te, sl, est, k, cnt):
    for q in range(m):
        i = buf_idx[q]
        x = te[i]
        e = est[i]
        _add(T, U, pm, x, x + e, -1, cnt)
        y = _earliest(T, U, pm, t, e, k)
        _add(T, U, pm, y, y + e, 1, cnt)
        if y != x:
            cnt[C_MOVES] += 1
        s = sl[i] - (y - x)
        sl[i] = s if s > 0 else 0
        te[i] = y


@njit(cache=True)
def _slack_trial(
    t, ts, j, T, U, pm, Tb, Ub, pmb, posb, m, first, buf_idx, te, sl, est, k, G, cnt
):
    """Fill buffer (Tb, Ub, pmb, posb) for candidate ts.  Returns (ok, cls, val, moved, inexact)."""
    _copy_profile(T, U, pm, Tb, Ub, pmb)
    shift = est[j] if j >= 0 else 0
    if shift > 0:
        for q in range(first, m):
            i = buf_idx[q]
            x = te[i]
            _add(Tb, Ub, pmb, x, x + est[i], -1, cnt)
            _add(Tb, Ub, pmb, x + shift, x + shift + est[i], 1, cnt)
    if j >= 0:
        if not _fits(Tb, Ub, pmb, ts, est[j], k):
            return False, 1, 0.0, 0, False
        _add(Tb, Ub, pmb, ts, ts + est[j], 1, cnt)
    for q in range(first, m):
        i = buf_idx[q]
        x = te[i] + shift
        e = est[i]
        _add(Tb, Ub, pmb, x, x + e, -1, cnt)
        y = _earliest(Tb, Ub, pmb, t, e, k)
        _add(Tb, Ub, pmb, y, y + e, 1, cnt)
        posb[q] = y
    val = float(ts - t) if j >= 0 else 0.0
    neg = False
    moved = 0
    inexact = False
    for q in range(first, m):
        i = buf_idx[q]
        d = posb[q] - te[i]
        if d == 0:
            continue
        if d > sl[i]:
            return False, 1, 0.0, 0, False
        moved += 1
        if sl[i] == 0:
            neg = True
        else:
            val += float(d) * float(G) / float(sl[i])
            ad = d if d > 0 else -d
            if ad < 7000000000 and G < 1300000000:
                if (d * G) % sl[i] != 0:
                    inexact = True
            else:
                inexact = True
    if neg:
        return True, 0, 0.0, moved, False
    return True, 1, val, moved, inexact


@njit(cache=True)
def _same_price(v1, v2):
    """Float prices within 1e-9 relative are a tie: exact rational ties (backfill.py sums
    Fractions) land there after rounding."""
    scale = max(1.0, abs(v1), abs(v2))
    return abs(v1 - v2) <= 1e-9 * scale


@njit(cache=True)
def _key_less(c1, v1, m1, t1, c2, v2, m2, t2):
    if c1 != c2:
        return c1 < c2
    if not _same_price(v1, v2):
        return v1 < v2
    if m1 != m2:
        return m1 < m2
    return t1 < t2


@njit(cache=True)
def _slack_schedule(
    t, j, nrun, T, U, pm, Tbuf, Ubuf, pmbuf, posbuf, wl, wh, wt, state, te, te0, sl,
    est, k, G, buf_idx, buf_te, cnt
):
    m = _sorted_waiting(wl, wh, wt, state, te, buf_idx, buf_te)
    if j >= 0:
        anchor = _earliest(T, U, pm, t, est[j], k)
        nc = 1 if anchor == t else 2
    else:
        anchor = t
        nc = 1
    best = -1
    bc = 0
    bv = 0.0
    bm = 0
    bts = np.int64(0)
    bfirst = 0
    binexact = False
    slot = 0
    for c in range(nc):
        ts = t if c == 0 else anchor
        if j >= 0 and ts == t and anchor != t:
            # j fits at t only if a server is free over [t, t + est_j) once every waiting
            # job is delayed past t + est_j; that usage is the running jobs alone.
            if nrun >= k:
                continue
            cnt[C_NOWTRIALS] += 1
        # delayed jobs: te >= ts (suffix of the sorted list)
        first = 0
        while first < m and buf_te[first] < ts:
            first += 1
        ok, cls, val, moved, inexact = _slack_trial(
            t, ts, j, T, U, pm, Tbuf[slot], Ubuf[slot], pmbuf[slot], posbuf[slot], m,
            first, buf_idx, te, sl, est, k, G, cnt,
        )
        if not ok:
            continue
        if best >= 0 and cls == 1 and bc == 1 and _same_price(val, bv):
            if val != bv or inexact or binexact:
                cnt[C_NEARTIE] += 1
        if best < 0 or _key_less(cls, val, moved, ts, bc, bv, bm, bts):
            best = slot
            bc = cls
            bv = val
            bm = moved
            bts = ts
            bfirst = first
            binexact = inexact
            slot = 1 - slot
    if best < 0:
        if j < 0:
            cnt[C_ERR] = ERR_NO_CANDIDATE
            return
        cnt[C_FALLBACK] += 1
        _add(T, U, pm, anchor, anchor + est[j], 1, cnt)
        te[j] = anchor
        te0[j] = anchor
        sl[j] = G
        return
    _copy_profile(Tbuf[best], Ubuf[best], pmbuf[best], T, U, pm)
    pb = posbuf[best]
    for q in range(bfirst, m):
        i = buf_idx[q]
        y = pb[q]
        if y != te[i]:
            cnt[C_MOVES] += 1
            sl[i] -= y - te[i]
            te[i] = y
    if j >= 0:
        te[j] = bts
        te0[j] = bts
        sl[j] = G


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
@njit(cache=True)
def simulate_backfill(a_us, s_us, est_us, k, rule, G_us, L_us, prof_cap):
    """Returns (start_us, promise_us, cnt).  promise = reservation at arrival (CBF) or
    scheduled time at insertion + G (SLACK).  cnt[C_ERR] != 0 invalidates the run."""
    n = a_us.shape[0]
    start = np.full(n, -1, np.int64)
    promise = np.zeros(n, np.int64)
    te = np.zeros(n, np.int64)
    te0 = np.zeros(n, np.int64)
    sl = np.zeros(n, np.int64)
    est = est_us.copy()
    state = np.zeros(n, np.uint8)
    wl = np.empty(n, np.int64)
    wh = 0
    wt = 0
    live = 0
    cnt = np.zeros(C_LEN, np.int64)

    T = np.empty(prof_cap, np.int64)
    U = np.empty(prof_cap, np.int64)
    pm = np.zeros(2, np.int64)
    T[0] = NEG_INF_T
    U[0] = 0
    pm[0] = 0
    pm[1] = 1
    slack = rule == RULE_SLACK
    bc = prof_cap if slack else 1
    Tbuf = np.empty((2, bc), np.int64)
    Ubuf = np.empty((2, bc), np.int64)
    pmbuf = np.zeros((2, 2), np.int64)
    pcap = n if slack else 1
    posbuf = np.empty((2, pcap), np.int64)
    buf_idx = np.empty(n, np.int64)
    buf_te = np.empty(n, np.int64)

    rj = np.empty(k, np.int64)
    rs = np.empty(k, np.int64)
    rend = np.empty(k, np.int64)
    rest = np.empty(k, np.int64)
    nrun = 0
    ev = np.empty(k, np.int64)

    nxt = 0
    nstarted = 0
    t = a_us[0]
    while nstarted < n:
        cnt[C_INSTANTS] += 1
        while pm[0] + 1 < pm[1] and T[pm[0] + 1] <= t:
            pm[0] += 1
        # 1. completions, in job-index order
        ne = 0
        for r in range(nrun):
            if rend[r] == t:
                ev[ne] = rj[r]
                ne += 1
        for a in range(1, ne):
            v = ev[a]
            b = a - 1
            while b >= 0 and ev[b] > v:
                ev[b + 1] = ev[b]
                b -= 1
            ev[b + 1] = v
        for q in range(ne):
            jj = ev[q]
            r = 0
            while rj[r] != jj:
                r += 1
            ee = rest[r]
            nrun -= 1
            rj[r] = rj[nrun]
            rs[r] = rs[nrun]
            rend[r] = rend[nrun]
            rest[r] = rest[nrun]
            if ee > t:
                _add(T, U, pm, t, ee, -1, cnt)
                if slack:
                    _slack_schedule(
                        t, -1, nrun, T, U, pm, Tbuf, Ubuf, pmbuf, posbuf, wl, wh, wt,
                        state, te, te0, sl, est, k, G_us, buf_idx, buf_te, cnt,
                    )
                else:
                    _cbf_compress(t, T, U, pm, wl, wh, wt, state, te, est, k, cnt)
        # 2. overruns, in job-index order
        ne = 0
        for r in range(nrun):
            if rest[r] == t and rend[r] > t:
                ev[ne] = rj[r]
                ne += 1
        for a in range(1, ne):
            v = ev[a]
            b = a - 1
            while b >= 0 and ev[b] > v:
                ev[b + 1] = ev[b]
                b -= 1
            ev[b + 1] = v
        for q in range(ne):
            jj = ev[q]
            r = 0
            while rj[r] != jj:
                r += 1
            cnt[C_OVERRUN] += 1
            newend = rs[r] + L_us
            _add(T, U, pm, t, newend, 1, cnt)
            rest[r] = newend
            est[jj] = L_us
            if slack:
                m = _sorted_waiting(wl, wh, wt, state, te, buf_idx, buf_te)
                _slack_repair(t, T, U, pm, m, buf_idx, te, sl, est, k, cnt)
            else:
                _cbf_compress(t, T, U, pm, wl, wh, wt, state, te, est, k, cnt)
        # 3. arrivals
        while nxt < n and a_us[nxt] <= t:
            j = nxt
            nxt += 1
            wl[wt] = j
            wt += 1
            live += 1
            if slack:
                _slack_schedule(
                    t, j, nrun, T, U, pm, Tbuf, Ubuf, pmbuf, posbuf, wl, wh, wt, state,
                    te, te0, sl, est, k, G_us, buf_idx, buf_te, cnt,
                )
                state[j] = 1
                promise[j] = te0[j] + G_us
            else:
                y = _earliest(T, U, pm, t, est[j], k)
                _add(T, U, pm, y, y + est[j], 1, cnt)
                te[j] = y
                state[j] = 1
                promise[j] = y
        if live > cnt[C_MAXW]:
            cnt[C_MAXW] = live
        if cnt[C_ERR] != 0:
            break
        # 4. starts, in arrival order; next scheduled time of the rest
        mint = POS_INF_T
        for p in range(wh, wt):
            j = wl[p]
            if state[j] != 1:
                continue
            x = te[j]
            if x == t:
                if nrun >= k:
                    cnt[C_ERR] = ERR_NO_SERVER
                    break
                state[j] = 2
                live -= 1
                nstarted += 1
                start[j] = t
                rj[nrun] = j
                rs[nrun] = t
                rend[nrun] = t + s_us[j]
                rest[nrun] = t + est[j]
                nrun += 1
            elif x < t:
                cnt[C_ERR] = ERR_PAST_RESERVATION
                break
            elif x < mint:
                mint = x
        if cnt[C_ERR] != 0:
            break
        while wh < wt and state[wl[wh]] != 1:
            wh += 1
        if wt - wh > 2 * live + 1024:
            w2 = wh
            for p in range(wh, wt):
                if state[wl[p]] == 1:
                    wl[w2] = wl[p]
                    w2 += 1
            wt = w2
        # next instant
        nt = mint
        if nxt < n and a_us[nxt] < nt:
            nt = a_us[nxt]
        for r in range(nrun):
            x = rend[r] if rend[r] <= rest[r] else rest[r]
            if x < nt:
                nt = x
        if nt >= POS_INF_T:
            break
        t = nt
    return start, promise, cnt
