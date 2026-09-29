"""Compare overlays built by the package with the ones the exploratory pipeline stored.

    uv run python scripts/check_overlays.py --ours <dir> --theirs <dir> \
        [--pool primary] [--overlays 0,1,2,3,4]

Arrays compared: arrival, service, week index, deadline-window flag, exam flag, heavy
flag, the server counts, the busy-hour work and the copies count.  All must be equal
element for element.  The package additionally stores `job_row`, which the old files do
not carry, so it is reported rather than compared.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

COMPARED = ("a", "svc", "wk", "dl", "exam", "hvt", "K", "W", "copies", "weeks")


def compare_one(ours: Path, theirs: Path) -> list[dict]:
    rows = []
    with np.load(ours) as mine, np.load(theirs) as other:
        for name in COMPARED:
            if name not in other.files:
                rows.append(
                    {
                        "array": name,
                        "status": "absent from the stored file",
                        "differing": -1,
                        "worst": float("nan"),
                    }
                )
                continue
            a, b = np.asarray(mine[name]), np.asarray(other[name])
            if a.shape != b.shape:
                rows.append(
                    {
                        "array": name,
                        "status": f"shape {a.shape} vs {b.shape}",
                        "differing": -1,
                        "worst": float("nan"),
                    }
                )
                continue
            equal = np.array_equal(a, b)
            if a.dtype.kind in "fiub" and a.size:
                delta = np.abs(a.astype("float64") - b.astype("float64"))
                differing, worst = int((delta > 0).sum()), float(delta.max())
            else:
                differing, worst = (0 if equal else -1), float("nan")
            rows.append(
                {
                    "array": name,
                    "status": "equal" if equal else "DIFFERS",
                    "differing": differing,
                    "worst": worst,
                }
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", required=True, type=Path)
    ap.add_argument("--theirs", required=True, type=Path)
    ap.add_argument("--pool", default="primary")
    ap.add_argument("--overlays", default="0,1,2,3,4")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "overlay_check.csv")
    args = ap.parse_args()

    out_rows = []
    failures = 0
    for overlay in (int(x) for x in args.overlays.split(",")):
        ours = args.ours / f"{args.pool}_rep{overlay}.npz"
        theirs = args.theirs / f"{args.pool}_rep{overlay}.npz"
        if not ours.is_file() or not theirs.is_file():
            print(f"overlay {overlay}: missing {ours if not ours.is_file() else theirs}")
            failures += 1
            continue
        for row in compare_one(ours, theirs):
            out_rows.append({"pool": args.pool, "overlay": overlay, **row})
            failures += row["status"] != "equal"
        state = (
            "all equal"
            if all(r["status"] == "equal" for r in out_rows if r["overlay"] == overlay)
            else "DIFFERS"
        )
        print(f"overlay {overlay}: {state}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)
    for row in out_rows:
        if row["status"] != "equal":
            print(
                f"  overlay {row['overlay']} {row['array']}: {row['status']} "
                f"({row['differing']} elements, worst {row['worst']})"
            )
    print(f"wrote {args.out}; {failures} comparison(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
