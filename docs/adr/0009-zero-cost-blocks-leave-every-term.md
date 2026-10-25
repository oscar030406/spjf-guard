# 0009 Zero-cost blocks leave the simulated trace in the sealed terms as well; the first freeze is void and the protocol is frozen again

Date 2026-09-25.

## Decision

We add the three sealed terms 2023-1, 2023-2 and 2024-1 to `clock.drop_zero_cost_terms` in `configs/main.yaml`. The sealed terms are the test terms that cannot be read before the method is frozen.
The rule in Supplementary Section S2 states that blocks whose recorded cost is exactly 0 leave the simulated trace. These blocks stay in the features, labels and all totals.

We wrote this rule in the configuration as a list of terms. The list named only the seven terms (from 2020 on) in which we found such blocks during development.
It did not name the sealed terms. The sealed run under the first freeze therefore failed at step 4, when it loaded the overlay traces,
with `service times must be positive`. The reason is that a zero-cost block has a service time of 0 after rounding to microseconds.
The first freeze is 1289aa2, and its lock is archived as `docs/archive/protocol_lock_1289aa2.json`.

After this change, we freeze the protocol again and rerun the sealed run from step 1. We store the configuration of the first freeze byte for byte as
`configs/main_frozen_1289aa2.yaml`. Five manifests of the development phase had `configs/main.yaml` as their configuration. We repoint these five to the stored file
(`check_preserved_outputs.py --pin-historical-config`, which changes only the path, after checking that the bytes are identical).

## Why

- A rule that the paper stated in advance determines this change, and the change does not depend on any sealed result. Under the first freeze, step 4 failed while loading
  and produced no table. We stopped step 6 manually while it was fitting the frozen model, and it had not started simulating. Nobody saw any sealed
  output, only the error message.
- The development cache `ev.parquet` contains only the eleven terms 2018-1 to 2022-2. The three terms that we added to the list do not appear in any
  computation of the development phase. Therefore every development result is unchanged row for row. The signatures of the online checkpoints changed because the configuration hash
  changed. We re-signed them in the same way as in 069cb06 (`local_tools/resign_online_checkpoints.py`, after checking
  the old per-cell signature of each checkpoint).

## Cost

- The procedure needs one more freeze and one more rerun, and the sealed-term access ledger gets one more group of rows. Section 5 of the procedure document covers exactly this case. It says:
  "If you really find a bug that must be fixed, the fix makes it a new
  method."
- The list form itself stays. Suppose that we changed the rule to "all terms". Then the feature computation for the development terms of 2018–2019 would change,
  and all development results would have to be rerun.
