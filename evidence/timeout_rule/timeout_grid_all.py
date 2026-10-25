"""The Timeout(theta) grid of timeout_overlays.py on overlays 1-4, so that the
equal-worst-excess comparison of Section 8 rests on all five overlays.

timeout_overlays.py ran the grid on overlay 0 only.  This script calls its run_cell with
grid=True on the other four overlays and the three loads, and writes the rows in the same
columns to timeout_grid_all.csv.  Overlay 0 is not rerun; its rows stay in
timeout_overlays.csv.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from timeout_overlays import OVERLAYS, ROOT, cfgmod, run_cell  # noqa: E402


def main() -> None:
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml")
    rows: list[dict] = []
    for overlay in (1, 2, 3, 4):
        for level in (0, 1, 2):
            started = time.time()
            run_cell(cfg, OVERLAYS[overlay], overlay, level, rows, grid=True)
            print(f"overlay {overlay} level {level} done [{time.time() - started:.0f} s]", flush=True)
            for r in rows[-19:]:
                print("  " + "  ".join(f"{key}={r[key]}" for key in (
                    "policy", "theta_s", "p99_dl_s", "gap_closed", "harm_s", "max_excess_s",
                    "bound_violations")), flush=True)
    with open(HERE / "timeout_grid_all.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("EXIT 0")


if __name__ == "__main__":
    main()
