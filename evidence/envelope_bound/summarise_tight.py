"""Per (family, overlay set, level) summary of tight_bound.csv: rows, worst ratio of max
wait to the tight absolute bound, smallest per-job slack under the tight form, rows with
a tight violation.  Reads only tight_bound.csv.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-sync python \
      evidence/envelope_bound/summarise_tight.py > evidence/envelope_bound/out_summarise_tight.txt
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    with open(HERE / "tight_bound.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        overlays = "k1_rep0" if r["overlay"] == "k1_rep0" else "primary"
        groups[(r["family"], overlays, r["level"])].append(r)
    print(f"rows {len(rows)}")
    print("family  overlays  level  k      rows  max_ratio  (overlay, policy)"
          "            min_slack_s  (overlay, policy)            violations")
    for (fam, overlays, level), sub in sorted(groups.items()):
        top = max(sub, key=lambda r: float(r["ratio_max_wait_over_tight"]))
        low = min(sub, key=lambda r: float(r["min_slack_tight_s"]))
        ks = sorted({int(r["k"]) for r in sub})
        viol = sum(r["per_job_violations_tight"] != "0" for r in sub)
        print(f"{fam:6s}  {overlays:8s}  {level:5s}  {str(ks):6s} {len(sub):4d}"
              f"  {float(top['ratio_max_wait_over_tight']):.4f}"
              f"     ({top['overlay']}, {top['policy']}){'':4s}"
              f"  {float(low['min_slack_tight_s']):10.3f}  ({low['overlay']}, {low['policy']})"
              f"  {viol}")


if __name__ == "__main__":
    main()
