# 0009 Zero-cost blocks leave the simulated trace in the sealed terms as well; the first freeze is void and the protocol is frozen again

Date 2026-09-25.

## Decision

The three sealed terms 2023-1, 2023-2 and 2024-1 are added to `clock.drop_zero_cost_terms` in `configs/main.yaml`.
The rule written in Supplementary Section S2 is: blocks whose recorded cost is exactly 0 leave the simulated trace but stay in the features, labels and all totals.
The configuration wrote this rule as a list of terms, and the list named only the seven terms (from 2020 on) in which such blocks were found during development,
not the sealed terms. The sealed run under the first freeze (1289aa2, lock archived as `docs/archive/protocol_lock_1289aa2.json`)
therefore failed at step 4, when loading the overlay traces, with `service times must be positive`:
a zero-cost block has a service time of 0 after rounding to microseconds.

After the revision the protocol is frozen again and the sealed run is rerun from step 1. The configuration of the first freeze is stored byte for byte as
`configs/main_frozen_1289aa2.yaml`, and the five development-phase manifests whose configuration was `configs/main.yaml`
are repointed to it (`check_preserved_outputs.py --pin-historical-config`, which changes only the path, after checking that the bytes are identical).

## Why

- The revision is determined by a rule the paper stated in advance and does not depend on any sealed result: under the first freeze, step 4 failed while loading
  and produced no table; step 6 was stopped manually while fitting the frozen model and had not started simulating; nobody saw any sealed
  output, only the error message.
- The development cache `ev.parquet` contains only the eleven terms 2018-1 to 2022-2, and the three terms added to the list do not appear in any
  development-phase computation, so every development result is unchanged row for row. The signatures of the online checkpoints changed because the configuration hash
  changed, and were re-signed the same way as in 069cb06 (`local_tools/resign_online_checkpoints.py`, after checking
  the old per-cell signature of each checkpoint).

## Cost

- The procedure needs one more freeze and one more rerun, and the ledger gets one more group of rows; Section 5 of the procedure document, "if a bug that really must be fixed is found, that is a new
  version of the method", was written for exactly this case.
- The list form itself stays: changing the rule to "all terms" would change the feature computation for the development terms of 2018–2019,
  and all development results would have to be rerun.
