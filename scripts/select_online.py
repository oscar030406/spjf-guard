"""Restricted reselection of the Guard parameters under the online protocol.

    uv run python scripts/select_online.py candidates --top 4
    uv run python scripts/run_online_visibility.py --pool validation --variants online \
        --candidates outputs/online_selection/candidates.csv \
        --out-dir outputs/online_selection/validation
    uv run python scripts/select_online.py choose

Rerunning the whole 258-point selection with every schedule replayed online is out of
reach, so the candidates are the ``--top`` feasible points of every family at every
promise under the original protocol (selection_v4's frontier, ranked by the selection
rule).  The same rule -- feasible when harm <= G/2 in every validation cell, then the
largest worst-cell gap -- is then applied to the online replays of those candidates, and
also to their original-clock replays, which must return selection_v4's picks.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import grids  # noqa: E402
from spjf_guard.experiment import select as sel  # noqa: E402

OUT = ROOT / "outputs" / "online_selection"


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def grid_point(row: dict[str, str]) -> grids.GridPoint:
    """The configured grid point a frontier or candidate row names."""
    return grids.GridPoint(
        row["family"],
        float(row["point_promise_s"]),
        float(row["b0_base_s"]),
        float(row["eta"]),
        float(row["gam_base_s"]),
        row["name"],
    )


def candidates(cfg, selection: Path, top: int) -> list[dict]:
    points = grids.grid_points(cfg["scheduling"]["selection"]["grids"], cfg.promises_s)
    by_key = {(p.family, p.b0_base_s, p.eta, p.gam_base_s, p.promise_s): p for p in points}
    frontier = [
        r for r in _rows(selection / "selection_frontier.csv") if r["feasible"] == "True"
    ]
    chosen: dict[str, dict] = {}
    for promise in cfg.promises_s:
        for family in ("fixed", "capped", "hybrid"):
            rows = [
                r
                for r in frontier
                if float(r["promise_s"]) == promise and r["family"] == family
            ]
            rows.sort(
                key=lambda r: (
                    -float(r["worst_gap_closed"]),
                    float(r["worst_harm_s"]),
                    float(r["b0_base_s"]),
                    float(r["eta"]),
                    float(r["gam_base_s"]),
                )
            )
            for r in rows[:top]:
                b0, eta, gam = float(r["b0_base_s"]), float(r["eta"]), float(r["gam_base_s"])
                point = (
                    by_key.get((family, b0, eta, gam, promise))
                    or by_key[(family, b0, eta, gam, grids.ANY_PROMISE)]
                )
                chosen[point.name] = {
                    "name": point.name,
                    "family": point.family,
                    "point_promise_s": point.promise_s,
                    "b0_base_s": point.b0_base_s,
                    "eta": point.eta,
                    "gam_base_s": point.gam_base_s,
                }
    return list(chosen.values())


def _cells(cfg, rows, points, variant) -> list[sel.Cell]:
    out = []
    by_name = {p.name: p for p in points}
    for row in rows:
        base, label = row["policy"].split("|", 1)
        if label != variant or base not in by_name:
            continue
        point = by_name[base]
        k = int(row["k"])
        out.append(
            sel.Cell(
                overlay=int(row["overlay"]),
                level=int(row["level"]),
                family=point.family,
                promise_s=point.promise_s,
                b0_base_s=point.b0_base_s,
                eta=point.eta,
                gam_base_s=point.gam_base_s,
                gap_closed=float(row["gap_closed"]),
                harm_s=float(row["harm_s"]),
                realised_promise_s=grids.realised_promise(point, k, cfg.limit_s),
            )
        )
    return out


def choose(cfg, cells_csv: Path, candidates_csv: Path) -> list[dict]:
    points = [grid_point(r) for r in _rows(candidates_csv)]
    rows = _rows(cells_csv)
    harm_fraction = float(cfg["scheduling"]["selection"]["harm_fraction"])
    out = []
    for variant in ("original", "online"):
        cells = _cells(cfg, rows, points, variant)
        for choice in sel.choose(cells, harm_fraction):
            out.append({"variant": variant, **vars(choice)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("candidates", "choose"))
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--selection", type=Path, default=ROOT / "outputs" / "selection_v4")
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--candidates", type=Path, default=OUT / "candidates.csv")
    ap.add_argument("--cells", type=Path, default=OUT / "validation" / "online_cells.csv")
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    if args.action == "candidates":
        path = _write(candidates(cfg, args.selection, args.top), args.candidates)
        print(f"wrote {path}")
        return 0
    path = _write(choose(cfg, args.cells, args.candidates), OUT / "online_choices.csv")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
