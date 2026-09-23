# Review of the proposed manuscript replacements

Historical review checkpoint. REPORT.md incorporates the arrival, overlay and score-fit corrections below and is the authoritative final replacement text. The complete source spans retained here identify the proposed edit anchors; early pending-result comments are review history.

## Verdict

The replacements need two factual corrections before use.

1. CodeBench does not contain a recorded enqueue instant. Its candidate arrival is
   reconstructed as the recorded run-end timestamp minus recorded execution cost.
   ACcoding preserves job sizes and within-group submission-id order, but every arrival
   instant is drawn. The present Section 1 proposal largely fixes this distinction, but
   the proposed Section 9 edit leaves the contradictory phrase “the arrival instants ...
   are recorded” in place. The Open-loop paragraph also begins with the inaccurate
   blanket statement that arrivals come from the log at recorded instants.
2. The timed-sleep run has a frozen protocol, but the current REPORT still says that it
   “measures,” “executes,” and “adds” implementation evidence before its completion and
   premise checks have been reported. Manuscript text should describe the protocol
   without implying success, or add result-bearing sentences only after the completed
   artifacts pass verification.

The capacity replacement must also name its two scopes precisely: all five overlays at
$k=1,\ldots,20$, and overlay 0 alone at $k=21,\ldots,76$, where only FCFS, SJF,
SPJF-E, and Guard(600) are included. “Cached development scores” should mean the stored
`tweedie` score array already embedded in each existing development overlay, not a new
fit or the later package refit. The guard *formulas* are frozen; their numeric budgets
change with $k$ as pre-specified.

The physical input is not a raw recorded-demand window. It is the complete
calendar-aligned 300-second bin with the largest capped offered-work sum in development
overlay 0, selected without policy outcomes. Every job in that bin is retained, and its
stored *overlay* release offset is replayed without thinning or time compression. These
qualifiers should replace “one recorded-demand window” and “original inter-arrival
times.”

## 1. Section 1: final paragraph before the development-data qualification

The REPORT calls this a three-sentence source span. It is exactly two sentences in
`01_introduction.tex`.

Exact current text:

```tex
The demand in every trace is real, recorded traffic. The server pool the judging traces are replayed on is our own design, because the platforms they come from never queued; Section~\ref{sec:data} states what supports the pool size we choose and what it does not.
```

Recommended replacement:

```tex
The execution records are real, but not every arrival instant is recorded: CodeBench candidate arrivals are reconstructed as the recorded run-end timestamp minus the recorded execution cost, while ACcoding retains real job costs and within-group submission-id order but draws every arrival instant. The shared judging pools and their capacities are counterfactual designs rather than measurements of either source platform; Section~\ref{sec:data} states how the workloads and capacities are constructed and what those constructions can support. The fixed-demand comparisons and capacity sensitivity do not identify the effect of migrating either source platform to a shared pool.
```

This version does not mention the timed-sleep result before it exists. After successful
completion and verification, an implementation sentence may be added with the actual
scope and measured result; it should not be used as evidence that the source platform
queued or that recorded execution costs transfer to the new service.

## 2. Section 7: “Building the Shared Pool”

Exact current sentence:

```tex
The three
load levels share that trace and differ only in the pool size.
```

Recommended replacement, conditional on the final artifact verification script confirming every
declared cell:

```tex
Within each overlay, the three headline load levels use the same arrivals, service costs and stored expected-cost scores and differ only in pool size. A separate capacity sensitivity reuses the stored \texttt{tweedie} score array in each existing development overlay without refitting, and retains the pre-specified promises and capacity-scaled guard formulas without re-selection. It evaluates every integer capacity from $k=1$ to $20$ on all five overlays; on overlay~0 alone, FCFS, SJF, SPJF-E and Guard(600) continue through the exact zero-wait endpoint at $k=76$. The extension is a sensitivity to authored capacity, not an estimate of an operator's optimal capacity or resource cost.
```

Retain the source sentences immediately following this replacement, beginning “Four
of the five overlays take ...” and continuing through the original busy-hour loads,
deadline-window count, week-shift dependence, and interval limitation. They preserve
useful facts that the sweep does not supersede. If any declared capacity cell fails
verification, replace the numerical ranges above by the exact verified ranges rather
than describing the intended grid as completed.

The REPORT's phrase “holds the ... guard settings fixed” is too loose. $B_0$,
$B_{\max}$, and the queue-length term scale with $k$; the fixed object is the
pre-specified formula and promise, not every numeric budget.

### Additional consistency edit in Section 7

The source paragraph “The Original Platform Has No Shared Queue” still calls the
candidate arrivals real without saying that they are reconstructed. This should be
corrected even though REPORT currently proposes no replacement at this location.

Exact current text:

```tex
The platform that produced the main trace gives each logged-in student a dedicated
container and runs their code inside it, so submissions there did not queue behind one
another. We use the log as a demand trace: arrival instants and per-job costs are real;
the server pool, the queue and the order are our design. Nothing in this paper claims
that the original platform slowed down before a deadline.
```

Recommended replacement:

```tex
The platform that produced the main trace gives each logged-in student a dedicated container and runs their code inside it, so submissions there did not queue behind one another. We use the log to reconstruct a candidate demand trace: the recorded execution cost is retained, and the candidate arrival is computed as the recorded run-end timestamp minus that cost. The server pool, queue and order are our design. Nothing in this paper claims that the original platform slowed down before a deadline.
```

## 3. Section 8: opening of “Setup”

Exact current text:

```tex
All scheduling runs replay the overlaid CodeBench pool built in
Section~\ref{sec:overlay}. The three load levels differ only in the pool size and the
five overlays only in the per-copy week shift, and every policy sees the same arrival
instants and the same service times, so the comparison is pathwise.
```

Recommended replacement, conditional on verification of the capacity artifacts:

```tex
The principal scheduling comparisons replay the complete overlaid CodeBench workload with common reconstructed arrivals and recorded service costs across policies, so those comparisons are pathwise conditional on the constructed workload. The separate capacity sensitivity reuses the stored \texttt{tweedie} score arrays and the pre-specified capacity-scaled guard formulas over the ranges stated in Section~\ref{sec:overlay}; neither scores nor guard shapes are re-selected by capacity. We report absolute deadline-window p99 differences alongside gap closed, mark ratios with nonpositive reference denominators as undefined, retain negative and zero cells, and distinguish pointwise paired-week intervals from simultaneous bands over the declared capacity--policy family.
```

Do not yet include the REPORT sentence saying that the timed-work experiment “executes”
the window. Once all physical policies and audits have completed without a protocol or
service-limit premise failure, the following exact sentence can be appended:

```tex
A separate timed-sleep implementation check uses two persistent worker processes and every job in the pre-specified calendar-aligned five-minute bin of development overlay~0 with the largest capped offered-work sum; it replays the stored overlay release offsets and cached scores without thinning or time compression, begins each policy run empty, and drains every admitted job.
```

That sentence describes the selected *overlay* window accurately. It does not call the
release offsets raw platform inter-arrival times, and it states no agreement or bound
result until the measured audit supplies one.

## 4. Section 9: “The shared pool is our design”

Replacing only “What it cannot support ...” is insufficient because the immediately
preceding sentence incorrectly calls the reconstructed CodeBench arrivals recorded.
Use the following larger exact source span.

Exact current text:

```tex
We use its logs as a demand trace: the
arrival instants and the per-job costs are recorded; the server pool, the
queue and the scheduler are ours. Section~\ref{sec:data} sets out what supports
that design, that a fixed pool of judge hosts on one queue is a standard
deployment \cite{domjudge_manual,peveler2019sandbox} and that pooling replaces
\devnum{1{,}636} concurrent containers with \devnum{14} servers on the same
demand \cite{smith1981pooling}. What it cannot support is any statement about
waiting on the real platform, the pooled side being simulated throughout.
```

Recommended replacement:

```tex
We use its logs to reconstruct a candidate demand trace: each arrival is computed as the recorded run-end timestamp minus the recorded execution cost, while the server pool, queue and scheduler are ours. Section~\ref{sec:data} explains that a fixed pool of judge hosts on one queue is a standard deployment \cite{domjudge_manual,peveler2019sandbox} and reports the container-to-pool comparison on the constructed demand \cite{smith1981pooling}. The fixed-demand capacity sensitivity cannot establish historical waiting on CodeBench. The timed-sleep protocol is limited to dispatch, process timing and completion accounting on one selected overlay window; it does not execute submitted programs or establish that recorded execution costs transfer unchanged to a different resource-isolation regime.
```

Retain the following original sentences about the 44-fold overlay, the fact that the
container count belongs to no deployment, the editing session, and the absence of a
cost-saving claim. The recommended replacement describes the physical protocol's scope
without asserting that it completed successfully.

## 5. Section 9: “Open-loop replay”

The REPORT correctly rejects the lower-bound claim, but replacing only that sentence
would leave the paragraph's first sentence factually wrong for reconstructed CodeBench
arrivals and drawn ACcoding arrivals. Replace the whole opening block through the
lower-bound sentence.

Exact current text:

```tex
Arrivals come from the log at their recorded instants and do not react to our
scheduler. Feitelson states the objection at its strongest, that
``logged workloads actually contain a `signature' of the logged system''
\cite{feitelson2021resampling}; a trace-driven simulation issues requests
irrespective of system state, so a scheduler is neither rewarded with the work
it would attract nor punished by the users it would drive away
\cite{shmueli2009simulation}. We cannot restore that feedback, our logs
carrying no session boundaries, no think times and no resubmission semantics,
but its direction is known: a closed loop returns work to a service that
answers quickly, so the omission suppresses the benefit of the policies that
shorten waits, and our reported gains are a lower bound.
```

Recommended replacement:

```tex
The replay holds arrivals fixed: CodeBench candidate arrivals are reconstructed from logged run ends and costs, while ACcoding arrival instants are drawn. Feitelson states the objection at its strongest, that ``logged workloads actually contain a `signature' of the logged system'' \cite{feitelson2021resampling}; a trace-driven simulation issues requests irrespective of system state, so a scheduler is neither rewarded with the work it would attract nor punished by the users it would drive away \cite{shmueli2009simulation}. The available records do not identify how arrivals would respond to changed completion times. Faster responses can release subsequent work either into a blocking interval or before a favourable dispatch opportunity, so open-loop replay can overstate or understate both mean-wait and p99 improvements; the reported gains are not a lower bound on a closed-loop deployment effect. The per-job theorem still applies to any realised arrival sequence, including one generated by feedback, when shadow FCFS is retrospectively replayed on that same sequence and the same executed costs; it does not compare two independently evolving closed-loop systems. The replay also freezes historical scores and recorded execution costs, although reordering can change when prior outcomes become visible to the predictor and a different contention or isolation regime can change wall-clock service requirements.
```

The last sentence is the most important additional identification limitation. It keeps
two distinct transport assumptions visible: the predictor's historical state can be
policy-dependent, and a service cost recorded under private-container contention need
not remain the same in the proposed pool. “Retrospectively” is necessary because a
job's service cost is revealed only when that job completes; shadow FCFS is a
conditional sample-path reference, not an online oracle or an independently evolving
FCFS system.

Retain the remainder of the paragraph beginning “Replaying into a differently sized
pool ...” and the existing citations. Those sentences explain the replay convention
and whole-term overlay choice without restoring the invalid lower-bound claim.

## 6. Section 9: capacity sentence in “Not studied”

Exact current text:

```tex
Capacity is fixed throughout, so this is not a
capacity-planning study.
```

Recommended replacement, after the declared sweep has passed verification:

```tex
Capacity is fixed within each run and varied only over the pre-specified sensitivity ranges; this is a sensitivity to authored capacity, not an estimate of an operator's optimal capacity, service objective or cost.
```

This avoids “complete declared grid,” which can be misread as every overlay and every
guard through disappearance of queueing. The actual high-capacity extension covers
overlay 0 and Guard(600), together with the three unguarded references, rather than all
five overlays and all three promises.

## 7. Section 9: end-to-end-system sentences in “Not studied”

The REPORT replacement drops the useful existing result that charging measured feature
and prediction latency changes gap closed by less than $\devnum{0.001}$. Preserve it.

Exact current text:

```tex
The reported runs compare policies at a common set of
enqueue instants and do not charge the cost of computing features and running the
predictor. Section~\ref{sec:prediction} measures that cost and charges it in a
sensitivity, where it moves the closed gap by less than \devnum{0.001} at every
load; what is missing is not the latency but the rest of an end-to-end system.
Nothing here was deployed.
```

Recommended replacement:

```tex
The fixed-demand runs compare policies at common reconstructed candidate arrivals and freeze the stored scores and recorded service costs. Section~\ref{sec:prediction} measures feature-construction and prediction latency and charges it in a sensitivity, where it moves the closed gap by less than \devnum{0.001} at every load; that result does not supply a live feature store or account for policy-dependent result visibility. The separately pre-specified timed-sleep protocol uses cached scores and timed payloads and is limited to process-level dispatcher behaviour; it is not an operational judge and does not test program isolation, grading correctness, container start-up or application contention. Nothing here was deployed, and no economic or production comparison is identified.
```

This wording preserves the measured latency fact while avoiding the REPORT's premature
claim that the prototype already “adds measured queueing, dispatcher overhead and checks
of realised dispatch decisions.” After the physical artifacts pass their completion,
service-limit and per-job audits, a separate result sentence may report the actual
measurements; the scope limitations above should remain.

## Required status gates before manuscript use

The Section 7, Section 8 and capacity-sentence replacements should be applied only after
the final capacity manifest and verification script confirm every named cell, stored score hash,
bound check, and uncertainty output. The optional physical sentence should be applied
only after all three policy checkpoints, the physical summary, the service-limit premise
check, and the measured-trace shadow-FCFS audit are complete. A failed or partial run is
reported as such; it is not silently converted into a successful implementation claim.
