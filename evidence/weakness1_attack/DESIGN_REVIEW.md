# Design review of the capacity-envelope protocol

## Verdict

The frozen protocol is scientifically defensible as a development-data sensitivity study, provided its claims follow its two different scopes exactly:

1. the five-overlay result covers only `k = 1..20` and all three fixed promises; and
2. the full `k = 1..76` envelope currently covers only overlay 0, with only Guard(600) above `k = 20`.

The second scope does not support a statement about all five overlay constructions, Guard(300), or Guard(1200) through disappearance of queueing. Either extend those cells or state the limitation wherever the full-capacity curve is discussed. The cleanest affordable completion is to use the analytic no-firing certificate below for Guard(300) and Guard(600), run Guard(1200) normally, and cover all three promises on overlay 0 through its exact peak. Extending all five overlays through their respective peaks would support the stronger five-overlay claim; it is not necessary if the paper explicitly calls the upper-capacity portion an overlay-0 sensitivity.

The study remains conditional on a constructed, open-loop development replay. It can answer whether the reported effect was confined to the three authored capacities. It cannot identify a production capacity, a hardware or cost saving, historical CodeBench waiting, demand feedback, or out-of-sample transportability. Section 8 already says the development results are not held out; the new sweep should preserve that qualification.

## Required protocol details

### 1. Bind the loader to approved development artefacts

`common.development_overlay()` operationally opens only `primary_rep{0..4}.npz`; it never opens `ev.parquet` or `ev_sealed.parquet`. Calling `sealed.guard_semesters(TERMS, ..., unseal=False)` before `load_overlay()` follows `run_main.py` and correctly rejects a bad declared term list. This is sufficient to avoid the documented possibly mixed event cache because the capacity study does not call the cache or overlay builders.

The guard call does **not** prove that a file named `primary_rep0.npz` contains those terms: it validates the caller's declaration, not the artefact. Before the final sweep, bind each accepted path to the already recorded development artefact in `outputs/dev_tables/manifest.json`. Require all of the following before `np.load`:

- resolved path is exactly one of `data/derived/overlay_traces/primary_rep{0..4}.npz`;
- its byte size and SHA-256 equal the corresponding recorded input entry;
- the manifest records `pool=primary`, `unseal=false`, reps `0,1,2,3,4`, and exactly the six declared terms;
- the current configuration hash matches the manifest, or any mismatch is recorded and shown irrelevant to the stored trace.

These checks read only the approved development overlays and text metadata; they do not require opening or hashing any sealed input or the event cache. They provide provenance rather than a semantic re-audit of the old cache, which is the strongest claim available without reopening source data. Record the five accepted hashes in the capacity-study manifest so later replacement of a same-named overlay is detectable.

The final loader must also return the stored `wk` and `weeks` arrays. Use those week indices for inference. Do not reconstruct weeks as `(arrival - first_arrival) // week`, which moves the boundary away from the calendar alignment used in the paper.

### 2. Define the capacity endpoint exactly

For each overlay separately, define

\[
K_\infty=\max_t \#\{i:a_i\le t<a_i+C_i\}.
\]

The pilot implementation is correct under the simulator's convention that completions precede arrivals at the same microsecond:

```text
finish = sort(a + C)
occupancy_at_arrival_i = (i + 1) - searchsorted(finish, a_i, side="right")
K_inf = max(occupancy_at_arrival_i)
```

Include `k = K_inf` as the exact zero-wait endpoint and call `1..K_inf-1` the queue-capable capacities. Assert with the production simulator that FCFS has zero positive waits at `K_inf` and at least one positive wait at `K_inf-1` when `K_inf > 1`. Every work-conserving policy is then identically zero at and above `K_inf`; those cells may be filled analytically rather than simulated. Do not assume the pilot's value 76 for overlays 1--4 without calculating their own peaks.

No capacities may be interpolated or dropped because their result is inconvenient. If computation limits the multi-overlay range to `1..20`, retain every integer there and present every overlay-0 integer through its peak. Preserve errors, zero-effect cells, sign reversals, and undefined ratios in machine-readable output.

### 3. Keep policies and guarantees fixed

Construct policies through the production configuration or the same factory it uses. At each `k`, retain the frozen shapes

```text
G=300:  B0/k=15, eta=.50, gamma/k=0
G=600:  B0/k=30, eta=.75, gamma/k=0
G=1200: B0/k=0,  eta=0,   gamma/k=4
```

and recompute only the theorem-mandated cap `Bmax = k(G-(3-2/k)L)`. Do not reselect a shape, score, capacity range, deadline window, or service target from the sweep. The cached expected-cost score must remain labelled as the earlier development predictor rather than the later package refit.

Run `assert_per_job_bounds` for every actually simulated guarded cell. In addition, assert the advertised promise directly in integer microseconds,

```text
max(wait_guard_us - wait_fcfs_us) <= G * 1_000_000
```

for every guarded or analytically certified cell. This direct check avoids making the empirical audit depend on floating-point presentation of the capacity-specific bound. Record jobs checked, violations, maximum excess, slack to `G`, simulator window errors, and firing counts for every cell.

## Safe analytic shortcut for Guard(300) and Guard(600)

The proposed no-firing certificate is valid. From the production SPJF-E result compute

```text
In, Out = bounds.in_out(trace.service_us, spjf_result.dispatch_order)
certified = all(In[i] < guard_policy.b0_us for every job i)
```

Use the actual integer `policy.b0_us` after any cap/clipping, not a separately recomputed decimal value. The inequality must be strict because the kernel fires on `over[q](t) >= budget(q,t)`.

Proof: suppose the guarded and SPJF schedules first diverge at a dispatch time `t`. Until `t` they have the same dispatches and completions. For any waiting job `q`, the completed higher-rank work `over[q](t)` is a subset of the total higher-rank work dispatched before `q` in the SPJF schedule, hence

\[
\operatorname{over}_q(t)\le \operatorname{In}_q < B_0
\le \min\{B_0+\eta k(t-a_q),B_{\max}\}.
\]

Thus the fired set is empty and the guard takes the same base choice, contradicting first divergence. Arrival or score ties cause no exception because `dispatch_order` and the simulator's rank tie-break define one total order. Jobs dispatched in the same phase make `In` more conservative, and draining the terminal queue does not change the argument.

Apply this only when `gamma=0`, `eta>=0`, and the actual `B0` is positive and no larger than the cap. It does not certify the selected Guard(1200), whose `B0=0`. For at least two cells that pass the certificate, run the actual guard once and require exact equality of waits, starts, dispatch order, and `n_forced=0`. Thereafter, reused SPJF results may be bound-checked and bootstrapped, but output must label the cells **analytically certified identical**, not simulated guard runs. Compute `In` once per `(overlay,k)` and reuse it for both eligible promises.

## Estimands and undefined cells

Make the raw deadline-window p99 difference the inferential endpoint:

\[
D_{G,k}=Q_{.99}(W_{\mathrm{FCFS}})-Q_{.99}(W_{\mathrm{Guard}(G)}).
\]

Positive values favor the guard. Also report the promise cost

\[
C_{G,k}=Q_{.99}(W_{\mathrm{Guard}(G)})-Q_{.99}(W_{\mathrm{SPJF-E}}),
\]

and the same raw comparison for SPJF-E. Raw seconds remain defined when the FCFS-to-SJF denominator approaches zero. They therefore support the capacity-wide analysis better than gap closed or percentage reduction.

At `K_inf`, FCFS, SJF, SPJF-E, and every guard have zero wait, so gap closed and relative reduction are `0/0`; print them as undefined. If any bootstrap draw has a nonpositive FCFS-to-SJF denominator or zero FCFS p99, report its count and do not silently form a percentile interval from the remaining finite draws. Ratio results at sparse high capacities are descriptive unless all declared draws are valid.

The theorem-floor region may be marked on the full plot, but it must not determine which capacity results are retained. It is an applicability annotation based on FCFS and `L`, not evidence that a particular `G` improves the queue.

## Paired bootstrap and simultaneous coverage

Use one `2000 x 30` matrix of week multiplicities for every policy, `G`, `k`, and overlay. The existing weighted-quantile routine computes each resampled quantile exactly without materialising duplicated jobs. Average the five overlay estimates within each draw for `k=1..20`, as in the paper; do not treat the overlays as five independent samples. For an overlay-0-only upper range, calculate and label the corresponding one-overlay draws separately.

Pointwise percentile intervals do not protect a statement selected after inspecting dozens of capacities. For each predeclared claim family, retain the complete bootstrap matrix `theta[b,j]`, where `j` indexes every capacity and policy comparison in that family. An efficient one-pass simultaneous max-t band is:

1. let `theta_hat[j]` be the observed paired difference and `s[j]` its bootstrap standard deviation;
2. for each draw, compute `T[b] = max_j abs((theta[b,j]-theta_hat[j])/s[j])` over cells with `s[j] > 0`;
3. let `c` be the 95th percentile of `T`; report `theta_hat[j] +/- c*s[j]` for all cells;
4. report zero-variance cells as point masses and do not use them as evidence of a strict effect.

For a directional benefit claim, use the analogous one-sided maximum and lower bands. The family must include all three guards and SPJF-E over the entire capacity range named in that claim. The current frozen family ending at `k=20` cannot support a positive-benefit claim through `k=75`. If the upper range remains overlay-0-only, use a separately declared overlay-0 family covering every included `k` and every included `G`; keep its conclusion separate from the five-overlay family.

A statement that benefit is positive at **every** capacity in a declared set is allowed only if every simultaneous lower bound in that set is above zero. Otherwise report the complete supported and unsupported capacity sets, including isolated failures; do not replace them with a visually chosen contiguous range. A service-target crossing may be read from the simultaneous upper band, but the existing 1/5/30-second targets were already inspected and should be called illustrative rather than newly confirmatory.

The weighted week bootstrap resamples realised job outcomes from schedules run on the complete trace. It does not concatenate weeks and rerun queue state, so it is not a bootstrap of a stochastic queueing process. Audit whether queues are nonempty across stored week boundaries and report the maximum spillover. If there is material cross-week carryover, the nominal week intervals are especially optimistic. In all cases describe the bands as conditional calendar-week uncertainty on the constructed overlays; they do not cover repeated copies of the same source jobs, semester selection, predictor fitting, trace construction, structural queue-model error, or demand feedback. “Computationally exact weighted quantiles” must not be shortened to “exact 95% coverage.”

## Claim language supported by this design

If the checks pass, the strongest defensible form is:

> On the five pre-existing development overlays, the complete integer sweep over `k=1..20` shows [the reported pattern] under frozen scores, guard shapes, promises, and arrivals. On overlay 0, the sweep continues through its exact no-wait threshold of 76 and shows [the reported pattern]. Simultaneous paired-week bands cover the full declared comparison family. These are open-loop replay results, not measured CodeBench queues or an economically identified capacity range.

Do not say “all capacities,” “universal,” or “through disappearance of queueing” without naming which overlays and promises were actually swept to their own `K_inf`. The full curves, zero endpoint, simultaneous family, invalid-draw counts, and negative cells must accompany any shorter summary.
