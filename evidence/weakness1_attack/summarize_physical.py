"""Describe one completed timed-work run without a sampling interval."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

import numpy as np


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
POLICIES = ("FCFS", "SPJF-E", "Guard(300)")
COLORS = {"FCFS": "#526579", "SPJF-E": "#bc673c", "Guard(300)": "#167f78"}
QUANTILES = (0.5, 0.95, 0.99, 1.0)


def describe(values):
    array = np.asarray(values, dtype=float)
    if not len(array):
        return None
    return {
        "n": len(array),
        "mean": float(array.mean()),
        **{f"q{quantile:g}": float(np.quantile(array, quantile)) for quantile in QUANTILES},
    }


def summarize_run(
    *,
    run_dir: Path,
    profile: str,
    title: str,
    include_deadline: bool,
    numbers_name: str = "physical_numbers.json",
    log_name: str = "out_summarize_physical.txt",
    svg_name: str = "physical_validation.svg",
    png_name: str = "physical_validation.png",
) -> dict:
    start, cpu = time.perf_counter(), time.process_time()
    run_dir = Path(run_dir).resolve()
    os.environ["MPLCONFIGDIR"] = str(run_dir / "cache" / "matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = json.loads((run_dir / "physical_summary.json").read_text(encoding="utf-8"))
    if summary["completed_policies"] != list(POLICIES):
        raise RuntimeError("all three physical policies must complete in protocol order")
    output = {
        "profile": profile,
        "input": summary["input"],
        "confidence_interval": None,
        "interval_reason": "one selected window; no independent window replication",
        "policies": {},
    }
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for policy in POLICIES:
        slug = policy.lower().replace("(", "_").replace(")", "").replace("-", "_")
        jobs = [
            json.loads(line)
            for line in (run_dir / f"physical_{slug}_jobs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        jobs.sort(key=lambda job: job["job_id"])
        if [job["job_id"] for job in jobs] != list(range(summary["input"]["jobs"])):
            raise AssertionError(f"{policy} job identities do not match the summary")
        wait = np.array([job["actual_wait_ns"] / 1e9 for job in jobs])
        ideal = np.array([job["production_replay_wait_us"] / 1e6 for job in jobs])
        requested = np.array([job["requested_service_ns"] / 1e9 for job in jobs])
        release = np.array([job["target_release_offset_ns"] / 1e9 for job in jobs])
        deadline = np.array([job["in_deadline_window"] for job in jobs], bool)
        decision = np.array([job["decision_wall_overhead_ns"] / 1e6 for job in jobs])
        delta = wait - ideal
        policy_output = {
            "wait_s": describe(wait),
            "queue_wait_exceeding_1ms_jobs": int((wait > 0.001).sum()),
            "queue_wait_exceeding_1s_jobs": int((wait > 1).sum()),
            "physical_minus_ideal_wait_s": describe(delta),
            "absolute_physical_minus_ideal_wait_s": describe(np.abs(delta)),
            "decision_wall_ms": describe(decision),
            "decision_to_dispatch_ms": describe(
                [(job["dispatcher_dispatch_ns"] - job["decision_clock_ns"]) / 1e6
                 for job in jobs]
            ),
            "dispatch_to_start_ms": describe(
                [job["dispatch_to_worker_start_ns"] / 1e6 for job in jobs]
            ),
            "completion_receipt_lag_ms": describe(
                [job["completion_ipc_lag_ns"] / 1e6 for job in jobs]
            ),
            "decision_cpu_ms": describe(
                [job["decision_cpu_overhead_ns"] / 1e6 for job in jobs]
            ),
            "release_lateness_ms": describe(
                [job["release_lateness_ns"] / 1e6 for job in jobs]
            ),
            "measured_service_s": describe(
                [job["worker_holding_ns"] / 1e9 for job in jobs]
            ),
            "sleep_overshoot_ms": describe(
                [
                    (job["worker_holding_ns"] - job["requested_service_ns"]) / 1e6
                    for job in jobs
                ]
            ),
            "nominal_top_one_percent_work_share": float(
                np.sort(requested)[-max(1, int(np.ceil(0.01 * len(jobs)))) :].sum()
                / requested.sum()
            ),
            "audits": summary["audits"][policy],
        }
        if include_deadline:
            policy_output["deadline_wait_s"] = describe(wait[deadline])
        output["policies"][policy] = policy_output

        color = COLORS[policy]
        axes[0, 0].scatter(release, wait, s=5, alpha=0.6, color=color, label=policy)
        axes[0, 1].scatter(ideal, wait, s=5, alpha=0.6, color=color, label=policy)
        absolute_delta = np.sort(np.abs(delta))
        axes[1, 0].plot(
            absolute_delta,
            (np.arange(len(jobs)) + 1) / len(jobs),
            color=color,
            label=policy,
        )
        ordered = np.sort(decision)
        axes[1, 1].plot(
            ordered,
            (np.arange(len(jobs)) + 1) / len(jobs),
            color=color,
            label=policy,
        )

    maximum = max(axes[0, 1].get_xlim()[1], axes[0, 1].get_ylim()[1])
    axes[0, 1].plot([0, maximum], [0, maximum], color="#aaaaaa", lw=1, ls="--")
    axes[0, 0].set(
        xlabel="Target arrival offset (s)",
        ylabel="Measured wait (s)",
        title="Unthinned 300 s demand window",
    )
    axes[0, 1].set(
        xlabel="Ideal replay wait on measured a, C (s)",
        ylabel="Measured wait (s)",
        title="Per-job physical versus ideal wait",
    )
    axes[1, 0].set(
        xlabel="Absolute wait discrepancy (s)",
        ylabel="Fraction of jobs",
        title="Physical versus ideal discrepancy",
    )
    axes[1, 1].set(
        xlabel="Decision wall time (ms)",
        ylabel="Fraction of decisions",
        title="Instrumented selection overhead",
    )
    axes[1, 0].set_xscale("symlog", linthresh=0.001)
    axes[1, 1].set_xscale("symlog", linthresh=0.001)
    for axis in axes.flat:
        axis.grid(alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0, 0].legend(frameon=False)
    fig.suptitle(title, fontsize=13)
    fig.savefig(run_dir / svg_name)
    fig.savefig(run_dir / png_name, dpi=170)
    plt.close(fig)

    output["execution"] = {
        "wall_s": time.perf_counter() - start,
        "cpu_s": time.process_time() - cpu,
    }
    text = json.dumps(output, indent=2, allow_nan=False) + "\n"
    (run_dir / numbers_name).write_text(text, encoding="utf-8")
    (run_dir / log_name).write_text(text, encoding="utf-8")
    print(text, end="")
    return output


def main() -> None:
    summarize_run(
        run_dir=HERE,
        profile="development_overlay",
        title="Two-worker timed-work implementation — one selected development-overlay window",
        include_deadline=True,
    )


if __name__ == "__main__":
    main()
