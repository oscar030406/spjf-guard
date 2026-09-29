"""Mean over the five overlays of timeout_overlays.csv, and the paired Guard - Timeout
difference in gap closed per overlay, at each load and promise."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    rows = list(csv.DictReader(open(HERE / "timeout_overlays.csv", encoding="utf-8")))
    cells = defaultdict(dict)
    for r in rows:
        if r["policy"] == "Timeout-grid":
            continue
        cells[(int(r["level"]), r["policy"])][int(r["overlay"])] = r
    print("level policy            p99_dl  gap_closed  worst_max_excess  worst_harm  violations")
    for level in (0, 1, 2):
        for name in ("FCFS", "SJF", "SPJF-E", "Guard(300)", "Fixed(300)", "Timeout(300)",
                     "Guard(600)", "Fixed(600)", "Timeout(600)",
                     "Guard(1200)", "Fixed(1200)", "Timeout(1200)"):
            per = cells[(level, name)]
            n = len(per)
            p99 = sum(float(r["p99_dl_s"]) for r in per.values()) / n
            gap = sum(float(r["gap_closed"]) for r in per.values()) / n
            exc = max(float(r["max_excess_s"]) for r in per.values())
            harm = max(float(r["harm_s"]) for r in per.values())
            viol = sum(int(r["bound_violations"] or 0) for r in per.values())
            print(f"{level:5d} {name:16s} {p99:8.2f}  {gap:10.4f}  {exc:16.1f}  {harm:10.1f}"
                  f"  {viol if name.startswith('Timeout') else '':>10}  (n={n})")
    print("\npaired gap closed, Guard(G) - Timeout(G), per overlay")
    for level in (0, 1, 2):
        for promise in ("300", "600", "1200"):
            g = cells[(level, f"Guard({promise})")]
            t = cells[(level, f"Timeout({promise})")]
            diffs = [float(g[o]["gap_closed"]) - float(t[o]["gap_closed"]) for o in sorted(g)]
            print(f"  level {level} G={promise:>4}: " + "  ".join(f"{d:+.3f}" for d in diffs)
                  + f"   mean {sum(diffs) / len(diffs):+.3f}  min {min(diffs):+.3f}")


if __name__ == "__main__":
    main()
