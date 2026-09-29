"""Why the sealed terms close more of the gap than the development ones, in figures.

    uv run python scripts/sealed_dev_contrast.py

Reads only outputs the development and sealed runs already wrote, and simulates nothing:

* the gap closed by SPJF-E and Guard(600) under the online protocol, and the guard's cost
  (SPJF-E minus Guard), from each pool's `online_comparison.csv`; at the busiest load the
  change in the guard's gap between the pools splits exactly into the change in SPJF-E's
  gap and the change in the guard's cost;
* the same ratio, (FCFS - policy) / (FCFS - SJF), on the 99th percentile over all jobs and
  on the mean wait, with FCFS and SJF from each pool's `main_table.csv`;
* the share of jobs that arrive in the 24 hours before a deadline, which is the set the
  primary metric reads, from `same_copy_exposure_cells.csv`;
* the pair of busiest-load cells, one per pool, with the same number of servers and the
  closest realised utilisation, and the guard's gap in each (`online_cells.csv`,
  `main_cells.csv`).

Writes outputs/sealed_dev_contrast/contrast.csv, one row per figure with the spelling the
paper prints; scripts/check_paper_numbers.py accepts a sealed figure in prose when it is in
that column.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard.experiment import provenance  # noqa: E402

POOLS = ("dev", "sealed")
POLICIES = ("SPJF-E|online", "Guard(600)|online")
METRICS = {"all": "p99_all_s", "mean": "mean_s"}
BUSIEST = 2
FIELDS = ("quantity", "pool", "level", "policy", "value", "printed")


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _row(quantity, pool, level, policy, value, digits) -> dict:
    return {
        "quantity": quantity,
        "pool": pool,
        "level": level,
        "policy": policy,
        "value": repr(float(value)),
        "printed": f"{value:.{digits}f}",
    }


def gap_rows(pool: str, main_table: list[dict], comparison: list[dict]) -> list[dict]:
    """Gap closed on the primary metric, on p99 over all jobs and on the mean, and the cost."""
    reference = {(r["level"], r["policy"]): r for r in main_table}
    online = {(r["level"], r["policy"]): r for r in comparison}
    rows = []
    for level in sorted({r["level"] for r in comparison}):
        fcfs, sjf = reference[(level, "FCFS")], reference[(level, "SJF")]
        gaps = {}
        for policy in POLICIES:
            row = online[(level, policy)]
            gaps[policy] = float(row["gap_closed"])
            rows.append(_row("gap_dl", pool, level, policy, gaps[policy], 3))
            for name, column in METRICS.items():
                top = float(fcfs[column]) - float(row[column])
                span = float(fcfs[column]) - float(sjf[column])
                rows.append(_row(f"gap_{name}", pool, level, policy, top / span, 3))
        cost = gaps["SPJF-E|online"] - gaps["Guard(600)|online"]
        rows.append(_row("guard_cost", pool, level, "Guard(600)|online", cost, 3))
    return rows


def decomposition_rows(rows: list[dict]) -> list[dict]:
    """Guard(sealed) - Guard(dev) = [SPJF-E(sealed) - SPJF-E(dev)] + [cost(dev) - cost(sealed)].

    The split is exact: cost is SPJF-E minus Guard in each pool.
    """
    level = str(BUSIEST)

    def value(quantity, pool, policy):
        (hit,) = [
            r
            for r in rows
            if (r["quantity"], r["pool"], r["level"], r["policy"])
            == (quantity, pool, level, policy)
        ]
        return float(hit["value"])

    guard = value("gap_dl", "sealed", "Guard(600)|online") - value(
        "gap_dl", "dev", "Guard(600)|online"
    )
    ranking = value("gap_dl", "sealed", "SPJF-E|online") - value(
        "gap_dl", "dev", "SPJF-E|online"
    )
    cost = value("guard_cost", "dev", "Guard(600)|online") - value(
        "guard_cost", "sealed", "Guard(600)|online"
    )
    return [
        _row("difference", "sealed-dev", level, "Guard(600)|online", guard, 3),
        _row("ranking_part", "sealed-dev", level, "SPJF-E|online", ranking, 3),
        _row("cost_part", "sealed-dev", level, "Guard(600)|online", cost, 3),
    ]


def share_row(pool: str, exposure: list[dict]) -> dict:
    """Share of jobs in the 24 hours before a deadline, over the pool's overlays."""
    cells = {(r["overlay"], r["level"]): r for r in exposure}
    deadline = sum(int(r["deadline_jobs"]) for r in cells.values())
    jobs = sum(int(r["jobs"]) for r in cells.values())
    return _row("deadline_share_pct", pool, "", "", 100 * deadline / jobs, 1)


def busiest_cells(main_cells: list[dict], online_cells: list[dict]) -> dict[str, dict]:
    """Per overlay at the busiest load: servers, utilisation, FCFS p99, span, guard gap."""
    level = str(BUSIEST)
    by = {(r["overlay"], r["policy"]): r for r in main_cells if r["level"] == level}
    guard = {
        r["overlay"]: float(r["gap_closed"])
        for r in online_cells
        if r["level"] == level and r["policy"] == "Guard(600)|online"
    }
    cells = {}
    for overlay in sorted(guard):
        fcfs, sjf = by[(overlay, "FCFS")], by[(overlay, "SJF")]
        cells[overlay] = {
            "servers": int(fcfs["servers"]),
            "rho": float(fcfs["rho_realised"]),
            "fcfs_p99_dl": float(fcfs["p99_dl_s"]),
            "span": float(fcfs["p99_dl_s"]) - float(sjf["p99_dl_s"]),
            "guard_gap": guard[overlay],
        }
    return cells


def matched_rows(dev: dict[str, dict], sealed: dict[str, dict]) -> list[dict]:
    """The dev and sealed cells with equal servers and the closest realised utilisation."""
    pairs = [
        (abs(d["rho"] - s["rho"]), od, os_)
        for od, d in dev.items()
        for os_, s in sealed.items()
        if d["servers"] == s["servers"]
    ]
    _, od, os_ = min(pairs)
    rows = []
    for pool, overlay, cell in (("dev", od, dev[od]), ("sealed", os_, sealed[os_])):
        policy = f"overlay {overlay}"
        rows += [
            _row("matched_servers", pool, str(BUSIEST), policy, cell["servers"], 0),
            _row("matched_rho", pool, str(BUSIEST), policy, cell["rho"], 3),
            _row("matched_fcfs_p99_dl", pool, str(BUSIEST), policy, cell["fcfs_p99_dl"], 1),
            _row("matched_span", pool, str(BUSIEST), policy, cell["span"], 1),
            _row("matched_guard_gap", pool, str(BUSIEST), policy, cell["guard_gap"], 3),
        ]
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs", type=Path, default=ROOT / "outputs")
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "outputs" / "sealed_dev_contrast"
    )
    options = parser.parse_args()
    o = options.outputs
    inputs: list[Path] = []
    rows: list[dict] = []
    cells: dict[str, dict] = {}
    for pool in POOLS:
        paths = {
            "main_table": o / f"{pool}_tables" / "main_table.csv",
            "main_cells": o / f"{pool}_tables" / "main_cells.csv",
            "comparison": o / f"{pool}_online_visibility" / "online_comparison.csv",
            "online_cells": o / f"{pool}_online_visibility" / "online_cells.csv",
            "exposure": o / f"{pool}_consistent_visibility" / "same_copy_exposure_cells.csv",
        }
        inputs += paths.values()
        data = {name: _read(path) for name, path in paths.items()}
        rows += gap_rows(pool, data["main_table"], data["comparison"])
        rows.append(share_row(pool, data["exposure"]))
        cells[pool] = busiest_cells(data["main_cells"], data["online_cells"])
    rows += decomposition_rows(rows)
    rows += matched_rows(cells["dev"], cells["sealed"])
    options.out_dir.mkdir(parents=True, exist_ok=True)
    out = options.out_dir / "contrast.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    provenance.write(
        options.out_dir,
        produced_by="scripts/sealed_dev_contrast.py",
        config_path=ROOT / "configs" / "main.yaml",
        outputs=[out],
        inputs=inputs,
        arguments={"outputs": str(options.outputs)},
    )
    for row in rows:
        print(row["quantity"], row["pool"], row["level"], row["policy"], row["printed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
