"""Write jobs_proposed.txt: the Skip, Timeout and Block grids on the 15 validation cells.

    python evidence/limit_family_selection/family/make_jobs.py --gb 10 --block-gb 11

Three jobs per (overlay, level): the Skip grid and the Timeout grid on the online replay, the
Block windows on the fixed point.  The o0 l0 job of each group comes first: it is the smoke the
run did not get to (no heavy process was allowed when the jobs were written).  Guard (A3) and Aging (E14) already have their rows.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from _setup import code_tag  # noqa: E402
from select_families import BLOCK_WIDTHS, PROMISES, SKIP_COUNTS, THETA_GRID_S  # noqa: E402

GROUPS = {
    "skip": ("online", [f"Skip({g:g})" for g in PROMISES] + [f"Skip(n={m})" for m in SKIP_COUNTS]),
    "timeout": ("online", [f"Timeout({g:g})" for g in PROMISES]
                + [f"Timeout(theta={t:g})" for t in THETA_GRID_S]),
    "block": ("fixed_point", [f"Block({w})" for w in BLOCK_WIDTHS]),
}
tag = code_tag(HERE.parent / "_setup.py", HERE.parent / "fixed_point.py", HERE / "run_family.py",
               ROOT / "evidence" / "skipc_block_online" / "block_kernel.py")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gb", type=int, required=True)
    ap.add_argument("--block-gb", type=int, required=True)
    args = ap.parse_args()
    lines = []
    for group, (variant, policies) in GROUPS.items():
        for level in (2, 1, 0):
            for overlay in range(5):
                name = f"fam_{group}_o{overlay}_l{level}"
                lines.append(json.dumps({
                    "name": name, "gb": args.block_gb if group == "block" else args.gb, "cmd": [
                        "{python}", "-u", "evidence/limit_family_selection/family/run_family.py",
                        "--pool", "validation", "--variants", variant,
                        "--policies", ",".join(policies), "--reps", str(overlay),
                        "--levels", str(level), "--workers", "1", "--resume",
                        "--out-dir", f"outputs/family_selection_{tag}/validation/{name}"]}))
    first = [line for line in lines if '_o0_l0"' in line]  # the smokes: cheapest cell of each group
    lines = first + [line for line in lines if line not in first]
    (HERE / "jobs_proposed.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} jobs, tag {tag}")


if __name__ == "__main__":
    main()
