# 0006 The number of copies in the single-server trace is chosen on the development pool; the sealed pool reuses it and reports the utilisation it actually reaches

Date 2026-09-21.

## Decision

The k = 1 trace is an overlay of a number of class-term copies, and how many copies to use is a design value. The original way of setting it was a probe:
add copies one at a time until the utilisation of one server in its busiest hour falls into `[0.78, 0.82]`, and take the state closest to 0.80
(`single_server_pool`, `overlay.single_server` in `configs/main.yaml`). On `primary` it
selects **321** copies, with busy-hour utilisation 0.8000.

From now on:

- The probe runs only on the pool it originally selected on (`overlay.single_server.pool`, i.e. `primary`),
  and its behaviour is unchanged in every detail. If the number of copies it selects disagrees with the `copies: 321` pinned in the configuration,
  the script prints a one-line mismatch notice at the start, the same way the main run treats parameter selection.
- On any other pool (the sealed pool is one of them), **the number 321 is reused**: take the first 321 copies of the candidate sequence
  drawn with the same seed, without looking at utilisation at any point, and report whatever utilisation it actually reaches (`single_server_copies`).

## Why

Rerunning the probe on the sealed pool would mean using sealed data to decide a design value: the number of copies would be chosen by
"which utilisation level on the sealed terms is closest to 0.80", and that information exists only after the sealed terms are opened.
That is exactly what the freeze is meant to prevent. The sentence in `docs/sealed_run_procedure.md`,
"the utilisation actually reached on the sealed terms is reported as it is; k is not adjusted afterwards to hit the target value", states the same discipline; that sentence is about
k, and this one is about the number of copies.

Conversely, carrying over the number chosen on the development pool costs this: the busy-hour utilisation of the sealed pool may not land near 0.80. That cost is
acceptable, and it is readable: the table prints the actual utilisation alongside, so the reader can judge how far apart the loads of the two traces are.
Re-selecting the number of copies on the sealed pool to align the utilisation would, by contrast, make the statement "all parameters are fixed before the freeze" false for the
single-server trace.

Another option would be to carry the 321 (class-term, week offset) pairs selected on the development pool over to the sealed pool unchanged. That cannot be done:
those class-terms belong to development terms, and the sealed pool has no objects with the same names. Only the number of copies and the drawing rule can be carried over.

## Cost

- Which utilisation the k = 1 trace of the sealed pool lands on is unknown at freeze time. If it is far from 0.80, that trace's load
  is not comparable with the multi-server tables, and the paper has to state the actual value; it cannot call it "the same load level".
- The sealed pool has fewer class-terms than the development pool (three terms against six), so to reach 321 copies the list has to be
  repeated several times. How many times is determined by the number of copies divided by the number of class-terms; it is not a separately chosen parameter. In a pool with few
  class-terms the same (class-term, week offset) can appear twice in the overlay, which is the same thing as the repetition already allowed in multi-server overlays. What is frozen is the number of copies, not the diversity of the copies.
- From now on the two k = 1 traces each have their own file name (`k1_rep0.npz` and `sealed_k1_rep0.npz`) and their own output manifest
  (`run.sealed_k1_tables`). Otherwise the sealed run would overwrite the development input, and the development tables are recorded in the manifest
  by the hash of that input.

## What did not change

The probe itself, the utilisation window, the target 0.80, the seed and offset (`seed * 100 + 50`), the 321 copies selected on `primary`,
and all the numbers in `outputs/dev_tables/k1/` produced from them.
