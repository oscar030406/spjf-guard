"""A fixed-lag anchor cannot silently acquire an invalid visibility certificate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_visibility import lag_certificate_status, report_lag_certificate  # noqa: E402


def _row(policy: str, variant: str, violations: int) -> dict:
    return {"policy": policy, "variant": variant, "lag_violations": violations}


def test_original_and_static_waits_do_not_certify_the_conservative_score():
    rows = [
        _row("Guard(600)-original", "original", 1),
        _row("SPJF-E-static", "static", 1),
        _row("FCFS", "reference", 0),
    ]
    assert " valid " in lag_certificate_status(rows)


def test_missing_diagnostics_cannot_certify_the_legacy_headline():
    assert "unavailable" in lag_certificate_status([])
    with pytest.raises(RuntimeError, match="conservative headline requires"):
        report_lag_certificate([], "conservative")


@pytest.mark.parametrize(
    "policy,variant", [("Guard(600)", "conservative"), ("FCFS", "reference")]
)
def test_conservative_failure_is_explicit_but_does_not_block_exact(policy, variant, capsys):
    rows = [_row(policy, variant, 1)]
    report_lag_certificate(rows, "exact")
    assert "legacy conservative certificate invalid" in capsys.readouterr().out
    with pytest.raises(RuntimeError, match="conservative headline requires"):
        report_lag_certificate(rows, "conservative")
