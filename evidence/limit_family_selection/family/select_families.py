"""Choose the family and then its parameters on the 15 validation cells only (#31).

    python evidence/limit_family_selection/family/select_families.py gates
    python evidence/limit_family_selection/family/select_families.py choose \
        --new <validation online_cells.csv> [--new ...] --out evidence/limit_family_selection/family/choices.csv

The rule, fixed on 2026-10-03 (local 07:10, UTC-4) before any validation row of Skip, Timeout or
Block existed and before any primary row of a non-paper policy was read:

Families and grids, every point replayed on the validation pool (overlays 0-4 x levels 0-2):
  Guard-fixed  A3 `fixed`: FIX-B<b> (constant budget b*k/4, promise B0/k + (3-2/k)L) and
               FIXEQ-G<G>, which is Fixed(G) (B0 = B_max; same Policy fields as policy.fixed)
  Guard-age    A3 `capped`, Guard-queue  A3 `hybrid`  (grids.realised_promise)
  Skip         Skip(G), N = floor(Gk/L - (2k-2)); Skip(n=m), N = floor(m*k/4),
               m in {4, 8, 16, 32, 64}; promise (N + 2k - 2) L / k
  Timeout      Timeout(G), theta = G - (3-2/k)L; Timeout(theta=t), t in THETA_GRID_S of
               evidence/timeout_rule/timeout_overlays.py; promise t + (3-2/k)L
  Aging        Aging(c=x), the configured credit grid (E14, outputs/online_aging); no promise
  Block        Block(W), W in {8, 32, 128, 512} (the G5 windows); no promise
For each G in {300, 600, 1200} and each clock (online is the result; original the reference):
  1. per point over the 15 cells: worst gap = min gap_closed, worst harm = max harm_s,
     worst promise = max realised promise (none for Aging and Block);
  2. candidates at G: points labelled G (A3 G-points, FIXEQ-G, Skip(G), Timeout(G)); unlabelled
     points (FIX-B, Skip(n=m), Timeout(theta=t)) whose worst promise <= G + 1e-9; every Aging
     and Block point (no promise, so only the harm constraint applies, as select_aging
     applies it at its reference promise 600);
  3. feasible: worst harm <= G/2;
  4. inside a family, select._pick: the feasible candidate with the largest worst gap, ties to
     smaller worst harm, then to smaller parameters (Guard: B0, eta, gam with FIXEQ's B0 = inf;
     Skip: m, Skip(G) as inf; Timeout: t, Timeout(G) as inf; Block: W), Aging ties to the
     larger credit (select_aging._choose).  No feasible candidate: the smallest worst harm,
     noted, and that pick takes no part in step 5;
  5. the three Guard families together as select.choose's joint (their parameters are
     comparable, so the same ordering runs over their union): this is the paper's Guard(G).
     Across Guard, Skip, Timeout, Aging and Block: the feasible pick with the largest worst
     gap, ties to smaller worst harm, then to that order of families.  The best pick among the
     promise-carrying families (Guard, Skip, Timeout) is reported beside the winner.
A Block row of the `fixed_point` variant is its online row (the same fixed point, reached by
iteration because Block has no online replay of its own).
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from select_aging import _choose as aging_choose  # noqa: E402
from select_aging import _summaries as aging_summaries  # noqa: E402
from select_online import grid_point  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import grids  # noqa: E402

PROMISES = (300.0, 600.0, 1200.0)
HARM_FRACTION = 0.5
SKIP_COUNTS = (4, 8, 16, 32, 64)
THETA_GRID_S = (15.0, 30.0, 60.0, 120.0, 240.0, 480.0, 960.0)
BLOCK_WIDTHS = (8, 32, 128, 512)
GUARD = {"fixed": "Guard-fixed", "capped": "Guard-age", "hybrid": "Guard-queue"}
ORDER = ("Guard", "Skip", "Timeout", "Aging", "Block")
PROMISED = ("Guard", "Skip", "Timeout")
A3 = ROOT / "outputs" / "online_selection"
AGING = ROOT / "outputs" / "online_aging" / "online_cells.csv"
CELLS = {(o, lv) for o in range(5) for lv in range(3)}


@dataclass(frozen=True)
class Point:
    family: str
    name: str
    at: float | None  # the G it is labelled with; None: any G its own promise allows
    params: tuple  # tie-break, smaller first
    promise: object  # k -> realised promise in s, or None for a family without one


def guard_points(cfg) -> list[Point]:
    limit = cfg.limit_s
    out = []
    with open(A3 / "candidates_all.csv", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            p = grid_point(row)
            out.append(Point(
                GUARD[p.family], p.name, None if p.promise_s == grids.ANY_PROMISE else p.promise_s,
                (p.b0_base_s, p.eta, p.gam_base_s),
                lambda k, p=p: grids.realised_promise(p, k, limit)))
    return out


def skip_count(promise: float, k: int, limit: float) -> int:
    return int(math.floor(promise * k / limit - (2 * k - 2) + 1e-9))


def other_points(cfg) -> list[Point]:
    limit = cfg.limit_s
    out = []
    for g in PROMISES:
        out.append(Point("Skip", f"Skip({g:g})", g, (math.inf,),
                         lambda k, g=g: (skip_count(g, k, limit) + 2 * k - 2) * limit / k))
        out.append(Point("Timeout", f"Timeout({g:g})", g, (math.inf,), lambda k, g=g: g))
    for m in SKIP_COUNTS:
        out.append(Point("Skip", f"Skip(n={m})", None, (float(m),),
                         lambda k, m=m: ((m * k) // 4 + 2 * k - 2) * limit / k))
    for t in THETA_GRID_S:
        out.append(Point("Timeout", f"Timeout(theta={t:g})", None, (t,),
                         lambda k, t=t: t + (3.0 - 2.0 / k) * limit))
    for c in cfg["scheduling"]["aging_baseline"]["credit_per_s_grid"]:
        out.append(Point("Aging", f"Aging(c={float(c):g})", None, (-float(c),), None))
    for w in BLOCK_WIDTHS:
        out.append(Point("Block", f"Block({w})", None, (float(w),), None))
    return out


def read_cells(paths) -> dict[tuple, dict]:
    """{(clock, policy name): {(overlay, level): row}} from rov's online_cells.csv files."""
    out: dict[tuple, dict] = {}
    for path in paths:
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                name, label = row["policy"].split("|", 1)
                clock = "online" if label == "fixed_point" else label
                cell = (int(row["overlay"]), int(row["level"]))
                block = out.setdefault((clock, name), {})
                if cell in block and block[cell] != row:
                    raise SystemExit(f"{path}: two different rows for {name}|{label} {cell}")
                block[cell] = row
    return out


def summary(point: Point, block: dict) -> dict:
    if set(block) != CELLS:
        raise SystemExit(f"{point.name}: {len(block)} of the 15 validation cells")
    rows = list(block.values())
    return {
        "worst_gap_closed": min(float(r["gap_closed"]) for r in rows),
        "worst_harm_s": max(float(r["harm_s"]) for r in rows),
        "worst_promise_s": None if point.promise is None
        else max(point.promise(int(r["k"])) for r in rows),
    }


def candidates(points, summaries, promise):
    out = []
    for p in points:
        s = summaries[p.name]
        if p.at is not None:
            if p.at == promise:
                out.append(p)
        elif s["worst_promise_s"] is None or s["worst_promise_s"] <= promise + 1e-9:
            out.append(p)
    return out


def pick(label, keys, summaries, promise) -> dict | None:
    """select._pick over these candidates."""
    if not keys:
        return None
    limit = promise * HARM_FRACTION
    feasible = [p for p in keys if summaries[p.name]["worst_harm_s"] <= limit]
    pool, note = feasible, ""
    if not pool:
        pool = [min(keys, key=lambda p: summaries[p.name]["worst_harm_s"])]
        note = "no feasible configuration; fell back to the smallest worst-cell harm"
    best = max(pool, key=lambda p: (summaries[p.name]["worst_gap_closed"],
                                    -summaries[p.name]["worst_harm_s"],
                                    *(-v for v in p.params)))
    return {"promise_s": promise, "family": label, "name": best.name,
            "from_family": best.family, **summaries[best.name], "harm_limit_s": limit,
            "n_feasible": len(feasible), "n_candidates": len(keys), "note": note}


def choose(points, cells, clocks) -> list[dict]:
    out = []
    for clock in clocks:
        present = [p for p in points if (clock, p.name) in cells]
        summaries = {p.name: summary(p, cells[(clock, p.name)]) for p in present}
        for promise in PROMISES:
            picks = {}
            for family in (*GUARD.values(), *ORDER[1:], "Guard"):
                members = [p for p in present
                           if p.family == family or (family == "Guard" and p.family in GUARD.values())]
                if not members:
                    continue
                choice = pick(family, candidates(members, summaries, promise), summaries, promise)
                if choice is not None:
                    picks[family] = choice
                    out.append({"clock": clock, **choice})
            for label, allowed in (("winner", ORDER), ("winner_with_promise", PROMISED)):
                feasible = [picks[f] for f in allowed if f in picks and not picks[f]["note"]]
                if feasible:
                    best = max(feasible, key=lambda c: (c["worst_gap_closed"], -c["worst_harm_s"],
                                                        -ORDER.index(c["family"])))
                    out.append({"clock": clock, **best, "family": label,
                                "note": f"families present: {sorted(picks)}"})
    return out


def gates(cfg) -> int:
    failures = 0
    # Gate 1: this code on A3's guard grid reproduces online_choices_all.csv.
    points = guard_points(cfg)
    cells = read_cells([A3 / "validation_all" / "online_cells.csv"])
    mine = [c for c in choose(points, cells, ("original", "online")) if c["family"] in
            (*GUARD.values(), "Guard")]
    by_name = {p.name: p for p in points}
    with open(A3 / "online_choices_all.csv", encoding="utf-8", newline="") as handle:
        theirs = list(csv.DictReader(handle))
    family_of = {"Guard-fixed": "fixed", "Guard-age": "capped", "Guard-queue": "hybrid",
                 "Guard": "joint"}
    if len(mine) != len(theirs):
        raise SystemExit(f"gate 1: {len(mine)} choices against {len(theirs)}")
    for m, t in zip(mine, theirs, strict=True):
        p = by_name[m["name"]]
        ours = {"variant": m["clock"], "promise_s": str(m["promise_s"]),
                "family": family_of[m["family"]], "b0_base_s": str(p.params[0]),
                "eta": str(p.params[1]), "gam_base_s": str(p.params[2]),
                "worst_gap_closed": str(m["worst_gap_closed"]),
                "worst_harm_s": str(m["worst_harm_s"]),
                "worst_promise_s": str(m["worst_promise_s"]),
                "harm_limit_s": str(m["harm_limit_s"]), "n_feasible": str(m["n_feasible"]),
                "n_candidates": str(m["n_candidates"]),
                "from_family": [k for k, v in GUARD.items() if v == m["from_family"]][0],
                "note": m["note"]}
        bad = [k for k in t if ours[k] != t[k]]
        failures += bool(bad)
        print(f"gate 1 {t['variant']:8s} G={t['promise_s']:>6s} {t['family']:7s} {m['name']:24s} "
              f"{'equal in all ' + str(len(t)) + ' columns' if not bad else 'DIFFER ' + str(bad)}")
    # Gate 2: the Aging family at G = 600 is E14's choice, and select_aging's rule agrees.
    aging = read_cells([AGING])
    aging_points = [p for p in other_points(cfg) if p.family == "Aging"]
    for clock in ("online", "original"):
        mine = [c for c in choose(aging_points, aging, (clock,))
                if c["family"] == "Aging" and c["promise_s"] == 600.0][0]
        rows = [{"credit_per_s": float(name[8:-1]), "gap_closed": float(r["gap_closed"]),
                 "harm_s": float(r["harm_s"])}
                for (c, name), block in aging.items() if c == clock for r in block.values()]
        reference = aging_choose(aging_summaries(cfg, rows))
        ok = mine["name"] == f"Aging(c={reference['credit_per_s']:g})" == "Aging(c=0.1)"
        failures += not ok
        print(f"gate 2 {clock}: this rule at G=600 picks {mine['name']} (worst gap "
              f"{mine['worst_gap_closed']!r}, worst harm {mine['worst_harm_s']!r}); "
              f"select_aging._choose picks credit {reference['credit_per_s']!r}; "
              f"{'equal, credit 0.1' if ok else 'DIFFER'}")
    print(f"{failures} gate failures")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("gates", "choose"))
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--new", type=Path, action="append", default=[],
                    help="online_cells.csv of the Skip, Timeout and Block validation runs")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    if args.action == "gates":
        return gates(cfg)
    points = guard_points(cfg) + other_points(cfg)
    cells = read_cells([A3 / "validation_all" / "online_cells.csv", AGING, *args.new])
    missing = sorted({p.family for p in points if ("online", p.name) not in cells})
    rows = choose(points, cells, ("online", "original"))
    for r in rows:
        r["worst_promise_s"] = "" if r["worst_promise_s"] is None else r["worst_promise_s"]
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out}: {len(rows)} rows; families without validation rows: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
