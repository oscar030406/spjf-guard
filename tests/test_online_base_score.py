"""The replaced base scores of run_online_visibility --base-score, as the model rescores."""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_online_visibility import _Learned, _TopShort, occurrence_rounds  # noqa: E402
from train_learned_policy import learned_score  # noqa: E402


class _Model:
    def __init__(self, values):
        self.values = np.asarray(values, np.float64)

    def predict(self, rows, histories):
        return self.values[rows].copy()


def test_a_listed_row_keeps_the_constant_whatever_the_model_says():
    model = _TopShort(_Model([5.0, 6.0, 7.0, 8.0]), rows=np.array([1, 3]), value=-2.0)
    out = model.predict(np.array([0, 1, 2, 3]), np.zeros((4, 1)))
    assert out.tolist() == [5.0, -2.0, 7.0, -2.0]


def test_the_learned_rescore_is_the_trained_score():
    spjf_e = np.array([0.5, 2.0, 9.0])
    phi_std = np.array([[1.0, 0.0], [0.0, 2.0], [-1.0, 1.0]])
    weights = np.array([0.3, -0.2])
    job_row = np.array([2, 0, 1, 2])
    model = _Learned(_Model(spjf_e), phi_std @ weights)
    rescored = model.predict(job_row, np.zeros((4, 1)))
    assert np.array_equal(rescored, learned_score(spjf_e[job_row], phi_std, job_row, weights))


def test_copies_without_rounds_get_one_round_per_copy_of_a_class_term():
    # Five copies, jobs listed out of copy order; class-terms 7, 9, 7, 7, 9.
    copy_entry = np.array([3, 0, 1, 2, 4, 0, 3])
    term_of_copy = np.array([7, 9, 7, 7, 9])
    rounds = occurrence_rounds(copy_entry, term_of_copy[copy_entry])
    names = {(int(term_of_copy[e]), int(r)) for e, r in zip(copy_entry, rounds)}
    assert len(names) == len(np.unique(copy_entry))
    assert rounds[copy_entry == 0].tolist() == [0, 0]
