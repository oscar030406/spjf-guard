# Internal referee report on the theory note (third pass)

**Question.** Does the material added in revision 2 of
`evidence/guard_theory/theory.md` — Theorem 3, Lemma 1'', Theorem 4B, section 6.4 —
survive an adversarial reading?

**What it is.** A reconstruction of the claims from the note's prose, written before any
of the note's scripts were read, plus a schedule auditor that re-derives
work-conservation and non-preemption from the produced schedule alone. Exact integer and
`Fraction` arithmetic throughout. `out_SUMMARY.txt` holds verdicts R3-1 … R3-14.

**Headline.** Theorem 3 survives; section 6.4's conjecture is refuted by an explicit
family and open problem 8.1 is settled in the affirmative.

**Paper items.** One of the three referee passes that revisions 1–3 of the theory note
answer.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# Referee 3 — adversarial review of `evidence/guard_theory/theory.md` (revision 2)

Third referee pass. Targets the NEW material of revision 2 (Theorem 3, Lemma 1'',
Theorem 4B, §6.4) and the statements rewritten for referee 2.

**Nothing outside this directory was modified.** The note's own code
(`sim_core.py`, `sharp_kernel.py`, `family_tight.py`) was *not* used to produce
any number here; `ref3_validate.py` imports `sim_core.py` and `family_tight.py`
once, at the end, only to *diff* them against this directory's independent
reconstruction. `ref3_thm3.py` was written from the prose of §1.1, §2 and §6.1
before any of the note's scripts were read.

## What is in here

| file | what it does | log |
|---|---|---|
| `ref3_sim.py` | independent exact simulator (§1.1 event order) + a schedule **auditor** that re-derives work-conservation and non-preemption from the produced schedule alone, + In/Out/R/rho bookkeeping, + the §4.1 wrapper | — |
| `ref3_validate.py` | simulator self-validation and the instance diff against `family_tight.py` | `out_validate.txt` |
| `ref3_thm3.py` | item 1: both Theorem 3 families rebuilt from the text; audits; the (d) limit for k=2..6; the (e) same-phase decomposition | `out_thm3.txt` |
| `ref3_thm4b.py` | item 2: Theorem 4B by exhaustive enumeration over **every** base choice, plus a random sweep | `out_thm4b.txt` |
| `ref3_attain.py` | is the bound ever attained (strictness), and the counterexample to Lemma 1' | `out_attain.txt` |
| `ref3_items.py` | item 3: Thm 5(a), Prop 8, Lemma 2, Cor 2.1, Prop 14 | `out_items.txt` |
| `ref3_wrapc.py` | item 5: the wrapper constant c(k) — an explicit family that drives it to the proved ceiling `3k-2` | `out_wrapc.txt` |
| `out_SUMMARY.txt` | the report: verdicts and findings R3-1 … R3-14 | |

## Reproducing

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run python <script>.py

(`ref3_validate.py` needs `--with numpy`, because `sim_core.py` imports it.)
Exact integer / `Fraction` arithmetic throughout; no floating point enters any
verdict. Total compute for the whole directory is under 40 minutes on one core.

## Headline

Theorem 3 survives: the families are genuine, the policies are legally
work-conserving and non-preemptive, and every measured `D` reproduces to the
last digit. What does not survive is §6.4: its conjecture is refuted by an
explicit family built out of the note's own cascade, and the note's open
problem 8.1 is settled in the affirmative. See `out_SUMMARY.txt`.
