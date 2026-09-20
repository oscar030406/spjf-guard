"""This package's selection against v3.2's, family by family.

    uv run python scripts/compare_selection.py [--ours outputs/selection_v3] \
        [--theirs prechecks/main_v3/v32] [--out outputs/selection_v3/vs_v32.csv]

The two runs search the same pre-stated grids under the same rule, but not on the same
predictions: this package refits the ranking score deterministically, v3.2 used the
stored one.  So a difference is possible and is not by itself an error.  What the report
has to show, when the two disagree, is both candidates measured both ways -- ours under
our predictions, theirs under theirs -- so that a reader can see whether the rule moved
or only the score did.  Our result is the one that stands; the row is flagged.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAMILIES = ("fixed", "capped", "hybrid")


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ours_by_family(rows: list[dict]) -> dict:
    return {(r["family"], float(r["promise_s"])): r for r in rows if r["family"] in FAMILIES}


def theirs_by_family(rows: list[dict]) -> dict:
    return {(r["family"], float(r["G"])): r for r in rows if r["family"] in FAMILIES}


def our_worst(rows: list[dict]) -> dict:
    """{(family, G, B0 base, eta, gam base): worst-cell numbers} from our own grid."""
    return {
        (
            r["family"],
            float(r["promise_s"]),
            float(r["b0_base_s"]),
            float(r["eta"]),
            float(r["gam_base_s"]),
        ): r
        for r in rows
    }


def their_worst(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        out[(r["family"], float(r["B0_base"]), float(r["eta"]), float(r["gam_base"]))] = r
    return out


def _their_numbers(table: dict, family: str, b0: float, eta: float, gam: float) -> tuple:
    row = table.get((family, b0, eta, gam))
    if row is None:
        return ("", "")
    return (row["worst_gap"], row["worst_harm"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", type=Path, default=ROOT / "outputs" / "selection_v3")
    ap.add_argument("--theirs", type=Path, default=ROOT / "prechecks" / "main_v3" / "v32")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    ours = ours_by_family(read(args.ours / "selected_parameters.csv"))
    theirs = theirs_by_family(read(args.theirs / "selected_params.csv"))
    our_grid = our_worst(read(args.ours / "selection_worst.csv"))
    their_grid = their_worst(read(args.theirs / "select_worst.csv"))

    rows = []
    for (family, promise), mine in sorted(ours.items(), key=str):
        other = theirs.get((family, promise))
        mine_point = (
            family,
            promise,
            float(mine["b0_base_s"]),
            float(mine["eta"]),
            float(mine["gam_base_s"]),
        )
        same = other is not None and (
            # v3.2 wrote its budgets rounded to the cent, so compare at that resolution
            abs(float(other["B0_base"]) - mine_point[2]) <= 0.005 + 1e-9
            and abs(float(other["eta"]) - mine_point[3]) <= 1e-9
            and abs(float(other["gam_base"]) - mine_point[4]) <= 1e-9
        )
        their_point = (
            None
            if other is None
            else (
                family,
                promise,
                float(other["B0_base"]),
                float(other["eta"]),
                float(other["gam_base"]),
            )
        )
        their_of_mine = _their_numbers(
            their_grid, family, mine_point[2], mine_point[3], mine_point[4]
        )
        ours_of_theirs = ("", "")
        if their_point is not None and their_point in our_grid:
            row = our_grid[their_point]
            ours_of_theirs = (row["worst_gap_closed"], row["worst_harm_s"])
        rows.append(
            {
                "family": family,
                "promise_s": promise,
                "same_point": same,
                "ours_b0": mine_point[2],
                "ours_eta": mine_point[3],
                "ours_gam": mine_point[4],
                "ours_gap_ours": mine["worst_gap_closed"],
                "ours_harm_ours": mine["worst_harm_s"],
                "ours_gap_v32": their_of_mine[0],
                "ours_harm_v32": their_of_mine[1],
                "v32_b0": "" if other is None else other["B0_base"],
                "v32_eta": "" if other is None else other["eta"],
                "v32_gam": "" if other is None else other["gam_base"],
                "v32_gap_v32": "" if other is None else other["worst_gap"],
                "v32_harm_v32": "" if other is None else other.get("worst_harm_s", ""),
                "v32_gap_ours": ours_of_theirs[0],
                "v32_harm_ours": ours_of_theirs[1],
                "kept": "ours",
                "flag": "" if same else "DIFFERS: predictions were refit; ours stands",
            }
        )

    out = args.out or args.ours / "vs_v32.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    agreeing = sum(1 for r in rows if r["same_point"])
    print(f"{agreeing} of {len(rows)} per-family selections agree with v3.2")
    for row in rows:
        if row["same_point"]:
            print(
                f"  [{row['family']:6s}] G = {row['promise_s']:6.0f}: same point "
                f"(B0 {row['ours_b0']:g}, eta {row['ours_eta']:g}, gam {row['ours_gam']:g})"
            )
            continue
        print(
            f"  [{row['family']:6s}] G = {row['promise_s']:6.0f}: ours B0 {row['ours_b0']:g}, "
            f"eta {row['ours_eta']:g}, gam {row['ours_gam']:g} "
            f"(gap {row['ours_gap_ours']}, harm {row['ours_harm_ours']} under our scores; "
            f"gap {row['ours_gap_v32'] or 'n/a'}, harm {row['ours_harm_v32'] or 'n/a'} under "
            f"v3.2's) against v3.2's B0 {row['v32_b0']}, eta {row['v32_eta']}, "
            f"gam {row['v32_gam']} (gap {row['v32_gap_v32']}, harm {row['v32_harm_v32']} under "
            f"v3.2's; gap {row['v32_gap_ours'] or 'n/a'}, harm {row['v32_harm_ours'] or 'n/a'} "
            f"under ours) -- keeping ours"
        )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
