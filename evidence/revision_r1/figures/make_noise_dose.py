"""Write the coordinates of paper/figures/fig_noise_dose.tex (reviewer 3, comment d).

Run from the repository root (standard library only):

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe \
        evidence/revision_r1/figures/make_noise_dose.py

Input: outputs/revision_r1/noise_dose/noise_dose_table.csv, written by
evidence/revision_r1/noise_dose/noise_dose.py (`table`): per level, source, sigma and
policy, gap_closed is the mean over 5 overlays and 3 seeds, and
bound_used_over_allowed_max and bound_violations are the maximum and the sum over them.
auroc_top1pct is the x axis.  One pgfplots table per (level, source), rows by sigma,
with the gap of SPJF and Guard(300|600|1200) and the used/allowed of the three guards.
Checks: every (level, source, sigma) has the four policies and one auroc_top1pct.
"""

from __future__ import annotations

from figgen import define, rows, table, write_block

SCRIPT = "evidence/revision_r1/figures/make_noise_dose.py"
NOISE = "outputs/revision_r1/noise_dose/noise_dose_table.csv"
POLICIES = {"spjf": "SPJF", "three": "Guard(300)", "six": "Guard(600)", "twelve": "Guard(1200)"}
GUARDS = ("three", "six", "twelve")
LEVELS = {"0": "A", "1": "B", "2": "C"}
SOURCES = {"true": "True", "spjf_e": "Spjfe", "random": "Random"}


def sigma_key(value: str) -> float:
    return -1.0 if value == "nan" else float(value)


def main() -> int:
    data = rows(NOISE)
    body = [
        "% Tables \\nd<Source><Level>: Source True = true cost x exp(sigma Z), Spjfe = stored",
        "% SPJF-E score x exp(sigma Z), Random = random score; Level A, B, C = level 0, 1, 2.",
        "% g<policy> = gap_closed, r<guard> = bound_used_over_allowed_max, auroc = auroc_top1pct.",
    ]
    for level, level_tag in LEVELS.items():
        for source, source_tag in SOURCES.items():
            mine = [r for r in data if r["level"] == level and r["source"] == source]
            points = []
            for sigma in sorted({r["sigma"] for r in mine}, key=sigma_key):
                cell = {r["policy"]: r for r in mine if r["sigma"] == sigma}
                assert sorted(cell) == sorted(POLICIES.values()), (level, source, sigma)
                auroc = {r["auroc_top1pct"] for r in cell.values()}
                assert len(auroc) == 1, (level, source, sigma, auroc)
                points.append(
                    [sigma, auroc.pop()]
                    + [cell[name]["gap_closed"] for name in POLICIES.values()]
                    + [cell[POLICIES[g]]["bound_used_over_allowed_max"] for g in GUARDS]
                )
            columns = ["sigma", "auroc"] + [f"g{p}" for p in POLICIES] + [f"r{g}" for g in GUARDS]
            body += table(f"nd{source_tag}{level_tag}", columns, points)
    guarded = [r for r in data if r["policy"].startswith("Guard(")]
    body += [
        "% Over all guarded rows: their number, the largest used/allowed, the summed violations.",
        define("ndGuardRows", str(len(guarded))),
        define("ndRatioMax", f"{max(float(r['bound_used_over_allowed_max']) for r in guarded):.3f}"),
        define("ndViolations", str(sum(int(r["bound_violations"]) for r in data))),
    ]
    near_one = [
        float(r["auroc_top1pct"])
        for r in data
        if r["source"] == "true" and sigma_key(r["sigma"]) <= 0.5
    ]
    body += [
        "% Smallest auroc_top1pct of the true-cost family at sigma <= 0.5; these marks share x = 1.",
        define("ndTrueNearOne", f"{min(near_one):.3f}"),
    ]
    path = write_block("fig_noise_dose.tex", SCRIPT, [NOISE], body)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
