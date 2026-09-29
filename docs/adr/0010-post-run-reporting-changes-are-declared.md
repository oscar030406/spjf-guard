# 0010 Changes to locked files after the sealed run are declared one by one, without a new freeze

Date 2026-09-25.

## Decision

After the sealed run had finished its ten commands under lock f6c1b3af (tree 2ae513f), writing the results into the paper exposed three defects in the table checks and tests,
and five locked files were modified: `scripts/check_paper_numbers.py`, `scripts/check_generated.py`,
`tests/test_eval_scores.py`, `tests/test_sealed_data.py`, `tests/test_sealed_paper_tables.py`.
Each change is written into `docs/post_run_changes.json`, with the file's current sha256 and the reason.
The lock check in `tests/test_sealed_data.py` compares file by file after the freeze: a file that differs from the lock must have an entry in the declaration
whose bytes match the declaration exactly; otherwise it still fails. `protocol_lock.json` is not touched; it remains the record of the code of the sealed run.

The three defects:

- When check C looked in the paper for each sourced number in `numbers.csv`, it recognised only `\devnum{}`, so the sealed numbers quoted in the main text
  (keys starting with `sealed.`) were bound to fail. It now finds the matching macro by the key's prefix.
- The old table-generation pass of `check_generated.py` reads only the sealed main tables, predictor and visibility directories, not exact and online,
  yet it also checked the sealed numbers in the main text, so online numbers could never be traced to a source in that pass. When sealed exact results exist, this pass no longer checks
  the sealed numbers in the main text; that is left to the exact pass, which reads all the sealed outputs.
- Two tests described the repository state before the freeze: one asserted that the reason for refusal was "no frozen lock", while after the freeze the same call is refused because
  `--unseal` was not passed; the other required the number of freeze rows in the ledger to equal the number of hashed inputs in the lock, and the second freeze wrote the same rows again,
  doubling the count. Both now assert the requirement itself: the call is refused and nothing is written; every hashed input has one freeze row.
  These two tests had been failing since the second freeze (f32c393); the freeze gate runs the tests before writing the lock, so this was not seen.

## Why

- What the lock has to prove is that the sealed run used the frozen method. All ten commands finished before the changes, and the manifest of each step's outputs records
  the implementation hashes; the only things changed are the scripts and tests that check the paper's numbers. No code executed by any sealed command was changed, and no sealed command was rerun.
- A new freeze would be wrong here: the sealed data have already been opened, and a new freeze would look like a method fixed before seeing the results.
- Simply relaxing the lock check (comparing only the frozen commit and ignoring the working tree) would let any later change pass silently. Declaring changes one by one pins the new bytes,
  which is the same kind of protection as the freeze pinning the old bytes.

## Cost

- The repository has one more declaration file and the lock check one more branch; any later change to these five files must also update the declaration.
- The protocol's own wording is "after the freeze, nothing under the locked paths is touched"; this change breaks the letter of that, which is accounted for by this ADR and the declaration file.

## Addendum (2026-09-26)

The lock covers the whole set of `scripts/*.py` and `tests/*.py`, so files added after the freeze also count as changes. After the full comparison set on the development pool was run
under the online protocol, `scripts/online_paired_differences.py` and `tests/test_online_paired_differences.py` were added:
the former reads the checkpoints of that run (development pool only, no sealed data) and gives the paired differences of Supplementary Section S11. Both are written into
`docs/post_run_changes.json` in the same way. No sealed command executes them, and the reasoning of the "Why" section above is unchanged.

On the same day `scripts/sealed_dev_contrast.py` and `tests/test_sealed_dev_contrast.py` were added: the former reads only CSVs already written by the development and sealed runs,
does not read sealed data and does not simulate, and gives the numbers with which Section 8.2 explains why the sealed terms close more of the gap; `check_paper_numbers.py` correspondingly gains
`--sealed-contrast-dir`, which accepts the numbers in that output that are not from the development pool as sources for sealed numbers, and `check_generated.py` passes it automatically when that output's manifest exists.
These four files are likewise written into the declaration file.
