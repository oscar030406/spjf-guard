"""Event-driven online replay: the scheduler pauses at an arrival whose history changed.

This is the online predictor run directly.  The package kernel (sim/kernel.py) is
replayed step for step, with two additions.  At every completion the finished job is
appended to the completed lists of its own-copy (class-term, exercise) and (class-term,
user) segments, in release order.  At every arrival the job's online state -- its
visible own-copy set and the membership of its two 120-record rolling windows -- is
summarised by the signature of experiment.online; when it equals the signature of the
job's original-clock state the job keeps its original score, and otherwise the kernel
returns, Python rebuilds the job's M4 row from exactly the completed outcomes and asks
the frozen model for its score, and the kernel resumes at the same instant.  Every
score is therefore computed once, at arrival, from the outcomes completed by then.

experiment.online reaches the same replay by a fixed-point iteration instead; the two
implementations are checked against each other and against a brute-force replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from numba import njit

from spjf_guard.experiment.online import WINDOW, OnlineIndex, _part, cell_layout
from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.sim.kernel import (
    MODE_FCFS,
    MODE_GUARD,
    MODE_SCORE,
    MODE_SKIP,
    S_COMPLETED_WORK,
    S_ERR,
    S_FIFO_TAIL,
    S_LEN,
    S_MAX_SPAN,
    S_NDISP,
    S_NEXT_ARRIVAL,
    S_NFORCED,
    S_NHEAP,
    S_NRUN,
    S_NSTARTED,
    S_NWAIT,
    S_QW_FORCED,
    S_QW_TOTAL,
    S_WINDOW_BASE,
    _base_choice,
    _choose,
    _dispatch,
    _fen_add,
    _fen_pref,
    _fifo_head,
    _next_instant,
    _rebuild_window,
    _run_pop,
    _score_push,
    _st_add_suffix,
    _st_clear,
    _st_set,
)
from spjf_guard.sim.policy import MICROS, Policy, eta_fraction
from spjf_guard.sim.runner import JobResults, Trace, _mode_of

MODE_TIMEOUT = 4
"""Serve the oldest waiting job once it has waited theta, else the base choice
(prechecks/timeout_rule/timeout_overlays.py).  The package kernel has no such mode."""
X_T = S_LEN
X_PENDING = S_LEN + 1
X_LEN = S_LEN + 2
PAUSED = 1
FINISHED = 0


@dataclass(frozen=True)
class ReplayResult:
    outcome: JobResults
    changed_jobs: np.ndarray
    corrected_score: np.ndarray
    score_delta: np.ndarray
    visible_counts: np.ndarray
    pauses: int
    kernel_s: float
    rescore_s: float


@njit(cache=True)
def _append(listing, fill, seg_offsets, totals, segment, job, release, job_row, labels):
    base = seg_offsets[segment]
    pos = base + fill[segment]
    while pos > base and (
        release[listing[pos - 1]] > release[job]
        or (
            release[listing[pos - 1]] == release[job]
            and job_row[listing[pos - 1]] > job_row[job]
        )
    ):
        listing[pos] = listing[pos - 1]
        pos -= 1
    listing[pos] = job
    fill[segment] += 1
    totals[segment] += labels[job_row[job]]


@njit(cache=True)
def _complete(
    t,
    st,
    rt,
    rj,
    s_us,
    fen_work,
    n,
    tre,
    lz,
    size,
    ed,
    mode,
    release,
    offset,
    job_row,
    labels,
    ex_segment,
    ex_list,
    ex_fill,
    ex_seg_offsets,
    ex_totals,
    u_segment,
    u_list,
    u_fill,
    u_seg_offsets,
    u_totals,
):
    """sim.kernel._apply_completions, plus the completed lists."""
    while st[S_NRUN] > 0 and rt[0] <= t:
        c = rj[0]
        done = rt[0]
        st[S_NRUN] = _run_pop(rt, rj, st[S_NRUN])
        if mode == MODE_GUARD:
            work = s_us[c]
            st[S_COMPLETED_WORK] += work
            _fen_add(fen_work, n, c, work)
            _st_add_suffix(tre, lz, size, c - st[S_WINDOW_BASE], -ed * work)
        release[c] = done / 1e6 + offset[c]
        _append(
            ex_list,
            ex_fill,
            ex_seg_offsets,
            ex_totals,
            ex_segment[c],
            c,
            release,
            job_row,
            labels,
        )
        _append(
            u_list, u_fill, u_seg_offsets, u_totals, u_segment[c], c, release, job_row, labels
        )


@njit(cache=True)
def _state_part(
    i,
    window,
    job_row,
    release,
    labels,
    own_class,
    availability,
    zero_lag,
    rows,
    offsets,
    key,
    visible,
    segment,
    listing,
    fill,
    seg_offsets,
    totals,
    salt,
):
    row = job_row[i]
    k = own_class[row]
    seg = segment[i]
    base = seg_offsets[seg]
    count = fill[seg]
    start = offsets[key[row]]
    e = visible[row] - 1
    o = base + count - 1
    taken = 0
    hashed = np.uint64(0)
    while taken < window:
        while e >= 0 and own_class[rows[start + e]] == k:
            e -= 1
        has_e = e >= 0
        has_o = o >= base
        if not has_e and not has_o:
            break
        take_e = has_e
        if has_e and has_o:
            external = rows[start + e]
            own = job_row[listing[o]]
            a = availability[external]
            b = release[listing[o]]
            take_e = a > b or (a == b and (zero_lag[external] or external > own))
        if take_e:
            hashed += labels[rows[start + e]]
            e -= 1
        else:
            hashed += labels[job_row[listing[o]]]
            o -= 1
        taken += 1
    return count, _part(count, totals[seg], taken, hashed, salt)


@njit(cache=True)
def _needs_score(
    i,
    decided,
    original,
    signature,
    counts,
    window,
    job_row,
    release,
    labels,
    own_class,
    availability,
    zero_lag,
    ex_rows,
    ex_offsets,
    ex_key,
    ex_visible,
    ex_segment,
    ex_list,
    ex_fill,
    ex_seg_offsets,
    ex_totals,
    u_rows,
    u_offsets,
    u_key,
    u_visible,
    u_segment,
    u_list,
    u_fill,
    u_seg_offsets,
    u_totals,
):
    """True when job i's online state differs from its original-clock state."""
    c0, s0 = _state_part(
        i,
        window,
        job_row,
        release,
        labels,
        own_class,
        availability,
        zero_lag,
        ex_rows,
        ex_offsets,
        ex_key,
        ex_visible,
        ex_segment,
        ex_list,
        ex_fill,
        ex_seg_offsets,
        ex_totals,
        1,
    )
    c1, s1 = _state_part(
        i,
        window,
        job_row,
        release,
        labels,
        own_class,
        availability,
        zero_lag,
        u_rows,
        u_offsets,
        u_key,
        u_visible,
        u_segment,
        u_list,
        u_fill,
        u_seg_offsets,
        u_totals,
        3,
    )
    signature[i] = s0 ^ s1
    counts[i] = c0 + c1
    if signature[i] == original[job_row[i]]:
        decided[i] = 1
        return False
    return True


@njit(cache=True)
def _guard_admit(
    i,
    st,
    a_us,
    fifo,
    served,
    fen_work,
    zs,
    tre,
    lz,
    size,
    mslots,
    en,
    ed,
    b0_us,
    gam_us,
    bmax_us,
):
    """The work-budget part of sim.kernel._admit_arrivals for job i; True on window error."""
    if st[S_NWAIT] == 0:
        st[S_WINDOW_BASE] = i
    elif i - st[S_WINDOW_BASE] >= mslots:
        _rebuild_window(st, fifo, served, fen_work, zs, tre, lz, size, mslots, ed, i)
        if st[S_ERR] == 1:
            return True
    span = i - st[S_WINDOW_BASE] + 1
    if span > st[S_MAX_SPAN]:
        st[S_MAX_SPAN] = span
    cb = b0_us + gam_us * st[S_NWAIT]
    if bmax_us > 0 and cb > bmax_us:
        cb = bmax_us
    zs[i] = en * a_us[i] - ed * cb
    _st_set(tre, lz, size, i - st[S_WINDOW_BASE], zs[i] - ed * _fen_pref(fen_work, i))
    return False


@njit(cache=True)
def _admit(
    t,
    st,
    a_us,
    score,
    n,
    fifo,
    hk,
    hi,
    served,
    fen_work,
    zs,
    tre,
    lz,
    size,
    mslots,
    en,
    ed,
    b0_us,
    gam_us,
    bmax_us,
    mode,
    decided,
    original,
    signature,
    counts,
    window,
    job_row,
    release,
    labels,
    own_class,
    availability,
    zero_lag,
    ex_rows,
    ex_offsets,
    ex_key,
    ex_visible,
    ex_segment,
    ex_list,
    ex_fill,
    ex_seg_offsets,
    ex_totals,
    u_rows,
    u_offsets,
    u_key,
    u_visible,
    u_segment,
    u_list,
    u_fill,
    u_seg_offsets,
    u_totals,
):
    """sim.kernel._admit_arrivals, preceded by the online state test.  1 = paused."""
    while st[S_NEXT_ARRIVAL] < n and a_us[st[S_NEXT_ARRIVAL]] <= t:
        i = st[S_NEXT_ARRIVAL]
        if decided[i] == 0 and _needs_score(
            i,
            decided,
            original,
            signature,
            counts,
            window,
            job_row,
            release,
            labels,
            own_class,
            availability,
            zero_lag,
            ex_rows,
            ex_offsets,
            ex_key,
            ex_visible,
            ex_segment,
            ex_list,
            ex_fill,
            ex_seg_offsets,
            ex_totals,
            u_rows,
            u_offsets,
            u_key,
            u_visible,
            u_segment,
            u_list,
            u_fill,
            u_seg_offsets,
            u_totals,
        ):
            st[X_PENDING] = i
            return 1
        if mode == MODE_GUARD and _guard_admit(
            i,
            st,
            a_us,
            fifo,
            served,
            fen_work,
            zs,
            tre,
            lz,
            size,
            mslots,
            en,
            ed,
            b0_us,
            gam_us,
            bmax_us,
        ):
            return 0
        if mode != MODE_SCORE:
            fifo[st[S_FIFO_TAIL]] = i
            st[S_FIFO_TAIL] += 1
        if mode != MODE_FCFS:
            st[S_NHEAP] = _score_push(hk, hi, st[S_NHEAP], score[i], i)
        st[S_NWAIT] += 1
        st[S_NEXT_ARRIVAL] += 1
    return 0


@njit(cache=True)
def _choose_online(
    t,
    st,
    fifo,
    hk,
    hi,
    served,
    fen_work,
    fen_count,
    tre,
    lz,
    size,
    en,
    ed,
    bmax_us,
    ncap,
    mode,
    a_us,
    theta_us,
):
    """sim.kernel._choose, plus the head-of-line timeout."""
    if mode == MODE_TIMEOUT:
        head = _fifo_head(st, fifo, served)
        if t - a_us[head] >= theta_us:
            return head, 1
        return _base_choice(st, hk, hi, served), 0
    return _choose(
        t,
        st,
        fifo,
        hk,
        hi,
        served,
        fen_work,
        fen_count,
        tre,
        lz,
        size,
        en,
        ed,
        bmax_us,
        ncap,
        mode,
    )


@njit(cache=True)
def _resume(
    a_us,
    s_us,
    score,
    k,
    mode,
    b0_us,
    en,
    ed,
    bmax_us,
    ncap,
    mslots,
    gam_us,
    theta_us,
    st,
    rt,
    rj,
    hk,
    hi,
    served,
    fifo,
    tre,
    lz,
    size,
    zs,
    fen_work,
    fen_count,
    wait_us,
    start_us,
    dispatch_index,
    decided,
    original,
    signature,
    counts,
    window,
    job_row,
    release,
    offset,
    labels,
    own_class,
    availability,
    zero_lag,
    ex_rows,
    ex_offsets,
    ex_key,
    ex_visible,
    ex_segment,
    ex_list,
    ex_fill,
    ex_seg_offsets,
    ex_totals,
    u_rows,
    u_offsets,
    u_key,
    u_visible,
    u_segment,
    u_list,
    u_fill,
    u_seg_offsets,
    u_totals,
):
    """The loop of sim.kernel.simulate_kernel from the saved instant: PAUSED or FINISHED."""
    n = a_us.shape[0]
    horizon = np.int64(1) << 62
    t = st[X_T]
    while st[S_NSTARTED] < n:
        _complete(
            t,
            st,
            rt,
            rj,
            s_us,
            fen_work,
            n,
            tre,
            lz,
            size,
            ed,
            mode,
            release,
            offset,
            job_row,
            labels,
            ex_segment,
            ex_list,
            ex_fill,
            ex_seg_offsets,
            ex_totals,
            u_segment,
            u_list,
            u_fill,
            u_seg_offsets,
            u_totals,
        )
        paused = _admit(
            t,
            st,
            a_us,
            score,
            n,
            fifo,
            hk,
            hi,
            served,
            fen_work,
            zs,
            tre,
            lz,
            size,
            mslots,
            en,
            ed,
            b0_us,
            gam_us,
            bmax_us,
            mode,
            decided,
            original,
            signature,
            counts,
            window,
            job_row,
            release,
            labels,
            own_class,
            availability,
            zero_lag,
            ex_rows,
            ex_offsets,
            ex_key,
            ex_visible,
            ex_segment,
            ex_list,
            ex_fill,
            ex_seg_offsets,
            ex_totals,
            u_rows,
            u_offsets,
            u_key,
            u_visible,
            u_segment,
            u_list,
            u_fill,
            u_seg_offsets,
            u_totals,
        )
        if paused == 1:
            st[X_T] = t
            return PAUSED
        if st[S_ERR] == 1:
            break
        if st[S_NRUN] < k and st[S_NWAIT] > 0:
            j, forced = _choose_online(
                t,
                st,
                fifo,
                hk,
                hi,
                served,
                fen_work,
                fen_count,
                tre,
                lz,
                size,
                en,
                ed,
                bmax_us,
                ncap,
                mode,
                a_us,
                theta_us,
            )
            start_us[j] = t
            _dispatch(
                t,
                j,
                forced,
                st,
                a_us,
                s_us,
                wait_us,
                dispatch_index,
                served,
                rt,
                rj,
                fen_count,
                n,
                mode,
            )
            continue
        nxt = _next_instant(t, st, a_us, rt, n, horizon)
        if nxt >= horizon:
            break
        t = nxt
    st[X_T] = t
    return FINISHED


class _Kernel:
    """The kernel's arrays for one policy on one trace, allocated as simulate_kernel does."""

    def __init__(self, n: int, k: int, mode: int, mslots: int):
        guarding = mode == MODE_GUARD
        size = 1
        while size < mslots:
            size *= 2
        tsize = 2 * size if guarding else 2
        self.size = size
        self.st = np.zeros(X_LEN, np.int64)
        self.st[X_T] = -(np.int64(1) << 62)
        self.rt = np.empty(k + 1, np.int64)
        self.rj = np.empty(k + 1, np.int64)
        self.hk = np.empty(n + 1, np.float64)
        self.hi = np.empty(n + 1, np.int64)
        self.served = np.zeros(n, np.uint8)
        self.fifo = np.empty(n + 1, np.int64)
        self.tre = np.empty(tsize, np.int64)
        self.lz = np.empty(tsize // 2, np.int64)
        if guarding:
            _st_clear(self.tre, self.lz, size)
        self.zs = np.empty(n if guarding else 1, np.int64)
        self.fen_work = np.zeros((n + 1) if guarding else 1, np.int64)
        self.fen_count = np.zeros((n + 1) if mode == MODE_SKIP else 1, np.int64)
        self.wait_us = np.empty(n, np.int64)
        self.start_us = np.empty(n, np.int64)
        self.dispatch_index = np.empty(n, np.int64)


class _Lists:
    """Completed own-copy outcomes per segment, in release order."""

    def __init__(self, segment: np.ndarray, n_segments: int):
        self.segment = segment
        counts = np.bincount(segment, minlength=n_segments)
        self.offsets = np.r_[0, np.cumsum(counts)].astype(np.int64)
        self.listing = np.empty(len(segment), np.int64)
        self.fill = np.zeros(n_segments, np.int64)
        self.totals = np.zeros(n_segments, np.uint64)

    def done(self, job: int) -> np.ndarray:
        segment = self.segment[job]
        start = self.offsets[segment]
        return self.listing[start : start + self.fill[segment]]


def replay_online(
    trace: Trace,
    policy: Policy,
    servers: int,
    window: int,
    arrays: dict[str, np.ndarray],
    index: OnlineIndex,
    recomputer: M4HistoryRecomputer,
    models,
    baseline_history: np.ndarray,
    baseline_score: np.ndarray,
    timeout_s: float | None = None,
) -> ReplayResult:
    """Run ``policy`` once with every score computed at its job's arrival.

    ``timeout_s`` replaces the policy's wrapper by the head-of-line timeout theta.
    """
    mode = _mode_of(policy) if timeout_s is None else MODE_TIMEOUT
    theta_us = 0 if timeout_s is None else int(round(timeout_s * MICROS))
    if mode == MODE_FCFS:
        raise ValueError("FCFS reads no score; its replay does not depend on visibility")
    if policy.wrapper != "none" and policy.b0_us > policy.bmax_us > 0:
        raise ValueError("B0 must not exceed B_max")
    started = perf_counter()
    n = len(trace)
    a_us = np.ascontiguousarray(trace.arrival_us)
    s_us = np.ascontiguousarray(trace.service_us)
    job_row = np.ascontiguousarray(arrays["job_row"], np.int64)
    raw = np.asarray(baseline_score, np.float64).copy()
    aging = (
        policy.age_credit_per_s * (a_us - a_us[0]) / MICROS
        if policy.age_credit_per_s > 0.0
        else np.zeros(n)
    )
    score = raw + aging
    en, ed = eta_fraction(policy.eta_k)
    kernel = _Kernel(n, servers, mode, window)
    layout = cell_layout(index, arrays)
    lists = [_Lists(layout.segments[g], layout.n_segments[g]) for g in range(2)]
    release = np.full(n, np.nan)
    offset = layout.offset
    decided = np.zeros(n, np.uint8)
    signature = np.zeros(n, np.uint64)
    counts = np.zeros(n, np.int64)
    histories = []
    for g, history in enumerate((index.exercise, index.user)):
        histories += [
            history.rows,
            history.offsets,
            history.key,
            history.visible,
            lists[g].segment,
            lists[g].listing,
            lists[g].fill,
            lists[g].offsets,
            lists[g].totals,
        ]
    pauses = 0
    rescore_s = 0.0
    while True:
        status = _resume(
            a_us,
            s_us,
            score,
            int(servers),
            mode,
            int(policy.b0_us),
            int(en),
            int(ed),
            int(policy.bmax_us),
            int(policy.skip_count),
            int(window),
            int(policy.gam_us),
            theta_us,
            kernel.st,
            kernel.rt,
            kernel.rj,
            kernel.hk,
            kernel.hi,
            kernel.served,
            kernel.fifo,
            kernel.tre,
            kernel.lz,
            kernel.size,
            kernel.zs,
            kernel.fen_work,
            kernel.fen_count,
            kernel.wait_us,
            kernel.start_us,
            kernel.dispatch_index,
            decided,
            index.original_signature,
            signature,
            counts,
            WINDOW,
            job_row,
            release,
            offset,
            index.labels,
            index.own_class,
            index.availability,
            index.zero_lag,
            *histories,
        )
        if status == FINISHED:
            break
        clock = perf_counter()
        job = int(kernel.st[X_PENDING])
        done = np.union1d(lists[0].done(job), lists[1].done(job))
        row = int(job_row[job])
        history = recomputer.recompute_visible(  # type: ignore[assignment]
            row, baseline_history[row], job_row[done], release[done]
        )
        raw[job] = float(models.predict(job_row[job : job + 1], history[None, :])[0])  # type: ignore[index]
        score[job] = raw[job] + aging[job]
        decided[job] = 2
        pauses += 1
        rescore_s += perf_counter() - clock
    if kernel.st[S_ERR]:
        raise RuntimeError(f"{policy.name}: the span of waiting ranks outgrew the window")
    if kernel.st[S_NSTARTED] != n:
        raise AssertionError(f"{policy.name}: the online replay stopped before every start")
    outcome = JobResults(
        policy=policy.name,
        servers=int(servers),
        wait_us=kernel.wait_us,
        start_us=kernel.start_us,
        dispatch_index=kernel.dispatch_index,
        n_dispatch=int(kernel.st[S_NDISP]),
        n_forced=int(kernel.st[S_NFORCED]),
        queue_weighted_dispatch=int(kernel.st[S_QW_TOTAL]),
        queue_weighted_forced=int(kernel.st[S_QW_FORCED]),
    )
    changed = np.flatnonzero((decided == 2) & (raw != baseline_score))
    return ReplayResult(
        outcome=outcome,
        changed_jobs=changed,
        corrected_score=raw[changed].copy(),
        score_delta=raw[changed] - np.asarray(baseline_score)[changed],
        visible_counts=counts[changed],
        pauses=pauses,
        kernel_s=perf_counter() - started - rescore_s,
        rescore_s=rescore_s,
    )
