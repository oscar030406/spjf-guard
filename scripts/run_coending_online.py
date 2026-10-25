"""The online replay on the co-ending overlays (merged or dropped).

    uv run python scripts/run_coending_online.py --variant merged|dropped <run_online_visibility args>

`run_online_visibility.py` builds its own-copy history from `prepared.simulatable`, the
unmodified job set, so on a co-ending overlay it would treat the members that the variant
removed as history sources that never run (its audit stops at the first of them). Here each
worker first lets `prepare_context` refit and verify the frozen model on the unmodified data,
then applies `build_coending_overlays.apply_variant` to a copy of the prepared data and
rebuilds the history recomputer and the same-copy index from that copy, so a job's own-copy
history holds only jobs of the variant's trace. Other classes and terms keep their recorded
histories, as they do under the original protocol and in the original-protocol co-ending run.
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_online_visibility as rov  # noqa: E402
from build_coending_overlays import VARIANTS, apply_variant  # noqa: E402
from spjf_guard.experiment.visibility import build_same_copy_history_index  # noqa: E402
from spjf_guard.features.refine import M4HistoryRecomputer  # noqa: E402

ENV = "SPJF_COENDING_VARIANT"


def variant_context(context: dict, cfg, pool_terms: list[str], variant: str) -> dict:
    """The context with the own-copy history rebuilt on the variant's job set."""
    prepared = copy.copy(context["prepared"])
    prepared.simulatable = context["prepared"].simulatable.copy()
    prepared.cost_s = context["prepared"].cost_s.copy()
    # build_overlays hands apply_variant the arrivals of the submissions, not of all events
    arrival = context["arrival"][prepared.submission_rows]
    apply_variant(prepared, arrival, pool_terms, cfg.limit_s, variant)
    recomputer = M4HistoryRecomputer(prepared, context["arrival"], context["availability"])
    same_copy = build_same_copy_history_index(
        prepared, context["arrival"], context["availability"], pool_terms
    )
    return context | {"prepared": prepared, "recomputer": recomputer, "same_copy": same_copy}


def _prepare_variant(cfg, args, pool_terms):
    context = _ORIGINAL_PREPARE(cfg, args, pool_terms)
    return variant_context(context, cfg, pool_terms, os.environ[ENV])


def initialize(*initargs):
    """Worker initializer: the stock one, with prepare_context replaced."""
    rov.prepare_context = _prepare_variant
    _ORIGINAL_INITIALIZE(*initargs)


_ORIGINAL_PREPARE = rov.prepare_context
_ORIGINAL_INITIALIZE = rov._initialize


def main() -> int:
    variant = sys.argv[sys.argv.index("--variant") + 1]
    if variant not in VARIANTS:
        raise SystemExit(f"--variant is one of {VARIANTS}")
    del sys.argv[sys.argv.index("--variant") : sys.argv.index("--variant") + 2]
    os.environ[ENV] = variant  # spawned workers inherit it
    rov._initialize = initialize  # run() hands this to the process pool by reference
    return rov.main()


if __name__ == "__main__":
    raise SystemExit(main())
