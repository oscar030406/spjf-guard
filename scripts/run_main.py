"""Run the main scheduling experiment from a configuration, end to end.

    uv run python scripts/run_main.py --config configs/main.yaml \
        --overlay-dir <dir> [--pool primary] [--reps 0,1,2,3,4] [--levels 0,1,2] \
        [--score-array tweedie] [--out-dir outputs/dev_tables] [--workers 4] \
        [--selection outputs/selection/selected_parameters.csv] \
        [--no-bootstrap] [--unseal | --dry-run-sealed]

Selection feeds the policy set, the run feeds the week-block paired bootstrap, and the
bootstrap feeds the CSV and the `\\devnum{}` LaTeX tables.  Every guarded run asserts its
per-job bound on every job, inside the run.  Without `--unseal` no sealed term can be
reached, and `--unseal` is refused until a frozen `protocol_lock.json` exists.

`--dry-run-sealed` builds the sealed plan, prints every file it would read, checks the
lock and exits without opening one of them.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402
from spjf_guard.experiment import (  # noqa: E402
    adversarial,  # noqa: E402
    parallel,
    provenance,
)
from spjf_guard.experiment import bootstrap as bs  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, reduction_percent, summarise  # noqa: E402
from spjf_guard.experiment.report import (  # noqa: E402
    DEVELOPMENT_MACRO,
    MAIN_COLUMNS,
    SEALED_MACRO,
    write_csv,
    write_latex,
)
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs  # noqa: E402

SCORE = cfgmod.SCORE_KEY
REFERENCE, TARGET = "FCFS", "SJF"
TARGET_RANKING = "SPJF-E"
"""The unguarded ranking the guard is put on top of: Guard(G) minus this is what the
promise costs."""
MEAN_FIELDS = (
    "p99_dl_s",
    "mean_s",
    "p99_all_s",
    "fired_pct",
    "gap_closed",
    "reduction_pct",
    "k",
    "fired_fraction_queue_weighted",
    "rho_realised",
)
WORST_FIELDS = ("max_excess_s", "harm_s", "max_heavy_s")
SEALED_SCORES_NAME = "sealed_scores.parquet"
"""What the sealed run's own ranking scores are called, as `docs/sealed_run_procedure.md`
names them in stage 3.  The plan prints that file rather than the development scores,
which belong to another pool and are what this run must not be given."""


def read_selection(path: Path) -> dict:
    """{(family, promise): entry} from a selection run, if one is on disk.

    `family` is one of the three budget shapes, or `joint` for the winner across them,
    which is the paper's Guard(G).
    """
    if not path or not path.is_file():
        return {}
    out = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[(row["family"], float(row["promise_s"]))] = {
                "b0_base_s": float(row["b0_base_s"]),
                "eta": float(row["eta"]),
                "gam_base_s": float(row.get("gam_base_s", 0.0) or 0.0),
                "from_family": row.get("from_family", ""),
                "worst_gap_closed": float(row.get("worst_gap_closed", "nan") or "nan"),
                "worst_harm_s": float(row.get("worst_harm_s", "nan") or "nan"),
            }
    return out


def read_external_scores(path: Path | None) -> dict:
    """Scores fitted by this package, per original submission row."""
    if path is None:
        return {}
    import pandas as pd

    frame = pd.read_parquet(path)
    wanted = {
        name: name
        for name in frame.columns
        if name == SCORE
        or name == cfgmod.LOG_SCORE_KEY
        or name.startswith(f"{SCORE}_")
        or name.startswith(f"{cfgmod.LOG_SCORE_KEY}_")
    }
    return {
        key: frame[column].to_numpy("float64")
        for column, key in wanted.items()
        if column in frame.columns
    }


def attach_scores(trace, external: dict, job_row: np.ndarray):
    """Index the per-row scores by the overlay's `job_row` and rebuild the trace."""
    from spjf_guard.sim import Trace

    scores = {name: values[job_row] for name, values in external.items()}
    for name, values in scores.items():
        if not np.isfinite(values).all():
            raise ValueError(f"the regenerated score {name!r} is not finite on every job")
    return Trace(trace.arrival_us, trace.service_us, scores, trace.limit_s)


def _same_point(a: dict, b: dict) -> bool:
    """Same grid point, at the precision the configuration writes its budgets with.

    The grid's own bases run to many digits; the configuration carries them rounded, and
    a centisecond of budget decides nothing (neighbouring bases differ by a fifth of their
    value).  eta and gamma are exact grid values and are compared as such.
    """
    return abs(float(a.get("b0_base_s", 0.0)) - float(b.get("b0_base_s", 0.0))) <= 0.01 and all(
        abs(float(a.get(f, 0.0)) - float(b.get(f, 0.0))) <= 1e-9 for f in ("eta", "gam_base_s")
    )


def check_selection_matches(cfg, selection: dict) -> list[str]:
    """The configuration's pinned points must be the ones the rule chose, family by
    family and for the joint winner."""
    notes = []
    for promise in cfg.promises_s:
        for family in ("joint", "fixed", "capped", "hybrid"):
            chosen = selection.get((family, promise))
            if chosen is None:
                continue
            pinned = (
                cfg.selected(promise) if family == "joint" else cfg.family_best(promise, family)
            )
            if pinned is None or not _same_point(chosen, pinned):
                notes.append(
                    f"G = {promise:g} [{family}]: the rule chose B0 = "
                    f"{chosen['b0_base_s']:g}, eta = {chosen['eta']:g}, gam = "
                    f"{chosen['gam_base_s']:g}; the configuration pins {pinned}"
                )
            if family == "joint" and chosen.get("from_family"):
                pinned_family = (cfg.selected(promise) or {}).get("family")
                if pinned_family and pinned_family != chosen["from_family"]:
                    notes.append(
                        f"G = {promise:g}: the joint winner came from the "
                        f"{chosen['from_family']} family, the configuration says "
                        f"{pinned_family}"
                    )
    return notes


def adversarial_policies(cfg, servers: int, selection: dict, trace) -> list:
    """Each corrupted ranking alone, and the same ranking under Guard(G_adv).

    The pair is the point: the unguarded row shows how bad the order is, the guarded row
    shows the wrapper holding the same promise over it.
    """
    from dataclasses import replace

    from spjf_guard.sim.policy import spjf as spjf_policy

    promise = float(cfg["scheduling"]["selection"].get("adversarial_promise_s", 600.0))
    entry = (selection or {}).get(("joint", promise)) or cfg.selected(promise)
    out = []
    for kind in adversarial.KINDS:
        if kind not in trace.scores:
            continue
        guarded = cfg._guard_from(entry, promise, servers, f"Guard({promise:g})-{kind}")
        out.append(spjf_policy(kind, f"SPJF-{kind}"))
        out.append(replace(guarded, score_key=kind))
    return out


def run_cell(
    cfg,
    trace,
    servers,
    labels,
    overlay,
    level,
    scratch,
    workers,
    multiplicities,
    selection,
    include_log_control,
    residuals=False,
):
    """Every reported policy on one cell, in worker processes over a mapped copy."""
    window = int(cfg["run"]["segment_tree_window_ranks"])
    reference = simulate(trace, fcfs(), servers, window=window)
    fcfs_wait = reference.wait_us
    policies = [
        p
        for p in cfg.policies(servers, include_log_control, selection)
        if p.name != REFERENCE and p.score_key in trace.scores or p.name == TARGET
    ]
    policies += adversarial_policies(cfg, servers, selection, trace)
    cell_dir = parallel.write_cell(
        scratch / f"cell_{overlay}_{level}",
        trace,
        labels,
        fcfs_wait,
        {k: trace.scores[k] for k in trace.scores},
    )
    tasks = [
        {
            "tag": p.name,
            "policy": p,
            "servers": servers,
            "window": window,
            "limit_s": cfg.limit_s,
            "assert_bounds": bool(cfg["run"]["assert_per_job_bounds"]),
            "bootstrap": multiplicities,
            "residuals": residuals,
        }
        for p in policies
    ]
    results = {
        REFERENCE: {
            "summary": summarise(reference, fcfs_wait, labels["in_window"], labels["is_heavy"]),
            "replicates": (
                parallel._bootstrap(
                    fcfs_wait, labels["week"], multiplicities, labels["in_window"]
                )
                if multiplicities is not None
                else None
            ),
        }
    }
    del reference
    for tag, payload in parallel.map_policies(
        cell_dir, tasks, cfg.limit_s, tuple(trace.scores), workers
    ):
        results[tag] = payload
    shutil.rmtree(cell_dir, ignore_errors=True)
    return results


def attach_adversarial(cfg, trace):
    """Add the three corrupted rankings to the trace, from its own costs and score."""
    from spjf_guard.sim import Trace
    from spjf_guard.sim.policy import MICROS

    ranking_score = str(cfg["scheduling"]["ranking_score"])
    if ranking_score not in trace.scores:
        return trace
    scores = dict(trace.scores)
    scores.update(
        adversarial.adversarial_scores(
            trace.service_us / MICROS,
            trace.scores[ranking_score],
            int(cfg["overlay"]["seed"]),
        )
    )
    return Trace(trace.arrival_us, trace.service_us, scores, trace.limit_s)


def parameter_rows(cfg, selection, overlay: int, level: int, servers: int) -> list[dict]:
    """What each guarded policy is actually running at this k, in seconds.

    Every budget scales with k/4 and the skip count with k, so the same setting is a
    different number of seconds at every load level; the tables have to say which.
    """
    from spjf_guard.sim.policy import MICROS

    rows = []
    for policy in cfg.policies(servers, include_log_control=False, selection=selection):
        if policy.wrapper == "none":
            continue
        rows.append(
            {
                "overlay": overlay,
                "level": level,
                "k": servers,
                "policy": policy.name,
                "b0_s": policy.b0_us / MICROS,
                "eta": policy.eta_k / servers,
                "gam_s": policy.gam_us / MICROS,
                "bmax_s": policy.bmax_us / MICROS,
                "skip_count": policy.skip_count,
                "promise_floor_s": (3.0 - 2.0 / servers) * cfg.limit_s,
            }
        )
    return rows


def level_utilisation(cfg, level: int, servers: int, work_s: float, n_levels: int) -> float:
    """The busy-hour utilisation this cell is labelled with.

    A trace built for the three load levels carries the configured target, which is what
    k was derived from and what the paper prints.  The single-server trace has one level
    of its own and is labelled with what it actually reached.
    """
    configured = cfg["overlay"]["target_busy_hour_utilisation"]
    if n_levels == len(configured):
        return float(configured[level])
    return round(work_s / (3600.0 * servers), 2)


def cell_rows(cfg, results, overlay, level, servers, rho_target, work_s):
    """One row per policy on this cell, carrying both utilisations.

    `rho_target` is the load the cell was built for and the label the paper prints;
    `rho_realised` is what the busy hour of this overlay actually reached at this k.  They
    differ by the rounding in the integer server count, and only the second one says how
    loaded the system a number came from really was.
    """
    base = results[REFERENCE]["summary"].p99_dl_s
    target = results[TARGET]["summary"].p99_dl_s
    rows = []
    for name, payload in results.items():
        stats = payload["summary"]
        rows.append(
            {
                "overlay": overlay,
                "level": level,
                "k": servers,
                "rho_target": rho_target,
                "rho_realised": round(work_s / (3600.0 * servers), 6),
                **stats.as_row(),
                "fired_pct": 100.0 * stats.fired_fraction_queue_weighted,
                "gap_closed": gap_closed(stats.p99_dl_s, base, target),
                "reduction_pct": reduction_percent(stats.p99_dl_s, base),
            }
        )
    return rows


def paired_differences(replicates_by_cell, pairs, levels) -> list[dict]:
    """Differences the paper states as differences, with their own paired interval.

    A difference of two policies has to be resampled as a difference: the same week draw
    moves both, so the interval of the difference is far tighter than the two separate
    intervals suggest, and it is the difference the claim is about.
    """
    out = []
    for level in levels:
        cells = [c for c in replicates_by_cell if c["level"] == level]
        if not cells or cells[0]["replicates"] is None:
            continue
        for left, right in pairs:
            series, gap_series = [], []
            for cell in cells:
                reps = cell["replicates"]
                if left not in reps or right not in reps:
                    break
                series.append(reps[left]["p99_dl"] - reps[right]["p99_dl"])
                # the same resample's own reference and target, so the difference of the
                # two gaps closed is resampled as one quantity
                span = reps[REFERENCE]["p99_dl"] - reps[TARGET]["p99_dl"]
                gap_series.append((reps[right]["p99_dl"] - reps[left]["p99_dl"]) / span)
            if len(series) != len(cells):
                continue
            difference = np.mean(np.vstack(series), axis=0)
            low, high = bs.interval(difference)
            gap_difference = np.mean(np.vstack(gap_series), axis=0)
            gap_low, gap_high = bs.interval(gap_difference)
            out.append(
                {
                    "level": level,
                    "left": left,
                    "right": right,
                    "difference_s": float(difference[0]),
                    "lo": low,
                    "hi": high,
                    "excludes_zero": bool(low > 0.0 or high < 0.0),
                    "difference_gap": float(gap_difference[0]),
                    "gap_lo": gap_low,
                    "gap_hi": gap_high,
                    "excludes_zero_gap": bool(gap_low > 0.0 or gap_high < 0.0),
                    "n_overlays": len(cells),
                }
            )
    return out


def difference_pairs(cfg, policies) -> list[tuple[str, str]]:
    """The three differences the paper states as differences.

    (SPJF-E, SPJF-log) is the ranking comparison; Guard(G) against each family best is
    the budget-shape comparison; Guard(G) against SPJF-E is the cost of the promise --
    what holding G costs against the same ranking run unguarded.  All three are resampled
    as differences, so the interval is the interval of the claim.
    """
    pairs = []
    if "SPJF-E" in policies and "SPJF-log" in policies:
        pairs.append(("SPJF-E", "SPJF-log"))
    for promise in cfg.promises_s:
        joint = f"Guard({promise:g})"
        if joint not in policies:
            continue
        for family in ("fixed", "capped", "hybrid"):
            other = f"{cfg.family_label(family)}({promise:g})"
            if other in policies and other != joint:
                pairs.append((joint, other))
        if TARGET_RANKING in policies:
            pairs.append((joint, TARGET_RANKING))
    return pairs


def paired_intervals(replicates_by_cell, policies, levels):
    """Mean over overlays of the per-replicate gap closed, then a percentile interval."""
    out = {}
    for level in levels:
        cells = [c for c in replicates_by_cell if c["level"] == level]
        if not cells or cells[0]["replicates"] is None:
            continue
        for policy in policies:
            gaps, reductions = [], []
            for cell in cells:
                reps = cell["replicates"]
                if policy not in reps:
                    continue
                base = reps[REFERENCE]["p99_dl"]
                target = reps[TARGET]["p99_dl"]
                value = reps[policy]["p99_dl"]
                with np.errstate(divide="ignore", invalid="ignore"):
                    gaps.append((base - value) / (base - target))
                    reductions.append(100.0 * (base - value) / base)
            if not gaps:
                continue
            gap = np.mean(np.vstack(gaps), axis=0)
            reduction = np.mean(np.vstack(reductions), axis=0)
            out[(level, policy)] = {
                "gap": bs.interval(gap),
                "reduction": bs.interval(reduction),
            }
    return out


def aggregate(rows, intervals):
    """Mean over overlays for waits and rates, worst over overlays for excess and harm."""
    out = []
    for level in sorted({r["level"] for r in rows}):
        block = [r for r in rows if r["level"] == level]
        for policy in dict.fromkeys(r["policy"] for r in block):
            cells = [r for r in block if r["policy"] == policy]
            row = {
                "level": level,
                "policy": policy,
                "n_overlays": len(cells),
                "rho_target": cells[0]["rho_target"],
            }
            row.update({f: float(np.mean([c[f] for c in cells])) for f in MEAN_FIELDS})
            row.update({f: float(np.max([c[f] for c in cells])) for f in WORST_FIELDS})
            band = intervals.get((level, policy))
            if band:
                row["gap_closed_lo"], row["gap_closed_hi"] = band["gap"]
                row["reduction_pct_lo"], row["reduction_pct_hi"] = band["reduction"]
            out.append(row)
    return out


def sealed_table_key(prefix: str | None) -> str:
    """Which pinned list a sealed run is checked against.

    The multi-server run and the single-server run write the same file names into two
    directories, so they carry one list each: merging them would make both fail.
    """
    return "sealed_k1_tables" if (prefix or "").endswith("k1") else "sealed_tables"


def check_sealed_tables(cfg, pool: str, prefix: str | None, written: list) -> None:
    """The sealed run writes the list the lock pins, one file more or fewer is an error.

    The dry run prints that list and the frozen lock carries it, so a run that quietly
    produced a different set would make both of them wrong.  Development runs are free to
    write whatever they need.
    """
    if pool != "sealed":
        return
    complaint = provenance.pinned_outputs_complaint(
        cfg["run"][sealed_table_key(prefix)], written
    )
    if complaint:
        raise SystemExit(complaint)


def sealed_plan(cfg, args) -> int:
    """Print every stage of the sealed run, what each would read, and the lock state.

    Eight stages, in order, each needing `--unseal` of its own: the event cache, the
    overlays, the ranking scores, this run, the visibility comparison, the single-server
    trace and its run, and the predictor metrics.  Nothing here opens a file.
    """
    from spjf_guard.data.cache import files_for

    terms = list(cfg["overlay"]["pools"]["sealed"])
    cache = Path(cfg["data"]["cache_dir"])
    raw = Path(cfg["data"].get("raw_parquet_dir", ROOT / "data" / "codebench" / "parquet"))
    events = [cache / cfg["data"]["events_file"], cache / cfg["data"]["sealed_events_file"]]
    scores = [args.score_parquet or cfg.data_path("score_dir", SEALED_SCORES_NAME)]
    stages = [
        ("1 event cache  scripts/build_cache.py --pool sealed", files_for(raw, terms)),
        ("2 overlays     scripts/build_overlays.py --pool sealed --no-scores", events),
        ("3 scores       scripts/fit_scores.py --pool sealed", events),
        (
            "4 main run     scripts/run_main.py --pool sealed",
            [args.overlay_dir / f"sealed_rep{o}.npz" for o in cfg["overlay"]["overlays"]]
            + scores,
        ),
        (
            "5 visibility   scripts/run_visibility.py --pool sealed",
            [args.overlay_dir / f"sealed_rep{o}.npz" for o in cfg["overlay"]["overlays"]]
            + scores,
        ),
        (
            "6 k = 1 trace  scripts/build_overlays.py --pool sealed --single-server",
            events,
        ),
        (
            "7 k = 1 run    scripts/run_main.py --pool sealed --prefix sealed_k1",
            [args.overlay_dir / "sealed_k1_rep0.npz"] + scores,
        ),
        ("8 predictor    scripts/eval_scores.py --pool sealed", events + scores),
    ]
    decision = sealed.decide(ROOT, unseal=True)
    print("sealed run plan (nothing is opened by this command)")
    lock_state = f"frozen at {decision.lock_path}" if decision.lock_path else "NOT FROZEN"
    verdict = "would proceed" if decision.permitted else f"REFUSED: {decision.reason}"
    print(f"  terms          {terms}")
    print(
        f"  caches         {cfg['data']['events_file']} (development, training rows) + "
        f"{cfg['data']['sealed_events_file']} (written by stage 1, read with it)"
    )
    print(
        f"  overlays       {list(cfg['overlay']['overlays'])} x "
        f"{len(cfg['overlay']['target_busy_hour_utilisation'])} load levels"
    )
    names = [p.name for p in cfg.policies(4, include_log_control=True)]
    if not args.no_adversarial:
        adv_g = float(cfg["scheduling"]["selection"].get("adversarial_promise_s", 600.0))
        for kind in adversarial.KINDS:
            names += [f"SPJF-{kind}", f"Guard({adv_g:g})-{kind}"]
    print(f"  policies       {names}")
    print(f"  promise -> B0  {cfg['scheduling']['selected']}")
    print(f"  tables         {list(cfg['run']['sealed_tables'])}")
    print(f"  k = 1 tables   {list(cfg['run']['sealed_k1_tables'])}")
    print(f"  predictor      {list(cfg['run']['sealed_predictor_tables'])}")
    print(f"  visibility     {list(cfg['run']['sealed_visibility_tables'])}")
    print(
        f"  k = 1 copies   {cfg['overlay']['single_server']['copies']} reused from pool "
        f"{cfg['overlay']['single_server']['pool']}; the utilisation reached is reported"
    )
    print("  would read, stage by stage (each stage needs --unseal and writes its own")
    print("  ledger row):")
    for label, files in stages:
        print(f"    [{label}]")
        for path in files[:4]:
            print(f"      {provenance.relative_path(path)}")
        if len(files) > 4:
            print(f"      ... {len(files) - 4} more of the same shape")
    print(f"  ledger         {provenance.relative_path(ROOT / sealed.LOG_RELATIVE_PATH)}")
    print(f"  protocol lock  {lock_state}")
    print(f"  verdict        {verdict}")
    return 0


def sweep_cells(cfg, args, selection, scratch):
    """Every (overlay, level) cell of the pool, in order.  Returns rows and replicates."""
    score_map = {args.score_array: SCORE}
    if args.log_score_array:
        score_map[args.log_score_array] = cfgmod.LOG_SCORE_KEY
    external = read_external_scores(args.score_parquet)
    if external:
        score_map = {}
        print(f"attaching regenerated scores {sorted(external)} by job_row", flush=True)
    rows: list[dict] = []
    replicate_cells: list[dict] = []
    extras: dict[str, list] = {"bounds": [], "residuals": [], "parameters": []}
    multiplicities = None
    reps = [int(x) for x in args.reps.split(",")]
    first_overlay = reps[0]
    for overlay in reps:
        path = args.overlay_dir / f"{args.prefix or args.pool}_rep{overlay}.npz"
        for level in (int(x) for x in args.levels.split(",")):
            started = time.time()
            trace, servers, labels = load_overlay(path, level, score_map, cfg.limit_s)
            with np.load(path) as store:
                labels["week"] = store["wk"].astype(np.int64)
                n_weeks = len(store["weeks"])
                work_s = float(store["W"])
                rho_target = level_utilisation(cfg, level, servers, work_s, len(store["K"]))
                if external:
                    trace = attach_scores(trace, external, store["job_row"])
            if not args.no_adversarial:
                trace = attach_adversarial(cfg, trace)
            if multiplicities is None and not args.no_bootstrap:
                multiplicities = bs.with_point_estimate(
                    bs.week_multiplicities(
                        n_weeks,
                        int(cfg["bootstrap"]["resamples"]),
                        int(cfg["bootstrap"]["seed"]),
                    )
                )
            include_log = bool(args.log_score_array) or any(
                key == cfgmod.LOG_SCORE_KEY or key.startswith(f"{cfgmod.LOG_SCORE_KEY}_")
                for key in trace.scores
            )
            results = run_cell(
                cfg,
                trace,
                servers,
                labels,
                overlay,
                level,
                scratch,
                args.workers,
                multiplicities,
                selection,
                include_log,
                residuals=(overlay == first_overlay),
            )
            rows += cell_rows(cfg, results, overlay, level, servers, rho_target, work_s)
            extras["bounds"] += [
                {
                    "overlay": overlay,
                    "level": level,
                    "k": servers,
                    "policy": tag,
                    **payload["bound"],
                }
                for tag, payload in results.items()
                if "bound" in payload
            ]
            extras["residuals"] += [
                {
                    "overlay": overlay,
                    "level": level,
                    "k": servers,
                    "policy": tag,
                    **payload["residuals"],
                }
                for tag, payload in results.items()
                if "residuals" in payload
            ]
            extras["parameters"] += parameter_rows(cfg, selection, overlay, level, servers)
            replicate_cells.append(
                {
                    "overlay": overlay,
                    "level": level,
                    "replicates": (
                        {k: v.get("replicates") for k, v in results.items()}
                        if multiplicities is not None
                        else None
                    ),
                }
            )
            print(
                f"overlay {overlay} level {level}: k = {servers}, "
                f"{len(results)} policies, {time.time() - started:.0f} s",
                flush=True,
            )
            del trace, labels, results
    return rows, replicate_cells, multiplicities, extras


def table_macro(pool: str) -> str:
    """Which of the paper's two marks this run's printed numbers are wrapped in.

    A sealed table typeset with `\\devnum{}` would say it came from development data, and
    every check in the package reads the mark to decide which run a number belongs to.
    """
    return SEALED_MACRO if pool == "sealed" else DEVELOPMENT_MACRO


def write_tables(args, out_dir: Path, rows, table, differences, extras) -> list[Path]:
    """Every file the run writes, in the order the pinned list names them."""
    written = [
        write_csv(rows, out_dir / "main_cells.csv"),
        write_csv(table, out_dir / "main_table.csv"),
        write_latex(
            table,
            out_dir / "main_table.tex",
            caption="Policies at three loads, five overlays. Waits in seconds; "
            "intervals are paired week-block bootstrap.",
            label="tab:main",
            columns=MAIN_COLUMNS,
            source_note="outputs/.../main_table.csv, regenerated by "
            "scripts/run_main.py; see GENERATED.md",
            macro=table_macro(args.pool),
        ),
    ]
    for name, data in (
        ("paired_differences.csv", differences),
        ("bound_checks.csv", extras["bounds"]),
        ("identity_residuals.csv", extras["residuals"]),
        ("policy_parameters.csv", extras["parameters"]),
    ):
        if data:
            written.append(write_csv(data, out_dir / name))
    return written


def produce(cfg, args, selection, out_dir: Path, terms, lock, outcome) -> int:
    """Sweep the cells, write the tables and the manifest, then check the pinned list.

    The check comes last on purpose.  It is the one step here that can fail after sealed
    rows have been read, and it used to run before the manifest and the ledger row were
    written, so a run that produced a slightly different set of files left no record of
    what it had produced -- the state the ledger exists to make impossible.
    """
    scratch = args.scratch or Path(tempfile.mkdtemp(prefix="spjf_main_"))
    outcome.at("逐格仿真")
    rows, replicate_cells, multiplicities, extras = sweep_cells(cfg, args, selection, scratch)
    if args.scratch is None:
        shutil.rmtree(scratch, ignore_errors=True)

    outcome.at("汇总与配对自助区间")
    policies = list(dict.fromkeys(r["policy"] for r in rows))
    levels = sorted({r["level"] for r in rows})
    intervals = (
        paired_intervals(replicate_cells, policies, levels)
        if multiplicities is not None
        else {}
    )
    table = aggregate(rows, intervals)
    differences = (
        paired_differences(replicate_cells, difference_pairs(cfg, policies), levels)
        if multiplicities is not None
        else []
    )
    written = write_tables(args, out_dir, rows, table, differences, extras)
    provenance.write(
        out_dir,
        produced_by="scripts/run_main.py",
        config_path=args.config,
        outputs=written,
        inputs=[
            args.overlay_dir / f"{args.prefix or args.pool}_rep{o}.npz"
            for o in (int(x) for x in args.reps.split(","))
        ]
        + ([args.score_parquet] if args.score_parquet else []),
        arguments={
            "pool": args.pool,
            "prefix": args.prefix,
            "reps": args.reps,
            "levels": args.levels,
            "score_array": args.score_array,
            "score_parquet": (
                provenance.relative_path(args.score_parquet) if args.score_parquet else None
            ),
            "selection": (provenance.relative_path(args.selection) if args.selection else None),
            "bootstrap": not args.no_bootstrap,
            "unseal": args.unseal,
        },
        notes={
            "protocol_lock": lock or "not frozen (development run)",
            "terms": terms,
            "policies": policies,
            "resamples": int(cfg["bootstrap"]["resamples"])
            if multiplicities is not None
            else 0,
        },
    )
    outcome.done(
        f"{len(rows)} 个策略—格的汇总写到 {provenance.relative_path(out_dir)}"
        f"（{len(policies)} 条策略 × {len(levels)} 档负载 × "
        f"{len(args.reps.split(','))} 条叠加）"
    )
    print(f"\nwrote {', '.join(str(p) for p in written)} and {out_dir / 'manifest.json'}")
    check_sealed_tables(cfg, args.pool, args.prefix, written)
    return 0


def fill_in_paths(cfg, args) -> None:
    """Where the package keeps its own two products, when the run did not say.

    The configuration names both, relative to the repository, so an ordinary run needs no
    machine-specific path on the command line and the manifest it writes has none either.
    The two defaults stand or fall together: a run over some other overlay directory is
    not the standard run, and the stored scores are indexed by the standard overlays'
    `job_row`, so attaching them to a different trace would be meaningless.
    """
    if args.overlay_dir is not None:
        return
    args.overlay_dir = cfg.data_path("overlay_dir")
    if args.score_parquet is None and args.pool != "sealed":
        # The sealed pool gets no default: those scores were fitted on another pool, and
        # a sealed run that silently used them would report the wrong ranking.
        default_scores = cfg.data_path("score_dir", "forward_scores.parquet")
        if default_scores.is_file():
            args.score_parquet = default_scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--overlay-dir", type=Path, default=None)
    ap.add_argument("--pool", default="primary")
    ap.add_argument(
        "--prefix", default=None, help="overlay file prefix; defaults to the pool name"
    )
    ap.add_argument("--reps", default="0,1,2,3,4")
    ap.add_argument("--levels", default="0,1,2")
    ap.add_argument("--score-array", default="tweedie")
    ap.add_argument(
        "--log-score-array",
        default=None,
        help="stored name of the log-scale control, when the file has one",
    )
    ap.add_argument(
        "--score-parquet",
        type=Path,
        default=None,
        help="attach scores from this file by the overlay's job_row index, instead of "
        "using the ones stored inside the overlay",
    )
    ap.add_argument("--out-dir", "--output-dir", dest="out_dir", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--scratch", type=Path, default=None)
    ap.add_argument("--selection", type=Path, default=None)
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument(
        "--no-adversarial",
        action="store_true",
        help="leave out the corrupted rankings and their guarded twins",
    )
    ap.add_argument("--unseal", action="store_true")
    ap.add_argument("--dry-run-sealed", action="store_true")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    if args.dry_run_sealed:
        # The plan is checked against the disk by the person reading it, so it prints the
        # paths the sealed run would really use.  It used to print the literal
        # `<overlay dir>`, which no one can compare with anything.  The score file is left
        # as it was given: the plan is about the sealed pool whatever `--pool` says, and
        # the development default would name the wrong pool's scores.
        args.overlay_dir = args.overlay_dir or cfg.data_path("overlay_dir")
        return sealed_plan(cfg, args)
    fill_in_paths(cfg, args)
    terms = list(cfg["overlay"]["pools"].get(args.pool, cfg["overlay"]["pools"]["primary"]))
    if args.unseal:
        decision = sealed.decide(ROOT, unseal=True)
        if not decision.permitted:
            raise sealed.SealedDataError(
                f"--unseal was given but {decision.reason}; freeze the protocol first "
                "(scripts/make_protocol_lock.py, then move the draft to "
                "protocol_lock.json). No file was opened."
            )
    sealed.guard_semesters(terms, ROOT, unseal=args.unseal)
    if args.pool == "sealed" and args.score_parquet is None:
        raise SystemExit(
            "--pool sealed needs --score-parquet: its overlays are built with no stored "
            "scores, and the development scores belong to another pool, so the run would "
            "quietly report the policies that need no ranking. Give it the file "
            f"scripts/fit_scores.py --pool sealed wrote ({SEALED_SCORES_NAME} in "
            "docs/sealed_run_procedure.md)."
        )
    lock = sealed.lock_fingerprint(ROOT)
    print(
        f"pool {args.pool} {terms}; protocol lock "
        f"{'frozen' if lock else 'not frozen (development run)'}",
        flush=True,
    )

    selection = read_selection(
        args.selection
        or ROOT / cfg["run"]["output_dir"] / "selection" / "selected_parameters.csv"
    )
    for note in check_selection_matches(cfg, selection):
        print(f"  selection mismatch: {note}", flush=True)
    if selection:
        print(
            "  selection read from disk: "
            + "; ".join(
                f"{fam} G={g:g}: B0={v['b0_base_s']:g}, eta={v['eta']:g}, "
                f"gam={v['gam_base_s']:g}"
                for (fam, g), v in sorted(selection.items(), key=str)
                if fam == "joint"
            ),
            flush=True,
        )

    out_dir = args.out_dir or (ROOT / cfg["run"]["output_dir"])
    with sealed.recording(ROOT, "scripts/run_main.py", terms, args.unseal) as outcome:
        return produce(cfg, args, selection, out_dir, terms, lock, outcome)


if __name__ == "__main__":
    raise SystemExit(main())
