"""Noise dose-response for reviewer 3: how the benefit falls as the score gets worse.

    python evidence/revision_r1/noise_dose/noise_dose.py cells --overlay 0 [--levels 0,1,2]
        [--seeds all|first] [--workers 2] [--out-dir outputs/revision_r1/noise_dose]
    python evidence/revision_r1/noise_dose/noise_dose.py table [--out-dir ...]
    python evidence/revision_r1/noise_dose/noise_dose.py gate [--out-dir ...]

Score arrays (one per source, sigma, seed):
    true     service_s * exp(sigma Z)          sigma = 0 is SJF's order
    spjf_e   stored SPJF-E score * exp(sigma Z) sigma = 0 is the paper's SPJF-E
    random   default_rng(seed).permutation(service_s), exactly run_main's `random`
Z is standard normal, drawn once per seed over the 863,149 submission rows of
forward_scores.parquet and indexed by the overlay's `job_row`, so copies of one submission
share one error (as the stored scores do), and the same Z is used for every sigma and both
sources.  Each array runs unguarded (SPJF) and under Guard(300/600/1200) with the paper's
selected joint parameters (outputs/selection_v4/selected_parameters.csv), on the main
table's cells (configs/main_frozen_1289aa2.yaml, primary_rep{0..4}.npz, levels 0-2, k from
the overlay).  FCFS and SJF run as the references of every cell.

Everything that is simulated goes through spjf_guard.experiment.parallel._run, the same
worker function scripts/run_main.py uses: per-job bound asserted inside the run, the same
summary and the same bound check.  No bootstrap (no intervals are needed).
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(os.path.abspath(__file__)).parents[3]
HERE = Path(os.path.abspath(__file__)).parent
DEFAULT_OUT = ROOT / "outputs" / "revision_r1" / "noise_dose"
os.environ.setdefault("NUMBA_CACHE_DIR", str(DEFAULT_OUT / "numba_cache"))
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "2")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Long runs share the machine: BELOW_NORMAL, with the typed handle (an untyped one fails
# silently; see evidence/cross_domain_online/common.py).  Worker processes inherit it.
_K32 = ctypes.windll.kernel32
_K32.GetCurrentProcess.restype = ctypes.c_void_p
_K32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_K32.GetPriorityClass.argtypes = [ctypes.c_void_p]
_K32.SetPriorityClass(_K32.GetCurrentProcess(), 0x4000)
if _K32.GetPriorityClass(_K32.GetCurrentProcess()) != 0x4000:
    raise RuntimeError("could not lower this process to BELOW_NORMAL priority")

import numpy as np  # noqa: E402

import run_main  # noqa: E402  (scripts/run_main.py: selection, external scores, cell metrics)
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import adversarial, parallel, provenance  # noqa: E402
from spjf_guard.experiment.metrics import gap_closed, reduction_percent, summarise  # noqa: E402
from spjf_guard.experiment.report import write_csv  # noqa: E402
from spjf_guard.experiment.reproduce import load_overlay  # noqa: E402
from spjf_guard.sim import simulate  # noqa: E402
from spjf_guard.sim.policy import MICROS, fcfs, sjf, spjf  # noqa: E402

CONFIG = ROOT / "configs" / "main_frozen_1289aa2.yaml"
SELECTION = ROOT / "outputs" / "selection_v4" / "selected_parameters.csv"
SCORES = ROOT / "data" / "derived" / "package_ranking_scores" / "forward_scores.parquet"
OVERLAYS = ROOT / "data" / "derived" / "overlay_traces"
MAIN_CELLS = ROOT / "outputs" / "dev_tables" / "main_cells.csv"
SCRATCH = Path("<cache-dir>/noise_dose")

SIGMAS = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0)
NOISE_SEEDS = (20261018, 20261019, 20261020)
RANDOM_SEEDS = (3, 1003, 2003)
"""3 is cfg['overlay']['seed'], the seed run_main gives `random`; the other two are new."""
QUALITY_SEED = 20261021
QUALITY_SAMPLE = 2_000_000
"""Spearman on a fixed 2M-job subsample; AUROC on 2M fixed random job pairs."""
QUALITY_METRICS = ("spearman", "auroc", "auroc_ratio2", "auroc_top1pct")
SOURCES = ("true", "spjf_e", "random")
SUMMARY_FIELDS = (
    "p99_dl_s",
    "mean_s",
    "p99_all_s",
    "max_excess_s",
    "harm_s",
    "max_heavy_s",
    "fired_fraction_queue_weighted",
)


# ---------------------------------------------------------------- memory readings
class _Counters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


_K32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Counters), ctypes.c_ulong]


def peak_private_gb() -> float:
    """This process's peak committed (private) memory, GB."""
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    if not _K32.K32GetProcessMemoryInfo(_K32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError("K32GetProcessMemoryInfo failed")
    return c.PeakPagefileUsage / 2**30


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def system_commit_gb() -> float:
    m = _MemStatus()
    m.dwLength = ctypes.sizeof(m)
    _K32.GlobalMemoryStatusEx(ctypes.byref(m))
    return (m.ullTotalPageFile - m.ullAvailPageFile) / 2**30


class CommitSampler:
    """System-wide commit every 5 s; max minus the reading at start is an upper bound on
    this run's own commit (other processes move it too)."""

    def __init__(self):
        self.start = system_commit_gb()
        self.peak = self.start
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(5.0):
            self.peak = max(self.peak, system_commit_gb())

    def stop(self) -> float:
        self._stop.set()
        self.peak = max(self.peak, system_commit_gb())
        return self.peak - self.start


# ---------------------------------------------------------------- score arrays
def specs(seed_choice: str, sources=SOURCES) -> list[dict]:
    """Every score array of a run, with a file-safe name.  sigma = 0 is one array per
    source (it does not depend on the seed)."""
    noise_seeds = NOISE_SEEDS if seed_choice == "all" else NOISE_SEEDS[:1]
    random_seeds = RANDOM_SEEDS if seed_choice == "all" else RANDOM_SEEDS[:1]
    out = []
    for source in ("true", "spjf_e"):
        if source not in sources:
            continue
        for sigma in SIGMAS:
            for seed in (noise_seeds if sigma > 0 else (0,)):
                out.append({"source": source, "sigma": sigma, "seed": seed,
                            "name": f"nd_{source}_s{sigma:g}_r{seed}"})
    if "random" in sources:
        for seed in random_seeds:
            out.append({"source": "random", "sigma": float("nan"), "seed": seed,
                        "name": f"nd_random_r{seed}"})
    return out


def noise_per_row(seed: int, n_rows: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n_rows)


def make_score(spec: dict, service_s: np.ndarray, stored: np.ndarray, job_row: np.ndarray,
               n_rows: int) -> np.ndarray:
    if spec["source"] == "random":
        return adversarial.adversarial_score(adversarial.RANDOM, service_s, stored, spec["seed"])
    base = service_s if spec["source"] == "true" else stored
    if spec["sigma"] == 0.0:
        return np.array(base, np.float64)
    z = noise_per_row(spec["seed"], n_rows)[job_row]
    return base * np.exp(spec["sigma"] * z)


def quality(score: np.ndarray, service_us: np.ndarray) -> dict:
    """Realised prediction quality against the true cost: Spearman on a fixed subsample,
    pairwise AUROC on fixed random pairs (pairs with equal true cost dropped, score ties
    count one half)."""
    from scipy.stats import spearmanr

    rng = np.random.default_rng(QUALITY_SEED)
    n = len(score)
    idx = rng.choice(n, size=min(QUALITY_SAMPLE, n), replace=False)
    rho = float(spearmanr(score[idx], service_us[idx]).statistic)
    i = rng.integers(0, n, QUALITY_SAMPLE)
    j = rng.integers(0, n, QUALITY_SAMPLE)
    dt = np.sign(service_us[i] - service_us[j])
    keep = dt != 0
    ds = np.sign(score[i] - score[j])[keep]
    dt = dt[keep]
    auroc = float(((ds == dt).sum() + 0.5 * (ds == 0).sum()) / len(dt))
    # The same pairs, kept only when one true cost is at least twice the other.
    far = np.maximum(service_us[i], service_us[j]) >= 2 * np.minimum(service_us[i], service_us[j])
    far = far[keep]
    auroc_ratio2 = float(((ds[far] == dt[far]).sum() + 0.5 * (ds[far] == 0).sum()) / far.sum())
    # Tail detection: AUROC of the score for the longest 1% of jobs against the rest.
    from scipy.stats import rankdata

    heavy = service_us[idx] > np.quantile(service_us, 0.99)
    ranks = rankdata(score[idx])
    n1, n0 = int(heavy.sum()), int((~heavy).sum())
    auroc_top1 = float((ranks[heavy].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
    return {"spearman": rho, "auroc": auroc, "n_pairs": int(len(dt)),
            "auroc_ratio2": auroc_ratio2, "auroc_top1pct": auroc_top1}


# ---------------------------------------------------------------- worker side
def _run_task(task):
    """parallel._run, plus this worker's peak commit."""
    tag, payload = parallel._run(task)
    payload["worker_peak_commit_gb"] = peak_private_gb()
    payload["worker_pid"] = os.getpid()
    return tag, payload


def map_tasks(directory: Path, tasks, limit_s: float, score_names, workers: int):
    with ProcessPoolExecutor(
        max_workers=min(workers, max(len(tasks), 1)),
        initializer=parallel._initialise,
        initargs=(str(directory), limit_s, tuple(score_names)),
    ) as pool:
        yield from pool.map(_run_task, tasks)


# ---------------------------------------------------------------- one overlay
def guard_policies(cfg, selection, servers: int, score_key: str) -> list:
    out = []
    for promise in cfg.promises_s:
        entry = selection.get(("joint", promise)) or cfg.selected(promise)
        name = f"Guard({promise:g})"
        out.append(replace(cfg._guard_from(entry, promise, servers, name), score_key=score_key))
    return out


def run_overlay(args) -> int:
    cfg = cfgmod.load(CONFIG)
    selection = run_main.read_selection(SELECTION)
    mismatch = run_main.check_selection_matches(cfg, selection)
    if mismatch:
        raise SystemExit("selection mismatch: " + "; ".join(mismatch))
    out_dir = Path(args.out_dir)
    (out_dir / "cells").mkdir(parents=True, exist_ok=True)
    (out_dir / "quality").mkdir(parents=True, exist_ok=True)
    overlay = int(args.overlay)
    levels = [int(x) for x in args.levels.split(",")]
    todo = [lv for lv in levels if not (out_dir / "cells" / f"rep{overlay}_level{lv}.csv").is_file()]
    quality_path = out_dir / "quality" / f"rep{overlay}.csv"
    if not todo and quality_path.is_file():
        print(f"overlay {overlay}: every cell already written", flush=True)
        return 0
    started = time.time()
    sampler = CommitSampler()
    window = int(cfg["run"]["segment_tree_window_ranks"])
    path = OVERLAYS / f"primary_rep{overlay}.npz"
    external = run_main.read_external_scores(SCORES)
    n_rows = len(external[cfgmod.SCORE_KEY])
    cell_dir = Path(args.scratch) / f"rep{overlay}"
    shutil.rmtree(cell_dir, ignore_errors=True)
    cell_dir.mkdir(parents=True)
    score_specs = specs(args.seeds, tuple(args.sources.split(",")))

    # Scores do not depend on the level: write them once per overlay.
    trace, _, labels = load_overlay(path, levels[0], {}, cfg.limit_s)
    with np.load(path) as store:
        job_row = store["job_row"]
        work_s = float(store["W"])
        n_levels = len(store["K"])
        ks = [int(k) for k in store["K"]]
    stored = external[cfgmod.SCORE_KEY][job_row]
    if not np.isfinite(stored).all():
        raise ValueError("the stored SPJF-E score is not finite on every job")
    service_s = trace.service_us / MICROS
    quality_rows = []
    for spec in score_specs:
        score = make_score(spec, service_s, stored, job_row, n_rows)
        np.save(cell_dir / f"score_{spec['name']}.npy", score)
        quality_rows.append({"overlay": overlay, **{k: spec[k] for k in ("source", "sigma", "seed")},
                             **quality(score, trace.service_us)})
        del score
    del stored, service_s
    write_csv(quality_rows, quality_path)
    print(f"overlay {overlay}: {len(score_specs)} score arrays and their quality in "
          f"{time.time() - started:.0f} s", flush=True)
    names = [s["name"] for s in score_specs]
    meta = {}

    for level in todo:
        t0 = time.time()
        servers = ks[level]
        reference = simulate(trace, fcfs(), servers, window=window)
        fcfs_wait = reference.wait_us
        fcfs_summary = summarise(reference, fcfs_wait, labels["in_window"], labels["is_heavy"])
        del reference
        parallel.write_cell(cell_dir, trace, labels, fcfs_wait, {})
        del fcfs_wait
        policies = [(sjf(), {"source": "reference", "sigma": float("nan"), "seed": 0})]
        for spec in score_specs:
            tagmeta = {k: spec[k] for k in ("source", "sigma", "seed")}
            policies.append((spjf(spec["name"], "SPJF"), tagmeta))
            policies += [(p, tagmeta) for p in guard_policies(cfg, selection, servers, spec["name"])]
        tasks = []
        for policy, tagmeta in policies:
            tag = f"{policy.score_key}|{policy.name}"
            meta[tag] = tagmeta
            tasks.append({
                "tag": tag, "policy": policy, "servers": servers, "window": window,
                "limit_s": cfg.limit_s,
                "assert_bounds": bool(cfg["run"]["assert_per_job_bounds"]),
                "bootstrap": None, "residuals": False,
            })
        results = dict(map_tasks(cell_dir, tasks, cfg.limit_s, names, args.workers))
        base = fcfs_summary.p99_dl_s
        target = results[f"{sjf().score_key}|SJF"]["summary"].p99_dl_s
        rho_target = run_main.level_utilisation(cfg, level, servers, work_s, n_levels)
        rows = [_row(overlay, level, servers, rho_target, work_s, "FCFS",
                     {"source": "reference", "sigma": float("nan"), "seed": 0},
                     {"summary": fcfs_summary}, base, target)]
        for tag, payload in results.items():
            rows.append(_row(overlay, level, servers, rho_target, work_s,
                             tag.split("|", 1)[1], meta[tag], payload, base, target))
        write_csv(rows, out_dir / "cells" / f"rep{overlay}_level{level}.csv")
        worker_peak = max(p.get("worker_peak_commit_gb", 0.0) for p in results.values())
        violations = sum(int(p.get("bound", {}).get("violations", 0)) for p in results.values())
        print(f"overlay {overlay} level {level}: k = {servers}, {len(tasks)} runs, "
              f"{time.time() - t0:.0f} s, worker peak commit {worker_peak:.2f} GB, "
              f"bound violations {violations}", flush=True)
        del results
    shutil.rmtree(cell_dir, ignore_errors=True)
    delta = sampler.stop()
    print(f"overlay {overlay}: done in {time.time() - started:.0f} s; parent peak commit "
          f"{peak_private_gb():.2f} GB; system commit rose by at most {delta:.2f} GB "
          f"(start {sampler.start:.1f} GB)", flush=True)
    return 0


def _row(overlay, level, servers, rho_target, work_s, policy, tagmeta, payload, base, target):
    stats = payload["summary"]
    bound = payload.get("bound", {})
    return {
        "overlay": overlay, "level": level, "k": servers, "rho_target": rho_target,
        "rho_realised": round(work_s / (3600.0 * servers), 6),
        "source": tagmeta["source"], "sigma": tagmeta["sigma"], "seed": tagmeta["seed"],
        "policy": policy,
        "n_jobs": stats.n_jobs,
        **{f: getattr(stats, f) for f in SUMMARY_FIELDS},
        "gap_closed": gap_closed(stats.p99_dl_s, base, target),
        "reduction_pct": reduction_percent(stats.p99_dl_s, base),
        "bound_worst_excess_s": bound.get("worst_excess_s", float("nan")),
        "bound_allowed_s": bound.get("allowed_s", float("nan")),
        "bound_used_over_allowed": bound.get("used_over_allowed", float("nan")),
        "bound_violations": bound.get("violations", 0),
        "worker_peak_commit_gb": payload.get("worker_peak_commit_gb", float("nan")),
    }


# ---------------------------------------------------------------- gate
GATE_PAIRS = (
    # (source, sigma, seed, our policy) -> main_cells policy
    (("reference", "nan", "0", "SJF"), "SJF"),
    (("reference", "nan", "0", "FCFS"), "FCFS"),
    (("true", "0", "0", "SPJF"), "SJF"),
    (("spjf_e", "0", "0", "SPJF"), "SPJF-E"),
    (("spjf_e", "0", "0", "Guard(300)"), "Guard(300)"),
    (("spjf_e", "0", "0", "Guard(600)"), "Guard(600)"),
    (("spjf_e", "0", "0", "Guard(1200)"), "Guard(1200)"),
    (("random", "nan", "3", "SPJF"), "SPJF-random"),
    (("random", "nan", "3", "Guard(600)"), "Guard(600)-random"),
)


def _key(row):
    sigma = float(row["sigma"])
    return (row["source"], "nan" if sigma != sigma else f"{sigma:g}", str(int(row["seed"])),
            row["policy"])


def gate(args) -> int:
    out_dir = Path(args.out_dir)
    with open(MAIN_CELLS, encoding="utf-8") as fh:
        main = {(int(r["overlay"]), int(r["level"]), r["policy"]): r for r in csv.DictReader(fh)}
    failures = checked = 0
    for path in sorted((out_dir / "cells").glob("rep*_level*.csv")):
        with open(path, encoding="utf-8") as fh:
            ours = {_key(r): r for r in csv.DictReader(fh)}
        for key, main_policy in GATE_PAIRS:
            if key not in ours:
                continue
            row = ours[key]
            ref = main[(int(row["overlay"]), int(row["level"]), main_policy)]
            fields = ("k", "n_jobs") + SUMMARY_FIELDS + ("gap_closed",)
            diffs = [f"{f}: {row[f]} vs {ref[f]}" for f in fields if float(row[f]) != float(ref[f])]
            checked += 1
            status = "EXACT" if not diffs else "DIFF " + "; ".join(diffs)
            failures += bool(diffs)
            print(f"rep{row['overlay']} level {row['level']} {'/'.join(key)} = {main_policy}: "
                  f"p99_dl {float(row['p99_dl_s']):.6f}  {status}")
    viol = 0
    for path in sorted((out_dir / "cells").glob("rep*_level*.csv")):
        with open(path, encoding="utf-8") as fh:
            viol += sum(int(r["bound_violations"]) for r in csv.DictReader(fh))
    print(f"gate: {checked} rows compared to {MAIN_CELLS.relative_to(ROOT)}, "
          f"{failures} differ; bound violations over all guarded rows: {viol}")
    return 1 if failures or not checked else 0


# ---------------------------------------------------------------- final table
def table(args) -> int:
    out_dir = Path(args.out_dir)
    cell_paths = sorted((out_dir / "cells").glob("rep*_level*.csv"))
    quality_paths = sorted((out_dir / "quality").glob("rep*.csv"))
    cells = [r for p in cell_paths for r in csv.DictReader(open(p, encoding="utf-8"))]
    qual = [r for p in quality_paths for r in csv.DictReader(open(p, encoding="utf-8"))]
    qkey = {}
    for r in qual:
        qkey.setdefault((r["source"], _sig(r["sigma"]), r["seed"]), []).append(r)
    per_seed, groups = [], {}
    for r in cells:
        groups.setdefault((int(r["level"]), r["source"], _sig(r["sigma"]), r["seed"], r["policy"]), []).append(r)
    for (level, source, sigma, seed, policy), block in sorted(groups.items(), key=str):
        q = qkey.get((source, sigma, seed), [])
        per_seed.append({
            "level": level, "source": source, "sigma": sigma, "seed": seed, "policy": policy,
            "n_overlays": len(block),
            "p99_dl_s": _mean(block, "p99_dl_s"), "gap_closed": _mean(block, "gap_closed"),
            "reduction_pct": _mean(block, "reduction_pct"), "mean_s": _mean(block, "mean_s"),
            "max_excess_s": max(float(b["max_excess_s"]) for b in block),
            "harm_s": max(float(b["harm_s"]) for b in block),
            "bound_used_over_allowed_max": max(float(b["bound_used_over_allowed"]) for b in block),
            "bound_violations": sum(int(b["bound_violations"]) for b in block),
            **{m: (_mean(q, m) if q else float("nan")) for m in QUALITY_METRICS},
        })
    written = [write_csv(per_seed, out_dir / "noise_dose_by_seed.csv")]
    pooled, groups = [], {}
    for r in per_seed:
        groups.setdefault((r["level"], r["source"], r["sigma"], r["policy"]), []).append(r)
    for (level, source, sigma, policy), block in sorted(groups.items(), key=str):
        gaps = [b["gap_closed"] for b in block]
        pooled.append({
            "level": level, "source": source, "sigma": sigma, "policy": policy,
            "n_seeds": len(block), "n_overlays": block[0]["n_overlays"],
            "p99_dl_s": float(np.mean([b["p99_dl_s"] for b in block])),
            "gap_closed": float(np.mean(gaps)),
            "gap_closed_seed_min": min(gaps), "gap_closed_seed_max": max(gaps),
            "max_excess_s": max(b["max_excess_s"] for b in block),
            "harm_s": max(b["harm_s"] for b in block),
            "bound_used_over_allowed_max": max(b["bound_used_over_allowed_max"] for b in block),
            "bound_violations": sum(b["bound_violations"] for b in block),
            **{m: float(np.mean([b[m] for b in block])) for m in QUALITY_METRICS},
        })
    written.append(write_csv(pooled, out_dir / "noise_dose_table.csv"))
    provenance.write(
        out_dir, produced_by="evidence/revision_r1/noise_dose/noise_dose.py", config_path=CONFIG,
        outputs=written + cell_paths + quality_paths,
        inputs=[OVERLAYS / f"primary_rep{o}.npz" for o in range(5)] + [SCORES, SELECTION,
                HERE / "noise_dose.py", ROOT / "scripts" / "run_main.py"],
        arguments={"sigmas": list(SIGMAS), "noise_seeds": list(NOISE_SEEDS),
                   "random_seeds": list(RANDOM_SEEDS), "quality_seed": QUALITY_SEED,
                   "quality_sample": QUALITY_SAMPLE},
        notes={"aggregation": "mean over overlays for p99/gap/mean/quality, max over overlays "
                              "for excess/harm, sum for violations; then mean over seeds"},
    )
    total_viol = sum(r["bound_violations"] for r in pooled)
    print(f"wrote {', '.join(str(p) for p in written)}; {len(cells)} cell rows from "
          f"{len(cell_paths)} cells; bound violations {total_viol}")
    return 0


def _sig(text: str) -> str:
    v = float(text)
    return "nan" if v != v else f"{v:g}"


def _mean(block, field) -> float:
    return float(np.mean([float(b[field]) for b in block]))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cells")
    c.add_argument("--overlay", type=int, required=True)
    c.add_argument("--levels", default="0,1,2")
    c.add_argument("--seeds", choices=("all", "first"), default="all")
    c.add_argument("--sources", default=",".join(SOURCES))
    c.add_argument("--workers", type=int, default=2)
    c.add_argument("--scratch", default=str(SCRATCH))
    for p in (c, sub.add_parser("table"), sub.add_parser("gate")):
        p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    return {"cells": run_overlay, "table": table, "gate": gate}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
