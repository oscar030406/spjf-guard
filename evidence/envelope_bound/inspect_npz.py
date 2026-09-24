"""List the arrays of the development overlays the envelope study reads (keys, shapes, K)."""

from pathlib import Path

import numpy as np

OVERLAYS = Path(__file__).resolve().parents[2] / "data" / "derived" / "overlay_traces"

for name in ("primary_rep0.npz", "validation_rep0.npz", "k1_rep0.npz"):
    with np.load(OVERLAYS / name) as z:
        print(name)
        for key in z.files:
            arr = z[key]
            extra = f" values={arr.tolist()}" if arr.size <= 8 else ""
            print(f"  {key:24s} {arr.dtype} {arr.shape}{extra}")
