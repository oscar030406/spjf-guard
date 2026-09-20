"""Every printed number of the package's development tables against v3.1's.

    uv run python scripts/diff_dev_tables.py \
        [--table outputs/dev_tables/main_table.csv] \
        [--v31 prechecks/main_v3/v31/table_main_primary.csv] \
        [--out outputs/dev_tables/diff_vs_v31.csv]

The package's kernel is the authority (ADR 0001: its clock is exact integer microseconds,
the exploratory kernel's is float64 seconds), so this is not a pass/fail gate.  It is the
list a reader of the paper needs: which printed figures move, by how much, and where.
Comparison happens at the precision the paper prints, not at full precision, because a
difference below the printed digit changes nothing a reader can see.

Exit status is 0 whatever it finds; the report is the product.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROMISES = (300.0, 600.0, 1200.0)

POLICY_LABEL = {
    "FCFS": "FCFS",
    "SJF": "SJF-ref",
    "SPJF-E": "SPJF-tweedie",
    "SPJF-log": "SPJF-M4",
}
for _g in PROMISES:
    POLICY_LABEL[f"Guard({_g:g})"] = f"CAP-G{_g:g}"
    POLICY_LABEL[f"Fixed({_g:g})"] = f"FIX-G{_g:g}"
    POLICY_LABEL[f"Fixed-admitted({_g:g})"] = f"FIXSEL-G{_g:g}"
    POLICY_LABEL[f"Skip({_g:g})"] = f"SKIP-G{_g:g}"
"""This package's policy name -> the label v3.1's table carries."""

FIELDS = (
    ("p99_dl_s", "p99_dl_s", 2, 1.0),
    ("gap_closed", "gap_closed", 3, 1.0),
    ("reduction_pct", "red_pct", 1, 1.0),
    ("mean_s", "mean_s", 3, 1.0),
    ("p99_all_s", "p99_all_s", 2, 1.0),
    ("max_excess_s", "max_excess_s", 1, 1.0),
    ("harm_s", "harm_wf1s_s", 1, 1.0),
    ("max_heavy_s", "max_heavy_s", 1, 1.0),
    ("fired_pct", "qw_fired", 1, 100.0),
    ("k", "k", 1, 1.0),
)
"""(our column, v3.1 column, digits the paper prints, factor applied to v3.1's value)."""


def _printed(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def read_table(path: Path, key_policy: str = "policy") -> dict:
    with open(path, encoding="utf-8") as fh:
        return {(int(r["level"]), r[key_policy]): r for r in csv.DictReader(fh)}


def compare(ours: dict, theirs: dict) -> tuple[list[dict], int, list[str]]:
    """Rows for the printed numbers that differ, how many were compared, what was absent."""
    differing, compared, missing = [], 0, []
    for (level, policy), row in sorted(ours.items()):
        label = POLICY_LABEL.get(policy)
        if label is None or (level, label) not in theirs:
            missing.append(f"L{level} {policy}")
            continue
        other = theirs[(level, label)]
        for field, column, digits, factor in FIELDS:
            if field not in row or column not in other:
                continue
            if row[field] == "" or other[column] in ("", "-"):
                continue
            mine, yours = float(row[field]), float(other[column]) * factor
            compared += 1
            if _printed(mine, digits) == _printed(yours, digits):
                continue
            differing.append(
                {
                    "level": level,
                    "rho_target": row.get("rho_target", ""),
                    "policy": policy,
                    "v31_policy": label,
                    "metric": field,
                    "digits": digits,
                    "package_printed": _printed(mine, digits),
                    "v31_printed": _printed(yours, digits),
                    "package_full": f"{mine:.9g}",
                    "v31_full": f"{yours:.9g}",
                    "difference": f"{mine - yours:.9g}",
                }
            )
    return differing, compared, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, default=ROOT / "outputs/dev_tables/main_table.csv")
    ap.add_argument(
        "--v31", type=Path, default=ROOT / "prechecks/main_v3/v31/table_main_primary.csv"
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    ours = read_table(args.table)
    theirs = read_table(args.v31)
    differing, compared, missing = compare(ours, theirs)
    out = args.out or args.table.with_name("diff_vs_v31.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "level",
        "rho_target",
        "policy",
        "v31_policy",
        "metric",
        "digits",
        "package_printed",
        "v31_printed",
        "package_full",
        "v31_full",
        "difference",
    ]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(differing)
    print(f"compared {compared} printed numbers, {len(differing)} differ")
    for row in differing:
        print(
            f"  L{row['level']} {row['policy']:22s} {row['metric']:14s} "
            f"{row['package_printed']} against v3.1's {row['v31_printed']}"
        )
    if missing:
        print(f"not in v3.1's table, not compared: {', '.join(missing)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
