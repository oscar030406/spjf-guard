"""The options run_online_visibility gains on 2026-10-01: the aging credit grid, free
Timeout thresholds, the capacity sweep, and the gate on a second sealed evaluation."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_online_visibility as rov  # noqa: E402
from spjf_guard import config as cfgmod  # noqa: E402

CFG = cfgmod.load(ROOT / "configs" / "main.yaml")


def _args(**kw):
    base = dict(aging_grid=False, candidates=None, policy_names=["SPJF-E"])
    return SimpleNamespace(**(base | kw))


def test_aging_grid_is_every_configured_credit_on_the_online_score():
    suite = rov._suite(CFG, _args(aging_grid=True), 4)
    credits = [float(c) for c in CFG["scheduling"]["aging_baseline"]["credit_per_s_grid"]]
    assert len(suite) == len(credits) == 11
    assert [p.name for p in suite] == [f"Aging(c={c:g})" for c in credits]
    assert {p.score_key for p in suite} == {"spjf_e"}
    assert len({p.name for p in suite}) == 11


def test_a_free_timeout_threshold_promises_theta_plus_the_service_term():
    suite = rov._suite(CFG, _args(policy_names=["SPJF-E", "Timeout(theta=480)"]), 4)
    assert [p.name for p in suite] == ["SPJF-E", "Timeout(theta=480)"]
    free = suite[1]
    assert rov._timeout_promise(free, 4, 60.0) == 480 + 2.5 * 60
    assert rov._theta_s(free, 4, 60.0) == pytest.approx(480.0, abs=1e-9)


def test_timeout_at_a_promise_keeps_its_threshold_bit_for_bit():
    named = rov.spjf("spjf_e", "Timeout(600)")
    for k in (1, 4, 7):
        assert rov._theta_s(named, k, 60.0) == 600.0 - (3.0 - 2.0 / k) * 60.0


@pytest.mark.parametrize(
    "extra",
    [
        ["--pool", "primary", "--second-sealed-evaluation", "--out-dir", "x"],
        ["--pool", "sealed", "--second-sealed-evaluation"],
        ["--pool", "sealed", "--second-sealed-evaluation",
         "--out-dir", str(ROOT / "outputs" / "sealed_online_visibility")],
        ["--pool", "sealed", "--policies", "SPJF-log"],
        ["--aging-grid", "--candidates", "c.csv"],
        ["--pool", "sealed", "--unseal", "--servers", "6"],
    ],
)
def test_the_sealed_terms_and_the_aging_grid_refuse_other_runs(monkeypatch, extra):
    monkeypatch.setattr(sys, "argv", ["run_online_visibility.py", *extra])
    with pytest.raises(SystemExit):
        rov.main()
