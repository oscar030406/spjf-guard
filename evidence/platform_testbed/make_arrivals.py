"""Cut one deadline-window arrival burst out of a development overlay and scale it
to the local two-worker service, for the open-loop demand rule of the platform test bed.

Only development material is opened.  The sealed terms are named in
`src/spjf_guard/data/sealed.py` and are never touched here: this script reads one
primary development overlay, whose path, byte count and SHA-256 are the ones recorded
in `evidence/weakness1_attack/development_inputs.json`, and it verifies all three
before parsing.  Only the arrival column and the deadline-window flag are read.

Two scalings, both stated in the output header:

1. time compression `alpha`: the 24 h deadline window is squeezed into the
   experiment window, so an arrival at source offset `t` fires at `t / alpha`;
2. count thinning: a fixed-seed uniform sample keeps `N = rho * k * T / E[C]`
   arrivals, so the offered load is the target `rho` at capacity `k`.

Run from the paper repository root:

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-sync python evidence/platform_testbed/make_arrivals.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = ROOT / "prechecks" / "weakness1_attack" / "development_inputs.json"
OUT_DIR = Path(__file__).resolve().parent / "records"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def development_overlay_path(rep: int) -> tuple[Path, dict]:
    """The recorded development overlay for `rep`, with its size and hash checked.

    The overlay at the canonical path was rebuilt after the weakness-1 run and no longer
    carries the recorded hash; the verified copy kept by that run's recovery step does,
    and is used when the canonical file does not match.  Either way a file is parsed only
    after its SHA-256 equals the one on record.
    """
    record = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert record["pool"] == "primary", "only the primary development pool is used here"
    assert record["unseal"] is False, "the recorded inputs must be the sealed-guard-off ones"
    entry = next(item for item in record["inputs"] if item["rep"] == rep)
    candidates = [
        ROOT / entry["path"],
        ROOT / "prechecks" / "weakness1_attack" / "raw" / "recovered_development" / f"primary_rep{rep}.npz",
    ]
    for path in candidates:
        if not path.exists() or path.stat().st_size != entry["bytes"]:
            continue
        if sha256_file(path) != entry["sha256"]:
            continue
        return path, {"terms": record["terms"], "rep": rep, "sha256": entry["sha256"]}
    raise SystemExit(
        "no development overlay on disk carries the recorded hash for rep "
        f"{rep}; looked at {[str(c) for c in candidates]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rep", type=int, default=0)
    parser.add_argument("--window-hours", type=float, default=24.0, help="source deadline window length")
    parser.add_argument("--experiment-seconds", type=float, default=7200.0, help="target experiment window")
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--rho", type=float, default=0.85)
    parser.add_argument("--mean-service-s", type=float, default=50.0,
                        help="measured mean executed work per job on this stack")
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--out", type=str, default=str(OUT_DIR / "arrivals_deadline_burst.csv"))
    args = parser.parse_args()

    path, provenance = development_overlay_path(args.rep)
    with np.load(path, allow_pickle=False) as store:
        # `a` and `svc` are stored in seconds (float64) in these overlays
        arrival_s = np.asarray(store["a"], dtype=np.float64)
        in_window = np.asarray(store["dl"], dtype=bool)

    selected = np.flatnonzero(in_window)
    if selected.size == 0:
        raise SystemExit("no deadline-window jobs in this overlay")
    window_s = args.window_hours * 3600.0

    # The deadline windows repeat through the overlay; take the busiest one, chosen on
    # arrival counts alone, with no policy outcome involved.
    bins = np.floor(arrival_s[selected] / window_s).astype(np.int64)
    ids, counts = np.unique(bins, return_counts=True)
    winner = int(ids[int(np.argmax(counts))])
    burst = arrival_s[selected][bins == winner]
    offsets_s = burst - burst.min()

    alpha = args.window_hours * 3600.0 / args.experiment_seconds
    target_n = int(round(args.rho * args.k * args.experiment_seconds / args.mean_service_s))
    rng = np.random.default_rng(args.seed)
    keep = np.sort(rng.choice(offsets_s.size, size=min(target_n, offsets_s.size), replace=False))
    kept = np.sort(offsets_s[keep] / alpha)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# open-loop arrival offsets, seconds from the start of the experiment window",
        f"# source: development overlay primary_rep{args.rep}, terms {','.join(provenance['terms'])}",
        f"# source sha256 {provenance['sha256']}",
        f"# busiest {args.window_hours:g} h deadline window of that overlay: {offsets_s.size} arrivals",
        f"# time compression alpha = {alpha:g} (24 h window -> {args.experiment_seconds:g} s)",
        f"# count thinning to rho = {args.rho:g} at k = {args.k} with E[C] = {args.mean_service_s:g} s",
        f"# kept {kept.size} of {offsets_s.size} arrivals, seed {args.seed}",
        "offset_s",
    ]
    out.write_text("\n".join(header + [f"{value:.3f}" for value in kept]) + "\n", encoding="utf-8")

    print(json.dumps({
        "overlay": str(path),
        "terms": provenance["terms"],
        "window_jobs": int(offsets_s.size),
        "alpha": alpha,
        "kept": int(kept.size),
        "first_offset_s": float(kept[0]),
        "last_offset_s": float(kept[-1]),
        "median_gap_s": float(np.median(np.diff(kept))) if kept.size > 1 else None,
        "out": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
