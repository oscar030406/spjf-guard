"""The three pre-stated parameter grids of the selection.

The guard is one mechanism.  Its guarantee rests on the cap

    B_max = k (G - (3 - 2/k) L)

and on nothing else, so the shape of the budget under the cap is a design freedom:

    budget(q, t) = min(B0 + gam * (jobs waiting when q arrived) + eta k (t - a_q), B_max)

Three shapes are searched, with grids of comparable density written into the
configuration before any number was measured, because an unequal search is how a
comparison becomes an artefact of the search rather than of the mechanism:

    fixed   eta = gam = 0.  Log-spaced constant budgets plus the anchors the capped grid
            uses, plus the equal-promise point B0 = B_max per G.  A constant budget
            carries its own promise B0/k + (3 - 2/k)L, which is below G for small
            budgets, so a fixed point is a candidate at G only when its promise in its
            worst cell is at most G.
    capped  gam = 0.  B0 x eta.
    hybrid  the queue-length term as well.

Every budget is scaled by k/4, so one grid value means the same per-server budget at
every load level.
"""

from __future__ import annotations

from dataclasses import dataclass

from spjf_guard.sim.policy import Policy, bmax_for_promise, guard

FIXED, CAPPED, HYBRID = "fixed", "capped", "hybrid"
FAMILIES = (FIXED, CAPPED, HYBRID)

ANY_PROMISE = -1.0
"""Promise field of a fixed-family point: one schedule, admissible at whichever G its own
promise allows."""


@dataclass(frozen=True)
class GridPoint:
    """One configuration of the search, before it meets a trace."""

    family: str
    promise_s: float
    b0_base_s: float
    eta: float
    gam_base_s: float
    name: str

    @property
    def key(self) -> tuple:
        return (self.family, self.promise_s, self.b0_base_s, self.eta, self.gam_base_s)


def log_spaced(lo: float, hi: float, points: int) -> list[float]:
    """`points` log-spaced values from lo to hi, rounded as the pre-stated grid rounds."""
    if points < 2 or lo <= 0.0 or hi <= lo:
        raise ValueError("a log-spaced grid needs 0 < lo < hi and at least two points")
    return [round(lo * (hi / lo) ** (i / (points - 1.0)), 3) for i in range(points)]


def fixed_bases(section: dict) -> list[float]:
    """The constant-budget grid: log-spaced values together with the shared anchors."""
    grid = log_spaced(
        float(section["log_from_s"]), float(section["log_to_s"]), int(section["log_points"])
    )
    return sorted(set(grid) | {float(a) for a in section["anchors_s"]})


def constant_promise(b0_s: float, k: int, limit_s: float) -> float:
    """What a constant budget B0 promises at k servers: B0/k + (3 - 2/k) L."""
    return b0_s / k + (3.0 - 2.0 / k) * limit_s


def grid_points(cfg_grids: dict, promises) -> list[GridPoint]:
    """Every point of the three grids, independent of k."""
    out: list[GridPoint] = []
    for base in fixed_bases(cfg_grids["fixed"]):
        out.append(GridPoint(FIXED, ANY_PROMISE, base, 0.0, 0.0, f"FIX-B{base:g}"))
    capped, hybrid = cfg_grids["capped"], cfg_grids["hybrid"]
    for promise in promises:
        if cfg_grids["fixed"].get("include_equal_promise", True):
            out.append(GridPoint(FIXED, promise, float("inf"), 0.0, 0.0, f"FIXEQ-G{promise:g}"))
        for b0 in capped["b0_base_s"]:
            for eta in capped["eta"]:
                out.append(
                    GridPoint(
                        CAPPED,
                        promise,
                        float(b0),
                        float(eta),
                        0.0,
                        f"CAP-G{promise:g}-B{b0:g}-e{eta:g}",
                    )
                )
        for b0 in hybrid["b0_base_s"]:
            for gam in hybrid["gam_base_s"]:
                for eta in hybrid["eta"]:
                    out.append(
                        GridPoint(
                            HYBRID,
                            promise,
                            float(b0),
                            float(eta),
                            float(gam),
                            f"HYB-G{promise:g}-B{b0:g}-g{gam:g}-e{eta:g}",
                        )
                    )
    return out


def realised_promise(point: GridPoint, k: int, limit_s: float) -> float:
    """The promise the point actually carries at k servers.

    A fixed point below the cap promises less than G; a capped point with eta < 1 carries
    the smaller of G and its own relative bound; every point whose budget can reach the
    cap carries G.
    """
    if point.family == FIXED and point.promise_s == ANY_PROMISE:
        return constant_promise(point.b0_base_s * k / 4.0, k, limit_s)
    cap = bmax_for_promise(point.promise_s, k, limit_s)
    if point.family == HYBRID or point.b0_base_s == float("inf"):
        return point.promise_s
    b0 = min(point.b0_base_s * k / 4.0, cap)
    if point.eta <= 0.0:
        return constant_promise(b0, k, limit_s)
    return min(point.promise_s, constant_promise(b0, k, limit_s) / (1.0 - point.eta))


def policy_for(point: GridPoint, k: int, limit_s: float, score_key: str, promises) -> Policy:
    """The simulated policy of one grid point at k servers.

    A fixed-family point is simulated once, under the largest cap, because a constant
    budget below the cap produces the same schedule whatever G is written next to it.
    """
    top = max(promises)
    promise = top if point.promise_s == ANY_PROMISE else point.promise_s
    cap = bmax_for_promise(promise, k, limit_s)
    b0 = cap if point.b0_base_s == float("inf") else min(point.b0_base_s * k / 4.0, cap)
    return guard(
        promise,
        k,
        limit_s,
        b0,
        point.eta,
        score_key,
        name=point.name,
        gam_s=point.gam_base_s * k / 4.0,
    )


def schedule_key(point: GridPoint, k: int, limit_s: float, promises) -> tuple:
    """Points that produce the same schedule share this key, so a cell simulates once.

    A budget already at or above the cap is the constant-cap policy whatever eta and gam
    are, which is what makes the three grids overlap at their top end.
    """
    policy = policy_for(point, k, limit_s, "", promises)
    if policy.b0_us >= policy.bmax_us:
        return ("saturated", policy.bmax_us)
    return (policy.b0_us, round(policy.eta_k, 9), policy.gam_us, policy.bmax_us)
