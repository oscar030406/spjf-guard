"""Loading `configs/main.yaml` and turning its scheduling section into policies.

The configuration is the single document the protocol lock hashes, so nothing here
invents a default that is not written in the file.

Every path in the document is relative to the repository root and is resolved against it
by `data_path`, so neither the file nor anything generated from it records where the
checkout happens to sit.  `${NAME}` in a string is still filled from the environment, for
a machine that has to point one input somewhere else; an absolute path given that way is
used as it stands.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from spjf_guard.sim.policy import Policy, aging, fcfs, fixed, guard, sjf, skip, spjf

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
SCORE_KEY = "spjf_e"
"""The configuration's name for the expected-cost score the paper calls SPJF-E."""
LOG_SCORE_KEY = "spjf_log"
"""The log-scale control fitted on the same features and run through the same simulator."""


class ConfigError(ValueError):
    """The configuration is missing something a run cannot proceed without."""


def _expand(value: Any) -> Any:
    if isinstance(value, str):

        def sub(m):
            name = m.group(1)
            if name not in os.environ:
                raise ConfigError(
                    f"the configuration refers to ${{{name}}}, which is not set; "
                    "export it or edit the file"
                )
            return os.environ[name]

        return _PLACEHOLDER.sub(sub, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


REQUIRED_SECTIONS = (
    "data",
    "semesters",
    "clock",
    "features",
    "predictor",
    "scheduling",
    "overlay",
    "metrics",
    "bootstrap",
    "run",
)


@dataclass(frozen=True)
class Config:
    """A loaded configuration, with the raw document kept for the protocol lock."""

    path: Path
    raw: dict

    def __getitem__(self, section: str) -> Any:
        try:
            return self.raw[section]
        except KeyError as exc:
            raise ConfigError(f"the configuration has no section {section!r}") from exc

    @property
    def root(self) -> Path:
        """The repository root: the directory `configs/` sits in."""
        folder = self.path.resolve().parent
        return folder.parent if folder.name == "configs" else folder

    def resolve(self, value: str | Path) -> Path:
        """A path from the document, anchored at the repository root when it is relative."""
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    def data_path(self, key: str, *parts: str) -> Path:
        """`data.<key>`, resolved, with any further components joined onto it."""
        value = self["data"].get(key)
        if value is None:
            raise ConfigError(f"the configuration has no data.{key}")
        return self.resolve(value).joinpath(*parts)

    @property
    def limit_s(self) -> float:
        return float(self["clock"]["limit_s"])

    @property
    def promises_s(self) -> list[float]:
        return [float(g) for g in self["scheduling"]["promises_s"]]

    def selected(self, promise_s: float) -> dict:
        """The joint winner for this promise: family, B0 base, eta, gamma base.

        This is the paper's Guard(G): the budget shape the rule picked across the three
        families, on validation overlays only.
        """
        table = self["scheduling"]["selected"]
        key = next((k for k in table if float(k) == promise_s), None)
        if key is None:
            raise ConfigError(f"no parameters are selected for the promise {promise_s}")
        entry = dict(table[key])
        entry.setdefault("gam_base_s", 0.0)
        return entry

    def family_best(self, promise_s: float, family: str) -> dict | None:
        """The best point inside one family: the ablation row for that budget shape."""
        table = self["scheduling"].get("family_best", {})
        key = next((k for k in table if float(k) == promise_s), None)
        if key is None or family not in table[key]:
            return None
        entry = dict(table[key][family])
        entry.setdefault("gam_base_s", 0.0)
        return entry

    def family_label(self, family: str) -> str:
        return self["scheduling"]["selection"]["family_names"].get(family, family)

    def _guard_from(self, entry: dict, promise: float, servers: int, name: str) -> Policy:
        return guard(
            promise,
            servers,
            self.limit_s,
            float(entry["b0_base_s"]) * servers / 4.0,
            float(entry["eta"]),
            self["scheduling"]["ranking_score"],
            name=name,
            gam_s=float(entry.get("gam_base_s", 0.0)) * servers / 4.0,
        )

    def policies(
        self,
        servers: int,
        include_log_control: bool = False,
        selection: dict | None = None,
        include_family_bests: bool = True,
    ) -> list[Policy]:
        """The reported policy set at one load level, in the order the tables print.

        Per promise: the joint winner (the paper's Guard(G)), the best point of each
        family (the ablation rows), the equal-promise constant budget, and the skip
        guard.  `selection` overrides the pinned parameters with what a selection run
        chose, keyed by (family, promise); `run_main` reports a disagreement rather than
        silently preferring one.
        """
        score_key = self["scheduling"]["ranking_score"]
        out: list[Policy] = [fcfs(), sjf(), spjf(score_key, "SPJF-E")]
        if include_log_control:
            log_key = (
                f"{LOG_SCORE_KEY}_conservative"
                if score_key.endswith("_conservative")
                else LOG_SCORE_KEY
            )
            out.append(spjf(log_key, "SPJF-log"))
        aging_section = self["scheduling"].get("aging_baseline")
        if aging_section:
            out.append(
                aging(
                    aging_section.get(
                        "ranking_score",
                        self["scheduling"].get("headline_ranking_score", score_key),
                    ),
                    float(aging_section["selected_credit_per_s"]),
                    str(aging_section["label"]),
                )
            )
        chosen = selection or {}
        for promise in self.promises_s:
            joint = chosen.get(("joint", promise)) or self.selected(promise)
            out.append(self._guard_from(joint, promise, servers, f"Guard({promise:g})"))
            if include_family_bests:
                for family in ("fixed", "capped", "hybrid"):
                    entry = chosen.get((family, promise)) or self.family_best(promise, family)
                    if entry is None:
                        continue
                    label = f"{self.family_label(family)}({promise:g})"
                    out.append(self._guard_from(entry, promise, servers, label))
            out.append(fixed(promise, servers, self.limit_s, score_key))
            out.append(skip(promise, servers, self.limit_s, score_key))
        return out


def load(path: str | Path, expand_environment: bool = True) -> Config:
    """Read a configuration and check that every section a run needs is present."""
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} does not hold a mapping")
    missing = [s for s in REQUIRED_SECTIONS if s not in raw]
    if missing:
        raise ConfigError(f"{path} is missing the section(s) {missing}")
    _check_pinned_constants(path, raw)
    return Config(path=path, raw=_expand(raw) if expand_environment else raw)


def _check_pinned_constants(path: Path, raw: dict) -> None:
    """Five keys the lock hashes are constants of the code, not values it reads.

    The heavy quantile, the class cuts, the reference terms of the heavy label, the
    extra-week range of an overlay copy and the harm's start-immediately threshold are
    fixed in the modules that use them.  The configuration states them so that the
    protocol lock covers them; a file that states a different value would change
    nothing at run time, so loading it is refused instead.
    """
    from spjf_guard.data.events import CLASS_CUT_QUANTILES, HEAVY_QUANTILE
    from spjf_guard.experiment.metrics import STARTS_IMMEDIATELY_S
    from spjf_guard.experiment.overlay import SHIFT_WEEKS_MAX

    features, overlay, metrics = raw["features"], raw["overlay"], raw["metrics"]
    pinned = {
        "features.heavy_quantile": (features.get("heavy_quantile"), HEAVY_QUANTILE),
        "features.class_cut_quantiles": (
            tuple(features.get("class_cut_quantiles", ())),
            CLASS_CUT_QUANTILES,
        ),
        "features.heavy_reference_semesters": (
            list(features.get("heavy_reference_semesters", [])),
            list(raw["semesters"]["train"]),
        ),
        "overlay.shift_weeks_max": (overlay.get("shift_weeks_max"), SHIFT_WEEKS_MAX),
        "metrics.starts_immediately_s": (
            metrics.get("starts_immediately_s"),
            STARTS_IMMEDIATELY_S,
        ),
    }
    wrong = [
        f"{key}: file says {stated!r}, code uses {used!r}"
        for key, (stated, used) in pinned.items()
        if stated != used and not _close(stated, used)
    ]
    if wrong:
        raise ConfigError(f"{path} disagrees with the code's constants: " + "; ".join(wrong))


def _close(stated: Any, used: Any) -> bool:
    """Equality up to float rounding, element-wise for tuples."""
    try:
        if isinstance(used, tuple):
            return len(stated) == len(used) and all(
                abs(float(a) - float(b)) < 1e-12 for a, b in zip(stated, used)
            )
        return abs(float(stated) - float(used)) < 1e-12
    except (TypeError, ValueError):
        return False
