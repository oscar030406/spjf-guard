"""The full measurement: wait for an idle machine, then parts 1 and 2.

    python measure.py [--poll 30] [--need 120] [--reps 5] [--out measure.json]

Idle means: total CPU below 15 % in every 30 s poll and no other python process with a
working set above 1 GB, for 120 s in a row.  There is no timeout.  The observed load of
the qualifying window, the CPU model and the power plan go into the output, which is
rewritten after each part so a crash keeps what was measured.
"""

from __future__ import annotations

import argparse
import time

import common
import scaling
import wholerun


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=float, default=30.0)
    ap.add_argument("--need", type=float, default=120.0)
    ap.add_argument("--cpu-limit", type=float, default=15.0)
    ap.add_argument("--mem-gb", type=float, default=1.0)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--exps", default="2,3,4,5,6")
    ap.add_argument("--min-seconds", type=float, default=1.0)
    ap.add_argument("--out", default="measure.json")
    a = ap.parse_args()
    path = common.OUT / a.out
    result = {"machine": common.machine_info(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    log(f"waiting for an idle machine (poll {a.poll:g} s, need {a.need:g} s)")
    result["idle_wait"] = common.wait_until_idle(a.poll, a.need, a.cpu_limit,
                                                  int(a.mem_gb * 2**30), log=log)
    result["measure_started"] = time.strftime("%Y-%m-%d %H:%M:%S")
    common.write_json(path, result)
    t0 = time.time()
    result["whole_run"] = wholerun.run(a.reps, [0, 1, 2], log=log)
    result["whole_run"]["elapsed_s"] = round(time.time() - t0, 1)
    ok = all(c["match"] for c in result["whole_run"]["checks"])
    result["gate_exact_reproduction"] = "PASS" if ok else "FAIL"
    log(f"part 1 done: reproduction {result['gate_exact_reproduction']}")
    common.write_json(path, result)
    t0 = time.time()
    result["scaling"] = scaling.measure([int(x) for x in a.exps.split(",")],
                                        ["queue", "production"], a.min_seconds, 5, log=log)
    result["scaling"]["elapsed_s"] = round(time.time() - t0, 1)
    result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    common.write_json(path, result)
    log(f"done -> {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
