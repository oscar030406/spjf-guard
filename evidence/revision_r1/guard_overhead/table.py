"""Final tables from measure.json: whole-run cost per event and per-operation scaling.

    python table.py [--whole measure.json] [--scaling measure.json] [--out table.md]

Each input is either measure.json (keys whole_run / scaling) or the file wholerun.py /
scaling.py writes on its own.  Writes <out> (Markdown) and the same rows as CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
import math

import common


def load(name, key):
    data = json.loads((common.OUT / name).read_text(encoding="utf-8"))
    return data.get(key, data), data


def whole_rows(whole):
    spjf = {r["level"]: r for r in whole["summary"] if r["policy"] == "SPJF-E"}
    rows = []
    for r in whole["summary"]:
        base = spjf[r["level"]]
        rows.append({
            "level": r["level"], "k": r["k"], "policy": r["policy"], "repeats": r["repeats"],
            "cpu_ns_per_event": r["cpu_ns_per_event_median"],
            "cpu_ns_per_event_min": r["cpu_ns_per_event_min"],
            "cpu_ns_per_event_max": r["cpu_ns_per_event_max"],
            "cpu_ns_per_job": r["cpu_ns_per_job_median"],
            "extra_ns_per_job_vs_spjf": r["cpu_ns_per_job_median"] - base["cpu_ns_per_job_median"],
            "wall_s": r["wall_s_median"], "cpu_s": r["cpu_s_median"],
            "peak_queue": r["peak_queue"],
            "mean_waiting_at_dispatch": r["mean_waiting_at_dispatch"],
            "window_rebuilds": r["n_rebuild"],
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--whole", default="measure.json")
    ap.add_argument("--scaling", default="measure.json")
    ap.add_argument("--out", default="table.md")
    a = ap.parse_args()
    whole, top = load(a.whole, "whole_run")
    scal, _ = load(a.scaling, "scaling")
    wr = whole_rows(whole)
    lines = [f"# Guard overhead (overlay 0, n = {whole['n_jobs']:,} jobs)", ""]
    if "idle_wait" in top:
        first = top["idle_wait"]["polls"][0]
        lines.append(f"Idle at start: waited {top['idle_wait']['waited_s']} s; first qualifying "
                     f"poll {first['time']}, CPU {first['cpu_pct']} %, largest other python "
                     f"working set {first['max_python_ws_gb']} GB.")
    m = top.get("machine", {})
    lines += [f"Machine: {m.get('cpu_model')}, {m.get('logical_cpus')} logical CPUs, power "
              f"plan {m.get('power_plan')}, numba {m.get('numba')}, "
              f"NUMBA_NUM_THREADS={m.get('numba_num_threads')}.",
              f"Exact reproduction of main_cells.csv: {top.get('gate_exact_reproduction')}.", "",
              "## Whole runs (thread CPU time of one simulate_kernel call; events = 3n)", "",
              "| level | k | policy | ns/event median [min, max] | ns/job | extra ns/job vs "
              "SPJF-E | run CPU s | peak queue | mean waiting at dispatch |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in wr:
        lines.append(
            f"| {r['level']} | {r['k']} | {r['policy']} | {r['cpu_ns_per_event']:.1f} "
            f"[{r['cpu_ns_per_event_min']:.1f}, {r['cpu_ns_per_event_max']:.1f}] | "
            f"{r['cpu_ns_per_job']:.0f} | {r['extra_ns_per_job_vs_spjf']:+.0f} | "
            f"{r['cpu_s']:.2f} | {r['peak_queue']:,} | {r['mean_waiting_at_dispatch']:.1f} |")
    lines += ["", "## Per-operation cost against n waiting jobs (wall ns, median over repeats, "
              "generator subtracted)", "",
              "| geometry | n | log2 n | arrival | completion | dispatch (query + remove) | "
              "guard per job | base heap pop+push |", "|---|---|---|---|---|---|---|---|"]
    for d in scal["derived"]:
        lines.append(
            f"| {d['geometry']} | {d['n']:,} | {math.log2(d['n']):.1f} | {d['arrival_ns']:.1f} | "
            f"{d['completion_ns']:.1f} | {d['dispatch_ns']:.1f} "
            f"({d['query_ns']:.1f} + {d['remove_ns']:.1f}) | {d['guard_per_job_ns']:.1f} | "
            f"{d['heap_ns']:.1f} |")
    out = common.OUT / a.out
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out.with_suffix(".whole.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(wr[0]))
        w.writeheader()
        w.writerows(wr)
    with open(out.with_suffix(".scaling.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(scal["derived"][0]))
        w.writeheader()
        w.writerows(scal["derived"])
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
