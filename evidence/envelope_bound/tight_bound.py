"""Re-scores the saved envelope run under the tighter absolute bound (P-abs), no simulation.

P-abs, for every policy:  k W[i] <= V_i^- + (k-1) L + In_i.
  Work guard, B_max = k (G - (3 - 2/k) L), In_i < B_max + k L (strict):
      W[i] < (V_i^- + B_max)/k + (2 - 1/k) L = old per-job bound - 2 (1 - 1/k) L.
  Skip guard with dispatch-charged count N, In_i <= N L (non-strict):
      W[i] <= (V_i^- + (k - 1 + N) L)/k = old per-job bound - (k G - (k - 1 + N) L)/k.
  FCFS: In_i = 0, the bound is unchanged.
The old run (envelope_bound.py) wrote, per (cell, policy), the minimum over jobs of
old per-job bound - W[i].  Each tight per-job bound is the old one minus a constant that
does not depend on i, so the tight minimum slack is the old one minus that constant, and
a cell has no tight violation exactly when that difference is > 0 (strict) or >= 0.
Cells failing that test are listed for a rerun; the script does not simulate.

Absolute bound, sigma = max_i (V_i^- + C_i) (column sigma_s):
  work guard: (sigma + B_max)/k + (2 - 1/k) L;  skip: (sigma + (k - 1 + N) L)/k;
  FCFS: (sigma + (k - 1) L)/k.

Part b is summarised from envelope_sigma_validation.csv in the same pass.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --no-sync python \
      evidence/envelope_bound/tight_bound.py > evidence/envelope_bound/out_tight_bound.txt
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = 60.0
LEVELS = (0, 1, 2)
TIGHT_FIELDS = [
    "overlay", "level", "k", "policy", "family", "promise_s", "bmax_or_skip",
    "sigma_s", "bound_abs_tight_s", "bound_abs_old_s", "max_wait_s",
    "ratio_max_wait_over_tight", "shift_per_job_s", "min_slack_old_s", "min_slack_tight_s",
    "per_job_violations_tight", "needs_rerun",
]


def skip_count(promise_s: float, k: int) -> int:
    """src/spjf_guard/sim/policy.py:skip_count_for_promise, copied so the check reads no src."""
    return int(math.floor(promise_s * k / L - (2 * k - 2) + 1e-9))


def family(policy: str) -> str:
    if policy == "FCFS":
        return "fcfs"
    if policy.startswith("Skip("):
        return "skip"
    return "work"


def tight_row(r: dict) -> dict:
    k = int(r["k"])
    sigma = float(r["sigma_s"])
    fam = family(r["policy"])
    g = float(r["promise_named_s"])
    if fam == "fcfs":
        shift, abs_tight, param, strict = 0.0, (sigma + (k - 1) * L) / k, "", False
    elif fam == "work":
        bmax = k * (g - (3 - 2 / k) * L)
        shift = 2 * (1 - 1 / k) * L
        abs_tight, param, strict = (sigma + bmax) / k + (2 - 1 / k) * L, f"B_max={bmax:g}", True
    else:
        n = skip_count(g, k)
        shift = (k * g - (k - 1 + n) * L) / k
        abs_tight, param, strict = (sigma + (k - 1 + n) * L) / k, f"N={n}", False
    slack_old = float(r["min_slack_s"])
    slack_tight = slack_old - shift
    # Old run: 0 per-job violations and 0 ties everywhere, so old slack > 0 for every job.
    ok = slack_tight > 1e-9 if strict else slack_tight >= -1e-9
    max_wait = float(r["max_wait_s"])
    return {
        "overlay": r["overlay"], "level": r["level"], "k": k, "policy": r["policy"],
        "family": fam, "promise_s": g, "bmax_or_skip": param, "sigma_s": sigma,
        "bound_abs_tight_s": round(abs_tight, 6), "bound_abs_old_s": float(r["bound_abs_s"]),
        "max_wait_s": max_wait, "ratio_max_wait_over_tight": round(max_wait / abs_tight, 4),
        "shift_per_job_s": round(shift, 6), "min_slack_old_s": slack_old,
        "min_slack_tight_s": round(slack_tight, 6),
        "per_job_violations_tight": 0 if ok else "rerun", "needs_rerun": not ok,
    }


def part_a() -> list[dict]:
    with open(HERE / "envelope_bound.csv", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["bound_kind"] != "none"]
    assert all(int(r["per_job_violations"]) == 0 and int(r["ties"]) == 0 or
               r["policy"] == "FCFS" for r in rows)
    out = [tight_row(r) for r in rows]
    with open(HERE / "tight_bound.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TIGHT_FIELDS)
        w.writeheader()
        w.writerows(out)
    print("[a] tight absolute bound, per (overlay, level, policy)")
    for t in out:
        print(f"  ov {t['overlay']:>7} lv {t['level']} k={t['k']} {t['policy']:18s}"
              f" {t['bmax_or_skip']:>14s} bound {t['bound_abs_tight_s']:8.1f} s"
              f" (old {t['bound_abs_old_s']:8.1f}) max wait {t['max_wait_s']:8.1f}"
              f" ratio {t['ratio_max_wait_over_tight']:.4f} min slack {t['min_slack_tight_s']:8.2f}"
              f" viol {t['per_job_violations_tight']}")
    for fam in ("fcfs", "work", "skip"):
        sub = [t for t in out if t["family"] == fam]
        worst = min(sub, key=lambda t: t["min_slack_tight_s"])
        top = max(sub, key=lambda t: t["ratio_max_wait_over_tight"])
        print(f"  summary {fam}: rows {len(sub)}, rerun needed {sum(t['needs_rerun'] for t in sub)},"
              f" min tight slack {worst['min_slack_tight_s']:.3f} s at ov {worst['overlay']}"
              f" lv {worst['level']} {worst['policy']}; max ratio"
              f" {top['ratio_max_wait_over_tight']:.4f} at ov {top['overlay']} lv {top['level']}"
              f" {top['policy']}")
    return out


def part_b(tight: list[dict]) -> None:
    with open(HERE / "envelope_sigma_validation.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print("\n[b] validation sigma as a forecast of primary sigma (same k)")
    ratios = [float(r["ratio_validation_over_primary"]) for r in rows]
    print(f"  cells {len(rows)}; ratio val/prim min {min(ratios):.4f} max {max(ratios):.4f};"
          f" under-forecast cells {sum(x < 1 for x in ratios)}")
    need_mult = max(1 / x for x in ratios)
    print(f"  multiplicative margin to cover every cell from its paired validation: x{need_mult:.4f}")
    for level in LEVELS:
        cells = [r for r in rows if int(r["level"]) == level]
        k = int(cells[0]["k_primary"])
        worst_val = max(float(r["sigma_validation_s"]) for r in cells)
        worst_prim = max(float(r["sigma_primary_s"]) for r in cells)
        add = max(float(r["sigma_primary_s"]) - float(r["sigma_validation_s"]) for r in cells)
        print(f"  level {level} (k={k} on primary; cells with other k:"
              f" {[r['overlay'] for r in cells if int(r['k_primary']) != k]}):"
              f" max additive shortfall {add:.1f} s of work = {add / k:.1f} s of promise;"
              f" max-of-5 validation {worst_val:.1f} vs max primary {worst_prim:.1f}"
              f" (covers {worst_val >= worst_prim})")
    print("\n  quoted promise from paired validation sigma, tight form, against realised max wait")
    sig = {(r["overlay"], r["level"]): float(r["sigma_validation_s"]) for r in rows}
    missed = 0
    for t in tight:
        if t["overlay"] == "k1_rep0" or t["policy"] not in ("FCFS", "Guard(300)", "Guard(600)",
                                                             "Guard(1200)"):
            continue
        quote = t["bound_abs_tight_s"] - (t["sigma_s"] - sig[(t["overlay"], t["level"])]) / t["k"]
        missed += t["max_wait_s"] >= quote
        if t["max_wait_s"] >= quote:
            print(f"    ov {t['overlay']} lv {t['level']} {t['policy']:12s} quote {quote:8.1f}"
                  f" realised {t['max_wait_s']:8.1f} short {t['max_wait_s'] - quote:7.1f} s")
    print(f"  realised max wait at or above the paired-validation quote: {missed} of 60 rows")


if __name__ == "__main__":
    part_b(part_a())
