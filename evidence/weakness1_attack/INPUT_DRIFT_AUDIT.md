# Development-input drift audit

## Decision

The capacity sweep had already loaded all five `primary` traces before they were
overwritten.  The checkpoint results therefore do not inherit the later on-disk change.
The on-disk inputs nevertheless drifted and should not be described as the original
inputs until they are restored or referenced from an exact-hash-matched copy.

A complete pre-overwrite copy was found in the current temporary-session tree at
`<cache-dir>/pkg_overlays/`.  Its five `primary_rep0..4.npz` files each have the old size
793,567,608 bytes and timestamps 2026-09-20 01:23--01:24.  The same directory also holds
five `validation_rep0..4.npz` files of 794,079,033 bytes and the unchanged-size
`k1_rep0.npz`.  `data/derived/README.md` states that the project's overlay directory was
copied from the temporary session on 2026-09-20 and was byte-for-byte identical.  This
copy is a materially stronger recovery source than reconstructing a ZIP from the
overwritten archive.

No data container was opened, parsed, or hashed for this audit.  All findings below use
source text, logs, JSON manifests, and filesystem name/size/time metadata only.

## What changed on disk

The five project `primary` files now have size 1,498,959,560 bytes and modification times
09:24:35--09:24:51 on 2026-09-21.  Before the overwrite, each was 793,567,608 bytes.  The
five `validation` files were also overwritten at 09:25:17--09:25:34 and now have size
1,499,925,585 bytes instead of 794,079,033 bytes.  The project `k1_rep0.npz` retained its
old size and was not part of this overwrite.

The original authoritative hashes are recorded twice, in
`outputs/dev_tables/manifest.json` and
`evidence/weakness1_attack/development_inputs.json`:

| file | old size (bytes) | original SHA-256 |
|---|---:|---|
| `primary_rep0.npz` | 793,567,608 | `4f5a6c84a59d1e60342593d26a81e92a38cb76a2b730c69a6babaffc983d4971` |
| `primary_rep1.npz` | 793,567,608 | `f300b3195d03bad713951bcf7051610ae6b7eb99753c61e85465299b9737b720` |
| `primary_rep2.npz` | 793,567,608 | `053b24fa860f2595ea2c0427945d107dabab1e65abf2e46a264678834dd3d981` |
| `primary_rep3.npz` | 793,567,608 | `84e95b15b9da99a4d6d6a9606c835db7396b552448995312bc238e2a3b4191e4` |
| `primary_rep4.npz` | 793,567,608 | `5581859bdf016c22f105563b43711543e4db908d3874ac1549d6a0adb454c1aa` |

`outputs/prefreeze/dev_tables/manifest.json`, written after the overwrite, records the
new sizes and new hashes.  It is evidence of drift, not a replacement authority for the
original development inputs.

## Development-only provenance

The current `configs/main.yaml` maps the `primary` pool to exactly these six terms:
`2020-ERE`, `2020-2`, `2021-1`, `2021-2`, `2022-1`, and `2022-2`.  The sealed terms remain
in a separate pool.

`scripts/build_overlays.py` derives the term list from that pool, calls
`sealed.guard_semesters(terms, ROOT, unseal=args.unseal)` before opening the event cache,
and declares `--unseal` as `store_true`, so its default is false.  The guarded loader is
called again by `prepare_everything`.  The post-overwrite manifest at
`outputs/prefreeze/dev_tables/manifest.json` records `pool=primary`, the same six terms,
and `unseal=false`; `outputs/prefreeze/prefreeze.log` also identifies the primary run as
a development run over exactly those terms.

These facts establish that the new files were subsequently accepted and consumed by a
guarded development-only run.  They do not preserve the command line of the 09:24 build
itself: no log containing that exact invocation was found.  It would therefore be too
strong to claim direct command-line proof that the writer used its default arguments.
The source guard, unchanged pool configuration, and downstream guarded run provide strong
indirect evidence that the overwritten files contain development data only.

## Score provenance and why reconstruction is not the first choice

At the committed source revision, `scripts/build_overlays.py` stored two arrays named
`tweedie` and `log`.  With no `--score-parquet` override it read
`data.score_predictions_file`, which `configs/main.yaml` resolves to
`data/derived/ranking_score_predictions/rs_pred_ires0.parquet`.  That file still exists,
has size 33,582,476 bytes, and has not changed since 2026-09-20 10:20:22 according to
filesystem metadata.  It is the best surviving source candidate for the original
embedded `tweedie` and `log` arrays.

The working-tree change expands the stored-score map with four arrays:
`tweedie_conservative`, `log_conservative`, `tweedie_static`, and `log_static`.
`src/spjf_guard/experiment/overlay.py` also adds `copy_entry` and `copy_round`.  These six
new members explain the large size increase when the chosen score parquet contains all
new columns.  The same working-tree revision retains the names `tweedie` and `log`, but
that fact alone does not prove their values are unchanged: an explicit `--score-parquet`
could have supplied the package's refitted scores instead of the older default source.
The exact 09:24 score-file argument is absent from the logs reviewed here.

`data/derived/package_ranking_scores/forward_scores.parquet` changed at 09:20:40 and now
has size 18,334,242 bytes.  `outputs/prefreeze/forward_scores.parquet`, last written at
07:49:54, remains a 6,723,454-byte copy of the earlier two-column package fit.  This older
package fit is useful for reproducing the external scores attached by `run_main.py`, but
it should not be substituted for the overlay's original embedded scores: project notes
and source distinguish the pre-check score cache used inside the trace from the package
scores attached later by `job_row`.

A first recovery attempt stripped the six new ZIP members from the overwritten rep0.
Its size returned exactly to 793,567,608 bytes, but its SHA-256 did not match the original
manifest.  This mismatch can arise from ZIP metadata or from retained-array differences;
without a matching hash it proves neither explanation.  That candidate was correctly
rejected.

## Safe recovery and acceptance rule

Use the surviving files in `<cache-dir>/pkg_overlays/` as immutable sources.  Locate that
directory by searching the current temporary directory for `pkg_overlays` rather than
hard-coding a machine-specific session root.  Copy each source into
`evidence/weakness1_attack/raw/recovered_development/` under a `.candidate.npz` name.
This task permits writes only below `evidence/weakness1_attack/`; it does not permit
replacing `data/derived/overlay_traces/`.

Accept a candidate only if all of the following hold:

1. The guarded project loader accepts it as a `primary` development trace with
   `unseal=False` and reports the expected schema.
2. Its byte size equals the original manifest size.
3. Its SHA-256 equals the corresponding original hash above, not the post-overwrite hash.
4. All five replicas pass together.  A partial set is retained only as diagnostic output.

An exact hash match is sufficient to establish original bytes, including every embedded
score, array order, and ZIP metadata.  If even one source file misses its original hash,
do not repair it by member stripping or score substitution.  Keep the candidate for
diagnosis and obtain an independently archived development package or reproduce the old
build with its exact source revision and original score input.  The validation traces
should be recovered by the same rule against their own pre-overwrite manifest before any
future selection run uses them.

## Effect on the completed capacity sweep

`evidence/weakness1_attack/overlay4_metadata.json` records that the last primary trace
finished loading at 09:18:59.  The first on-disk overwrite began at 09:24:35.  The sweep
therefore held all five inputs in memory before any file changed.  Its 824 completed
results and numerical checkpoint are not mixtures of old and new files.  This timing
argument protects the completed computation; it does not make the current paths suitable
for rerunning that computation without explicit reference to exact-hash-matched recovery
copies.

## Remaining uncertainty

No direct 09:24 build transcript identifies the selected score parquet.  The stripped
candidate's hash mismatch does not distinguish changed retained arrays from archive
metadata.  Both uncertainties disappear for practical purposes if the `pkg_overlays`
files match all original manifest hashes.  Until that check is recorded, the temporary
files are strong recovery candidates rather than verified originals.

## Completed recovery

`recover_original_backups.py` subsequently copied the five original primary backups
into this study's `raw/recovered_development/`. All five files match the original size
and SHA-256 recorded above. The project term guard and overlay loader accepted them;
each contains 17,634,760 jobs with service capped at 60 seconds. The final artefact
verification passed against these copies. No validation overlay was opened or copied,
because this study does not use that pool. The changed project files remain untouched.

The rejected rep0 candidate was also re-serialised using NumPy. Its hash remained
`489985370be6e8e9f29e1e6edc6ffb1aa75b56b8332e084a9142534da032b881`,
not the original hash. That diagnostic is retained separately; none of its bytes enter
the accepted analyses. Exact recovery makes identifying which rebuilt array changed
unnecessary for this study's reproducibility.
