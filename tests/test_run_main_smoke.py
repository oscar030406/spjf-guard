"""End to end on a miniature overlay: the run script writes the CSVs and the LaTeX rows.

The point is that the path from a stored overlay through the configuration's policy set
to the reported tables works and asserts the per-job bounds, not that the numbers mean
anything: the overlay here is 40,000 synthetic jobs.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mini_overlay(path: Path, n: int = 40_000, seed: int = 21) -> None:
    rng = np.random.default_rng(seed)
    service = np.clip(
        np.where(rng.random(n) < 0.05, rng.uniform(5.0, 60.0, n), rng.gamma(0.4, 0.5, n)),
        1e-3,
        60.0,
    )
    arrival = np.cumsum(rng.exponential(service.mean() / 2.0, n))
    np.savez(
        path,
        a=arrival,
        svc=service,
        dl=(rng.random(n) < 0.25),
        exam=(rng.random(n) < 0.05),
        hvt=(service > 5.0),
        wk=np.floor(arrival / 604800).astype(np.int64),
        weeks=np.unique(np.floor(arrival / 604800).astype(np.int64)),
        job_row=np.arange(n, dtype=np.int64),
        K=np.array([4, 3, 2], np.int64),
        W=np.float64(service.sum()),
        tweedie=service + rng.normal(0.0, 0.3, n),
    )


@pytest.mark.slow
def test_the_run_script_produces_the_tables(tmp_path, monkeypatch):
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    _mini_overlay(overlays / "mini_rep0.npz")
    env = {
        "SPJF_CACHE_DIR": str(tmp_path / "cache"),
        "SPJF_SCORE_PRED": str(tmp_path / "pred.parquet"),
    }
    monkeypatch.chdir(ROOT)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out_dir = tmp_path / "outputs"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_main.py"),
            "--overlay-dir",
            str(overlays),
            "--prefix",
            "mini",
            "--reps",
            "0",
            "--levels",
            "0,1,2",
            "--output-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    table = out_dir / "main_table.csv"
    assert table.is_file()
    rows = list(csv.DictReader(open(table, encoding="utf-8")))
    policies = {r["policy"] for r in rows}
    assert {"FCFS", "SJF", "SPJF-E", "Guard(600)", "Fixed(600)", "Skip(600)"} <= policies
    for row in rows:
        if row["policy"] == "FCFS":
            assert float(row["max_excess_s"]) == 0.0
            assert float(row["gap_closed"]) == 0.0
    latex = (out_dir / "main_table.tex").read_text(encoding="utf-8")
    assert r"\devnum{" in latex and r"\label{tab:main}" in latex
