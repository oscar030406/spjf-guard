# Cost ratio: how loose a count of overtakes is on the main trace

**Question.** A rule that counts overtakes must charge each one the worst case, the time
limit L, while a work budget charges what actually ran. By what factor, L over the mean
job cost, is a count loose on the main development trace?

**Paper items.** The ratio 150 in Section 5 ("Why the budget is measured in work"),
Section 6.4, the conclusions in Section 9, and the count remark in Supplementary
Section S4.4.

**Inputs.** `data/derived/overlay_traces/primary_rep0.npz` and `k1_rep0.npz`, field
`svc`; L = 60 s, the analysis cap of the main trace. No sealed data.

**Status.** Done. Mean cost 0.3997 s, median 0.2136 s, L / mean = 150.1 on both files
(`out_mean_cost_ratio.txt`). The other traces were not computed.

Rerun from the repository root:

```bash
uv run python evidence/cost_ratio/mean_cost_ratio.py
```
