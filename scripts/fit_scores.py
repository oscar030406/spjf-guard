"""Fit the ranking scores forward, from the parsed cache, inside the package.

    uv run python scripts/fit_scores.py --out <parquet> [--pool primary] \
        [--targets 2020-ERE,...] [--repeat] [--unseal]

Writes one column per score (`spjf_e`, the Tweedie estimate of expected cost, and
`spjf_log`, the log-scale control) over every submission row, `nan` outside the target
terms.  `--repeat` fits everything twice and asserts the two passes are identical, which
is the determinism check the configuration's LightGBM settings exist for.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.predict.forward import fit_forward, to_frame  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from build_overlays import clock_from  # noqa: E402


def development_terms(cfg) -> list:
    terms = cfg["semesters"]
    return (
        list(terms["train"])
        + list(terms["train_remote"])
        + list(terms["validation"])
        + list(terms["development_test"])
    )


def load_prepared(cfg, unseal: bool):
    """The event cache and the keys derived from it, guarded before anything is opened.

    The fit and anything that scores its output have to see the same rows in the same
    order -- the scores are stored by position -- so both read the cache through here.
    """
    from spjf_guard.data.events import load_events, prepare

    terms = development_terms(cfg)
    if unseal:
        terms += list(cfg["semesters"]["sealed_test"])
    sealed.guard_semesters(terms, ROOT, unseal=unseal)
    events = load_events(
        cfg.data_path("cache_dir"),
        cfg["data"]["events_file"],
        cfg["data"]["sealed_events_file"] if unseal else None,
    )
    prepared = prepare(
        events,
        seed=int(cfg["predictor"]["seed"]),
        limit_s=cfg.limit_s,
        train_terms=cfg["semesters"]["train"],
        zero_cost_drop_terms=cfg["clock"]["drop_zero_cost_terms"],
        jitter_key=cfg["clock"]["jitter"]["key"],
    )
    return events, prepared, terms


def run_once(cfg, targets, unseal: bool, quiet: bool = False):
    from spjf_guard.data.events import static_submission_columns

    events, prepared, terms = load_prepared(cfg, unseal)
    static = static_submission_columns(events, prepared)

    def report(entry):
        if not quiet:
            print(
                f"  [{entry['target']}] train {entry['n_train']:,} "
                f"({entry['train_terms']}), target {entry['n_target']:,}, "
                f"cut-offs from {entry['cutoff_source']} "
                f"(heavy {entry['heavy_threshold_s']:.4f} s)",
                flush=True,
            )

    return fit_forward(
        prepared,
        static,
        events,
        clock_from(cfg),
        cfg["predictor"],
        cfg.limit_s,
        targets,
        terms,
        progress=report,
    )


def terms_read(cfg, targets: list[str], unseal: bool) -> list[str]:
    """Every term this fit opens, each named once.

    An unsealed fit reads the sealed cache as well as its targets, and on `--pool sealed`
    those are the same terms; adding the two lists without removing the repeats put the
    sealed terms in the ledger row twice, which reads as two separate readings.
    """
    sealed_test = list(cfg["semesters"]["sealed_test"]) if unseal else []
    return list(dict.fromkeys(list(targets) + sealed_test))


def fit(cfg, args, targets: list[str], outcome) -> int:
    """Fit the forward scores, write them, and check determinism when asked."""
    started = time.time()
    outcome.at("前向拟合")
    run = run_once(cfg, targets, args.unseal)
    frame = to_frame(run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out, index=False)
    pd.DataFrame(run.log).to_csv(args.out.with_suffix(".log.csv"), index=False)
    print(f"wrote {args.out} in {time.time() - started:.0f} s", flush=True)
    outcome.done(f"{len(frame):,} 行排序分数写到 {provenance.relative_path(args.out)}")
    if not args.repeat:
        return 0
    print("second pass, for the determinism check", flush=True)
    again = run_once(cfg, targets, args.unseal, quiet=True)
    for name in run.scores:
        first, second = run.scores[name], again.scores[name]
        same = np.array_equal(first, second, equal_nan=True)
        print(f"  {name}: {'identical' if same else 'DIFFERS'}")
        if not same:
            delta = np.abs(np.nan_to_num(first) - np.nan_to_num(second))
            print(f"    {int((delta > 0).sum()):,} rows differ, worst {float(delta.max()):.3e}")
            return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--pool", default="primary", help="which overlay pool's terms to fit")
    ap.add_argument(
        "--targets", default=None, help="default: the terms of --pool in the configuration"
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="default: data.score_dir/forward_scores.parquet of the config",
    )
    ap.add_argument(
        "--repeat",
        action="store_true",
        help="fit twice and assert the two passes are identical",
    )
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    if args.out is None:
        args.out = cfg.data_path("score_dir", "forward_scores.parquet")
    pools = cfg["overlay"]["pools"]
    if args.pool not in pools:
        raise SystemExit(f"no pool {args.pool!r}; the configuration has {sorted(pools)}")
    targets = args.targets.split(",") if args.targets else list(pools[args.pool])
    sealed.guard_semesters(targets, ROOT, unseal=args.unseal)
    print(f"targets {targets}", flush=True)
    read = terms_read(cfg, targets, args.unseal)
    with sealed.recording(ROOT, "scripts/fit_scores.py", read, args.unseal) as outcome:
        return fit(cfg, args, targets, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
