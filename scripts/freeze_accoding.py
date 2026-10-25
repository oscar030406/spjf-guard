"""Check a committed ACcoding protocol and write its independent lock only with --yes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))

import run_accoding_heldout as heldout  # noqa: E402


def clean_commit(root=ROOT):
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise RuntimeError("refusing freeze: dirty git tree\n" + status.stdout.strip())
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_lock(root, config, commit):
    files = heldout.required_files(root, config)
    return {
        "status": "frozen",
        "commit": commit,
        "runtime_versions": heldout.runtime_versions(),
        "sha256": {name: heldout.provenance.sha256_file(root / name) for name in files},
        "config_values": config,
        "params_files": config["guard"]["params_files"],
        "parameters": {
            name: heldout.read_parameters(root / name, config)
            for name in config["guard"]["params_files"]
        },
        "outputs": heldout.output_names("sealed"),
        "sealed_block": {
            "quantiles": [0.80, 1.00],
            "first_id": heldout.SEALED_FIRST_ID,
            "rows": config["data"]["row_bounds"][4] - config["data"]["row_bounds"][3],
        },
        "tests": [sys.executable, "-m", "pytest", "-q", "tests/test_accoding_heldout.py"],
        "package_gate": "Existing protocol_lock.json must also pass sealed.guard_id_block",
        "input_policy": "No submissions file is opened or hashed by the freeze command",
    }


def freeze(yes=False, root=ROOT):
    target = root / heldout.LOCK_REL
    if target.exists():
        raise FileExistsError(f"refusing freeze: {heldout.LOCK_REL} already exists")
    commit = clean_commit(root)
    config = heldout.read_config(root)
    before = build_lock(root, config, commit)
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_accoding_heldout.py"],
        cwd=root,
        check=True,
    )
    after = build_lock(root, heldout.read_config(root), clean_commit(root))
    if before != after:
        raise RuntimeError("refusing freeze: protocol files changed while tests ran")
    if yes:
        with target.open("x", encoding="utf-8") as stream:
            json.dump(after, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        print(f"Wrote {target}")
    else:
        print(json.dumps(after, indent=2, ensure_ascii=False))
        print("Dry run passed; no lock written and no submissions read")
    return after


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    freeze(yes=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
