"""Feed the platform's measured arrivals and executed work into the paper's simulator
and compare its per-job waits with the ones the platform actually produced.

This is the third independent system of the test-bed plan: the platform is a Next.js
service calling a Python engine over HTTP, the simulator is the package kernel, and
nothing is shared between them but the numbers in the job records.

Input is one or more `jobs-<cell>.jsonl` files written by
`apps/classroom/lib/server/classroom-dispatch.ts`.  For each cell it rebuilds the input
`(a_i, C_i, score_i, k)` from the record, runs the same policy in the simulator, and
reports the signed per-job difference `simulated - measured`.

Run from the paper repository root:

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-sync python evidence/platform_testbed/replay_simulator.py \
        evidence/platform_testbed/records/jobs-smoke-*.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

SCORE_KEY = "proxy"


def load_cell(path: Path) -> dict[str, list[dict]]:
    cells: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cells.setdefault(row["cell"], []).append(row)
    return cells


def policy_for(rows: list[dict], k: int):
    from spjf_guard.sim.policy import fcfs, guard, spjf

    name = rows[0]["policy"]
    if name == "fcfs":
        return fcfs(), "FCFS"
    if name == "spjf":
        return spjf(SCORE_KEY, "SPJF-E"), "SPJF-E"
    if name == "guard":
        return (
            guard(
                rows[0]["promiseMs"] / 1000.0,
                k,
                max(r["limitMs"] for r in rows) / 1000.0,
                rows[0]["b0Ms"] / 1000.0,
                rows[0]["eta"],
                SCORE_KEY,
            ),
            f"Guard({rows[0]['promiseMs'] / 1000:g})",
        )
    raise SystemExit(f"unknown policy {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "records" / "simulator_replay.json"))
    parser.add_argument("--append", action="store_true",
                        help="merge these rows into --out, replacing any row with the same cell")
    args = parser.parse_args()

    from spjf_guard.sim import Trace, simulate

    report = []
    for pattern in args.files:
        candidate = Path(pattern)
        matches = (
            sorted(Path().glob(pattern))
            if not candidate.is_absolute() and any(ch in pattern for ch in "*?[")
            else [candidate]
        )
        for path in matches:
            for cell, rows in load_cell(path).items():
                rows.sort(key=lambda r: r["enqueueUs"])
                k = rows[0]["k"]
                base = rows[0]["enqueueUs"]
                # The simulator's per-job cap is one number, so the run uses the largest
                # class cap; each job's own executed work is already capped in the record,
                # so no job can exceed its own limit here either.
                limit_s = max(r["limitMs"] for r in rows) / 1000.0
                arrival_us = np.array([r["enqueueUs"] - base for r in rows], dtype=np.int64)
                service_us = np.array([round(r["executedMs"] * 1000) for r in rows], dtype=np.int64)
                score = np.array([r["predictedCostS"] for r in rows], dtype=np.float64)
                measured = np.array([r["waitMs"] / 1000.0 for r in rows], dtype=np.float64)

                trace = Trace(arrival_us, service_us, {SCORE_KEY: score}, limit_s=limit_s)
                policy, label = policy_for(rows, k)
                result = simulate(trace, policy, k)
                simulated = result.wait_us / 1e6
                difference = simulated - measured

                # The package simulator only carries the completed-work wrapper.  A cell run
                # under reservation-and-refund charging is therefore compared against a
                # DIFFERENT mechanism, and the difference below measures that, not fidelity.
                comparable = not (rows[0]["policy"] == "guard"
                                  and rows[0]["charging"] == "reservation")

                report.append({
                    "cell": cell,
                    "policy_in_simulator": label,
                    "comparable": comparable,
                    "note": None if comparable else (
                        "the simulator has no reservation-and-refund wrapper; this row compares "
                        "rule R against Algorithm 1 and is a mechanism difference, not a fidelity "
                        "measure"
                    ),
                    "k": k,
                    "jobs": len(rows),
                    "measured_mean_wait_s": float(measured.mean()),
                    "simulated_mean_wait_s": float(simulated.mean()),
                    "measured_max_wait_s": float(measured.max()),
                    "simulated_max_wait_s": float(simulated.max()),
                    "mean_signed_error_s": float(difference.mean()),
                    "max_abs_error_s": float(np.abs(difference).max()),
                    "jobs_with_error_over_1s": int((np.abs(difference) > 1.0).sum()),
                })

    merged = report
    out = Path(args.out)
    if args.append and out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
        fresh = {row["cell"] for row in report}
        merged = [row for row in existing if row["cell"] not in fresh] + report
    merged.sort(key=lambda row: row["cell"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
