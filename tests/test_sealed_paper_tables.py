"""The sealed side of the paper tooling, on synthetic CSVs.

No sealed run exists yet, so the sealed options are exercised the only way they can be:
a directory of small CSVs stands in for `outputs/sealed_tables`, and a two-file paper
stands in for `paper/`.  What has to hold is that the sealed tables carry the same
figures as the run they come from, that they are marked as sealed rather than as
development data, and that the checks are silent about a sealed table the paper does not
carry yet but not about one whose values disagree.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_paper_numbers as cpn  # noqa: E402
import emit_paper_tables as ept  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402

CONFIG = ROOT / "configs" / "main.yaml"
POLICIES = ("FCFS", "SJF", "SPJF-E", "SPJF-log", "Guard(600)")


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _run_dir(base: Path, offset: float) -> Path:
    """One run's CSVs, the sealed copy differing from the development one by `offset`."""
    _write(
        base / "main_table.csv",
        [
            {
                "level": 0,
                "k": 4,
                "rho_target": 1.0,
                "policy": name,
                "p99_dl_s": 20.0 + offset + i,
                "mean_s": 0.5 + offset,
                "gap_closed": 0.7,
                "gap_closed_lo": 0.6,
                "gap_closed_hi": 0.8,
                "reduction_pct": 40.0,
                "max_excess_s": 100.0 + offset,
                "harm_s": 50.0,
                "fired_pct": 1.5,
            }
            for i, name in enumerate(POLICIES)
        ],
    )
    _write(
        base / "identity_residuals.csv",
        [
            {
                "level": 0,
                "k": 4,
                "rho_target": 1.0,
                "overlay": 0,
                "policy": name,
                "max_abs_residual_L": 0.1 + offset,
                "ratio_to_bound": 0.5,
                "share_residual_zero": 0.25,
                "samephase_share_sum_in": 0.125,
                "r2_net_over_k": 0.9,
                "max_abs_error_s": 3.0,
                "n_jobs": 1000,
            }
            for name in ("SPJF-E", "Guard(600)", "SPJF-reversed")
        ],
    )
    return base


def _emit(tmp_path: Path) -> tuple[Path, Path, dict]:
    """Emit both copies into `package`, from a development and a sealed run."""
    cfg = cfgmod.load(CONFIG, expand_environment=False)
    development = ept.read_run(cfg, _run_dir(tmp_path / "dev", 0.0), None)
    sealed = ept.read_run(cfg, _run_dir(tmp_path / "sealed", 7.0), tmp_path / "sealed" / "k1")
    package = tmp_path / "package"
    package.mkdir()
    ept.emit_tables(cfg, development, package)
    ept.emit_tables(cfg, sealed, package, sealed=True)
    return package, tmp_path / "sealed", ept.run_values(sealed, "sealed_tables", [])


def test_a_run_without_a_sealed_directory_emits_no_sealed_table(tmp_path):
    cfg = cfgmod.load(CONFIG, expand_environment=False)
    package = tmp_path / "package"
    package.mkdir()
    written = ept.emit_tables(
        cfg, ept.read_run(cfg, _run_dir(tmp_path / "dev", 0.0), None), package
    )
    assert not any("_sealed" in name for name in written)
    assert not list(package.glob("*_sealed.tex"))


def test_the_sealed_table_carries_the_sealed_runs_figures_under_its_own_macro(tmp_path):
    package, _, _ = _emit(tmp_path)
    text = (package / "tab_rank_sealed.tex").read_text(encoding="utf-8")
    assert r"\label{tab:rank_sealed}" in text
    assert r"\devnum{" not in text, "a sealed figure must not be marked as development data"
    assert r"\sealednum{27.00}" in text  # 20 + 7 + 0, the sealed run's FCFS p99
    development = (package / "tab_rank.tex").read_text(encoding="utf-8")
    assert r"\devnum{20.00}" in development
    renamed = ept.as_sealed(development)
    assert renamed.replace(r"\sealednum{", r"\devnum{").replace("_sealed}", "}") == development
    assert renamed.splitlines()[:11] == text.splitlines()[:11]  # same shape, other figures


def test_the_sealed_figures_of_the_paper_are_keyed_apart_and_sourced(tmp_path):
    package, sealed_dir, values = _emit(tmp_path)
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "08_experiments.tex").write_text(
        "\\section{Results}\n"
        "the sealed terms give p99 \\sealednum{27.00} s against \\devnum{20.00} s\n",
        encoding="utf-8",
    )
    rows = ept.paper_numbers(paper, {"20.00": "dev_tables/main_table.csv[FCFS]"}, values)
    keyed = {r["key"]: r for r in rows}
    sealed_key = next(k for k in keyed if k.startswith(ept.SEALED_PREFIX))
    assert keyed[sealed_key]["value"] == "27.00"
    assert keyed[sealed_key]["produced_by"].startswith("sealed_tables/main_table.csv")
    assert keyed[sealed_key]["not_produced"] == ""
    assert sum(not k.startswith(ept.SEALED_PREFIX) for k in keyed) == 1


def _sourced_paper(tmp_path: Path, printed: str) -> tuple[Path, Path]:
    """A paper that quotes one sealed figure in prose, and the numbers.csv emitted from it."""
    package, _, values = _emit(tmp_path)
    paper = tmp_path / "paper"
    paper.mkdir()
    source = paper / "08_experiments.tex"
    source.write_text(
        "\\section{Results}\nthe sealed terms give p99 \\sealednum{27.00} s\n", encoding="utf-8"
    )
    ept.write_numbers(ept.paper_numbers(paper, {}, values), package)
    source.write_text(
        f"\\section{{Results}}\nthe sealed terms give p99 \\sealednum{{{printed}}} s\n",
        encoding="utf-8",
    )
    return paper, package


def test_a_sourced_sealed_figure_in_prose_counts_as_printed_under_its_own_macro(tmp_path):
    assert cpn.SEALED_KEY_PREFIX == ept.SEALED_PREFIX
    paper, package = _sourced_paper(tmp_path, "27.00")
    assert cpn.check_sourced(paper, package, {}) == []


def test_a_sourced_sealed_figure_changed_in_prose_is_caught(tmp_path):
    paper, package = _sourced_paper(tmp_path, "27.01")
    complaints = cpn.check_sourced(paper, package, {})
    assert len(complaints) == 1 and "\\sealednum{27.00}" in complaints[0]


def test_a_line_that_says_sealed_stops_excusing_a_number_once_the_sealed_run_is_in(tmp_path):
    line = "the sealed terms give \\devnum{99.99} s"
    assert ept.classify(line, "07_data", "", ept.reasons(False)) == "sealed"
    assert ept.classify(line, "07_data", "", ept.reasons(True)) == "data-description"


def _paper_with(package: Path, tmp_path: Path, name: str = "sealed_tables.tex") -> Path:
    """A paper that carries the emitted sealed tables, as an author would paste them."""
    paper = tmp_path / "paper"
    paper.mkdir(exist_ok=True)
    (paper / name).write_text(
        "\n".join(
            (package / f"tab_{stem}_sealed.tex").read_text(encoding="utf-8")
            for stem in ("rank", "guard", "adv", "resid")
        ),
        encoding="utf-8",
    )
    return paper


def test_the_sealed_tables_of_the_paper_are_checked_value_for_value(tmp_path):
    package, sealed_dir, _ = _emit(tmp_path)
    paper = _paper_with(package, tmp_path)
    labels = [t for t in cpn.TABLES if t != "tab:k1"]
    assert cpn.check_sealed_tables(paper, package, labels) == []


def test_a_sealed_value_the_paper_changed_by_hand_is_caught(tmp_path):
    package, _, _ = _emit(tmp_path)
    paper = _paper_with(package, tmp_path)
    file = paper / "sealed_tables.tex"
    file.write_text(
        file.read_text(encoding="utf-8").replace(r"\sealednum{27.00}", r"\sealednum{27.01}", 1),
        encoding="utf-8",
    )
    complaints = cpn.check_sealed_tables(
        paper, package, [t for t in cpn.TABLES if t != "tab:k1"]
    )
    assert any("27.00" in c or "27.01" in c for c in complaints)


def test_a_sealed_run_without_its_single_server_tables_is_not_an_error(tmp_path):
    """The sealed k = 1 run is a command of its own; `k1/` may simply not be there."""
    package, sealed_dir, _ = _emit(tmp_path)
    paper = _paper_with(package, tmp_path)
    assert cpn.read_rows(sealed_dir / "k1" / "main_table.csv", optional=True) == []
    with pytest.raises(SystemExit):
        cpn.read_rows(sealed_dir / "k1" / "main_table.csv")
    assert cpn.run(paper, tmp_path / "dev", package, only="D", sealed=sealed_dir) == []


def test_a_sealed_predictor_figure_the_paper_invents_is_caught(tmp_path):
    rows = [
        {
            "target": "2023-1",
            "score": "spjf_e",
            "auroc": "0.9123",
            "average_precision": "0.301",
            "rmse_log1p": "0.2500",
            "spearman": "0.402",
        }
    ]
    paper = tmp_path / "paper"
    (paper / "sections").mkdir(parents=True)
    section = paper / cpn.PREDICTOR_SECTION
    section.write_text("AUROC \\sealednum{0.9123} on the sealed terms\n", encoding="utf-8")
    assert cpn.check_sealed_predictor(paper, rows) == []
    section.write_text("AUROC \\sealednum{0.9321} on the sealed terms\n", encoding="utf-8")
    assert len(cpn.check_sealed_predictor(paper, rows)) == 1


def test_a_pass_told_to_leave_sealed_prose_alone_does_not_count_an_unknown_figure(tmp_path):
    """The legacy package reads no online output, so an online figure is unknown to it."""
    package, sealed_dir, _ = _emit(tmp_path)
    paper = _paper_with(package, tmp_path)
    (paper / "08_experiments.tex").write_text(
        "online the guard closes \\sealednum{0.894}\n", encoding="utf-8"
    )
    predictor = tmp_path / "sealed_predictor"
    _write(
        predictor / "predictor_metrics.csv",
        [{"target": "pooled", "score": "spjf_e", "auroc": "0.9123", "spearman": "0.402"}],
    )
    args = (paper, tmp_path / "dev", package)
    known = {"sealed": sealed_dir, "sealed_predictor": predictor}
    checked = cpn.run(*args, only="D", **known)
    assert any("0.894" in c for c in checked)
    assert cpn.run(*args, only="D", sealed_prose=False, **known) == []


def test_a_sealed_visibility_figure_is_a_known_prose_source(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "08_experiments.tex").write_text(
        "gap closed \\sealednum{0.641}\n", encoding="utf-8"
    )
    comparison = [
        {
            "level": 0,
            "policy": "Guard(600)",
            "gap_closed": 0.641,
        }
    ]
    assert cpn.check_sealed_prose(paper, [], comparison, []) == []
