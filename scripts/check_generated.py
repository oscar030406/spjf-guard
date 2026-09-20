"""Check that every generated artefact still matches its recipe (see GENERATED.md).

    uv run python scripts/check_generated.py [--only protocol_lock]

A hand edit to a generated file fails here.  Artefacts that are not on disk are skipped
with a note rather than treated as failures, because a fresh clone has none of them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

VOLATILE = ("written_at",)
"""Fields that differ between two runs of the same recipe and carry no information."""


def _strip(lock: dict) -> dict:
    return {k: v for k, v in lock.items() if k not in VOLATILE}


def check_protocol_lock() -> tuple[bool, str]:
    from make_protocol_lock import build

    path = ROOT / "protocol_lock.draft.json"
    if not path.is_file():
        return True, "protocol_lock.draft.json: not on disk, skipped"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    rebuilt = build(ROOT / on_disk["config"]["path"], ROOT)
    if _strip(on_disk) == _strip(rebuilt):
        return True, "protocol_lock.draft.json: matches its recipe"
    differing = sorted(
        k
        for k in set(_strip(on_disk)) | set(_strip(rebuilt))
        if _strip(on_disk).get(k) != _strip(rebuilt).get(k)
    )
    return False, (
        f"protocol_lock.draft.json: stale or hand-edited; section(s) "
        f"{differing} differ. Regenerate with "
        f"scripts/make_protocol_lock.py"
    )


def check_outputs() -> tuple[bool, str]:
    """Every `manifest.json` under the output directory still describes its directory.

    Each run writes one beside the tables it produced.  The check is a hash comparison,
    not a rerun: it catches a hand-edited CSV and a configuration that moved under a
    table, and says nothing about whether the numbers are right.
    """
    from spjf_guard.experiment.provenance import MANIFEST_NAME, verify

    manifests = sorted(p for p in ROOT.glob(f"outputs/**/{MANIFEST_NAME}") if p.is_file())
    if not manifests:
        return True, "outputs: no manifest on disk, skipped"
    complaints = []
    for path in manifests:
        where = path.parent.relative_to(ROOT)
        complaints += [f"{where}/{c}" for c in verify(path)]
    if complaints:
        return False, "outputs: " + "; ".join(complaints)
    return True, f"outputs: {len(manifests)} manifest(s) match the files on disk"


def check_paper_numbers() -> tuple[bool, str]:
    """Every `\\devnum{}` in the paper has a producing artefact or a stated reason.

    The failure this catches is a number with no source at all: a figure that was once
    measured, then edited in the text, and now points at nothing.
    """
    import csv

    path = ROOT / "outputs" / "paper_tables" / "numbers.csv"
    if not path.is_file():
        return True, "paper numbers: outputs/paper_tables/numbers.csv not on disk, skipped"
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    orphans = [r for r in rows if not r["produced_by"] and not r["not_produced"]]
    produced = sum(1 for r in rows if r["produced_by"])
    differs = sum(1 for r in rows if r["not_produced"] == "package-differs")
    if orphans:
        first = ", ".join(r["key"] for r in orphans[:5])
        return False, (
            f"paper numbers: {len(orphans)} of {len(rows)} have neither a source nor a "
            f"reason ({first}...); rerun scripts/emit_paper_tables.py"
        )
    return True, (
        f"paper numbers: {len(rows)} numbers, {produced} printed identically by this "
        f"package, {differs} printed differently by it, "
        f"{len(rows) - produced - differs} from outside the package"
    )


def check_paper_prints() -> tuple[bool, str]:
    """The paper prints what the package produced (scripts/check_paper_numbers.py).

    Skipped when `paper/` or the tables are not on disk, so a clone without the paper
    still passes the other checks.
    """
    from check_paper_numbers import run

    paper = ROOT / "paper"
    dev = ROOT / "outputs" / "dev_tables"
    package = ROOT / "outputs" / "paper_tables"
    if not (paper.is_dir() and (dev / "main_table.csv").is_file()):
        return True, "paper prints: paper/ or outputs/dev_tables/ not on disk, skipped"
    complaints = run(paper, dev, package)
    if complaints:
        return False, "paper prints: " + "; ".join(complaints[:4]) + (
            f" (and {len(complaints) - 4} more)" if len(complaints) > 4 else ""
        )
    return True, "paper prints: the paper agrees with the package, value for value"


MACHINE_PATHS = (
    "App" + "Data",
    "Temp" + "/",
    "scratch" + "pad",
    "C:/Use" + "rs",
    "C:\\Use" + "rs",
)
"""What a path that belongs to one machine, or to one session, looks like.

Any of these inside a file the repository carries means the repository is describing this
computer rather than the experiment: a reader who clones it gets a path that never existed
for them, and a path under a session temporary directory is gone the next day.  The
needles are spelled in halves so that this file is not itself an instance of what it
looks for.
"""

SCANNED = (
    "configs/*.yaml",
    "scripts/*.py",
    "src/spjf_guard/**/*.py",
    "tests/*.py",
    "docs/**/*.md",
    "*.md",
    "*.toml",
    "protocol_lock*.json",
)
"""The file sets that go into the repository.  Everything under `data/` and `outputs/` is
git-ignored and is skipped, as is any other file git is told to ignore."""

PATH_EXCEPTIONS = {
    "docs/related_work/shared_queue_evidence.md": "prose: it says where a one-off probe "
    "script was run from, and says in the same sentence that the directory is temporary "
    "and that nothing reads it",
}
"""Files allowed to name a machine path, with the reason.  A file earns a place here only
when the path is the subject of a sentence, never when something reads it."""


def _ignored() -> set[str]:
    """What git is configured to ignore, as repository-relative names and directories.

    Asked in one call.  When git cannot be asked -- no git, no repository yet -- the set
    is empty and every candidate is scanned, which is the safe direction for a check.
    """
    import subprocess

    try:
        done = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--directory"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.strip().rstrip("/") for line in done.stdout.splitlines() if line.strip()}


def _is_ignored(relative: str, ignored: set[str]) -> bool:
    parts = relative.split("/")
    return any("/".join(parts[: i + 1]) in ignored for i in range(len(parts)))


def check_paths() -> tuple[bool, str]:
    """No file the repository carries names a path that exists only on this machine."""
    candidates = [
        p
        for pattern in SCANNED
        for p in sorted(ROOT.glob(pattern))
        if p.is_file() and not {"outputs", "data"} & set(p.parts)
    ]
    ignored = _ignored()
    complaints, scanned = [], 0
    for path in candidates:
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        if _is_ignored(relative, ignored):
            continue
        scanned += 1
        if relative in PATH_EXCEPTIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = sorted({needle for needle in MACHINE_PATHS if needle in text})
        if hits:
            complaints.append(f"{relative}: {', '.join(hits)}")
    if complaints:
        return False, (
            "machine paths: "
            + "; ".join(complaints)
            + " -- write the path relative to the repository, or put the file under "
            "data/derived/ and name it in the configuration"
        )
    return True, (
        f"machine paths: none in {scanned} tracked files "
        f"({len(PATH_EXCEPTIONS)} documented exception)"
    )


CHECKS = {
    "outputs": check_outputs,
    "paper_numbers": check_paper_numbers,
    "paper_prints": check_paper_prints,
    "paths": check_paths,
    "protocol_lock": check_protocol_lock,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(CHECKS))
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "scripts"))
    names = [args.only] if args.only else sorted(CHECKS)
    failed = 0
    for name in names:
        ok, message = CHECKS[name]()
        print(("ok   " if ok else "FAIL ") + message)
        failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
