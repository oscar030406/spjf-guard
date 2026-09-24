# Late completion charges: a check with the strongest adversary

**Question.** Does Proposition 3 survive an adversary that is not limited to static
priority keys and fixed delays? Are its constants attained for k >= 2?

**Paper items.** Proposition `prop:late` (Section 6.9): the sentence saying the bound is
attained in the limit at k = 1 and k = 2 for delta > 0. Supplementary Section S4.12: the
k >= 2 instances, the per-server variant and the paragraph describing the checks.

**Inputs.** None from `data/`. Synthetic integer instances only; no sealed data. The
simulator was written from the paper, before the code in `../` was read.

**Status.** Done, 0 violations. The adversary may take any dispatch the budget allows,
which covers dynamic and clairvoyant base policies and any budget within the cap. It
also picks the arrival time of each charge within [f_c, f_c + delta], the pulling order
at each instant, a separate delay per view in the per-server model and, under
report-before-pull, delivery at any time or never.

- Exhaustive search: k = 1, 2, 3, up to six jobs of sizes {1, 2, 3} with L = 3. It
  covered 1.03e9 decision paths for the shared counter, 5.06e7 for report-before-pull
  and 3.49e8 for per-server views.
- Hill-climbing: up to 40 jobs, k <= 4, 15.4 million evaluations.
- Constructions: at k = 2 the shared-counter family falls short of the bound by exactly
  2 time units at every depth m (ratio 0.99988 to 0.99990 at m = 12). The per-server
  family falls short by exactly 3/2. At k = 3 and 4 the shortfall matches
  (1 - 1/k) L ((k-1)/k)^m + 1 + 1/k on every instance built; that formula has no proof.

| File | What it is |
| --- | --- |
| `core.py` | exhaustive search over every adversary choice, three models |
| `exhaustive.py`, `out_exhaustive.txt` | the exhaustive runs (time scaled by 2, so L = 6 in the code) |
| `sim.py` | single-run event simulator |
| `hill.py`, `out_hill_a.txt`, `out_hill_b.txt` | hill-climbing search |
| `construct.py`, `out_construct.txt`, `out_construct_pserv.txt` | the lower-bound families |

Commands:

```
python exhaustive.py <shared|rbp|pserv> 6
python hill.py <shared|rbp|pserv> <k> <seconds> <seed>
python construct.py
python -c "import construct; construct.main_pserv()"
```
