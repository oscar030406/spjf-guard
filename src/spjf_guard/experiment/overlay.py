"""Building the counterfactual shared judge pool.

One course term does not fill a judge machine, so the load is built by superposing
class-terms: each copy keeps its own weekday and clock time and is shifted by a whole
number of weeks, which preserves the daily and weekly rhythm.  The three load levels
share one superposed trace and differ only in the integer number of servers, chosen so
that the busiest hour runs at about 0.5, 0.8 and 1.0 utilisation.

The copies count is not tuned: a probe adds whole copies of the pool until every overlay
reaches at least four servers at full load with three distinct server counts, then takes
five more, and the arrival work is monotone in the count so every larger count qualifies
too.  Five overlays are different constructions of the same data, not five independent
platforms.

The pool is a list of terms taken from the configuration.  The sealed run passes a
different list; nothing else about the construction changes, which is why the sealed
terms are just another whitelist entry that `sealed.py` refuses today.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REFERENCE_MONDAY_S = 1578268800
"""2020-01-06 00:00:00 UTC, the Monday every copy is aligned to."""
WEEK_S = 604800
_FIRST_MONDAY_S = 345600
"""1970-01-05, the first Monday of the epoch."""


def base_shift(first_timestamp_s: float) -> float:
    """The whole-week shift putting the Monday of the first event's week on the reference
    Monday.  Weekday and clock time of every arrival are preserved."""
    monday = _FIRST_MONDAY_S + int((first_timestamp_s - _FIRST_MONDAY_S) // WEEK_S) * WEEK_S
    return REFERENCE_MONDAY_S - monday


def overlay_entries(pool, copies: int, overlay: int, seed: int) -> list[tuple[str, int]]:
    """`copies` copies of the pool, copy-major, each with its own 0-11 extra whole weeks.

    Draws are copy-major and in pool order, so the overlay with c copies is a prefix of
    the one with c + 1 and the probe's work is monotone in the count.
    """
    rng = np.random.default_rng(seed * 100 + overlay)
    return [(term, int(rng.integers(0, 12))) for _ in range(copies) for term in pool]


def superpose(entries, per_term: dict, arrival_key: str):
    """Superpose the class-term copies and sort by arrival.

    A job's identity in the overlay is (copy, row): copies never share an id, and no
    feature is computed on the overlay, because predictions are attached per original row.
    Returns (arrival, service, original row index, copy number), in rank order.
    """
    arrivals, services, rows, copies = [], [], [], []
    for copy, (term, weeks) in enumerate(entries):
        group = per_term[term]
        arrivals.append(group[arrival_key] + (group["base"] + weeks * WEEK_S))
        services.append(group["svc"])
        rows.append(group["idx"])
        copies.append(np.full(len(group["idx"]), copy, np.int32))
    arrival = np.concatenate(arrivals)
    order = np.argsort(arrival, kind="stable")
    return (
        arrival[order].astype("float64"),
        np.concatenate(services)[order],
        np.concatenate(rows)[order],
        np.concatenate(copies)[order],
    )


def rebase(arrival: np.ndarray) -> np.ndarray:
    """Drop whole days from the epoch after the busy hour is counted.  Waits are
    unchanged and the float rounding of start times falls from ~2e-7 s to ~1e-9 s."""
    return arrival - np.floor(arrival[0] / 86400.0) * 86400.0


def busy_hour_work(arrival: np.ndarray, service: np.ndarray) -> float:
    """Executed work arriving in the busiest whole hour; this is what sets k."""
    hour = np.floor(arrival / 3600.0).astype(np.int64)
    _, inverse = np.unique(hour, return_inverse=True)
    return float(np.bincount(inverse, weights=service).max())


def hour_histogram(per_term: dict, arrival_key: str) -> dict:
    """Work per arrival hour of every class-term after its base shift."""
    out = {}
    for term, group in per_term.items():
        hour = np.floor(
            (group[arrival_key] + group["base"] - REFERENCE_MONDAY_S) / 3600.0
        ).astype(np.int64)
        offset = int(hour.min())
        out[term] = (offset, np.bincount(hour - offset, weights=group["svc"]))
    return out


def level_servers(work_s: float, utilisations) -> list[int]:
    """Integer server count per target busy-hour utilisation, rounded half up."""
    return [max(1, int(np.floor(work_s / (3600.0 * rho) + 0.5))) for rho in utilisations]


def servers_acceptable(counts, min_at_full_load: int, distinct: int) -> bool:
    return (
        counts[-1] >= min_at_full_load
        and all(a > b for a, b in zip(counts, counts[1:]))
        and len(set(counts)) >= distinct
    )


def copies_probe(
    pool,
    per_term: dict,
    arrival_key: str,
    overlays,
    seed: int,
    utilisations,
    min_at_full_load: int,
    distinct: int,
    stop_after_extra: int,
    maximum: int = 300,
):
    """(chosen count, {overlay: [busy-hour work at 1, 2, ... copies]}).

    Stops `stop_after_extra` copies after the first count at which every overlay
    qualifies.  Uses the same draws as `overlay_entries`, so the two agree.
    """
    histogram = hour_histogram(per_term, arrival_key)
    lowest = min(offset for offset, _ in histogram.values())
    span = max(offset + len(w) for offset, w in histogram.values()) - lowest + 12 * 168 + 1
    totals = {o: np.zeros(span) for o in overlays}
    rngs = {o: np.random.default_rng(seed * 100 + o) for o in overlays}
    work: dict[int, list[float]] = {o: [] for o in overlays}
    chosen = None
    for count in range(1, maximum + 1):
        for overlay in overlays:
            running = totals[overlay]
            for term in pool:
                weeks = int(rngs[overlay].integers(0, 12))
                offset, hours = histogram[term]
                start = offset - lowest + weeks * 168
                running[start : start + len(hours)] += hours
            work[overlay].append(float(running.max()))
        if chosen is None and all(
            servers_acceptable(
                level_servers(work[o][-1], utilisations), min_at_full_load, distinct
            )
            for o in overlays
        ):
            chosen = count
        if chosen is not None and count >= chosen + stop_after_extra:
            break
    if chosen is None:
        raise RuntimeError(
            f"no copy count up to {maximum} reaches {min_at_full_load} servers at full load"
        )
    return chosen, work


def week_index(arrival: np.ndarray, weeks: np.ndarray) -> np.ndarray:
    """Position of each job's whole week inside the trace's week set."""
    week = np.floor((arrival - REFERENCE_MONDAY_S) / WEEK_S).astype(np.int64)
    position = np.searchsorted(weeks, week)
    if not np.array_equal(weeks[np.minimum(position, len(weeks) - 1)], week):
        raise AssertionError("a job falls outside the trace's week set")
    return position.astype(np.int16)


def week_set(
    pool, per_term: dict, arrival_key: str, copies: int, overlays, seed: int
) -> np.ndarray:
    """The union of whole weeks touched by the overlays that will be simulated."""
    weeks: set[int] = set()
    for overlay in overlays:
        arrival, _, _, _ = superpose(
            overlay_entries(pool, copies, overlay, seed), per_term, arrival_key
        )
        weeks |= set(
            np.unique(
                np.floor((arrival - REFERENCE_MONDAY_S) / WEEK_S).astype(np.int64)
            ).tolist()
        )
        del arrival
    return np.array(sorted(weeks), dtype=np.int64)


def _k1_candidates(pool, seed: int, repeats: int):
    """The pool listed `repeats` times in a drawn order, each copy with its week shift."""
    order = np.random.default_rng(seed).permutation(repeats * len(pool))
    listed = list(pool) * repeats
    shifts = np.random.default_rng(seed + 1).integers(0, 12, repeats * len(pool))
    return [(listed[i], int(shifts[n])) for n, i in enumerate(order)]


def _k1_peak(totals, histogram, lowest, term: str, weeks: int) -> tuple[int, np.ndarray, float]:
    offset, hours = histogram[term]
    start = offset - lowest + weeks * 168
    return start, hours, float((totals[start : start + len(hours)] + hours).max())


class _SingleServerState:
    """The running superposition of the single-server selection: peak, copies, history."""

    def __init__(self, per_term: dict, arrival_key: str):
        self.histogram = hour_histogram(per_term, arrival_key)
        self.lowest = min(offset for offset, _ in self.histogram.values())
        span = (
            max(offset + len(w) for offset, w in self.histogram.values())
            - self.lowest
            + 12 * 168
            + 1
        )
        self.totals = np.zeros(span)
        self.current = 0.0
        self.selected: list[tuple[str, int]] = []
        self.states: list[tuple[int, float]] = []

    @property
    def utilisation(self) -> float:
        return self.current / 3600.0

    def peak_after(self, term: str, weeks: int) -> float:
        return max(
            self.current, _k1_peak(self.totals, self.histogram, self.lowest, term, weeks)[2]
        )

    def add(self, term: str, weeks: int, peak: float) -> None:
        start, hours, _ = _k1_peak(self.totals, self.histogram, self.lowest, term, weeks)
        self.totals[start : start + len(hours)] += hours
        self.current = peak
        self.selected.append((term, int(weeks)))
        self.states.append((len(self.selected), self.utilisation))

    def best_addition(self, pool, target: float, window):
        """The (class-term, shift) landing closest to the target without passing the top."""
        best = None
        for term in sorted(pool):
            for weeks in range(12):
                peak = self.peak_after(term, weeks)
                if peak / 3600.0 > window[1] or peak <= self.current + 1e-9:
                    continue
                distance = abs(peak / 3600.0 - target)
                if best is None or distance < best[0]:
                    best = (distance, term, weeks, peak)
        return best


def single_server_pool(
    pool, per_term: dict, arrival_key: str, seed: int, target: float, window, repeats: int = 8
):
    """Class-term copies whose busiest-hour utilisation at one server sits near `target`.

    Two phases, because a copy whose own peak misses the current busiest hour is free and
    the random phase can therefore run out of candidates below the window.  Phase 1 adds
    drawn copies while the utilisation stays under the window's top, stopping at the first
    state that reaches `target`.  Phase 2, only when phase 1 ended below the window's
    bottom, repeatedly adds the (class-term, shift) whose result lands closest to `target`.
    Of the states inside the window the one closest to `target` is kept, and the selection
    is a prefix of the additions, so the returned utilisation is the returned entries'.
    """
    state = _SingleServerState(per_term, arrival_key)
    for term, weeks in _k1_candidates(pool, seed, repeats):
        peak = state.peak_after(term, weeks)
        if peak / 3600.0 > window[1]:
            continue
        state.add(term, weeks, peak)
        if state.utilisation >= target:
            break
    while state.utilisation < window[0]:
        best = state.best_addition(pool, target, window)
        if best is None:
            break
        state.add(best[1], best[2], best[3])
    inside = [
        (abs(rho - target), n, rho) for n, rho in state.states if window[0] <= rho <= window[1]
    ]
    if not inside:
        raise RuntimeError(
            f"the single-server selection reached utilisation {state.utilisation:.3f}, "
            f"outside {tuple(window)}"
        )
    _, count, rho = min(inside)
    return state.selected[:count], rho


def single_server_copies(
    pool, per_term: dict, arrival_key: str, seed: int, copies: int, repeats: int = 8
):
    """The first `copies` drawn class-term copies, and the utilisation they reach.

    How many copies the single-server trace superposes is a design value, selected once
    on the pool named in the configuration by `single_server_pool` and pinned there.  On
    any other pool that count is reused and nothing here looks at the utilisation before
    it stops: selecting copies by the busy hour they produce would be choosing a design
    value on that pool's data, which is exactly what must not happen on the sealed pool.
    The utilisation that comes out is reported as it is.  See ADR 0006.

    A pool with fewer class-terms is listed as many times as it takes to offer `copies`
    candidates: the count is the frozen value, the number of listings follows from it.
    """
    state = _SingleServerState(per_term, arrival_key)
    listings = max(repeats, -(-copies // max(len(pool), 1)))
    drawn = _k1_candidates(pool, seed, listings)
    if len(drawn) < copies:
        raise RuntimeError(f"{len(pool)} class-terms cannot offer {copies} copies")
    for term, weeks in drawn[:copies]:
        state.add(term, weeks, state.peak_after(term, weeks))
    return state.selected, state.utilisation


@dataclass(frozen=True)
class PoolInputs:
    """Per-row inputs of a simulated trace, and the class-terms it superposes."""

    per_term: dict
    pool: list
    in_deadline_window: np.ndarray
    in_exam: np.ndarray
    is_heavy: np.ndarray
    executed_work_s: np.ndarray
    keep: np.ndarray
    info: dict


def pool_inputs(
    prepared,
    static: dict,
    arrival: np.ndarray,
    header_s: np.ndarray,
    terms,
    limit_s: float,
    deadline_window_s: float,
    arrival_key: str = "arr",
) -> PoolInputs:
    """Rows of the terms in `terms` that may enter a simulated trace, grouped by class-term.

    A row qualifies when its term is in the list and it is not one of the zero-cost
    blocks that never ran.  The deadline-window and exam flags and the heavy label are
    attached here, so the trace carries everything the metrics need.
    """
    rows = prepared.submission_rows
    semester = prepared.semester[rows]
    executed = np.minimum(prepared.cost_s[rows], limit_s)
    to_deadline = static["a_end"] - arrival
    in_window = (to_deadline <= deadline_window_s) & (to_deadline >= 0)
    in_exam = (
        (static["a_is_exam"] == 1)
        & (arrival >= static["a_start"])
        & (arrival <= static["a_end"])
    )
    in_pool = np.isin(semester, list(terms))
    keep = in_pool & prepared.simulatable
    heavy = executed > prepared.heavy_threshold
    codes, uniques = pd.factorize(static["class_term"])
    per_term = {}
    for code in np.unique(codes[keep]):
        index = np.flatnonzero((codes == code) & keep)
        order = np.argsort(header_s[index], kind="stable")
        per_term[uniques[code]] = {
            "ts": header_s[index][order],
            "arr": arrival[index][order],
            "svc": executed[index][order],
            "idx": index[order],
            "base": base_shift(header_s[index].min()),
        }
    info = {
        "rows": int(in_pool.sum()),
        "zero_dropped": int((in_pool & ~prepared.simulatable).sum()),
        "jobs": int(keep.sum()),
        "work_s": round(float(executed[keep].sum()), 1),
    }
    return PoolInputs(
        per_term=per_term,
        pool=sorted(per_term),
        in_deadline_window=in_window,
        in_exam=in_exam,
        is_heavy=heavy,
        executed_work_s=executed,
        keep=keep,
        info=info,
    )


def build_overlay(
    inputs: PoolInputs,
    pool,
    copies: int,
    overlay: int,
    seed: int,
    weeks: np.ndarray,
    utilisations,
    arrival_key: str = "arr",
    scores: dict | None = None,
    entries=None,
    servers=None,
) -> dict:
    """One overlay, as the arrays a trace is made of.

    `entries` overrides the drawn copies of the pool, and `servers` overrides the load
    levels: together they are how the single-server trace is built, which superposes a
    selection of its own at one fixed server count instead of three derived ones.
    """
    arrival, service, rows, _ = superpose(
        entries if entries is not None else overlay_entries(pool, copies, overlay, seed),
        inputs.per_term,
        arrival_key,
    )
    work = busy_hour_work(arrival, service)
    servers = list(servers) if servers is not None else level_servers(work, utilisations)
    index = week_index(arrival, weeks)
    arrival = rebase(arrival)
    if np.any(np.diff(arrival) < 0):
        raise AssertionError("the superposed arrivals are not sorted")
    out = {
        "a": arrival,
        "svc": service,
        "dl": inputs.in_deadline_window[rows],
        "exam": inputs.in_exam[rows],
        "hvt": inputs.is_heavy[rows],
        "wk": index,
        "weeks": weeks.astype(np.int64),
        "K": np.array(servers, np.int64),
        "W": np.float64(work),
        "copies": np.int64(copies),
        "job_row": rows,
    }
    for name, values in (scores or {}).items():
        out[name] = np.asarray(values)[rows].astype(np.float64)
    return out
