"""Frozen wiring for the exact policy-specific visibility assessment."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_generated  # noqa: E402
import check_paper_numbers as cpn  # noqa: E402
import emit_paper_tables as ept  # noqa: E402
import run_main  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.experiment import paper_tables as pt  # noqa: E402


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _metric_row(policy: str, variant: str) -> dict:
    return {
        "level": 0,
        "k": 4,
        "rho_target": 1.0,
        "policy": f"{policy}|{variant}",
        "base_policy": policy,
        "variant": variant,
        "p99_dl_s": 12.34,
        "gap_closed": 0.456,
        "gap_closed_lo": 0.4,
        "gap_closed_hi": 0.5,
        "max_excess_s": 100.0,
        "harm_s": 20.0,
        "fired_pct": 1.25,
    }


def _exposure_row(policy: str) -> dict:
    return {
        "level": 0,
        "policy": policy,
        "n_overlays": 5,
        "jobs": 100,
        "affected_jobs": 10,
        "affected_share": 0.1,
        "deadline_jobs": 50,
        "deadline_affected_jobs": 4,
        "deadline_affected_share": 0.08,
        "records_mean": 1.25,
        "records_p50": 1,
        "records_p90": 2,
        "records_p99": 3,
        "records_max": 4,
        "abs_delta_score_mean": 0.1,
        "abs_delta_score_p50": 0.1,
        "abs_delta_score_p90": 0.2,
        "abs_delta_score_p99": 0.3,
        "abs_delta_score_max": 0.4,
        "rank_displacement_mean": -1,
        "rank_displacement_p50": -1,
        "rank_displacement_p90": 1,
        "rank_displacement_p99": 2,
        "rank_displacement_max": 3,
        "abs_rank_displacement_mean": 1,
        "abs_rank_displacement_p50": 1,
        "abs_rank_displacement_p90": 2,
        "abs_rank_displacement_p99": 3,
        "abs_rank_displacement_max": 4,
    }


def test_exact_protocol_and_output_names_are_frozen_without_moving_the_headline():
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml", expand_environment=False)
    exact = cfg["features"]["exact_visibility"]
    assert cfg["features"]["headline_variant"] == "conservative"
    assert cfg["scheduling"]["headline_ranking_score"] == "spjf_e_conservative"
    assert exact == {
        "algorithm": "monotone_per_job_withholding",
        "base_score": "spjf_e",
        "model_weights": "frozen",
        "own_class_term_copy_outcome_rule": "completion_j <= replay_arrival_i",
        "external_history_clock": "original_relative",
        "same_semester_other_class_history": "exogenous",
        "alternative_sensitivity": "drop_same_semester_other_class_records",
        "sensitivity_policies": ["Guard(600)"],
        "terminal_assertion": "no_new_violation",
        "policies": ["SPJF-E", "Guard(300)", "Guard(600)", "Guard(1200)", "Aging(600)"],
        "fixed_lags_s": [60.0, 300.0, 900.0, 3600.0],
        "selection_assessment": "retained_original_due_cost",
        "selection_cost_seed": 20260922,
        "reselection_budget_hours": 8.0,
        "development_overlays": [0, 1, 2, 3, 4],
        "development_levels": [0, 1, 2],
    }
    pinned = set(cfg["run"]["sealed_consistent_visibility_tables"])
    assert pinned == {
        "exact_cells.csv",
        "exact_comparison.csv",
        "exact_passes.csv",
        "same_copy_exposure_cells.csv",
        "same_copy_exposure.csv",
        "attribution_cells.csv",
        "attribution_comparison.csv",
        "exact_delta_manifest.csv",
        "exact_costs.csv",
        "exact_sensitivity_cells.csv",
        "exact_sensitivity_comparison.csv",
        "manifest.json",
    }
    assert not any(name.endswith(".npz") for name in pinned)


def test_the_protocol_lock_carries_exact_choices_and_their_own_output_list(monkeypatch):
    import make_protocol_lock as lock

    cfg = cfgmod.load(ROOT / "configs" / "main.yaml", expand_environment=False)
    monkeypatch.setattr(lock.cfgmod, "load", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(lock, "code_manifest", lambda root: [])
    monkeypatch.setattr(lock, "input_manifest", lambda config, root: [])
    monkeypatch.setattr(lock, "grid_manifest", lambda config: {})
    monkeypatch.setattr(lock, "cache_stage", lambda root, config: {})
    built = lock.build(ROOT / "configs" / "main.yaml", ROOT)
    assert (
        built["pinned"]["visibility_protocol"]["exact"] == cfg["features"]["exact_visibility"]
    )
    assert (
        built["pinned"]["sealed_consistent_visibility_tables"]
        == cfg["run"]["sealed_consistent_visibility_tables"]
    )


def test_changing_the_headline_does_not_change_any_legacy_reported_policy():
    historical = cfgmod.load(ROOT / "configs/main_original_84932d9.yaml")
    current = cfgmod.load(ROOT / "configs/main.yaml")
    current.raw["scheduling"]["headline_ranking_score"] = "policy_specific_exact"
    for servers in (1, 4, 5, 7):
        assert current.policies(servers) == historical.policies(servers)


def test_archived_recipes_remain_the_original_byte_sequences():
    expected = {
        "main_original_84932d9.yaml": (
            "94c82eabb1428300a6badc037e6fc795e5e451388af9fad83dcc4e1123f153ee"
        ),
        "visibility_development_20260922.yaml": (
            "3ecc81fe448828622088fade31856b9d3f68b8f5163d77f97d0f1f0ac9654bc0"
        ),
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "configs" / name).read_bytes()).hexdigest() == digest


def test_the_exact_certificate_gate_skips_a_fresh_clone(tmp_path, monkeypatch):
    monkeypatch.setattr(check_generated, "ROOT", tmp_path)
    ok, message = check_generated.check_consistent_certificates()
    assert ok
    assert "no manifest on disk, skipped" in message


def test_preservation_gate_detects_a_change_to_an_existing_column(tmp_path, monkeypatch):
    monkeypatch.setattr(check_generated, "ROOT", tmp_path)
    assert check_generated.check_preserved_development()[0]
    table = tmp_path / "outputs/dev_tables/example.csv"
    table.parent.mkdir(parents=True)
    table.write_bytes(b"original_column\n1.0\n")
    snapshot = tmp_path / "outputs/consistent_original_tables.json"
    snapshot.write_text(
        json.dumps(
            [
                {
                    "path": "outputs/dev_tables/example.csv",
                    "rows": 1,
                    "sha256": hashlib.sha256(table.read_bytes()).hexdigest(),
                }
            ]
        ),
        encoding="utf-8",
    )
    assert check_generated.check_preserved_development()[0]
    table.write_bytes(b"original_column\n1.1\n")
    assert not check_generated.check_preserved_development()[0]
    table.unlink()
    assert not check_generated.check_preserved_development()[0]


def test_the_sealed_dry_run_lists_the_exact_stage_and_its_own_outputs(capsys):
    cfg = cfgmod.load(ROOT / "configs" / "main.yaml", expand_environment=False)
    args = SimpleNamespace(
        overlay_dir=cfg.data_path("overlay_dir"),
        score_parquet=None,
        no_adversarial=False,
    )
    assert run_main.sealed_plan(cfg, args) == 0
    text = capsys.readouterr().out
    assert (
        "[6 exact        scripts/run_consistent_visibility.py --pool sealed --workers 2 --resume]"
        in text
    )
    assert "exact_costs.csv" in text
    assert "sealed_consistent_controls.npz" in text
    assert "monotone_per_job_withholding" in text
    assert "original_relative" in text
    assert "[9 predictor" in text


def test_the_two_exact_tables_are_optional_generated_recipes(tmp_path):
    exact = tmp_path / "exact"
    package = tmp_path / "package"
    paper = tmp_path / "paper"
    package.mkdir()
    paper.mkdir()
    comparison = [_metric_row("Guard(600)", variant) for variant in ("original", "exact")]
    exposure = [_exposure_row("Guard(600)")]
    _write(exact / "exact_comparison.csv", comparison)
    _write(exact / "same_copy_exposure.csv", exposure)

    assert ept.emit_optional_exact(None, package) == []
    assert not list(package.iterdir()), (
        "the historical table directory stays untouched by default"
    )
    written = ept.emit_exact(exact, package)
    assert written == ["tab_exact_visibility.tex", "tab_same_copy_exposure.tex"]
    assert r"\label{tab:exact_visibility}" in pt.exact_visibility_table(comparison)
    assert r"\label{tab:same_copy_exposure}" in pt.same_copy_exposure_table(exposure)
    assert cpn.check_exact_tables(paper, package, exact) == []

    path = package / "tab_exact_visibility.tex"
    path.write_text(
        path.read_text(encoding="utf-8").replace("12.34", "12.35", 1), encoding="utf-8"
    )
    assert any(
        "does not match" in item for item in cpn.check_exact_tables(paper, package, exact)
    )
