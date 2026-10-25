"""Summary of the late-report grid: one row per (level, policy, model, law, delta).

    python -u evidence/revision_r1/report_delay/summarize.py [--cells-dir cells]

Reads outputs/revision_r1/report_delay/<cells-dir>/rep<o>_L<l>.csv and writes summary.csv
and summary.md next to it.  Mean over overlays: p99_dl_s, gap_closed, fired_pct.  Worst
over overlays: max_excess_s, harm_s, worst_ratio_late, worst_ratio_orig.  Sums:
viol_late, viol_orig.  The delta = 0 row (model "all") is expanded into every (model,
law) series; d_p99_s and d_gap are the change from delta = 0 within an overlay, averaged.
Cells or rows that are missing are listed, not filled.
"""

from __future__ import annotations

import _setup

import argparse
import csv
import math
from collections import defaultdict

OUT = _setup.OUT
OVERLAYS = range(5)
LEVELS = range(3)
GUARDS = ("Guard(300)", "Guard(600)", "Guard(1200)")
REFS = ("FCFS", "SJF", "SPJF-E")
MODELS = ("U", "A1", "A2")
LAWS = ("const", "unif")
DELTAS = ("0.0", "0.1", "1.0", "5.0", "30.0", "60.0", "300.0")


def f(x):
    return float(x) if x not in ("", None) else math.nan


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells-dir", default="cells")
    a = ap.parse_args()
    cdir = OUT / a.cells_dir
    rows = {}
    missing_cells = []
    for o in OVERLAYS:
        for lv in LEVELS:
            p = cdir / f"rep{o}_L{lv}.csv"
            if not p.exists():
                missing_cells.append(f"rep{o}_L{lv}")
                continue
            with p.open(encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    rows[(o, lv, r["policy"], r["model"], r["law"], r["delta_s"])] = r
    missing_rows = []
    groups = defaultdict(list)  # (level, policy, model, law, delta) -> [(overlay, row, row at delta 0)]
    for lv in LEVELS:
        for o in OVERLAYS:
            if f"rep{o}_L{lv}" in missing_cells:
                continue
            for name in REFS:
                r = rows.get((o, lv, name, "", "", ""))
                if r is None:
                    missing_rows.append(f"rep{o}_L{lv} {name}")
                else:
                    groups[(lv, name, "", "", "")].append((o, r, r))
            for name in GUARDS:
                r0 = rows.get((o, lv, name, "all", "all", "0.0"))
                if r0 is None:
                    missing_rows.append(f"rep{o}_L{lv} {name} delta 0")
                for m in MODELS:
                    for law in LAWS:
                        for d in DELTAS:
                            r = r0 if d == "0.0" else rows.get((o, lv, name, m, law, d))
                            if r is None:
                                if d != "0.0":
                                    missing_rows.append(f"rep{o}_L{lv} {name} {m} {law} {d}")
                                continue
                            groups[(lv, name, m, law, d)].append((o, r, r0))
    out = []
    for (lv, name, m, law, d), items in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3], f(kv[0][4]) if kv[0][4] else -1)
    ):
        def mean(c):
            v = [f(r[c]) for _, r, _ in items]
            return sum(v) / len(v)

        def worst(c):
            v = [f(r[c]) for _, r, _ in items]
            v = [x for x in v if not math.isnan(x)]
            return max(v) if v else math.nan

        def total(c):
            v = [f(r[c]) for _, r, _ in items]
            return int(sum(v)) if not any(math.isnan(x) for x in v) else ""

        guard = name in GUARDS
        d_p99 = [f(r["p99_dl_s"]) - f(r0["p99_dl_s"]) for _, r, r0 in items if r0 is not None]
        d_gap = [f(r["gap_closed"]) - f(r0["gap_closed"]) for _, r, r0 in items if r0 is not None]
        out.append({
            "level": lv, "k": items[0][1]["k"], "policy": name, "model": m, "law": law,
            "delta_s": d, "n_overlays": len(items),
            "p99_dl_s": mean("p99_dl_s"), "gap_closed": mean("gap_closed"),
            "d_p99_s": sum(d_p99) / len(d_p99) if guard and d_p99 else "",
            "d_gap": sum(d_gap) / len(d_gap) if guard and d_gap else "",
            "fired_pct": mean("fired_pct"),
            "max_excess_s": worst("max_excess_s"), "harm_s": worst("harm_s"),
            "late_bound_excess_s": worst("late_bound_excess_s") if guard else "",
            "worst_ratio_late": worst("worst_ratio_late") if guard else "",
            "viol_late": total("viol_late") if guard else "",
            "worst_ratio_orig": worst("worst_ratio_orig") if guard else "",
            "viol_orig": total("viol_orig") if guard else "",
        })
    if not out:
        raise SystemExit(f"no rows under {cdir}")
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    lines = [
        "# Late completion reports: summary",
        "",
        f"Cells read: {15 - len(missing_cells)} of 15. Missing cells: {', '.join(missing_cells) or 'none'}. "
        f"Missing rows: {len(missing_rows)}.",
        "",
        "p99 and gap: mean over overlays; d_p99 and d_gap: change from delta = 0, mean over overlays;",
        "max excess, harm, ratios: worst overlay; violations: sum over overlays.",
        "viol_late: k*excess >= Bmax + (3k-2)L + X (X: k(L+delta) U, (k-1)(L+delta) A2, 0 A1).",
        "viol_orig: wait above guard_upper_bound (Theorem 3, the main table's check).",
        "",
        "| level | k | policy | model | law | delta (s) | n | p99 (s) | gap | d_p99 (s) | d_gap | max exc (s) | harm (s) | late bound (s) | ratio late | viol late | ratio orig | viol orig |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def g(x, fmt):
        return "" if x == "" or (isinstance(x, float) and math.isnan(x)) else format(x, fmt)

    for r in out:
        lines.append(
            f"| {r['level']} | {r['k']} | {r['policy']} | {r['model'] or '-'} | {r['law'] or '-'} | "
            f"{r['delta_s'] or '-'} | {r['n_overlays']} | {g(r['p99_dl_s'], '.3f')} | {g(r['gap_closed'], '.4f')} | "
            f"{g(r['d_p99_s'], '+.3f')} | {g(r['d_gap'], '+.4f')} | {g(r['max_excess_s'], '.1f')} | "
            f"{g(r['harm_s'], '.1f')} | {g(r['late_bound_excess_s'], '.1f')} | {g(r['worst_ratio_late'], '.4f')} | "
            f"{r['viol_late']} | {g(r['worst_ratio_orig'], '.4f')} | {r['viol_orig']} |"
        )
    if missing_rows:
        lines += ["", "Missing rows:", ""] + [f"- {m}" for m in missing_rows[:200]]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"summary: {len(out)} rows, {15 - len(missing_cells)} cells, {len(missing_rows)} missing rows "
          f"-> {OUT / 'summary.csv'}", flush=True)


if __name__ == "__main__":
    main()
