# Theory note: a pathwise identity for FCFS-relative delay

**Question.** Can the per-job bound of the guard kernel be turned into a two-sided
structural statement that holds for *every* non-preemptive work-conserving policy, with
no stationarity and no assumption on prediction quality?

**Paper items.** `theory.md` is the long form of Section 6 and Appendix A of the
manuscript. `rev5_items.py` and `out_rev5_items.txt` carry the provenance of the
Appendix A.2 item cited in `paper/sections/A_proofs.tex` (section RR-4), and
`paper/supplementary.tex` points at this directory for the simulation behind
Appendix A.2.

**What is here.** `theory.md` (revision 5) holds the proofs; its section 9 is the
script-to-log map and its section 10 the referee CHANGELOG. `CHANGES_rev5.md` lists every
revision-5 edit with before/after text. Three independent exact-integer simulators are
included, sharing no code with `evidence/guard_variants/guardkern.py`.

**A note on references.** The note cites `docs/referee_readthrough/`, an internal referee
report that is not distributed with the repository; its findings are reproduced in
`CHANGES_rev5.md` and in the note's own CHANGELOG.

**Status.** Current (revision 5).

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

Self-contained theory work for the FCFS-relative overtake guard.

theory.md holds the proofs (revision 5: revisions 1-3 answer the three referee
directories, revision 4 answers the paper draft's general statement of the
wrapper theorem, revision 5 answers the fourth referee, who read the built
manuscript -- see docs/referee_readthrough/); its §9 is the script-to-log map
and its §10 the referee CHANGELOG. CHANGES_rev5.md lists every revision-5 edit
to the note and to the paper's Section 6 / Appendix A, with before/after text
and the verification behind each.

Three independent exact-integer simulators, all written here and sharing no code
with evidence/guard_variants/guardkern.py: sim_core.py (pure Python),
sharp_kernel.py (numba) and gen_budget.py's own kernel (numba, for an arbitrary
budget rule). run_sharp.py agree cross-checks the first two; gen_budget.py is
cross-checked against the second by replaying Theorem 4C's family through it.

rev5_items.py needs no third-party package at all (sim_core.py only) and runs as
`uv run --no-project python rev5_items.py`.

Files are named by what they produce: run_*.py write the matching out_*.txt;
family_tight.py builds the explicit extremal families of Theorem 3 and writes
out_sharp_family.txt; wrapper_tight.py builds the family of Theorem 4C and
writes out_wrapper_tight.txt; rev3_items.py writes out_rev3_items.txt;
gen_budget.py writes out_gen_budget.txt. The out_sharp_*.txt logs are revision
2's, out_wrapper_tight.txt and out_rev3_items.txt are revision 3's,
out_gen_budget.txt is revision 4's, out_rev5_items.txt is revision 5's, and the
remaining out_*.txt are revision 1's and are still current.

A bare out_*.txt cited in theory.md always means a file in this directory. The
three citations of another directory's logs are written out in full.

numba writes its compilation cache to __pycache__/ (*.nbi, *.nbc); it is a
build artefact, safe to delete, and regenerated on the next run.
