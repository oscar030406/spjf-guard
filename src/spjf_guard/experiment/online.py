"""Online replay: every score is computed at arrival from the outcomes completed by then.

The monotone refinement in :mod:`consistent` only withholds outcomes.  An online
predictor also reads an own-copy outcome that completes earlier in the replay than in
the source log (a job whose measured cost exceeds the service cap), and it orders its
rolling windows by replay completion.  This module finds the replay in which every
job's score is the frozen predictor applied to exactly that state.

Fixed point.  Each pass simulates the current scores, computes every job's online
state from that replay, and rescores the jobs whose state differs from the one their
current score was computed from.  Let t be the earliest arrival among those jobs.  No
score of a job arriving before t changes, so the next replay agrees with this one on
every event before t; completions at or before t come from dispatches before t, so
every job arriving at or before t is consistent in the next pass.  The earliest
mismatch moves strictly later on every pass, the iteration terminates, and the same
induction over arrival order shows that its terminal replay is the unique online one.

State.  A job's online state is its visible own-copy outcome set and the membership of
its two 120-record rolling windows (exercise and user); every other M4 field that reads
outcomes is a function of the visible set.  Both are summarised by a 64-bit signature
built from random 64-bit record labels: equal states give equal signatures, and a
different state collides with probability about 2^-64 per comparison.  Float64
summation order is outside the signature, so a job whose set and windows are unchanged
keeps its original score even when records outside its window were released in a
different order; :func:`audit_online` recomputes a random sample from scratch to check
that this never changes a score.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

import numpy as np
from numba import njit, prange

from spjf_guard.features.refine import M4HistoryRecomputer
from spjf_guard.sim import Trace, simulate
from spjf_guard.sim.policy import MICROS, Policy
from spjf_guard.sim.runner import JobResults

WINDOW = 120
_LABEL_SEED = 20260924


@dataclass(frozen=True)
class OnlinePass:
    number: int
    mismatched_jobs: int
    frontier_s: float
    rescored_jobs_total: int
    simulation_s: float
    detection_s: float
    rescore_s: float


@dataclass(frozen=True)
class OnlineResult:
    outcome: JobResults
    initial_outcome: JobResults
    passes: list[OnlinePass]
    changed_jobs: np.ndarray
    score_delta: np.ndarray
    corrected_score: np.ndarray
    visible_counts: np.ndarray


@dataclass(frozen=True)
class _History:
    """One unscoped history (exercise or user) plus its own-copy scoping."""

    rows: np.ndarray  # submission rows by key, each key in sweep order
    offsets: np.ndarray  # key -> start in ``rows``
    key: np.ndarray  # key of every submission row
    visible: np.ndarray  # original visible prefix length at each row's own arrival
    prefix_hash: np.ndarray  # label sums along ``rows``
    scope: np.ndarray  # (class-term, key) code of a replayed row, else -1
    n_scopes: int
    scoped_offsets: np.ndarray
    scoped_position: np.ndarray  # position in ``rows`` of each scoped entry
    scoped_hash: np.ndarray  # label sums along the scoped entries


@dataclass(frozen=True)
class OnlineIndex:
    """Structures shared by every cell and pass of one pool."""

    exercise: _History
    user: _History
    labels: np.ndarray
    own_class: np.ndarray  # class-term of a replayed submission row, else -1
    arrival: np.ndarray  # original-clock arrival of each submission row
    availability: np.ndarray
    zero_lag: np.ndarray
    original_signature: np.ndarray  # per submission row; 0 for rows never replayed


@njit(cache=True)
def _visible_prefix(rows, offsets, key, availability, zero_lag, now, targets, out):
    for t in range(len(targets)):
        row = targets[t]
        start = offsets[key[row]]
        stop = offsets[key[row] + 1]
        lo, hi = start, stop
        while lo < hi:
            mid = (lo + hi) // 2
            if availability[rows[mid]] <= now[row]:
                lo = mid + 1
            else:
                hi = mid
        end = lo
        while (
            end > start and availability[rows[end - 1]] == now[row] and zero_lag[rows[end - 1]]
        ):
            end -= 1
        out[row] = end - start


def _history(grouped, key, recomputer, labels, own_class, targets) -> _History:
    rows = grouped.rows.astype(np.int64)
    offsets = grouped.offsets.astype(np.int64)
    availability = recomputer.sub_availability
    zero_lag = availability == recomputer.sub_arrival
    visible = np.zeros(len(key), np.int64)
    _visible_prefix(
        rows, offsets, key, availability, zero_lag, recomputer.sub_arrival, targets, visible
    )
    prefix_hash = np.zeros(len(rows) + 1, np.uint64)
    prefix_hash[1:] = np.cumsum(labels[rows], dtype=np.uint64)
    replayed = own_class >= 0
    width = np.int64(key.max()) + 1
    scope = np.full(len(key), -1, np.int64)
    codes, inverse = np.unique(
        own_class[replayed].astype(np.int64) * width + key[replayed], return_inverse=True
    )
    scope[replayed] = inverse
    position = np.empty(len(rows), np.int64)
    position[rows] = np.arange(len(rows))
    members = rows[scope[rows] >= 0]
    members = members[np.lexsort((position[members], scope[members]))]
    counts = np.bincount(scope[members], minlength=len(codes))
    scoped_hash = np.zeros(len(members) + 1, np.uint64)
    scoped_hash[1:] = np.cumsum(labels[members], dtype=np.uint64)
    return _History(
        rows=rows,
        offsets=offsets,
        key=key,
        visible=visible,
        prefix_hash=prefix_hash,
        scope=scope,
        n_scopes=len(codes),
        scoped_offsets=np.r_[0, np.cumsum(counts)].astype(np.int64),
        scoped_position=position[members],
        scoped_hash=scoped_hash,
    )


@njit(cache=True)
def _mix(value):
    value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


@njit(cache=True)
def _part(count, digest, taken, window, salt):
    salt = np.uint64(salt) * np.uint64(0x9E3779B97F4A7C15)
    return _mix(digest + np.uint64(count) * np.uint64(0xD6E8FEB86659FD93) + salt) ^ _mix(
        window + np.uint64(taken) * np.uint64(0xA0761D6478BD642F) + salt + salt
    )


@njit(cache=True)
def _original_part(
    row, window, offsets, key, visible, prefix, scope, s_off, s_pos, s_hash, salt
):
    start = offsets[key[row]]
    p = visible[row]
    lo, hi = s_off[scope[row]], s_off[scope[row] + 1]
    first = lo
    while lo < hi:
        mid = (lo + hi) // 2
        if s_pos[mid] < start + p:
            lo = mid + 1
        else:
            hi = mid
    taken = min(window, p)
    return _part(
        lo - first,
        s_hash[lo] - s_hash[first],
        taken,
        prefix[start + p] - prefix[start + p - taken],
        salt,
    )


_ORIGINAL_FIELDS = (
    "offsets",
    "key",
    "visible",
    "prefix_hash",
    "scope",
    "scoped_offsets",
    "scoped_position",
    "scoped_hash",
)


@njit(cache=True)
def _original_loop(
    targets, window, e0, e1, e2, e3, e4, e5, e6, e7, u0, u1, u2, u3, u4, u5, u6, u7, out
):
    for t in range(len(targets)):
        row = targets[t]
        out[row] = _original_part(row, window, e0, e1, e2, e3, e4, e5, e6, e7, 1) ^ (
            _original_part(row, window, u0, u1, u2, u3, u4, u5, u6, u7, 3)
        )


def build_online_index(recomputer: M4HistoryRecomputer) -> OnlineIndex:
    """Static signatures and scoping for every replayed submission row of the pool."""
    prepared = recomputer.prepared
    n_rows = len(recomputer.submission_events)
    labels = np.random.default_rng(_LABEL_SEED).integers(
        0, np.iinfo(np.uint64).max, n_rows, dtype=np.uint64, endpoint=True
    )
    own_class = np.full(n_rows, -1, np.int64)
    replayed = np.flatnonzero(prepared.simulatable)
    own_class[replayed] = prepared.class_term[recomputer.submission_events[replayed]]
    targets = replayed.astype(np.int64)
    exercise = _history(
        recomputer.exercise, recomputer.sub_exercise, recomputer, labels, own_class, targets
    )
    user = _history(
        recomputer.user, recomputer.sub_user, recomputer, labels, own_class, targets
    )
    signature = np.zeros(n_rows, np.uint64)
    fields = [getattr(h, name) for h in (exercise, user) for name in _ORIGINAL_FIELDS]
    _original_loop(targets, WINDOW, *fields, signature)
    return OnlineIndex(
        exercise=exercise,
        user=user,
        labels=labels,
        own_class=own_class,
        arrival=recomputer.sub_arrival,
        availability=recomputer.sub_availability,
        zero_lag=recomputer.sub_availability == recomputer.sub_arrival,
        original_signature=signature,
    )


@dataclass(frozen=True)
class _CellLayout:
    """Per-cell static layout: each job's own-copy segments and the clock slack."""

    segments: tuple[np.ndarray, np.ndarray]  # per history: segment of every job
    n_segments: tuple[int, int]
    slack_s: float


def cell_layout(index: OnlineIndex, arrays: dict[str, np.ndarray]) -> _CellLayout:
    rows = arrays["job_row"]
    rounds = arrays["copy_round"].astype(np.int64)
    n_rounds = int(rounds.max()) + 1
    segments, sizes = [], []
    for history in (index.exercise, index.user):
        scope = history.scope[rows]
        if np.any(scope < 0):
            raise AssertionError("a replayed job has no own-copy scope")
        segments.append(scope * n_rounds + rounds)
        sizes.append(history.n_scopes * n_rounds)
    # Replay and original clocks differ by one constant per copy up to quantisation;
    # the slack bounds how far a job's release can sit from the done rule's boundary.
    offset = index.arrival[rows] - arrays["arrival_us"] / MICROS
    order = np.argsort(arrays["copy_entry"], kind="stable")
    entries = arrays["copy_entry"][order]
    starts = np.r_[0, np.flatnonzero(entries[1:] != entries[:-1]) + 1]
    spread = np.maximum.reduceat(offset[order], starts) - np.minimum.reduceat(
        offset[order], starts
    )
    return _CellLayout(tuple(segments), tuple(sizes), float(spread.max()) + 1e-6)


@dataclass(frozen=True)
class _PassView:
    """One replay's own-copy outcomes, per history, sorted by (segment, release, row)."""

    completion: np.ndarray
    release: np.ndarray
    order: tuple[np.ndarray, np.ndarray]
    offsets: tuple[np.ndarray, np.ndarray]
    hashes: tuple[np.ndarray, np.ndarray]


def release_times(
    index: OnlineIndex, arrays: dict[str, np.ndarray], completion: np.ndarray
) -> np.ndarray:
    """Original-clock instant at which each job's outcome is released in the replay."""
    return index.arrival[arrays["job_row"]] + (completion - arrays["arrival_us"]) / MICROS


def pass_view(
    index: OnlineIndex,
    layout: _CellLayout,
    arrays: dict[str, np.ndarray],
    completion: np.ndarray,
) -> _PassView:
    release = release_times(index, arrays, completion)
    rows = arrays["job_row"]
    orders, offsets, hashes = [], [], []
    for segment, size in zip(layout.segments, layout.n_segments):
        order = np.lexsort((rows, release, segment))
        counts = np.bincount(segment, minlength=size)
        cumulative = np.zeros(len(order) + 1, np.uint64)
        cumulative[1:] = np.cumsum(index.labels[rows[order]], dtype=np.uint64)
        orders.append(order)
        offsets.append(np.r_[0, np.cumsum(counts)].astype(np.int64))
        hashes.append(cumulative)
    return _PassView(completion, release, tuple(orders), tuple(offsets), tuple(hashes))


@njit(cache=True)
def _upper(values, order, lo, hi, bound):
    while lo < hi:
        mid = (lo + hi) // 2
        if values[order[mid]] <= bound:
            lo = mid + 1
        else:
            hi = mid
    return lo


@njit(cache=True)
def _online_part(
    i,
    window,
    slack,
    job_row,
    arrival_us,
    completion,
    release,
    labels,
    own_class,
    availability,
    zero_lag,
    now_s,
    rows,
    offsets,
    key,
    visible,
    segment,
    order,
    seg_offsets,
    cumulative,
):
    """Visible count and window state of job i in one history."""
    row = job_row[i]
    k = own_class[row]
    now = now_s[row]
    s0 = seg_offsets[segment[i]]
    s1 = seg_offsets[segment[i] + 1]
    sure = _upper(release, order, s0, s1, now - slack)
    maybe = _upper(release, order, sure, s1, now + slack)
    count = sure - s0
    digest = cumulative[sure] - cumulative[s0]
    for q in range(sure, maybe):
        if completion[order[q]] <= arrival_us[i]:
            count += 1
            digest += labels[job_row[order[q]]]
    start = offsets[key[row]]
    e = visible[row] - 1
    o = maybe - 1
    taken = 0
    hashed = np.uint64(0)
    while taken < window:
        while e >= 0 and own_class[rows[start + e]] == k:
            e -= 1
        while o >= sure and completion[order[o]] > arrival_us[i]:
            o -= 1
        has_e = e >= 0
        has_o = o >= s0
        if not has_e and not has_o:
            break
        take_e = has_e
        if has_e and has_o:
            external = rows[start + e]
            own = job_row[order[o]]
            a = availability[external]
            b = release[order[o]]
            take_e = a > b or (a == b and (zero_lag[external] or external > own))
        if take_e:
            hashed += labels[rows[start + e]]
            e -= 1
        else:
            hashed += labels[job_row[order[o]]]
            o -= 1
        taken += 1
    return count, digest, taken, hashed


@njit(parallel=True, cache=True)
def _online_loop(
    job_row,
    arrival_us,
    completion,
    release,
    labels,
    own_class,
    availability,
    zero_lag,
    now_s,
    window,
    slack,
    e0,
    e1,
    e2,
    e3,
    e4,
    e5,
    e6,
    e7,
    u0,
    u1,
    u2,
    u3,
    u4,
    u5,
    u6,
    u7,
    out,
    visible_count,
):
    for i in prange(len(job_row)):
        c0, d0, t0, w0 = _online_part(
            i,
            window,
            slack,
            job_row,
            arrival_us,
            completion,
            release,
            labels,
            own_class,
            availability,
            zero_lag,
            now_s,
            e0,
            e1,
            e2,
            e3,
            e4,
            e5,
            e6,
            e7,
        )
        c1, d1, t1, w1 = _online_part(
            i,
            window,
            slack,
            job_row,
            arrival_us,
            completion,
            release,
            labels,
            own_class,
            availability,
            zero_lag,
            now_s,
            u0,
            u1,
            u2,
            u3,
            u4,
            u5,
            u6,
            u7,
        )
        visible_count[i] = c0 + c1
        out[i] = _part(c0, d0, t0, w0, 1) ^ _part(c1, d1, t1, w1, 3)


def online_signatures(
    index: OnlineIndex,
    layout: _CellLayout,
    arrays: dict[str, np.ndarray],
    view: _PassView,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(arrays["job_row"])
    out = np.zeros(n, np.uint64)
    counts = np.zeros(n, np.int64)
    histories = []
    for g, history in enumerate((index.exercise, index.user)):
        histories += [
            history.rows,
            history.offsets,
            history.key,
            history.visible,
            layout.segments[g],
            view.order[g],
            view.offsets[g],
            view.hashes[g],
        ]
    _online_loop(
        arrays["job_row"],
        arrays["arrival_us"],
        view.completion,
        view.release,
        index.labels,
        index.own_class,
        index.availability,
        index.zero_lag,
        index.arrival,
        WINDOW,
        layout.slack_s,
        *histories,
        out,
        counts,
    )
    return out, counts


def own_outcomes(
    job: int,
    layout: _CellLayout,
    arrays: dict[str, np.ndarray],
    view: _PassView,
) -> tuple[np.ndarray, np.ndarray]:
    """Own-copy outcomes sharing the job's exercise or user, completed by its arrival."""
    now_us = arrays["arrival_us"][job]
    parts = []
    for g in range(2):
        segment = layout.segments[g][job]
        order = view.order[g][view.offsets[g][segment] : view.offsets[g][segment + 1]]
        parts.append(order[view.completion[order] <= now_us])
    jobs = np.union1d(*parts)
    rows = arrays["job_row"][jobs]
    return rows, view.release[jobs]


def _rescore(
    jobs: np.ndarray,
    signature: np.ndarray,
    layout: _CellLayout,
    arrays: dict[str, np.ndarray],
    view: _PassView,
    recomputer: M4HistoryRecomputer,
    models,
    baseline_history: np.ndarray,
    cache: dict[tuple[int, int], float],
) -> np.ndarray:
    rows = arrays["job_row"][jobs]
    keys = [(int(row), int(sig)) for row, sig in zip(rows, signature[jobs])]
    missing: dict[tuple[int, int], int] = {}
    for job, key in zip(jobs, keys):
        if key not in cache:
            missing.setdefault(key, int(job))
    if missing:
        unique = np.fromiter(missing.values(), np.int64, count=len(missing))
        histories = np.vstack(
            [
                recomputer.recompute_visible(
                    int(arrays["job_row"][job]),
                    baseline_history[arrays["job_row"][job]],
                    *own_outcomes(int(job), layout, arrays, view),
                )
                for job in unique
            ]
        )
        values = models.predict(arrays["job_row"][unique], histories)
        cache.update(zip(missing, map(float, values)))
    return np.array([cache[key] for key in keys], np.float64)


def refine_policy_online(
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
    score_key: str,
    max_passes: int = 400,
    simulator: Callable[[Trace], JobResults] | None = None,
) -> OnlineResult:
    """Iterate to the online replay of one policy in one cell."""
    layout = cell_layout(index, arrays)
    scores = np.asarray(baseline_score, np.float64).copy()
    stored = index.original_signature[arrays["job_row"]].copy()
    explicit = np.zeros(len(scores), bool)
    cache: dict[tuple[int, int], float] = {}
    passes: list[OnlinePass] = []
    initial_outcome = None
    while True:
        number = len(passes) + 1
        if number > max_passes:
            raise RuntimeError(f"{policy.name}: no online fixed point in {max_passes} passes")
        started = perf_counter()
        current = Trace(trace.arrival_us, trace.service_us, {score_key: scores}, trace.limit_s)
        outcome = (
            simulate(current, policy, servers, window=window)
            if simulator is None
            else simulator(current)
        )
        if initial_outcome is None:
            initial_outcome = outcome
        simulated = perf_counter()
        completion = arrays["arrival_us"] + outcome.wait_us + arrays["service_us"]
        view = pass_view(index, layout, arrays, completion)
        signature, counts = online_signatures(index, layout, arrays, view)
        mismatched = np.flatnonzero(signature != stored)
        detected = perf_counter()
        frontier = (
            float(arrays["arrival_us"][mismatched].min()) / MICROS if len(mismatched) else -1.0
        )
        if len(mismatched):
            scores[mismatched] = _rescore(
                mismatched,
                signature,
                layout,
                arrays,
                view,
                recomputer,
                models,
                baseline_history,
                cache,
            )
            stored[mismatched] = signature[mismatched]
            explicit[mismatched] = True
            if len(cache) > 400000:
                cache.clear()
        passes.append(
            OnlinePass(
                number=number,
                mismatched_jobs=len(mismatched),
                frontier_s=frontier,
                rescored_jobs_total=int(explicit.sum()),
                simulation_s=simulated - started,
                detection_s=detected - simulated,
                rescore_s=perf_counter() - detected,
            )
        )
        print(
            f"    {policy.name} online pass {number}: {len(mismatched):,} jobs "
            f"({perf_counter() - started:.1f} s)",
            flush=True,
        )
        if not len(mismatched):
            break
    changed = np.flatnonzero(explicit & (scores != baseline_score))
    return OnlineResult(
        outcome=outcome,
        initial_outcome=initial_outcome,
        passes=passes,
        changed_jobs=changed,
        score_delta=scores[changed] - baseline_score[changed],
        corrected_score=scores[changed].copy(),
        visible_counts=counts[changed],
    )


def audit_online(
    result: OnlineResult,
    sample: np.ndarray,
    arrays: dict[str, np.ndarray],
    index: OnlineIndex,
    recomputer: M4HistoryRecomputer,
    models,
    baseline_history: np.ndarray,
    baseline_score: np.ndarray,
) -> int:
    """Rebuild sampled jobs' online scores by an independent route; count disagreements.

    Candidates come from the recomputer's own (class-term, key) arrival index rather
    than from the pass view, completion is read from the terminal replay, and the score
    the replay used is the baseline score unless the job was rescored.
    """
    completion = arrays["arrival_us"] + result.outcome.wait_us + arrays["service_us"]
    release = release_times(index, arrays, completion)
    by_copy = np.lexsort((arrays["job_row"], arrays["copy_entry"]))
    entries = arrays["copy_entry"][by_copy]
    copy_rows = arrays["job_row"][by_copy]
    used = np.asarray(baseline_score, np.float64).copy()
    used[result.changed_jobs] = result.corrected_score
    histories = []
    for job in sample:
        row = int(arrays["job_row"][job])
        candidates = recomputer.own_copy_candidates(row)
        entry = arrays["copy_entry"][job]
        lo = np.searchsorted(entries, entry, side="left")
        hi = np.searchsorted(entries, entry, side="right")
        position = lo + np.searchsorted(copy_rows[lo:hi], candidates)
        inside = position < hi
        if not inside.all() or np.any(copy_rows[position] != candidates):
            raise AssertionError("an own-copy candidate has no job in this copy")
        jobs = by_copy[position]
        done = completion[jobs] <= arrays["arrival_us"][job]
        histories.append(
            recomputer.recompute_visible(
                row, baseline_history[row], candidates[done], release[jobs[done]]
            )
        )
    rebuilt = models.predict(arrays["job_row"][sample], np.vstack(histories))
    return int(np.sum(rebuilt != used[sample]))
