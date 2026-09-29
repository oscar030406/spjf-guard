"""Path-level protection for the sealed part of every trace.

The sealed terms and blocks are named here and nowhere else.  Any read of one is refused
unless two things hold at once: a frozen `protocol_lock.json` exists (the draft does not
count), and the caller passed `--unseal` explicitly.  When a read is permitted, a line is
appended to `docs/sealed_access_log.md`, whose columns are the ones that file already
carries: date, script, what was read, what came out, who saw the output, and whether it
influenced the design.

What this protects against is reading the test result and then changing the method.  It
is not a claim that a file may be opened only once.
"""

from __future__ import annotations

import contextlib as _contextlib
import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path

SEALED_SEMESTERS = ("2023-1", "2023-2", "2024-1")
"""CodeBench terms that stay shut until the protocol is frozen."""

SEALED_ID_BLOCK = (0.80, 1.00)
"""ACcoding submission-id quantile range that stays shut."""

SEALED_OULAD_YEAR = "2014"
"""The OULAD academic year that stays shut."""

DEVELOPMENT_SEMESTERS = (
    "2018-1",
    "2018-2",
    "2019-1",
    "2019-2",
    "2020-ERE",
    "2020-1",
    "2020-2",
    "2021-1",
    "2021-2",
    "2022-1",
    "2022-2",
)
"""The whitelist: every term a development run may read."""

LOG_RELATIVE_PATH = Path("docs") / "sealed_access_log.md"

CONFIG_SNAPSHOT_PATHS = (
    Path("configs") / "main_original_84932d9.yaml",
    Path("configs") / "visibility_development_20260922.yaml",
    Path("configs") / "visibility_development_20260924.yaml",
    Path("configs") / "main_frozen_1289aa2.yaml",
)
"""Archived ordinary configurations that the frozen protocol must preserve."""


class SealedDataError(RuntimeError):
    """Raised when a sealed term, id block or academic year would be read."""


@dataclass(frozen=True)
class AccessDecision:
    """Whether a read of sealed material is permitted, and why."""

    permitted: bool
    reason: str
    lock_path: Path | None = None


def is_sealed_semester(semester: str) -> bool:
    return semester in SEALED_SEMESTERS


def sealed_semesters_in(semesters) -> tuple[str, ...]:
    return tuple(s for s in semesters if is_sealed_semester(s))


def check_semester_whitelist(semesters) -> None:
    """Refuse any term that is neither a development term nor explicitly unsealed."""
    unknown = [
        s for s in semesters if s not in DEVELOPMENT_SEMESTERS and not is_sealed_semester(s)
    ]
    if unknown:
        raise SealedDataError(
            f"{unknown} are not on the development whitelist and are not sealed terms; "
            "add them to DEVELOPMENT_SEMESTERS deliberately or fix the caller"
        )


def frozen_lock(project_root: Path) -> Path | None:
    """The frozen protocol lock, or None.  `protocol_lock.draft.json` does not count."""
    lock = Path(project_root) / "protocol_lock.json"
    return lock if lock.is_file() else None


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _code_complaints(document: dict) -> list[str]:
    recorded = document.get("code")
    if not isinstance(recorded, dict):
        return ["the lock has no code manifest"]
    if not isinstance(recorded.get("files"), list) or not _valid_sha256(recorded.get("digest")):
        return ["the lock has an incomplete code manifest"]
    return []


def _config_complaints(document: dict) -> list[str]:
    recorded = document.get("config")
    if not isinstance(recorded, dict) or recorded.get("path") != "configs/main.yaml":
        return ["the lock does not name configs/main.yaml"]
    if not _valid_sha256(recorded.get("sha256")):
        return ["the lock has no configs/main.yaml digest"]
    return []


def _snapshot_complaints(document: dict) -> list[str]:
    recorded = document.get("config_snapshots")
    if not isinstance(recorded, list) or any(not isinstance(entry, dict) for entry in recorded):
        return ["the lock has no archived-configuration manifest"]
    by_path = {entry.get("path"): entry for entry in recorded}
    expected = {str(path).replace("\\", "/") for path in CONFIG_SNAPSHOT_PATHS}
    if set(by_path) != expected or len(recorded) != len(expected):
        return ["the archived-configuration manifest has missing or extra paths"]
    invalid = [
        path
        for path, entry in by_path.items()
        if not isinstance(entry.get("present"), bool)
        or (entry["present"] and not _valid_sha256(entry.get("sha256")))
        or (not entry["present"] and entry.get("sha256") is not None)
    ]
    return (
        [f"the archived-configuration manifest has invalid entries {invalid}"]
        if invalid
        else []
    )


def _sealed_hash_complaints(document: dict) -> list[str]:
    entries = document.get("sealed_input_hashes")
    if not isinstance(entries, list) or not entries:
        return ["the lock has no sealed input hashes"]
    invalid = [
        entry
        for entry in entries
        if not isinstance(entry, dict)
        or not isinstance(entry.get("path"), str)
        or not _valid_sha256(entry.get("sha256"))
        or not isinstance(entry.get("bytes"), int)
        or entry["bytes"] < 0
    ]
    if invalid:
        return ["the lock has an incomplete sealed input hash entry"]
    return []


def frozen_lock_complaints(project_root: Path, document: dict) -> list[str]:
    """Why a lock cannot release data, without reading or hashing any sealed input."""
    del project_root
    complaints = []
    if document.get("status") != "frozen":
        complaints.append("protocol_lock.json does not have status=frozen")
    commit = document.get("commit")
    valid_commit = (
        isinstance(commit, str)
        and len(commit) == 40
        and all(character in "0123456789abcdef" for character in commit)
    )
    if not valid_commit:
        complaints.append("the lock has no valid frozen commit")
    complaints += _sealed_hash_complaints(document)
    complaints += _config_complaints(document)
    complaints += _snapshot_complaints(document)
    complaints += _code_complaints(document)
    return complaints


def decide(project_root: Path, unseal: bool) -> AccessDecision:
    """Whether sealed material may be read right now."""
    root = Path(project_root)
    lock = frozen_lock(root)
    if lock is None:
        return AccessDecision(False, "no frozen protocol_lock.json exists")
    if not unseal:
        return AccessDecision(False, "the --unseal flag was not given", lock)
    try:
        document = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return AccessDecision(
            False, f"protocol_lock.json cannot be read ({type(exc).__name__})", lock
        )
    if not isinstance(document, dict):
        return AccessDecision(False, "protocol_lock.json is not a JSON object", lock)
    complaints = frozen_lock_complaints(root, document)
    if complaints:
        return AccessDecision(False, "; ".join(complaints), lock)
    return AccessDecision(True, "validated frozen protocol lock and --unseal given", lock)


def guard_semesters(semesters, project_root: Path, unseal: bool = False) -> None:
    """Refuse the read unless every sealed term in `semesters` has been released.

    Raises `SealedDataError` and touches no file when the read is not permitted, so the
    refusal can be tested without the data being present.
    """
    check_semester_whitelist(semesters)
    sealed = sealed_semesters_in(semesters)
    if not sealed:
        return
    decision = decide(Path(project_root), unseal)
    if not decision.permitted:
        raise SealedDataError(
            f"refusing to read the sealed term(s) {list(sealed)}: {decision.reason}. "
            "Freeze the protocol with scripts/freeze_protocol.py --dry-run followed by "
            "scripts/freeze_protocol.py --yes, then pass --unseal."
        )


def guard_id_block(
    quantile_lo: float, quantile_hi: float, project_root: Path, unseal: bool = False
) -> None:
    """The ACcoding equivalent: submission-id quantiles 0.80-1.00 are sealed."""
    lo, hi = SEALED_ID_BLOCK
    if quantile_hi <= lo or quantile_lo >= hi:
        return
    decision = decide(Path(project_root), unseal)
    if not decision.permitted:
        raise SealedDataError(
            f"refusing to read the sealed ACcoding id block [{lo}, {hi}] "
            f"(request [{quantile_lo}, {quantile_hi}]): {decision.reason}"
        )


def guard_oulad_year(year: str, project_root: Path, unseal: bool = False) -> None:
    if str(year) != SEALED_OULAD_YEAR:
        return
    decision = decide(Path(project_root), unseal)
    if not decision.permitted:
        raise SealedDataError(
            f"refusing to read the sealed OULAD year {year}: {decision.reason}"
        )


def _with_row(text: str, row: str) -> str:
    """The ledger with one row added to its table, not to the end of the file.

    The ledger's table is followed by a sentence about what has not been computed on any
    sealed part.  A row appended to the file lands under that sentence, where it reads as
    a second table with no header and makes the sentence look like it was written first;
    a reader then meets "nothing has been computed" above twelve rows saying what was
    read.  So a row goes after the last row of the table, and the prose stays last.
    """
    lines = text.splitlines(keepends=True)
    table = [i for i, line in enumerate(lines) if line.lstrip().startswith("|")]
    at = table[-1] + 1 if table else len(lines)
    if at and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    return "".join(lines[:at] + [row] + lines[at:])


def record_access(
    project_root: Path,
    script: str,
    what: str,
    produced: str,
    seen_by: str,
    influenced_design: str = "否",
) -> Path:
    """Add one row to the ledger's table.  Called for a permitted sealed read.

    The columns are the ones `docs/sealed_access_log.md` already uses:
    date, script, what was read, what came out, who saw it, whether it changed the design.
    Every call adds a row; none rewrites one, because a second reading of the same file is
    a second entry and the ledger is the record of how often a sealed part was opened.
    """
    path = Path(project_root) / LOG_RELATIVE_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"the ledger {path} is missing; a sealed read cannot be "
            "recorded and therefore must not happen"
        )
    today = _dt.date.today().isoformat()
    row = f"| {today} | `{script}` | {what} | {produced} | {seen_by} | {influenced_design} |\n"
    path.write_text(
        _with_row(path.read_text(encoding="utf-8"), row), encoding="utf-8", newline=""
    )
    return path


def record_run(
    project_root: Path,
    script: str,
    semesters,
    produced: str,
    unseal: bool,
    seen_by: str = "运行者",
    influenced_design: str = "否",
) -> Path | None:
    """Append the ledger row for a run that actually read sealed terms, or nothing.

    The entry points call this after they finish, not before: the row says what came
    out, which is only known then.  A run over development terms writes nothing, so a
    script can call it unconditionally.
    """
    sealed = sealed_semesters_in(semesters)
    if not sealed or not unseal:
        return None
    return record_access(
        project_root,
        script,
        f"封存学期 {', '.join(sealed)}",
        produced,
        seen_by,
        influenced_design,
    )


class RunOutcome:
    """What a command will put in the ledger's "what came out" column.

    It starts as "interrupted": a command that reads a sealed part and then dies has read
    it, and the ledger has to say so.  The entry point replaces it once it knows what it
    produced, and `recording` writes whichever text is current when the block ends.
    """

    def __init__(self) -> None:
        self.produced = "运行中断，未产出"

    def done(self, produced: str) -> None:
        self.produced = produced

    def at(self, step: str) -> None:
        """Where the run has got to, for the row an interruption would leave."""
        self.produced = f"运行中断于{step}，未产出汇总表"


@_contextlib.contextmanager
def recording(project_root: Path, script: str, semesters, unseal: bool, seen_by="运行者"):
    """Run a command's sealed work, and write its ledger row however it ends.

    The row used to be written after the work, so a command that read a sealed part and
    then crashed left nothing in the ledger at all -- the one state the ledger exists to
    make impossible.  Now the row is written in a `finally`, and it says whether the run
    finished or where it stopped.  A re-run adds its own row; nothing is rewritten.

    A process that is killed outright (out of memory, the machine goes down) still writes
    nothing, which is why `docs/sealed_run_procedure.md` also asks for that row by hand.
    """
    outcome = RunOutcome()
    refused = False
    try:
        yield outcome
    except SealedDataError:
        # The guard raises this before anything is opened, so there is nothing to record:
        # a row here would say a sealed term was read when it was refused.
        refused = True
        raise
    except BaseException as exc:  # noqa: BLE001 -- the row is written, then it is re-raised
        outcome.produced = f"{outcome.produced}（{type(exc).__name__}: {str(exc)[:120]}）"
        raise
    finally:
        if not refused:
            record_run(project_root, script, semesters, outcome.produced, unseal, seen_by)


def lock_fingerprint(project_root: Path) -> dict | None:
    """The frozen lock's contents, for a run to quote in its own output."""
    lock = frozen_lock(Path(project_root))
    if lock is None:
        return None
    with open(lock, encoding="utf-8") as fh:
        return json.load(fh)
