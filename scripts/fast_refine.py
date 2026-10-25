"""A compiled `M4HistoryRecomputer.recompute_visible` for the online replay, bit for bit.

Not wired into any run yet (2026-09-29).  The replay pauses at every job whose own-copy
history changed and rebuilds its M4 row; a 20,000-pause capture of a level-0 validation
cell showed about 7,000 history rows per call (median 4,634 in the exercise group) and
about 460 us per call in numpy, two thirds of a candidate's run.  This version returns
the same float32 bits on all 20,000 calls in 175-210 us (runs on a loaded machine), so a
candidate would run about 1.3 times as fast; too little to change the protocol's code path during the revision.
What was tried and did not move that, measured on saved inputs: copying each group's
fields into group order (sequential reads), forcing the per-row helpers inline, a reused
workspace instead of per-call arrays, and branchless compaction.  Reading the same rows
with no logic takes 11 us, so the remaining cost is in the per-row work, not in memory.

How it keeps the bits:
- each group's external history is already in `_by_release` order (release, zero lag,
  row), because `_grouped` sorted it that way, so only the own-copy rows are sorted
  (three stable sorts, lexsort's semantics) and then merged in;
- the pair and event groups only feed `_latest`, which needs no order;
- `np.cumsum(x)[-1]` is a left-to-right sum, and `x.mean()` is numpy's pairwise sum over
  the whole array divided by its length (`_pairwise`, `_mean`);
- Python's `max(var, 0.0)` keeps -0.0 and nan, and so does `_summary`.

`src/` is not touched (it is locked by protocol_lock.json and hashed into the replay's
checkpoint signature).  A runner that used this would hand it to `replay_online` only, so
that `audit_online` keeps checking against the original implementation.
"""

from __future__ import annotations

import numpy as np
from numba import njit

# No cache=True: loading this module's cached code crashed with an access violation on its
# first call (2026-09-29, twice), while a fresh compile of the same code passed 20,000
# captured calls under NUMBA_BOUNDSCHECK=1.  Compiling costs each process a few seconds.

_ROLLING = 120  # spjf_guard.features.refine._ROLLING
_NAN = np.nan
_BLOCK = 128  # numpy's PW_BLOCKSIZE


@njit
def _pairwise(a, start, n):
    """numpy's pairwise_sum over a[start:start+n] (umath loops_utils, PW_BLOCKSIZE 128)."""
    if n < 8:
        res = -0.0
        for i in range(n):
            res += a[start + i]
        return res
    if n <= _BLOCK:
        r0 = a[start]
        r1 = a[start + 1]
        r2 = a[start + 2]
        r3 = a[start + 3]
        r4 = a[start + 4]
        r5 = a[start + 5]
        r6 = a[start + 6]
        r7 = a[start + 7]
        i = 8
        stop = n - n % 8
        while i < stop:
            r0 += a[start + i]
            r1 += a[start + i + 1]
            r2 += a[start + i + 2]
            r3 += a[start + i + 3]
            r4 += a[start + i + 4]
            r5 += a[start + i + 5]
            r6 += a[start + i + 6]
            r7 += a[start + i + 7]
            i += 8
        res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7))
        while i < n:
            res += a[start + i]
            i += 1
        return res
    n2 = n // 2
    n2 -= n2 % 8
    return _pairwise(a, start, n2) + _pairwise(a, start + n2, n - n2)


@njit
def _mean(a):
    """`a.mean()` for a contiguous float64 array: the pairwise sum of all of it over its
    length (numpy 2.5.3; seeding with a[0] matched only 699 of 2,020 random arrays)."""
    return _pairwise(a, 0, len(a)) / len(a)


@njit
def _visible(rows, offsets, key, now, availability, arrival):
    """`_GroupedRows.before`: the group's rows available by `now`, less those that arrived
    and became available exactly at `now` (zero lag at the read)."""
    if key < 0 or key + 1 >= len(offsets):
        return np.empty(0, np.int64)
    lo = offsets[key]
    a, b = lo, offsets[key + 1]  # searchsorted(availability[group], now, side="right")
    while a < b:
        mid = (a + b) // 2
        if availability[rows[mid]] <= now:
            a = mid + 1
        else:
            b = mid
    out = np.empty(a - lo, np.int64)
    k = 0
    for i in range(lo, a):
        r = rows[i]
        if not (availability[r] == now and arrival[r] == now):
            out[k] = r
            k += 1
    return out[:k]


@njit
def _external(events, row_of, simulatable, class_term, own_class):
    """Mask of events outside the target's own replayed class-term (`not _own_copy`)."""
    keep = np.empty(len(events), np.bool_)
    for i in range(len(events)):
        e = events[i]
        s = row_of[e]
        keep[i] = not (s >= 0 and simulatable[s] and class_term[e] == own_class)
    return keep


@njit
def _precedes(r1, z1, i1, r2, z2, i2):
    """(release, zero lag, row) order of `_by_release`'s lexsort; False sorts first."""
    if r1 != r2:
        return r1 < r2
    if z1 != z2:
        return z2
    return i1 < i2


@njit
def _ordered(external, own, own_release, release, arrival):
    """`_by_release(np.r_[external, own], np.r_[release[external], own_release], arrival)`:
    `external` is already in that order, so sort the own rows and merge the two."""
    m = len(own)
    order = np.argsort(own, kind="mergesort")  # lexsort as three stable sorts
    order = order[np.argsort(own_release[order] == arrival[own[order]], kind="mergesort")]
    order = order[np.argsort(own_release[order], kind="mergesort")]
    out = np.empty(len(external) + m, np.int64)
    a = b = k = 0
    while a < len(external) or b < m:
        if b == m:
            first = True
        elif a == len(external):
            first = False
        else:
            e, o = external[a], order[b]
            first = _precedes(release[e], release[e] == arrival[e], e,
                              own_release[o], own_release[o] == arrival[own[o]], own[o])
        if first:
            out[k] = external[a]
            a += 1
        else:
            out[k] = own[order[b]]
            b += 1
        k += 1
    return out


@njit
def _summary(values, errors, heavy, out, at):
    """`refine._summary` into out[at:at+6] (mean, sd, p50 and p90 of the last 120, error
    and heavy rates); returns the max of the last 120 for the exercise summary."""
    count = len(values)
    if count == 0:
        for j in range(6):
            out[at + j] = _NAN
        return _NAN
    total = 0.0
    squares = 0.0
    for v in values:  # np.cumsum(...)[-1]: left to right
        total += v
        squares += v * v
    mean = total / count
    var = squares / count - mean * mean
    var = 0.0 if 0.0 > var else var  # Python's max(var, 0.0): keeps -0.0 and nan
    tail = np.sort(values[max(0, count - _ROLLING):])
    last = len(tail) - 1
    out[at] = mean
    out[at + 1] = np.sqrt(var)
    out[at + 2] = tail[min(last, int(0.5 * last + 0.5))]
    out[at + 3] = tail[min(last, int(0.9 * last + 0.5))]
    out[at + 4] = _mean(errors)
    out[at + 5] = _mean(heavy)
    return np.max(values[max(0, count - _ROLLING):])


@njit
def _latest(rows, arrival):
    """`refine._latest`: the latest arrival, ties to the largest row; -1 when empty."""
    best = -1
    for r in rows:
        if best < 0 or arrival[r] > arrival[best] or (arrival[r] == arrival[best] and r > best):
            best = r
    return best


@njit
def _recompute(
    target, baseline, own_rows, own_release, pair_code,
    ex_rows, ex_off, us_rows, us_off, pr_rows, pr_off, ev_rows, ev_off,
    sub_arrival, sub_availability, arrival, availability, submission_events,
    sub_exercise, sub_user, sub_pair, row_of, simulatable, class_term,
    log_cost, error, heavy, n_testcases,
):
    now = sub_arrival[target]
    own_class = class_term[submission_events[target]]
    user = sub_user[target]
    out = baseline.astype(np.float64)

    # exercise, in release order -> out[1:9] = mean, sd, p50, p90, max, error, heavy, tests
    original = _visible(ex_rows, ex_off, sub_exercise[target], now, sub_availability, sub_arrival)
    ext = original[_external(submission_events[original], row_of, simulatable, class_term, own_class)]
    sel = sub_exercise[own_rows] == sub_exercise[target]
    ex = submission_events[_ordered(ext, own_rows[sel], own_release[sel], sub_availability, sub_arrival)]
    if len(ex):
        top = _summary(log_cost[ex], error[ex], heavy[ex], out, 1)
        err_rate, heavy_rate = out[5], out[6]
        out[5] = top
        out[6] = err_rate
        out[7] = heavy_rate
        out[8] = _mean(n_testcases[ex])
    else:
        for j in range(1, 9):
            out[j] = _NAN

    # user, in release order -> out[10:16]
    original = _visible(us_rows, us_off, user, now, sub_availability, sub_arrival)
    ext = original[_external(submission_events[original], row_of, simulatable, class_term, own_class)]
    mine = sub_user[own_rows] == user
    us = submission_events[_ordered(ext, own_rows[mine], own_release[mine], sub_availability, sub_arrival)]
    _summary(log_cost[us], error[us], heavy[us], out, 10)

    # pair: the latest record only -> out[17:19]
    original = _visible(pr_rows, pr_off, pair_code, now, sub_availability, sub_arrival)
    ext = original[_external(submission_events[original], row_of, simulatable, class_term, own_class)]
    best = _latest(np.concatenate((ext, own_rows[sub_pair[own_rows] == pair_code])), sub_arrival)
    out[17] = log_cost[submission_events[best]] if best >= 0 else _NAN
    out[18] = error[submission_events[best]] if best >= 0 else _NAN

    # the user's events: the latest only -> out[20]
    events = _visible(ev_rows, ev_off, user, now, availability, arrival)
    ext = events[_external(events, row_of, simulatable, class_term, own_class)]
    best = _latest(np.concatenate((ext, submission_events[own_rows[mine]])), arrival)
    out[20] = error[best] if best >= 0 else _NAN
    return out.astype(np.float32)


class FastRecomputer:
    """Stands in for an `M4HistoryRecomputer` inside `replay_online` only."""

    def __init__(self, reference):
        p = reference.prepared
        self.reference = reference
        self._arrays = (
            reference.exercise.rows, reference.exercise.offsets,
            reference.user.rows, reference.user.offsets,
            reference.pair.rows, reference.pair.offsets,
            reference.event_user.rows, reference.event_user.offsets,
            reference.sub_arrival, reference.sub_availability,
            reference.arrival, reference.availability, reference.submission_events,
            reference.sub_exercise, reference.sub_user, reference.sub_pair.astype(np.int64),
            p.row_of.astype(np.int64), p.simulatable, p.class_term.astype(np.int64),
            p.log_cost.astype(np.float64), p.error.astype(np.float64),
            p.heavy.astype(np.float64), p.n_testcases.astype(np.float64),
        )

    def recompute_visible(self, target, baseline, own_rows, own_release):
        return _recompute(
            int(target), np.asarray(baseline, np.float32),
            np.asarray(own_rows, np.int64), np.asarray(own_release, np.float64),
            int(self.reference._pair_code(target)), *self._arrays,
        )

    def __getattr__(self, name):  # anything else the replay reads is the reference's
        return getattr(self.reference, name)
