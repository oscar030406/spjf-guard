"""Score the ranking scores as predictors, on the terms they were fitted forward for.

    uv run python scripts/eval_scores.py --pool sealed \
        --scores data/derived/package_ranking_scores/sealed_scores.parquet \
        --out-dir outputs/sealed_predictor --unseal

For every target term of the pool and for each score column (`spjf_e`, `spjf_log`): AUROC
and average precision for the heavy class, RMSE on the `log1p` scale and Spearman
correlation, then the same four over the pool's terms pooled.  The heavy label is the one
definition section 4 uses -- capped cost above the p95 of the reference terms named in
`features.heavy_reference_semesters` -- computed with the package's own threshold
function, not restated here.  `log1p` is the scale the two scores are comparable on: the
expected-cost score is mapped onto it, which is not the objective it was fitted with, and
the column is read as a description of the fitted score rather than of the objective.

Every figure carries a percentile interval from the package's bootstrap at the
configured resample count and seed, **blocked by user**.  A student's submissions share
an exercise history, a code style and a machine, so they are not independent draws; the
whole-week block the queueing statistics use is a property of the overlay timeline, which
a per-submission predictor metric does not have, so the timeline's unit cannot be carried
over.  The blocks of a row are the distinct users of the rows that row scores.

Guarded like the other sealed commands: the terms are checked before a file is opened,
the sealed pool needs a frozen protocol lock and `--unseal`, and the run appends its own
ledger row.  What it writes is pinned in `run.sealed_predictor_tables`, checked here the
way `run_main.py` checks `run.sealed_tables`; the two lists are kept apart on purpose.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.data.events import heavy_threshold_and_cuts  # noqa: E402
from spjf_guard.experiment import bootstrap as bs  # noqa: E402
from spjf_guard.experiment import predictor_metrics as pm  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.experiment.report import write_csv  # noqa: E402
from spjf_guard.predict.scores import SCORE_SPECS  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from fit_scores import load_prepared  # noqa: E402

POOLED = "pooled"
"""What the rows over all target terms together are called in the `target` column."""


def read_scores(path: Path, n_rows: int) -> dict:
    """The score columns, one value per submission row, in the rows' own order.

    The file carries no key: `scripts/fit_scores.py` writes one row per prepared
    submission and nothing else, so a file of another length belongs to another cache and
    scoring it by position would silently compare one pool's scores with another pool's
    costs.  That is refused rather than worked around.
    """
    import pandas as pd

    if not path.is_file():
        raise SystemExit(f"{path} is missing; run scripts/fit_scores.py first")
    frame = pd.read_parquet(path)
    if len(frame) != n_rows:
        raise SystemExit(
            f"{path} has {len(frame):,} rows and the prepared cache has {n_rows:,}; "
            "the scores were fitted on another cache, so they cannot be read by position"
        )
    names = [
        name
        for name in frame.columns
        if name == cfgmod.SCORE_KEY
        or name == cfgmod.LOG_SCORE_KEY
        or name.startswith(f"{cfgmod.SCORE_KEY}_")
        or name.startswith(f"{cfgmod.LOG_SCORE_KEY}_")
    ]
    if not names:
        raise SystemExit(f"{path} carries none of the score columns this package writes")
    return {name: frame[name].to_numpy("float64") for name in names}


def heavy_label(cfg, events, prepared) -> tuple[np.ndarray, np.ndarray, float]:
    """(capped cost, heavy flag, threshold) for every submission row.

    The threshold is the p95 of the reference terms' capped cost, from the same function
    the features and the fit use, so the label the metrics are read against is the label
    section 4 defines and no second definition enters the package.
    """
    rows = prepared.submission_rows
    reference = list(cfg["features"]["heavy_reference_semesters"])
    cost32 = events["exec_time"].to_numpy()[rows]
    threshold, _ = heavy_threshold_and_cuts(
        cost32[np.isin(prepared.semester[rows], reference)], cfg.limit_s
    )
    c_cap = np.minimum(np.nan_to_num(prepared.cost_s[rows]), cfg.limit_s)
    return c_cap, c_cap > threshold, threshold


def on_log1p_scale(name: str, score: np.ndarray) -> np.ndarray:
    """The score on the scale the error is taken on, without refitting anything."""
    base = cfgmod.LOG_SCORE_KEY if name.startswith(cfgmod.LOG_SCORE_KEY) else cfgmod.SCORE_KEY
    if SCORE_SPECS[base].target == "log1p_c_cap":
        return score
    return np.log1p(np.maximum(score, 0.0))


def one_row(cfg, group: str, name: str, score: np.ndarray, columns: dict, mask) -> dict:
    """One (target, score) row: the four figures and their intervals on `mask`'s rows."""
    on_rows = score[mask]
    prepared_sample = pm.sample(
        on_rows,
        columns["heavy"][mask],
        np.log1p(columns["c_cap"][mask]),
        on_log1p_scale(name, on_rows),
    )
    users, block = np.unique(columns["user"][mask], return_inverse=True)
    section = cfg["bootstrap"]
    draws = bs.with_point_estimate(
        bs.block_multiplicities(len(users), int(section["resamples"]), int(section["seed"]))
    )
    row = {
        "target": group,
        "score": name,
        "n": int(mask.sum()),
        "n_heavy": int(columns["heavy"][mask].sum()),
        "n_users": len(users),
        "heavy_threshold_s": round(columns["threshold"], 6),
    }
    for metric, values in pm.replicates(prepared_sample, block, draws).items():
        row[metric] = float(values[0])
        row[f"{metric}_lo"], row[f"{metric}_hi"] = bs.interval(values)
    return row


def metric_rows(cfg, columns: dict, targets: list) -> list[dict]:
    """A row per target term and score, then the same over the terms pooled."""
    rows = []
    for group, terms in [(t, [t]) for t in targets] + [(POOLED, targets)]:
        in_group = np.isin(columns["semester"], terms)
        for name, score in columns["scores"].items():
            mask = in_group & np.isfinite(score)
            if not mask.any():
                raise SystemExit(f"no row of {group} carries a finite {name} score")
            rows.append(one_row(cfg, group, name, score, columns, mask))
            print(
                f"  [{group}] {name}: {rows[-1]['n']:,} rows, "
                f"{rows[-1]['n_heavy']:,} heavy, AUROC {rows[-1]['auroc']:.4f} "
                f"[{rows[-1]['auroc_lo']:.4f}, {rows[-1]['auroc_hi']:.4f}]",
                flush=True,
            )
    return rows


def evaluate(cfg, args, targets: list[str], outcome) -> int:
    """Score the held-out terms, write the table and its manifest, then check the list.

    The pinned-list check runs last on purpose: it is the one step that can fail after
    sealed rows have been read, and a failure that left no manifest and no ledger row
    would hide what the run had already produced.
    """
    started = time.time()
    outcome.at("读取事件与分数")
    events, prepared, _ = load_prepared(cfg, args.unseal)
    rows = prepared.submission_rows
    c_cap, heavy, threshold = heavy_label(cfg, events, prepared)
    columns = {
        "scores": read_scores(args.scores, len(rows)),
        "semester": prepared.semester[rows],
        "user": prepared.user[rows],
        "c_cap": c_cap,
        "heavy": heavy,
        "threshold": threshold,
    }
    print(f"heavy threshold {threshold:.6f} s, {len(rows):,} submission rows", flush=True)
    outcome.at("自助重抽指标")
    table = metric_rows(cfg, columns, targets)

    out = write_csv(table, args.out_dir / "predictor_metrics.csv")
    provenance.write(
        args.out_dir,
        produced_by="scripts/eval_scores.py",
        config_path=args.config,
        outputs=[out],
        inputs=[args.scores, cfg.data_path("cache_dir", cfg["data"]["events_file"])]
        + (
            [cfg.data_path("cache_dir", cfg["data"]["sealed_events_file"])]
            if args.unseal
            else []
        ),
        arguments={
            "pool": args.pool,
            "targets": targets,
            "scores": provenance.relative_path(args.scores),
            "unseal": args.unseal,
        },
        notes={
            "protocol_lock": sealed.lock_fingerprint(ROOT) or "not frozen (development run)",
            "heavy_threshold_s": round(threshold, 6),
            "heavy_reference_semesters": list(cfg["features"]["heavy_reference_semesters"]),
            "bootstrap_block": "user",
            "resamples": int(cfg["bootstrap"]["resamples"]),
        },
    )
    print(
        f"\nwrote {out} and {args.out_dir / provenance.MANIFEST_NAME} "
        f"in {time.time() - started:.0f} s"
    )
    outcome.done(f"{len(table)} 行预测器指标写到 {provenance.relative_path(out)}")
    if args.pool == "sealed":
        complaint = provenance.pinned_outputs_complaint(
            cfg["run"]["sealed_predictor_tables"], [out]
        )
        if complaint:
            raise SystemExit(complaint)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--pool", default="primary", help="which pool's terms were fitted")
    ap.add_argument(
        "--targets", default=None, help="default: the terms of --pool in the configuration"
    )
    ap.add_argument(
        "--scores",
        type=Path,
        default=None,
        help="default: data.score_dir/forward_scores.parquet of the config",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="default: outputs/sealed_predictor for the sealed pool, outputs/dev_predictor "
        "for any other, so that the two runs cannot land in one directory",
    )
    ap.add_argument("--unseal", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    pools = cfg["overlay"]["pools"]
    if args.pool not in pools:
        raise SystemExit(f"no pool {args.pool!r}; the configuration has {sorted(pools)}")
    if args.out_dir is None:
        where = "sealed_predictor" if args.pool == "sealed" else "dev_predictor"
        args.out_dir = ROOT / "outputs" / where
    targets = args.targets.split(",") if args.targets else list(pools[args.pool])
    sealed.guard_semesters(targets, ROOT, unseal=args.unseal)
    if args.scores is None:
        args.scores = cfg.data_path("score_dir", "forward_scores.parquet")
    print(f"targets {targets}; scores {provenance.relative_path(args.scores)}", flush=True)
    with sealed.recording(ROOT, "scripts/eval_scores.py", targets, args.unseal) as outcome:
        return evaluate(cfg, args, targets, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
