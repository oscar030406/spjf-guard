"""Shared loading helpers for the semantics tests (reads cache/ written by build_cache.py)."""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
SEMS = ["2018_1", "2018_2", "2019_1", "2019_2", "2020_ERE", "2020_1", "2020_2",
        "2021_1", "2021_2", "2022_1", "2022_2"]
ERA = {s: ("2018-19" if s.startswith(("2018", "2019")) else "2020-22") for s in SEMS}
KEY = ["semester", "class", "user", "assessment", "exercise"]

pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200)


def _load(prefix: str, sems=None) -> pd.DataFrame:
    out = []
    for s in sems or SEMS:
        d = pd.read_parquet(os.path.join(CACHE, f"{prefix}_{s}.parquet"))
        for c in ("class", "user", "assessment", "exercise"):
            d[c] = d[c].astype(str)
        d.insert(0, "semester", s)
        out.append(d)
    d = pd.concat(out, ignore_index=True)
    d["era"] = d["semester"].map(ERA)
    return d


def load_blocks(sems=None) -> pd.DataFrame:
    return _load("blocks", sems)


def load_cm(sems=None) -> pd.DataFrame:
    return _load("cm", sems)


def q(x, ps=(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)) -> str:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return "n=0"
    qs = np.quantile(x, ps)
    return f"n={x.size:,} " + " ".join(f"p{int(p * 100)}={v:.2f}" for p, v in zip(ps, qs))
