"""The paper's paired differences under the online replay, as paired week-block intervals.

    uv run python scripts/online_paired_differences.py

The online runner (scripts/run_online_visibility.py) keeps each policy's week-block
replicates in its checkpoints and writes no paired difference.  This reads them back,
recomputes FCFS and SJF in each cell the way the runner does, and states two kinds of
difference as one resampled quantity each:

* every pair of outputs/dev_tables/paired_differences.csv (the guard against SPJF-E, the
  guard against its family, SPJF-E against SPJF-log), through run_main.paired_differences,
  the function that wrote that file;
* Guard(G) against Timeout(G), with each policy's own interval beside the difference, as
  prechecks/timeout_rule/timeout_intervals.py states it on the original clock.

Nothing is simulated except FCFS and SJF.  Three checks run before anything is written,
because each original-clock quantity was computed once before by another route: the pairs
equal outputs/dev_tables/paired_differences.csv exactly, the Timeout rows equal
prechecks/timeout_rule/timeout_intervals.csv at six decimals, and every online policy's
own gap closed and interval equal the runner's online_comparison.csv exactly.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_consistent_visibility import (  # noqa: E402
    _cell_store,
    _multiplicities,
    _replicates,
    _unpack_replicates,
    _write_csv,
)
from run_main import paired_differences  # noqa: E402
from run_online_visibility import _run_signature  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import bootstrap as bs  # noqa: E402
from spjf_guard.experiment import provenance  # noqa: E402
from spjf_guard.experiment.paper_tables import policy_label  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import fcfs, sjf  # noqa: E402

VARIANTS = ("original", "online")
DEV_PAIRS = ROOT / "outputs" / "dev_tables" / "paired_differences.csv"
CLOCK_CHECK = ROOT / "prechecks" / "timeout_rule" / "timeout_intervals.csv"
PAIR_FIELDS = ("difference_s", "lo", "hi", "difference_gap", "gap_lo", "gap_hi")
CLOCK_FIELDS = (
    "guard_gap",
    "guard_gap_lo",
    "guard_gap_hi",
    "timeout_gap",
    "timeout_gap_lo",
    "timeout_gap_hi",
    "gap_difference",
    "gap_difference_lo",
    "gap_difference_hi",
    "p99_timeout_minus_guard_s",
    "p99_diff_lo",
    "p99_diff_hi",
)


def _runner_args(cfg: cfgmod.Config, config: Path, out_dir: Path) -> argparse.Namespace:
    """The arguments the development suite ran with, which fix its checkpoint signature."""
    return argparse.Namespace(
        config=config,
        pool="primary",
        unseal=False,
        audit=int(cfg["features"]["online_visibility"]["audit_sample"]),
        scores=cfg.data_path("score_dir", "forward_scores.parquet"),
        out_dir=out_dir,
        resume=True,
    )


def cell_replicates(cfg, args, signature, path, overlay, level, multiplicities, policies):
    """p99 replicates of FCFS, SJF and of each policy on both clocks, in one cell."""
    trace, servers, labels = load_overlay(path, level, {}, cfg.limit_s)
    with np.load(path) as source:
        labels["week"] = source["wk"].astype(np.int64)
    window = int(cfg["run"]["segment_tree_window_ranks"])
    reps = {
        name: _replicates(
            simulate(trace, policy, servers, window=window), labels, multiplicities
        )["p99_dl"]
        for name, policy in (("FCFS", fcfs()), ("SJF", sjf()))
    }
    store = _cell_store(args, signature, overlay, level, path)
    for policy in policies:
        payload = store.load(f"o{overlay}_l{level}_online_{policy}")
        if payload is None:
            raise SystemExit(
                f"no valid online checkpoint for {policy} in overlay {overlay} level "
                f"{level}; run scripts/run_online_visibility.py --policies all first"
            )
        for key, values in _unpack_replicates(payload["replicates"]).items():
            reps[key] = values["p99_dl"]
    return reps


def _gap(cells: list[dict], name: str) -> np.ndarray:
    return np.mean(
        np.vstack([(c["FCFS"] - c[name]) / (c["FCFS"] - c["SJF"]) for c in cells]), axis=0
    )


def _interval_fields(prefix: str, values: np.ndarray) -> dict[str, float]:
    low, high = bs.interval(values)
    return {prefix: float(values[0]), f"{prefix}_lo": low, f"{prefix}_hi": high}


def paired_rows(cells: list[dict], level: int, promises, variant: str) -> list[dict]:
    """Guard(G) against Timeout(G) at each promise, both gaps and their paired difference."""
    rows = []
    for g in promises:
        guard, clock = f"Guard({g:g})|{variant}", f"Timeout({g:g})|{variant}"
        guard_gap, clock_gap = _gap(cells, guard), _gap(cells, clock)
        p99_diff = np.mean(np.vstack([c[clock] - c[guard] for c in cells]), axis=0)
        diff_low, diff_high = bs.interval(p99_diff)
        rows.append(
            {"variant": variant, "level": level, "promise_s": g}
            | _interval_fields("guard_gap", guard_gap)
            | _interval_fields("timeout_gap", clock_gap)
            | _interval_fields("gap_difference", guard_gap - clock_gap)
            | {
                "p99_timeout_minus_guard_s": float(p99_diff[0]),
                "p99_diff_lo": diff_low,
                "p99_diff_hi": diff_high,
            }
        )
    return rows


def package_rows(cells: list[dict], level: int, pairs, variant: str) -> list[dict]:
    """The dev_tables pairs on one clock, through the function that wrote dev_tables."""
    by_cell = [
        {"level": level, "replicates": {name: {"p99_dl": values} for name, values in c.items()}}
        for c in cells
    ]
    named = [(f"{left}|{variant}", f"{right}|{variant}") for left, right in pairs]
    rows = paired_differences(by_cell, named, [level])
    for row in rows:
        row["left"], row["right"] = row["left"].split("|")[0], row["right"].split("|")[0]
    return [{"variant": variant} | row for row in rows]


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def pair_complaints(rows: list[dict], reference: list[dict]) -> list[str]:
    """Original-clock pairs that differ in any bit from outputs/dev_tables."""
    expected = {(int(r["level"]), r["left"], r["right"]): r for r in reference}
    complaints = []
    for row in rows:
        if row["variant"] != "original":
            continue
        other = expected[(row["level"], row["left"], row["right"])]
        for field in PAIR_FIELDS:
            if row[field] != float(other[field]):
                complaints.append(
                    f"level {row['level']} {row['left']} - {row['right']} {field}: "
                    f"{row[field]!r} here, {other[field]} in {DEV_PAIRS.name}"
                )
    return complaints


def clock_complaints(rows: list[dict], reference: list[dict]) -> list[str]:
    """Original-clock Timeout rows that differ from the independent precheck at six decimals."""
    expected = {(int(r["level"]), float(r["promise_s"])): r for r in reference}
    complaints = []
    for row in rows:
        if row["variant"] != "original":
            continue
        other = expected[(row["level"], row["promise_s"])]
        for field in CLOCK_FIELDS:
            if round(row[field], 6) != float(other[field]):
                complaints.append(
                    f"level {row['level']} G {row['promise_s']:g} {field}: "
                    f"{round(row[field], 6)} here, {other[field]} in {CLOCK_CHECK.name}"
                )
    return complaints


def online_complaints(rows: list[dict], comparison: list[dict]) -> list[str]:
    """Online gaps and intervals that differ from the runner's own online_comparison.csv."""
    written = {(int(r["level"]), r["policy"]): r for r in comparison}
    complaints = []
    for row in rows:
        if row["variant"] != "online":
            continue
        for prefix, name in (("guard_gap", "Guard"), ("timeout_gap", "Timeout")):
            policy = f"{name}({row['promise_s']:g})|online"
            other = written[(row["level"], policy)]
            for suffix in ("", "_lo", "_hi"):
                if row[prefix + suffix] != float(other["gap_closed" + suffix]):
                    complaints.append(
                        f"level {row['level']} {policy} gap_closed{suffix}: "
                        f"{row[prefix + suffix]!r} here, {other['gap_closed' + suffix]} written"
                    )
    return complaints


def _num(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}".replace(",", "{,}")


def _signed(value: float) -> str:
    return f"${value:+.3f}$"


def latex_rows(rows: list[dict], comparison: list[dict]) -> list[str]:
    """Body rows of Supplementary Table tab:s_online_clock, in the layout of tab:clock."""
    written = {(int(r["level"]), r["policy"]): r for r in comparison}
    body = []
    for level in sorted({r["level"] for r in rows}):
        block = [r for r in rows if r["level"] == level and r["variant"] == "online"]
        if body:
            body.append(r"\midrule")
        for index, row in enumerate(block):
            g = row["promise_s"]
            guard = written[(level, f"Guard({g:g})|online")]
            clock = written[(level, f"Timeout({g:g})|online")]
            load = rf"\devnum{{{float(guard['rho_target']):.1f}}}" if index == 0 else ""
            cells = [
                load,
                rf"\devnum{{{g:g}}}",
                rf"\devnum{{{row['guard_gap']:.3f} [{row['guard_gap_lo']:.3f}, "
                rf"{row['guard_gap_hi']:.3f}]}}",
                rf"\devnum{{{row['timeout_gap']:.3f} [{row['timeout_gap_lo']:.3f}, "
                rf"{row['timeout_gap_hi']:.3f}]}}",
                rf"\devnum{{{_signed(row['gap_difference'])} "
                rf"[{_signed(row['gap_difference_lo'])}, "
                rf"{_signed(row['gap_difference_hi'])}]}}",
                rf"\devnum{{{_num(float(guard['harm_s']), 1)}}} / "
                rf"\devnum{{{_num(float(clock['harm_s']), 1)}}}",
            ]
            body.append(" & ".join(cells) + r" \\")
    return body


def _pair_cell(row: dict) -> str:
    return (
        rf"\devnum{{{_signed(row['difference_gap'])} [{_signed(row['gap_lo'])}, "
        rf"{_signed(row['gap_hi'])}]}}"
    )


def pair_latex_rows(rows: list[dict], comparison: list[dict]) -> list[str]:
    """Body rows of Supplementary Table tab:s_online_pairs: each pair on both clocks.

    A pair whose two policies are the same grid point differs by zero in every resample
    on both clocks and prints no row; the caption says which.
    """
    rho = {int(r["level"]): float(r["rho_target"]) for r in comparison}
    online = {(r["level"], r["left"], r["right"]): r for r in rows if r["variant"] == "online"}
    body = []
    for level in sorted(rho):
        block = [
            (before, online[(level, before["left"], before["right"])])
            for before in rows
            if before["variant"] == "original" and before["level"] == level
        ]
        printed = [
            pair
            for pair in block
            if any(r[f] != 0.0 for r in pair for f in ("gap_lo", "gap_hi"))
        ]
        if body:
            body.append(r"\midrule")
        for index, (before, after) in enumerate(printed):
            load = rf"\devnum{{{rho[level]:.1f}}}" if index == 0 else ""
            pair = f"{policy_label(before['left'])} $-$ {policy_label(before['right'])}"
            body.append(f"{load} & {pair} & {_pair_cell(before)} & {_pair_cell(after)} \\\\")
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    parser.add_argument(
        "--online-dir", type=Path, default=ROOT / "outputs" / "dev_online_visibility"
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "online_paired")
    options = parser.parse_args()
    cfg = cfgmod.load(options.config)
    args = _runner_args(cfg, options.config, options.online_dir)
    signature, _ = _run_signature(cfg, args, list(cfg["overlay"]["pools"]["primary"]))
    reference = _read(DEV_PAIRS)
    pairs = list(dict.fromkeys((r["left"], r["right"]) for r in reference))
    clocks = [(f"Guard({g:g})", f"Timeout({g:g})") for g in cfg.promises_s]
    policies = sorted({name for pair in pairs + clocks for name in pair})
    paths = [cfg.data_path("overlay_dir", f"primary_rep{o}.npz") for o in range(5)]
    multiplicities = _multiplicities(cfg, paths[0])
    clock_rows, pair_rows = [], []
    for level in (0, 1, 2):
        cells = []
        for overlay, path in enumerate(paths):
            cells.append(
                cell_replicates(
                    cfg, args, signature, path, overlay, level, multiplicities, policies
                )
            )
            print(f"level {level} overlay {overlay} read", flush=True)
        for variant in VARIANTS:
            clock_rows += paired_rows(cells, level, cfg.promises_s, variant)
            pair_rows += package_rows(cells, level, pairs, variant)
    comparison = _read(options.online_dir / "online_comparison.csv")
    complaints = (
        pair_complaints(pair_rows, reference)
        + clock_complaints(clock_rows, _read(CLOCK_CHECK))
        + online_complaints(clock_rows, comparison)
    )
    if complaints:
        print("\n".join(complaints))
        return 1
    written = [
        _write_csv(pair_rows, options.out_dir / "online_paired_differences.csv", ("variant",)),
        _write_csv(clock_rows, options.out_dir / "online_clock_intervals.csv", ("variant",)),
    ]
    bodies = {
        "tab_s_online_clock_body.tex": latex_rows(clock_rows, comparison),
        "tab_s_online_pairs_body.tex": pair_latex_rows(pair_rows, comparison),
    }
    for name, body in bodies.items():
        (options.out_dir / name).write_text("\n".join(body) + "\n", encoding="utf-8")
        written.append(options.out_dir / name)
    provenance.write(
        options.out_dir,
        produced_by="scripts/online_paired_differences.py",
        config_path=options.config,
        outputs=written,
        inputs=[
            options.online_dir / "online_comparison.csv",
            options.online_dir / "manifest.json",
            DEV_PAIRS,
            CLOCK_CHECK,
            *paths,
        ],
        arguments={"online_dir": str(options.online_dir)},
        notes={
            "checks": "original pairs equal outputs/dev_tables/paired_differences.csv "
            "exactly; original Timeout rows equal prechecks/timeout_rule/"
            "timeout_intervals.csv at six decimals; online gaps and intervals equal "
            "online_comparison.csv exactly",
            "online_signature": signature,
        },
    )
    print("wrote", ", ".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
