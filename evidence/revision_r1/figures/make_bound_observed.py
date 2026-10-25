"""Write the coordinates of paper/figures/fig_bound_observed.tex (reviewer 3, comment c).

Run from the repository root (standard library only):

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME .venv/Scripts/python.exe \
        evidence/revision_r1/figures/make_bound_observed.py

The figure sets the bound G of Guard(G) against the largest excess over FCFS that any
job reaches under it, along three axes.  Selection and aggregation done here:

(a) servers k: capacity_curve.csv, rows Guard(300|600|1200) and SPJF-E, k = 1..20;
    max_excess_s, promise_G_s and max_fraction_of_allowed_excess as written.
(b) time limit L: limit_summary.csv, clock = online, rows Guard(G) with status run;
    excess_max for L = 45, 90, 120 and L60_excess_max for L = 60, which the file repeats
    on every row of a (policy, clock, level) and which must agree across those rows.
    The point is the worst over the three loads; the ratio excess / G is computed here.
    Guard(300) at L = 120 has status FCFS (no budget) and is left out.
(c) load: online_comparison.csv, rows Guard(G)|online, max_excess_s by level, with
    rho_target and k; each value must equal the L60_excess_max of (b) for its level.
"""

from __future__ import annotations

from figgen import define, ratio, rows, table, write_block

SCRIPT = "evidence/revision_r1/figures/make_bound_observed.py"
CAPACITY = "evidence/weakness1_attack/capacity_curve.csv"
LIMIT = "evidence/limit_family_selection/limit/limit_summary.csv"
ONLINE = "outputs/dev_online_visibility/online_comparison.csv"
PROMISES = {"three": 300, "six": 600, "twelve": 1200}
LEVELS = ("0", "1", "2")


def panel_k(capacity: list[dict[str, str]]) -> tuple[list[str], list[float], dict[int, str]]:
    body, ratios = [], []
    for tag, promise in PROMISES.items():
        series = sorted(
            (r for r in capacity if r["policy"] == f"Guard({promise})"), key=lambda r: int(r["k"])
        )
        assert [int(r["k"]) for r in series] == list(range(1, 21))
        assert all(float(r["promise_G_s"]) == promise for r in series)
        body += table(
            f"boK{tag}",
            ["k", "exc", "bound", "ratio"],
            [
                [r["k"], r["max_excess_s"], r["promise_G_s"], r["max_fraction_of_allowed_excess"]]
                for r in series
            ],
        )
        ratios += [float(r["max_fraction_of_allowed_excess"]) for r in series]
    unguarded = sorted((r for r in capacity if r["policy"] == "SPJF-E"), key=lambda r: int(r["k"]))
    body += table("boKspjf", ["k", "exc"], [[r["k"], r["max_excess_s"]] for r in unguarded])
    # From which k on the unguarded ranking's own worst excess stays below each promise.
    below = {}
    for promise in PROMISES.values():
        ks = [int(r["k"]) for r in unguarded]
        above = [int(r["k"]) for r in unguarded if float(r["max_excess_s"]) >= promise]
        below[promise] = str(max(above) + 1 if above else min(ks))
    return body, ratios, below


def panel_l(limit: list[dict[str, str]]) -> tuple[list[str], list[float], dict]:
    online = [r for r in limit if r["clock"] == "online"]
    body, ratios, at_60 = [], [], {}
    for tag, promise in PROMISES.items():
        mine = [r for r in online if r["policy"] == f"Guard({promise})"]
        points = []
        for level in LEVELS:
            l60 = {r["L60_excess_max"] for r in mine if r["level"] == level}
            assert len(l60) == 1, (promise, level, l60)
            at_60[(promise, level)] = l60.pop()
        by_l = {"60": {level: at_60[(promise, level)] for level in LEVELS}}
        for r in mine:
            if r["status"] == "run":
                by_l.setdefault(r["L_s"], {})[r["level"]] = r["excess_max"]
            else:
                assert r["status"] == "FCFS" and r["L_s"] == "120" and promise == 300, r
        for limit_s in sorted(by_l, key=float):
            cells = by_l[limit_s]
            assert sorted(cells) == list(LEVELS), (promise, limit_s, cells)
            level = max(LEVELS, key=lambda lv: float(cells[lv]))
            value = float(cells[level])
            points.append([limit_s, cells[level], str(promise), ratio(value / promise), level])
            ratios.append(value / promise)
        body += table(f"boL{tag}", ["L", "exc", "bound", "ratio", "level"], points)
    return body, ratios, at_60


def panel_load(online: list[dict[str, str]], at_60: dict) -> tuple[list[str], list[float]]:
    body, ratios = [], []
    for tag, promise in PROMISES.items():
        series = sorted(
            (r for r in online if r["policy"] == f"Guard({promise})|online"),
            key=lambda r: r["level"],
        )
        assert [r["level"] for r in series] == list(LEVELS)
        points = []
        for r in series:
            assert float(r["max_excess_s"]) == float(at_60[(promise, r["level"])]), r
            value = float(r["max_excess_s"])
            points.append([r["rho_target"], r["k"], r["max_excess_s"], str(promise), ratio(value / promise)])
            ratios.append(value / promise)
        body += table(f"boC{tag}", ["rho", "k", "exc", "bound", "ratio"], points)
    return body, ratios


def span(name: str, values: list[float]) -> list[str]:
    return [define(f"{name}min", f"{min(values):.3f}"), define(f"{name}max", f"{max(values):.3f}")]


def main() -> int:
    capacity = rows(CAPACITY)
    k_body, k_ratios, below = panel_k(capacity)
    l_body, l_ratios, at_60 = panel_l(rows(LIMIT))
    c_body, c_ratios = panel_load(rows(ONLINE), at_60)
    first = next(r for r in capacity if r["policy"] == "FCFS" and r["k"] == "1")
    body = [
        "% (a) Guard(G) and SPJF-E by k; (b) worst over the three loads by L, online clock;",
        "% (c) by load at L = 60 s, online clock.  ratio = worst excess / G.",
        *k_body,
        *l_body,
        *c_body,
        "% Offered load at k = 1 (busy_hour_offered_load_mean); at k servers it is this / k.",
        define("boLoadPerServer", f"{float(first['busy_hour_offered_load_mean']):.2f}"),
        "% Smallest k from which SPJF-E's worst excess stays below G = 300, 600, 1200 s.",
        define("boBelowThree", below[300]),
        define("boBelowSix", below[600]),
        define("boBelowTwelve", below[1200]),
        "% Range of worst excess / G over the plotted Guard(G) points of each panel.",
        *span("boA", k_ratios),
        *span("boB", l_ratios),
        *span("boC", c_ratios),
    ]
    path = write_block("fig_bound_observed.tex", SCRIPT, [CAPACITY, LIMIT, ONLINE], body)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
