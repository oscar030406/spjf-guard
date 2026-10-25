"""Write the coordinates of paper/figures/fig_operating_region.tex (reviewer 3, comment h).

Run from the repository root (standard library only):

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe \
        evidence/revision_r1/figures/make_operating_region.py

Gap closed and harm of Guard(300|600|1200) and unguarded SPJF-E against the offered load.
Selection done here, nothing else:

- capacity_curve.csv (capacity scan, k = 1..20 on fixed arrivals): rows Guard(G) and
  SPJF-E; busy_hour_offered_load_mean as the load, gap_closed, harm_s.  gap_closed is
  empty at k = 20 (FCFS and SJF both have p99 0) and is written as nan, which pgfplots
  leaves out.
- main_table.csv (Table 9 and Supplementary Table S6): rows Guard(G) and SPJF-E at
  levels 0, 1, 2; rho_realised, k, gap_closed, harm_s.
"""

from __future__ import annotations

from figgen import define, rows, table, write_block

SCRIPT = "evidence/revision_r1/figures/make_operating_region.py"
CAPACITY = "evidence/weakness1_attack/capacity_curve.csv"
MAIN = "outputs/dev_tables/main_table.csv"
POLICIES = {"three": "Guard(300)", "six": "Guard(600)", "twelve": "Guard(1200)", "spjf": "SPJF-E"}


def main() -> int:
    capacity, main_rows = rows(CAPACITY), rows(MAIN)
    body = [
        "% \\oprCap<policy>: capacity scan, k = 1..20; \\oprTab<policy>: Table 9, levels 0-2.",
        "% rho = busy_hour_offered_load_mean (scan) or rho_realised (Table 9).",
    ]
    for tag, policy in POLICIES.items():
        scan = sorted((r for r in capacity if r["policy"] == policy), key=lambda r: int(r["k"]))
        assert [int(r["k"]) for r in scan] == list(range(1, 21)), policy
        body += table(
            f"oprCap{tag}",
            ["k", "rho", "gap", "harm"],
            [
                [r["k"], r["busy_hour_offered_load_mean"], r["gap_closed"] or "nan", r["harm_s"]]
                for r in scan
            ],
        )
        cells = sorted((r for r in main_rows if r["policy"] == policy), key=lambda r: r["level"])
        assert [r["level"] for r in cells] == ["0", "1", "2"], policy
        body += table(
            f"oprTab{tag}",
            ["level", "k", "rho", "gap", "harm"],
            [[r["level"], r["k"], r["rho_realised"], r["gap_closed"], r["harm_s"]] for r in cells],
        )
    first = next(r for r in capacity if r["policy"] == "FCFS" and r["k"] == "1")
    body += [
        "% Offered load at k = 1 (busy_hour_offered_load_mean); at k servers it is this / k.",
        define("oprLoadPerServer", f"{float(first['busy_hour_offered_load_mean']):.2f}"),
    ]
    path = write_block("fig_operating_region.tex", SCRIPT, [CAPACITY, MAIN], body)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
