"""Overlay traces with the co-ending groups merged or dropped, for a sensitivity run.

    uv run python scripts/build_coending_overlays.py --variant merged|dropped \
        --out-dir <dir> [--config configs/main.yaml] [--overlays 0,1,2,3,4]

A co-ending group is a set of at least two submission blocks of one user in one term that
end in the same second (`prepared.co_ending`); these runs lengthened each other.  The two
treatments change only which jobs enter the simulated trace, as the earlier pipeline's
`sbatch` and `sdrop` did (evidence/codebench_service_v2/service_precheck_v2.py,
`p2_inputs`):

    dropped  every member of every group in the pool leaves the trace.
    merged   each group becomes one job: its earliest-arriving member, with the largest
             capped cost of the group as its service.  Its score, labels and history are
             its own, the only ones that exist at that arrival.

Features, scores and the history of every row are those of the main cache; everything
after the job set (copies probe, weeks, servers, overlays) is `build_overlays.build`
unchanged, so each variant selects its own copies and server counts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_overlays  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402

VARIANTS = ("merged", "dropped")


def apply_variant(prepared, arrival: np.ndarray, terms, limit_s: float, variant: str) -> dict:
    """Change `prepared` in place so that `pool_inputs` sees the variant's job set."""
    rows = prepared.submission_rows
    group = prepared.co_ending
    members = np.flatnonzero(
        np.isin(prepared.semester[rows], list(terms)) & prepared.simulatable & (group >= 0)
    )
    if variant == "dropped":
        prepared.simulatable[members] = False
        return {"groups": len(np.unique(group[members])), "removed": len(members)}
    order = members[np.lexsort((members, arrival[members], group[members]))]
    starts = np.flatnonzero(np.r_[True, group[order][1:] != group[order][:-1]])
    keep = order[starts]
    capped = np.minimum(prepared.cost_s[rows[order]], limit_s)
    prepared.cost_s[rows[keep]] = np.maximum.reduceat(capped, starts)
    prepared.simulatable[np.setdiff1d(order, keep)] = False
    return {"groups": len(keep), "members": len(order), "removed": len(order) - len(keep)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=VARIANTS, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--overlays", default=None)
    ap.add_argument(
        "--score-parquet",
        type=Path,
        default=ROOT / "data" / "derived" / "package_ranking_scores" / "forward_scores.parquet",
    )
    args = ap.parse_args()
    args.pool, args.single_server, args.no_scores, args.unseal = "primary", False, False, False

    cfg = cfgmod.load(args.config)
    terms = build_overlays.pool_terms(cfg, args.pool)
    sealed.guard_semesters(terms, ROOT, unseal=False)
    overlays = (
        [int(x) for x in args.overlays.split(",")]
        if args.overlays
        else list(cfg["overlay"]["overlays"])
    )
    unchanged = build_overlays.pool_inputs

    def variant_inputs(prepared, static, arrival, header_s, pool, limit_s, *rest, **kw):
        info = apply_variant(prepared, arrival, pool, limit_s, args.variant)
        print(f"co-ending {args.variant}: {info}", flush=True)
        return unchanged(prepared, static, arrival, header_s, pool, limit_s, *rest, **kw)

    build_overlays.pool_inputs = variant_inputs
    with sealed.recording(ROOT, "scripts/build_coending_overlays.py", terms, False) as outcome:
        return build_overlays.build(cfg, args, terms, overlays, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
