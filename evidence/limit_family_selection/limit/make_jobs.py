"""Write jobs_proposed.txt: the gate cell again, then one queue job per (L, overlay, level).

    python evidence/limit_family_selection/limit/make_jobs.py --gb 10

The first job replays the gate cell (L = 60 s, o0 l2) with the fixed-point check that was added
after the gate run; gate1_compare.py is then run on its directory.  The
second is the L = 45 s smoke (o0 l0, the cheapest cell), which the run did not get to.  L = 60 s is otherwise not
proposed: its rows are outputs/dev_online_visibility's.  At L = 90 and 120 s SPJF-E is left out:
neither its trace nor its scores depend on L.  Policies that the run's L leaves without a budget
are listed and dropped by run_limit.py itself (they are FCFS).
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _setup import code_tag  # noqa: E402

GUARDED = [f"{kind}({g})" for kind in ("Guard", "Fixed", "Skip") for g in (300, 600, 1200)]
POLICIES = {45: ["SPJF-E", *GUARDED], 90: GUARDED, 120: GUARDED}
tag = code_tag(HERE.parent / "_setup.py", HERE.parent / "fixed_point.py", HERE / "run_limit.py")


def job(name: str, limit: int, policies: list[str], overlay: int, level: int, gb: int) -> str:
    return json.dumps({"name": name, "gb": gb, "cmd": [
        "{python}", "-u", "evidence/limit_family_selection/limit/run_limit.py",
        "--config", f"evidence/limit_family_selection/limit/main_L{limit}.yaml",
        "--policies", ",".join(policies), "--reps", str(overlay), "--levels", str(level),
        "--workers", "1", "--resume", "--out-dir", f"outputs/limit_sensitivity_{tag}/jobs/{name}"]})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gb", type=int, required=True)
    args = ap.parse_args()
    lines = [job("lim_L60_o0_l2", 60, ["SPJF-E", *GUARDED], 0, 2, args.gb)]
    for limit, policies in POLICIES.items():
        for level in (2, 1, 0):
            for overlay in range(5):
                lines.append(job(f"lim_L{limit}_o{overlay}_l{level}", limit, policies,
                                 overlay, level, args.gb))
    first = [line for line in lines if '"lim_L45_o0_l0"' in line]  # the L = 45 s smoke
    lines = lines[:1] + first + [line for line in lines[1:] if line not in first]
    (HERE / "jobs_proposed.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} jobs, tag {tag}")


if __name__ == "__main__":
    main()
