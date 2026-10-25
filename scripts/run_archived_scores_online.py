"""The archived ranking-score fits, replayed online (Table S14 and Table S16, row a).

    uv run python scripts/run_archived_scores_online.py --reps 0 --levels 2 --workers 1 \
        --policies SPJF-hurdle,SPJF-phv,SPJF-q99,SPJF-q90,SPJF-q50,SPJF-l2raw,SPJF-tweedie,\
SPJF-M4refit --out-dir outputs/score_variants_online/jobs/o0_l2
    uv run python scripts/run_archived_scores_online.py --reps 0 --levels 1 --workers 1 \
        --policies 2CLASS-FCFS-tau0.02 \
        --out-dir outputs/score_variants_online/twoclass/jobs/o0_l1

evidence/ranking_score/rs_fit.py fitted one LightGBM model per (score, target term) on the
M4 design and stored the predictions in data/derived/ranking_score_predictions/
rs_pred_ires0.parquet; rs_sim.py ran them on the original clock as SPJF-<score> and as
2CLASS-FCFS-tau0.02 (predicted-light jobs, P(heavy) <= 0.02, before predicted-heavy ones,
FCFS inside each class), and evidence/main_v3 ran the `log` column as SPJF-M4refit.

Each worker refits those models with rs_fit's recipe (its LightGBM settings, labels and
training rows) on the package's M4 design, which equals the study's design bit for bit,
and asserts that they reproduce every stored prediction of the pool's targets.  rs_fit
left LightGBM to choose its histogram layout at run time.  Forced row-wise, the refit
reproduces the stored log, l2raw, tweedie, q50, q90, q99, phv and hurdle columns of all
six targets bit for bit; forced column-wise it misses the log score of 2020-2 by up to
0.50, and left to choose again it missed phv of 2021-2.  run_online_visibility then
replays the policies online, with three of its functions replaced:
  _suite          the policies named by --policies;
  _scoring        an archived policy's stored score and its refitted model (any other
                  name, e.g. the control SPJF-E, keeps the script's own);
  _run_signature  also hashes this file and the stored predictions, so a resumed run
                  never reuses a checkpoint written by another version of either.
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_online_visibility as rov  # noqa: E402
from consistent_cells import sha256_file, signature  # noqa: E402
from spjf_guard.features.sweep import HIST_COLS  # noqa: E402
from spjf_guard.predict.forward import FrozenM4Models, term_order  # noqa: E402
from spjf_guard.sim.policy import spjf  # noqa: E402

STORED = ROOT / "data" / "derived" / "ranking_score_predictions" / "rs_pred_ires0.parquet"
LGB_REG = dict(
    objective="regression",
    n_estimators=300,
    learning_rate=0.06,
    num_leaves=63,
    min_child_samples=50,
    colsample_bytree=1.0,
    subsample=0.8,
    subsample_freq=1,
    random_state=3,
    verbose=-1,
    n_jobs=6,
)
"""LGB_REG of prechecks/codebench_service/service_precheck.py, which rs_fit.fit starts from;
its LGB_CLF differs only in the objective, which rs_fit sets for the binary fit anyway."""
OBJECTIVES = {
    "log": ({}, "log"),
    "l2raw": ({}, "capped"),
    "tweedie": ({"objective": "tweedie", "tweedie_variance_power": 1.5}, "capped"),
    "q50": ({"objective": "quantile", "alpha": 0.5}, "log"),
    "q90": ({"objective": "quantile", "alpha": 0.9}, "log"),
    "q99": ({"objective": "quantile", "alpha": 0.99}, "log"),
    "phv": ({"objective": "binary"}, "heavy"),
}
"""rs_fit's objective and label of each stored column."""
COLUMN = {"SPJF-M4refit": "log", "SPJF-hurdle": "hurdle"}
COLUMN.update({f"SPJF-{name}": name for name in OBJECTIVES if name != "log"})
TWO_CLASS = "2CLASS-FCFS-tau0.02"
TAU = 0.02

_ORIGINAL_INITIALIZE = rov._initialize
_ORIGINAL_SCORING = rov._scoring
_ORIGINAL_SIGNATURE = rov._run_signature
_ARCHIVED: dict[str, tuple[np.ndarray, object]] = {}


def _fit(objective: dict, x: np.ndarray, y: np.ndarray):
    """rs_fit.fit, with LightGBM's row-wise histograms forced."""
    params = dict(LGB_REG)
    params.update(objective)
    params.update(random_state=3, num_threads=4, verbose=-1)
    params.pop("n_jobs")
    rounds = params.pop("n_estimators")
    params["force_row_wise"] = True
    return lgb.train(params, lgb.Dataset(x, label=y), num_boost_round=rounds)


class _Hurdle:
    """rs_fit's two-part score, P(heavy) E[C | heavy] + (1 - P(heavy)) E[C | light]."""

    def __init__(self, heavy, given_heavy, given_light):
        self.parts = (heavy, given_heavy, given_light)

    def predict(self, x: np.ndarray) -> np.ndarray:
        p, big, small = (part.predict(x) for part in self.parts)
        return p * big + (1.0 - p) * small


class _TwoClass:
    """1 for a job whose refitted P(heavy) exceeds TAU, else 0; ties are served FCFS."""

    def __init__(self, heavy: FrozenM4Models):
        self.heavy = heavy

    def predict(self, rows: np.ndarray, histories: np.ndarray) -> np.ndarray:
        return (self.heavy.predict(rows, histories) > TAU).astype(np.float64)


def archived_models(
    cfg, context: dict, stored: pd.DataFrame, columns: set[str]
) -> dict[str, FrozenM4Models]:
    """The refitted model of every stored column named, checked against the stored scores."""
    prepared, frozen = context["prepared"], context["models"]
    pool = sorted(context["pool_terms"])
    rows = prepared.submission_rows
    available = context["availability"][rows]
    first, order = term_order(prepared.semester, context["arrival"], context["all_terms"])
    capped = np.minimum(prepared.cost_s[rows], cfg.limit_s)
    labels = {
        "log": np.log1p(capped),
        "capped": capped,
        "heavy": (capped > prepared.heavy_threshold).astype(np.float64),
    }
    fitted: dict[str, dict[str, object]] = {name: {} for name in columns}
    for target in [term for term in order if term in pool]:
        prior = [term for term in order if first[term] < first[target]]
        train = np.isin(frozen.semester, prior) & (available < first[target])
        x = frozen.design[train]
        for name in sorted(columns - {"hurdle"}):
            objective, label = OBJECTIVES[name]
            fitted[name][target] = _fit(objective, x, labels[label][train])
        if "hurdle" in columns:
            heavy, cost = labels["heavy"][train], labels["capped"][train]
            big, small = heavy > 0.5, heavy <= 0.5
            fitted["hurdle"][target] = _Hurdle(
                fitted["phv"][target]
                if "phv" in columns
                else _fit(OBJECTIVES["phv"][0], x, heavy),
                _fit({}, x[big], cost[big]),
                _fit({}, x[small], cost[small]),
            )
        print(f"  archived scores {target}: {sorted(columns)} refitted", flush=True)
    targets = np.flatnonzero(np.isin(frozen.semester, pool))
    history = frozen.design[targets, -len(HIST_COLS) :]
    out = {}
    for name, models in fitted.items():
        out[name] = FrozenM4Models(models, frozen.design, frozen.semester)
        np.testing.assert_array_equal(
            out[name].predict(targets, history), stored[name].to_numpy("float64")[targets]
        )
        print(f"  archived {name}: {len(targets):,} stored scores reproduced", flush=True)
    return out


def _initialize(*initargs):
    _ORIGINAL_INITIALIZE(*initargs)
    cfg, args, context = rov._STATE["cfg"], rov._STATE["args"], rov._STATE["context"]
    named = [name for name in args.policy_names if name in COLUMN or name == TWO_CLASS]
    columns = {COLUMN[name] for name in named if name in COLUMN}
    columns |= {"phv"} if TWO_CLASS in named else set()
    stored = pd.read_parquet(STORED)
    models = archived_models(cfg, context, stored, columns)
    for name in named:
        if name == TWO_CLASS:
            base = (stored["phv"].to_numpy("float64") > TAU).astype(np.float64)
            _ARCHIVED[name] = (base, _TwoClass(models["phv"]))
        else:
            _ARCHIVED[name] = (stored[COLUMN[name]].to_numpy("float64"), models[COLUMN[name]])
    rov._suite = _suite
    rov._scoring = _scoring


def _suite(cfg, args, servers):
    return [spjf("spjf_e", name) for name in args.policy_names]


def _scoring(cell, policy):
    if policy.name not in _ARCHIVED:
        return _ORIGINAL_SCORING(cell, policy)
    base, model = _ARCHIVED[policy.name]
    return base[cell["arrays"]["job_row"]], model


def _run_signature(cfg, args, pool_terms):
    run, implementation = _ORIGINAL_SIGNATURE(cfg, args, pool_terms)
    document = {
        "run": run,
        "archived_scores_script": sha256_file(Path(__file__)),
        "stored_scores": sha256_file(STORED),
    }
    return signature(document), implementation


def main() -> int:
    sys.argv = [
        sys.argv[0],
        "--pool",
        "primary",
        "--variants",
        "online",
        "--out-dir",
        str(ROOT / "outputs" / "score_variants_online"),
        *sys.argv[1:],
    ]
    rov._initialize = _initialize  # run() hands these to the process pool by reference
    rov._run_signature = _run_signature
    return rov.main()


if __name__ == "__main__":
    raise SystemExit(main())
