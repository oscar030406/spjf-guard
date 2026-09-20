"""Choosing the guard's parameters, on validation overlays only.

    feasible   harm (the worst extra wait among the jobs FCFS would start within 1 s) is
               at most G/2 in every one of the 15 (overlay, load level) cells;
    objective  the deadline-window p99 gap closed in the WORST cell;
    choice     the feasible point with the largest worst-cell objective, ties to the
               smaller worst-cell harm, then smaller B0, then smaller eta, then smaller
               gamma.

The rule is applied four times per promise: once inside each of the three families, which
gives the ablation rows (Guard-fixed, Guard-age, Guard-queue), and once over all three
together, which gives the joint winner.  The joint winner is the paper's Guard(G): one
mechanism whose budget shape was chosen by a stated rule on data the results are not
reported on.  Nothing here reads a cell of the test trace.

A fixed-family point carries its own promise B0/k + (3 - 2/k)L, which is below G for
small budgets, so it is a candidate at G only when its promise, in its worst cell, is at
most G.  That is what makes the families comparable: every candidate at G actually
promises G.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from spjf_guard.experiment.grids import ANY_PROMISE, FAMILIES

FIXED_SENTINEL = float("inf")
"""B0 base standing for B0 = B_max, the equal-promise fixed comparator."""

JOINT = "joint"
"""Family label of the winner across the three families: the paper's Guard(G)."""


@dataclass(frozen=True)
class Cell:
    """One configuration measured in one (overlay, load level) cell of the validation
    trace."""

    overlay: int
    level: int
    family: str
    promise_s: float
    b0_base_s: float
    eta: float
    gam_base_s: float
    gap_closed: float
    harm_s: float
    realised_promise_s: float

    @property
    def key(self) -> tuple:
        return (self.family, self.promise_s, self.b0_base_s, self.eta, self.gam_base_s)


@dataclass(frozen=True)
class Choice:
    """The configuration the rule selects, with what decided it."""

    promise_s: float
    family: str
    b0_base_s: float
    eta: float
    gam_base_s: float
    worst_gap_closed: float
    worst_harm_s: float
    worst_promise_s: float
    harm_limit_s: float
    n_feasible: int
    n_candidates: int
    from_family: str = ""
    note: str = ""


def summarise(cells: list[Cell], harm_fraction: float = 0.5) -> dict:
    """{(family, G, B0 base, eta, gam base): worst gap, worst harm, worst promise, ...}.

    The worst cell is the least favourable one on each axis separately: the smallest gap
    closed and the largest harm need not come from the same cell, and the rule is
    deliberately that pessimistic.
    """
    grouped: dict[tuple, list[Cell]] = {}
    for c in cells:
        grouped.setdefault(c.key, []).append(c)
    sizes = {len(v) for v in grouped.values()}
    if len(sizes) > 1:
        raise ValueError(
            f"configurations were measured in different numbers of cells: {sorted(sizes)}"
        )
    out = {}
    for key, group in grouped.items():
        worst_gap = float(np.min([c.gap_closed for c in group]))
        worst_harm = float(np.max([c.harm_s for c in group]))
        worst_promise = float(np.max([c.realised_promise_s for c in group]))
        out[key] = {
            "worst_gap_closed": worst_gap,
            "worst_harm_s": worst_harm,
            "worst_promise_s": worst_promise,
            "n_cells": len(group),
        }
    return out


def candidates_at(summary: dict, promise: float, family: str | None = None) -> list[tuple]:
    """Every point that actually promises `promise`, optionally inside one family."""
    out = []
    for key, row in summary.items():
        fam, grid_promise = key[0], key[1]
        if family is not None and fam != family:
            continue
        if grid_promise == ANY_PROMISE:
            if row["worst_promise_s"] <= promise + 1e-9:
                out.append(key)
        elif grid_promise == promise:
            out.append(key)
    return out


def _rank(summary: dict, key: tuple) -> tuple:
    """The rule's ordering: bigger gap first, then less harm, then smaller parameters."""
    row = summary[key]
    return (row["worst_gap_closed"], -row["worst_harm_s"], -key[2], -key[3], -key[4])


def _pick(promise, label, keys, summary, harm_fraction) -> Choice | None:
    if not keys:
        return None
    limit = promise * harm_fraction
    feasible = [k for k in keys if summary[k]["worst_harm_s"] <= limit]
    note, pool = "", feasible
    if not pool:
        pool = [min(keys, key=lambda k: summary[k]["worst_harm_s"])]
        note = "no feasible configuration; fell back to the smallest worst-cell harm"
    best = max(pool, key=lambda k: _rank(summary, k))
    row = summary[best]
    return Choice(
        promise_s=promise,
        family=label,
        b0_base_s=best[2],
        eta=best[3],
        gam_base_s=best[4],
        worst_gap_closed=row["worst_gap_closed"],
        worst_harm_s=row["worst_harm_s"],
        worst_promise_s=row["worst_promise_s"],
        harm_limit_s=limit,
        n_feasible=len(feasible),
        n_candidates=len(keys),
        from_family=best[0],
        note=note,
    )


def choose(cells: list[Cell], harm_fraction: float = 0.5) -> list[Choice]:
    """Per-family bests and the joint winner, for every promise, in that order."""
    summary = summarise(cells, harm_fraction)
    promises = sorted({c.promise_s for c in cells if c.promise_s != ANY_PROMISE})
    out: list[Choice] = []
    for promise in promises:
        for family in FAMILIES:
            choice = _pick(
                promise, family, candidates_at(summary, promise, family), summary, harm_fraction
            )
            if choice is not None:
                out.append(choice)
        joint = _pick(promise, JOINT, candidates_at(summary, promise), summary, harm_fraction)
        if joint is not None:
            out.append(joint)
    return out


def frontier(cells: list[Cell], harm_fraction: float = 0.5) -> list[dict]:
    """Every candidate of every promise with its worst-cell numbers and feasibility.

    The frontier is what lets a reader see how flat the choice is, instead of taking the
    winner on trust.
    """
    summary = summarise(cells, harm_fraction)
    rows = []
    for promise in sorted({c.promise_s for c in cells if c.promise_s != ANY_PROMISE}):
        limit = promise * harm_fraction
        for key in candidates_at(summary, promise):
            row = summary[key]
            rows.append(
                {
                    "promise_s": promise,
                    "family": key[0],
                    "b0_base_s": key[2],
                    "eta": key[3],
                    "gam_base_s": key[4],
                    "worst_gap_closed": row["worst_gap_closed"],
                    "worst_harm_s": row["worst_harm_s"],
                    "worst_promise_s": row["worst_promise_s"],
                    "harm_limit_s": limit,
                    "feasible": row["worst_harm_s"] <= limit,
                }
            )
    rows.sort(key=lambda r: (r["promise_s"], r["family"], -r["worst_gap_closed"]))
    return rows


def next_better_point(cells, choice: Choice, harm_fraction: float = 0.5) -> str:
    """The infeasible point just above the choice, which says what the constraint cost."""
    summary = summarise(cells, harm_fraction)
    keys = candidates_at(
        summary, choice.promise_s, None if choice.family == JOINT else choice.family
    )
    better = [
        k
        for k in keys
        if summary[k]["worst_gap_closed"] > choice.worst_gap_closed
        and summary[k]["worst_harm_s"] > choice.harm_limit_s
    ]
    if not better:
        return "none: the chosen point has the best worst-cell gap among the candidates"
    best = max(better, key=lambda k: summary[k]["worst_gap_closed"])
    row = summary[best]
    return (
        f"{best[0]} B0={best[2]:g} eta={best[3]:g} gam={best[4]:g} "
        f"(gap {row['worst_gap_closed']:.4f}, harm {row['worst_harm_s']:.1f} s, "
        f"infeasible by {row['worst_harm_s'] - choice.harm_limit_s:.1f} s)"
    )
