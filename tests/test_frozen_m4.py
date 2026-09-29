"""Targeted rescoring changes history columns, not frozen model weights or other inputs."""

import numpy as np
import pytest

from spjf_guard.features.sweep import HIST_COLS
from spjf_guard.predict.forward import FrozenM4Models


class _Model:
    def __init__(self, scale: float):
        self.scale = scale
        self.blocks: list[np.ndarray] = []

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        self.blocks.append(matrix.copy())
        return self.scale * np.nan_to_num(matrix).sum(axis=1)


def test_frozen_rescore_keeps_static_design_and_returns_original_requested_order():
    width = len(HIST_COLS)
    design = np.arange(4 * (width + 2), dtype=np.float32).reshape(4, width + 2)
    models = {"a": _Model(1.0), "b": _Model(2.0)}
    frozen = FrozenM4Models(models, design, np.array(["a", "b", "a", "b"]))
    rows = np.array([3, 0, 2], np.int64)
    histories = np.ones((3, width), np.float32)
    original = design.copy()
    prediction = frozen.predict(rows, histories)
    expected = (design[rows, :2].sum(axis=1) + width) * np.array([2.0, 1.0, 1.0])
    np.testing.assert_array_equal(prediction, expected)
    np.testing.assert_array_equal(design, original)
    np.testing.assert_array_equal(models["b"].blocks[0][:, :2], design[[3], :2])
    np.testing.assert_array_equal(models["a"].blocks[0][:, 2:], histories[[1, 2]])
    assert models["a"].scale == 1.0 and models["b"].scale == 2.0


def test_frozen_rescore_rejects_misaligned_history_rows():
    frozen = FrozenM4Models({}, np.zeros((1, len(HIST_COLS) + 2)), np.array(["a"]))
    with pytest.raises(ValueError, match="differ in length"):
        frozen.predict(np.array([0]), np.empty((0, len(HIST_COLS))))
