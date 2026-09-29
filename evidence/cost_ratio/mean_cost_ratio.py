"""L / mean cost on the main development overlay: the ratio by which a count of overtakes
is loose against a work budget (05_scheduling.tex, 06_theory.tex, 09_limitations.tex and
the supplement's count remark).

Reads data/derived/overlay_traces/primary_rep0.npz (development overlay) and k1_rep0.npz,
field svc (service seconds). L = 60 s is the analysis cap of the main trace.
"""
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
L = 60.0
for name in ("primary_rep0.npz", "k1_rep0.npz"):
    with np.load(ROOT / "data" / "derived" / "overlay_traces" / name) as z:
        svc = z["svc"]
    mean = float(svc.mean())
    print(f"{name}: n={svc.size:,} mean={mean:.4f} s median={float(np.median(svc)):.4f} s "
          f"max={float(svc.max()):.3f} s  L/mean={L / mean:.1f}  share<1s={float((svc < 1).mean()):.4f}")
