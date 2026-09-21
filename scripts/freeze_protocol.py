"""Freeze the protocol: every gate green, every input hashed, then the lock is written.

    uv run python scripts/freeze_protocol.py [--skip-gates] [--dry-run] [--yes]

Freezing is the moment the method stops being editable, so this script does the checking
that a person cannot be relied on to do at that moment, and nothing else:

1. **The tree is committed.**  A frozen lock names a commit; a dirty tree or a repository
   with no commit means the lock would name code that is not recoverable.  Refused.
2. **Every gate passes**: ruff, mypy, the whole test suite, the generated-artefact checks
   and the paper-number checks.  A gate that fails after the freeze is a gate that was
   never run before it.
3. **Every input is hashed**, including the sealed archives and the sealed per-semester
   parquet -- their *bytes*, never their contents.  Hashing is a read, so each hashed
   sealed file gets its own row in `docs/sealed_access_log.md`: the ledger has to show
   every time a sealed file was opened at all, even to be weighed.  `--dry-run` therefore
   lists the files and their sizes and hashes nothing: a rehearsal that opened 1.58 GB of
   sealed archives and wrote no row would be the very thing the ledger is for.
4. **`protocol_lock.json` is written** from the draft, with the commit id and the sealed
   input hashes added, and the draft is left where it is.

After this the tests that assert no frozen lock exists will fail; that is what they are
for.  `--dry-run` does everything except write the lock and the ledger rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from spjf_guard import config as cfgmod  # noqa: E402
from spjf_guard.data import sealed  # noqa: E402

GATES = (
    ("ruff", ("-m", "ruff", "check", "src", "tests", "scripts")),
    ("ruff format", ("-m", "ruff", "format", "--check", "src", "tests", "scripts")),
    ("mypy", ("-m", "mypy")),
    ("pytest", ("-m", "pytest", "-q")),
    ("generated artefacts", ("scripts/check_generated.py",)),
    ("paper numbers", ("scripts/check_paper_numbers.py",)),
)
"""What has to be green before the method stops being editable.

Every gate is spelled as arguments to *this* interpreter rather than as a command name:
`python`, `ruff` and `mypy` on the PATH are whichever ones the shell finds, which on this
machine is an interpreter without the project's dependencies, and a freeze that reported
`No module named pytest` as a failing gate would be reporting the PATH, not the code.
"""

DRAFT = "protocol_lock.draft.json"
FROZEN = "protocol_lock.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("git",) + args, cwd=ROOT, capture_output=True, text=True, timeout=120
    )


def commit_state() -> tuple[str | None, list[str]]:
    """(commit id, complaints).  A commit id of None means the freeze cannot proceed."""
    complaints = []
    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        return None, ["the repository has no commit yet; commit before freezing"]
    status = git("status", "--porcelain")
    if status.returncode != 0:
        return None, ["git status failed; is this a repository?"]
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    if dirty:
        complaints.append(
            f"the working tree has {len(dirty)} uncommitted change(s), first: "
            f"{dirty[0].strip()}"
        )
    return head.stdout.strip(), complaints


def run_gates(runner: tuple[str, ...] = (sys.executable,)) -> list[str]:
    """Every gate, in order, in this interpreter; returns the ones that failed."""
    failed = []
    for name, command in GATES:
        done = subprocess.run(runner + command, cwd=ROOT, capture_output=True, text=True)
        state = "ok  " if done.returncode == 0 else "FAIL"
        print(f"  {state} {name}")
        if done.returncode != 0:
            tail = (done.stdout or done.stderr).strip().splitlines()[-3:]
            for line in tail:
                print(f"       {line}")
            failed.append(name)
    return failed


def sealed_files(cfg) -> list[Path]:
    """Every sealed input the run will read: the archives and the per-semester tables.

    They are hashed, not opened for content.  Naming them here is also the last chance to
    see the list before it becomes part of the frozen document.  A file that is not on
    disk is an error and not a shorter list: the lock would then promise a set of inputs
    that nobody can check, and the document says twelve.
    """
    from spjf_guard.data.cache import sealed_inputs

    out = sealed_inputs(
        cfg.data_path("archive_dir"),
        cfg.data_path("raw_parquet_dir"),
        list(cfg["overlay"]["pools"]["sealed"]),
    )
    missing = [p for p in out if not p.is_file()]
    if missing:
        from make_protocol_lock import relative_to_root

        raise SystemExit(
            "these sealed inputs are not on disk: "
            + ", ".join(relative_to_root(p, ROOT) for p in missing)
            + f" ({len(out) - len(missing)} of {len(out)} present). The lock would name "
            "files it never saw; put them in place or fix the configuration."
        )
    return out


def hash_sealed_inputs(cfg, root: Path) -> list[dict]:
    """sha256 of each sealed file's bytes, with its size, nothing else."""
    from make_protocol_lock import relative_to_root

    out = []
    for path in sealed_files(cfg):
        out.append(
            {
                "path": relative_to_root(path, root),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return out


def write_ledger_rows(entries: list[dict], terms: list[str]) -> None:
    """One ledger row per sealed file whose bytes were read to hash it."""
    for entry in entries:
        sealed.record_access(
            ROOT,
            "scripts/freeze_protocol.py",
            f"封存学期 {', '.join(terms)}",
            f"只读取字节求 sha256：{entry['path']}（{entry['bytes']:,} 字节），未解析内容",
            "冻结脚本",
            "否",
        )


def build_frozen(draft: dict, commit: str, sealed_hashes: list[dict]) -> dict:
    document = dict(draft)
    document["status"] = "frozen"
    document["commit"] = commit
    document["sealed_input_hashes"] = sealed_hashes
    return document


def _already_done(frozen_path: Path, draft_path: Path) -> list[str]:
    """Why there is nothing to freeze: it is done, or there is no draft to freeze."""
    if frozen_path.is_file():
        return [f"{FROZEN} already exists; the protocol is frozen. Nothing to do."]
    if not draft_path.is_file():
        return [f"{DRAFT} is not on disk; run scripts/make_protocol_lock.py first."]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "main.yaml")
    ap.add_argument("--skip-gates", action="store_true", help="for testing this script only")
    ap.add_argument("--dry-run", action="store_true", help="check and print, write nothing")
    ap.add_argument("--yes", action="store_true", help="do not ask before writing the lock")
    args = ap.parse_args()

    frozen_path, draft_path = ROOT / FROZEN, ROOT / DRAFT
    for complaint in _already_done(frozen_path, draft_path):
        print(complaint)
        return 1

    print("1. the tree")
    commit, complaints = commit_state()
    for complaint in complaints:
        print(f"  FAIL {complaint}")
    if commit is None or complaints:
        return 1
    print(f"  ok   committed at {commit[:12]}")

    print("2. the gates")
    failed = [] if args.skip_gates else run_gates()
    if args.skip_gates:
        print("  skipped by request; this is only correct when testing the script itself")
    if failed:
        print(f"  {len(failed)} gate(s) failed: {', '.join(failed)}")
        return 1

    print("3. the sealed inputs")
    cfg = cfgmod.load(args.config)
    terms = list(cfg["overlay"]["pools"]["sealed"])
    files = sealed_files(cfg)
    if args.dry_run:
        # A dry run does not open a sealed file, not even to weigh it: reading the bytes
        # to hash them is an opening, and an opening that writes no ledger row is exactly
        # what the ledger exists to prevent.  The names and the sizes are what a person
        # checks here, and `stat` reads neither.
        from make_protocol_lock import relative_to_root

        for path in files:
            print(f"  {path.stat().st_size:>14,}  {relative_to_root(path, ROOT)}")
        print(f"  dry run: {len(files)} sealed file(s) listed, none opened, none hashed")
        print(f"  dry run: {FROZEN} not written, no ledger row appended")
        return 0
    entries = hash_sealed_inputs(cfg, ROOT)
    for entry in entries:
        print(f"  {entry['sha256'][:16]}  {entry['bytes']:>14,}  {entry['path']}")

    print("4. the lock")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    document = build_frozen(draft, commit, entries)
    if not args.yes:
        print("  re-run with --yes to write the lock; freezing is a decision, not a step")
        return 0
    write_ledger_rows(entries, terms)
    frozen_path.write_text(
        json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {FROZEN} at commit {commit[:12]}, sha256 {sha256_file(frozen_path)}")
    print(f"  appended {len(entries)} row(s) to {sealed.LOG_RELATIVE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
