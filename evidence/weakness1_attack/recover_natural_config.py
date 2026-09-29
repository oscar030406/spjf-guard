"""Recover the frozen natural-preflight config source from Git history.

This script reads only repository source history and the current config source.  It
does not import the project package and does not inspect any data artifact.  Recovery
succeeds only when the exact expected SHA-256 is reproduced.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RELATIVE = "src/spjf_guard/config.py"
CURRENT = ROOT / RELATIVE
PINNED = HERE / "pinned_src" / "spjf_guard" / "config.py"
LOG = HERE / "out_natural_source_recovery.txt"
EXPECTED = "b3f13b89d146005fde6056c7c3117473803809fcaccf84c1b949c2434bbdf23c"
sys.dont_write_bytecode = True


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def git_bytes(*arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed with {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout


def variants(blob: bytes):
    lf = blob.replace(b"\r\n", b"\n")
    newline_forms = {
        "git_blob": blob,
        "normalized_lf": lf,
        "checkout_crlf": lf.replace(b"\n", b"\r\n"),
    }
    emitted = set()
    for newline_name, value in newline_forms.items():
        for ending_name, ended in (
            ("terminal_newline", value),
            ("no_terminal_newline", value.rstrip(b"\r\n")),
        ):
            for bom_name, candidate in (
                ("no_bom", ended),
                ("utf8_bom", b"\xef\xbb\xbf" + ended),
            ):
                if candidate in emitted:
                    continue
                emitted.add(candidate)
                yield f"{newline_name}_{ending_name}_{bom_name}", candidate


def without_aging_extension(current: bytes) -> list[tuple[str, bytes]]:
    """Remove only the two aging additions, retaining every other working-tree edit."""
    lf = current.replace(b"\r\n", b"\n")
    old_import = (
        b"from spjf_guard.sim.policy import Policy, aging, fcfs, fixed, guard, sjf, skip, spjf"
    )
    new_import = b"from spjf_guard.sim.policy import Policy, fcfs, fixed, guard, sjf, skip, spjf"
    block = (
        b"        aging_section = self[\"scheduling\"].get(\"aging_baseline\")\n"
        b"        if aging_section:\n"
        b"            out.append(\n"
        b"                aging(\n"
        b"                    self[\"scheduling\"].get(\"headline_ranking_score\", score_key),\n"
        b"                    float(aging_section[\"selected_credit_per_s\"]),\n"
        b"                    str(aging_section[\"label\"]),\n"
        b"                )\n"
        b"            )\n"
    )
    if lf.count(old_import) != 1 or lf.count(block) != 1:
        raise RuntimeError("current config does not contain exactly the expected aging additions")
    reduced = lf.replace(old_import, new_import, 1).replace(block, b"", 1)
    return [
        ("working_tree_minus_aging_lf", reduced),
        ("working_tree_minus_aging_crlf", reduced.replace(b"\n", b"\r\n")),
    ]


def main() -> int:
    wall0, cpu0 = time.perf_counter(), time.process_time()
    current_before = digest_file(CURRENT)
    commits = git_bytes("rev-list", "--all", "--", RELATIVE).decode("ascii").splitlines()
    if not commits:
        raise RuntimeError(f"no Git history found for {RELATIVE}")

    examined = []
    match = None
    seen = set()
    for commit in commits:
        if commit in seen:
            continue
        seen.add(commit)
        blob = git_bytes("cat-file", "blob", f"{commit}:{RELATIVE}")
        row = {"commit": commit, "representations": []}
        for representation, content in variants(blob):
            observed = digest_bytes(content)
            row["representations"].append(
                {"name": representation, "sha256": observed, "bytes": len(content)}
            )
            if observed == EXPECTED and match is None:
                match = (commit, representation, content)
        examined.append(row)

    current_bytes = CURRENT.read_bytes()
    intermediate_candidates = []
    for representation, content in without_aging_extension(current_bytes):
        observed = digest_bytes(content)
        intermediate_candidates.append(
            {"name": representation, "sha256": observed, "bytes": len(content)}
        )
        if observed == EXPECTED and match is None:
            match = ("uncommitted_working_tree_intermediate", representation, content)

    if match is None:
        result = {
            "status": "FAIL",
            "scope": "bounded source-only recovery; no data artifact accessed",
            "logical_path": RELATIVE,
            "expected_sha256": EXPECTED,
            "current_worktree_sha256": current_before,
            "commits_examined": examined,
            "working_tree_minus_aging_candidates": intermediate_candidates,
            "pinned_written": False,
            "execution": {
                "python_processes": 1,
                "git_subprocess_calls": 1 + len(commits),
                "wall_s": time.perf_counter() - wall0,
                "cpu_s": time.process_time() - cpu0,
            },
        }
        LOG.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="")
        raise RuntimeError("expected config SHA-256 was not found in the bounded source candidates")

    commit, representation, content = match
    PINNED.parent.mkdir(parents=True, exist_ok=True)
    temporary = PINNED.with_suffix(".py.tmp")
    temporary.write_bytes(content)
    if digest_file(temporary) != EXPECTED:
        raise RuntimeError("temporary recovered config does not match expected SHA-256")
    temporary.replace(PINNED)
    if digest_file(PINNED) != EXPECTED:
        raise RuntimeError("pinned recovered config does not match expected SHA-256")
    current_after = digest_file(CURRENT)
    if current_after != current_before:
        raise RuntimeError("current repository config changed during source recovery")

    result = {
        "status": "PASS",
        "scope": "bounded source-only recovery; no data artifact accessed",
        "logical_path": RELATIVE,
        "expected_sha256": EXPECTED,
        "current_worktree_sha256": current_before,
        "current_worktree_preserved": True,
        "recovered_from_commit": commit,
        "recovered_representation": representation,
        "commits_examined": examined,
        "pinned": {
            "path": PINNED.relative_to(ROOT).as_posix(),
            "sha256": digest_file(PINNED),
            "bytes": PINNED.stat().st_size,
        },
        "recovery_script_sha256": digest_file(Path(__file__)),
        "execution": {
            "python_processes": 1,
            "git_subprocess_calls": 1 + len(commits),
            "wall_s": time.perf_counter() - wall0,
            "cpu_s": time.process_time() - cpu0,
        },
    }
    text = json.dumps(result, indent=2) + "\n"
    LOG.write_text(text, encoding="utf-8", newline="")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
