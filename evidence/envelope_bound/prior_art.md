# Prior art for the fluid comparison (L1) and the clock rule (P-clock)

Question: (i) is L1, V(t) <= U(t) <= V(t) + (k-1)L for every work-conserving
non-preemptive k-server policy, or its FCFS consequence W_FCFS <= (sigma + (k-1)L)/k,
stated before; (ii) is a pathwise per-job bound of a maximum-waiting-time rule relative to
FCFS stated anywhere.

Answer in one line each. (i) The upper half of L1 is the all-jobs-relevant case of Lemma
5.2 in Grosof, Scully and Harchol-Balter (SRPT-k against one server k times as fast),
proved there by the same few-jobs / many-jobs interval argument, for preemptive SRPT only;
no source we read states it for every work-conserving non-preemptive policy, or states
the FCFS consequence with sigma. (ii) Not found. Every deployed maximum-waiting-time rule
we read ships without a bound; the nearest proved statement is the Boost line (Yu and
Scully 2024; Li et al. 2026, App. A.2): FCFS latency plus crossing work, M/G/1 only, with
the reference a stationary quantity rather than the same job's FCFS wait on the same input.

Reading depth is stated per source. A quote is taken only from text opened in the second run
or by the first run where marked; none is from memory or from a search snippet.

## (i) L1 and the FCFS consequence

| Source | Read | What it states | Quote (<= 25 words) | Difference from L1 |
|---|---|---|---|---|
| Grosof, Scully, Harchol-Balter, "SRPT for multiserver systems", Performance Evaluation 127-128:154-175 (2018), doi 10.1016/j.peva.2018.10.001; read as arXiv:1805.07686v1 | full text, Sections 3 and 5 (PDF text, https://arxiv.org/pdf/1805.07686v1) | System k: k servers of speed 1/k under SRPT-k; System 1: one server of speed 1 under SRPT. Relevant work (jobs of size <= x) of System k exceeds System 1's by at most kx at all times; in a few-jobs interval by at most (k-1)x. | "the difference between the relevant work in System 1 and the relevant work in System k is bounded by ∆≤x(t) ≤ kx" (Lemma 5.2) | Preemptive SRPT-k only. The kx comes from irrelevant jobs turning relevant; with x = L every job is relevant and the few-jobs case gives (k-1)L, which is L1's upper half. Our L1 extends it to any work-conserving non-preemptive policy. Cite it as the source of the argument. |
| Cruz, "A calculus for network delay, Part I", IEEE Trans. Inf. Theory 37(1):114-131 (1991), doi 10.1109/18.61109 | full text, by the first run (bib_entries.bib x-verified) | (sigma, rho) burstiness; the least sigma equals the largest backlog of a work-conserving rate-rho server. | not re-quoted the second run | Single-server elements only; no multiserver element and no (k-1)L term. Source for sigma, not for L1. |
| Le Boudec and Thiran, Network Calculus, LNCS 2050 (2001), doi 10.1007/3-540-45318-0 | full text of the authors' online version, by the first run | Delay <= horizontal deviation; leaky bucket (b, r) through rate-latency (R, T) gives T + b/R; an L-packetizer adds l_max/R latency (Thm 1.7.1). | not re-quoted the second run | L1 has the same shape with R = k and deficit (k-1)L; the book has no multiserver element. |
| Leontyev, Chakraborty, Anderson, "Multiprocessor extensions to real-time calculus", RTSS 2009, pp. 410-421, doi 10.1109/RTSS.2009.29 | full text, by the first run | Global m-processor scheduling in real-time calculus; response-time test with a term (m-1)(E*(k)-1). | not re-quoted the second run | Preemptive fixed-job-priority schedulers, a schedulability test, not a pathwise workload envelope. |
| Brumelle, "Some inequalities for parallel-server queues", Operations Research 19(2):402-413 (1971), doi 10.1287/opre.19.2.402 | abstract only (OpenAlex rendering of the DOI record) | Bounds on the expected wait of A/G/k by two constructed single-server systems. | "The wait in queue for the first single-server system is stochastically larger than the wait in the given multiserver system" | Stochastic and in expectation, no service cap, no additive term. |
| Wolff, "An upper bound for multi-channel queues", J. Appl. Prob. 14(4):884-888 (1977), doi 10.1017/S0021900200105431 | abstract only (OpenAlex) | Multi-channel performance bounded above by single-channel queues. | "bounded above by corresponding quantities for one or a collection of single-channel queues" | An ordering between two systems with no additive slack. Its sample-path version is the one Wolff 1987 refutes. |
| Wolff, "Upper bounds on work in system for multichannel queues", J. Appl. Prob. 24(2):547-551 (1987), doi 10.2307/3214279 | abstract, keywords (Cambridge Core landing page, read the second run) | Refutes the earlier sample-path upper bounds; reproves the stochastic ones. Keywords include CYCLIC ASSIGNMENT. | "Previously derived sample path upper bounds for multi-channel work in system and work in queue are shown to be false." | See the next paragraph. |
| Scheller-Wolf and Sigman, "New bounds for expected delay in FIFO M/G/c queues", Queueing Systems 26:169-186 (1997), doi 10.1023/a:1019177023405; "Delay moments for FIFO GI/GI/s queues", Queueing Systems 25:77-95 (1997), doi 10.1023/a:1019152317954 | title and Crossref record only | Expected-delay and moment conditions for FIFO multiserver queues. | none (not read) | Stochastic by title; not checked further. |
| Gusfield, "Bounds for naive multiple machine scheduling with release times and deadlines", J. Algorithms 5(1):1-6 (1984), doi 10.1016/0196-6774(84)90035-X | NOT READ: closed access (OpenAlex: closed, no repository copy); Crossref metadata only | A search-result summary says greedy list scheduling with release times has maximum lateness within a p_max-type term of optimal. | none | UNVERIFIED. It is the closest candidate from list scheduling with release dates; its constant may match the (2 - 1/k)L of P-abs. Read it before the new text says anything about list-scheduling prior art. |

Graham 1969 (graham1969bounds, already in docs/related_work/refs.bib) carries the
list-scheduling pattern W <= total/k + (1 - 1/k) p_max behind the FCFS consequence; not
re-read in the second run.

Wolff 1987 and L1. What Wolff refuted is a sample-path ordering between the multi-channel
queue and single-channel comparison systems, without additive slack; his reference list
(read by the first run of the sibling track, evidence/new_theory_refutation/refutation.md,
section "Wolff 1987 and whether L1 falls under it") names Wolff 1977 and Loulou 1983, not
Brumelle. L1 is an additive envelope around one rate-k fluid server whose slack (k-1)L
exists only because of the service cap; the lower half V <= U is not what Wolff refuted.
The sibling track's search found Wolff-type orderings false (k = 2, arrivals all 0, sizes
(2,1,1,2), `out_refute_extras.txt:4`) and no L1 violation on the same instances. We agree:
L1 does not fall under the refutation, and there is no instance to give. We did not read
Wolff's full text (paywalled; see docs/related_work/references_verified.md R2-6).

A correction to the repository's own evidence. docs/related_work/references_verified.md,
R2-6 "数值旁证" paragraph, reports that comparing k servers with "one server of speed k"
breaks (k-1)L (|D| = 22 > 8 at k = 3, L = 4). The first run's `l1_check.py` reproduces
22 only with a speed-k server whose next start is t + size, which drains at rate k but
spaces its starts as a speed-1 server would; with the next start at t + size/k the
maximum is 13/3 <= 8 (`out_l1_check.txt:1-5`). The reported breach is an implementation
error in that control, and the paragraph should drop the speed-k example; the
cyclic-assignment example is unaffected.

## (ii) Maximum waiting time, aging and starvation thresholds

| Source | Read | Rule | Bound stated | Quote (<= 25 words) | Difference from P-clock |
|---|---|---|---|---|---|
| Li, Chen, Chen, Choukse, Qiu, Suh, Fonseca, Scully, Gupta, "Beyond Prediction: Tail-Aware Scheduling for LLM Inference", arXiv:2606.18431v1 (2026); refs.bib li2026tailaware | App. A.2 in the arXiv HTML v1 | UniBoost: Boost with an attained-service boost function. | Yes, sketched: worst case is FCFS latency plus crossing work V, M/G/1, with E[exp(gamma V)] finite (Lemma A.1). | "the worst-case scenario for any given request's latency under Boost is to have the same latency as under FCFS, plus at most V" | Single server; stated "roughly"; V is random and unbounded pathwise; the authors write that they "expect the argument to extend to the M/G/k" but do not prove it. Nearest statement to P-clock found. |
| Yu and Scully, "Strongly tail-optimal scheduling in the light-tailed M/G/1", POMACS 8(2):1-33 (2024), doi 10.1145/3656011; refs.bib yu2024boost | Section 3.2 of arXiv:2404.08826v2 (arxiv MCP) | Boost: serve by boosted arrival time. | Lemma 3.3: response time between W - B + V(W) + S and (W - min(B,u))^+ + V(infinity) + S + Vbar(u)1(...). | "quantifying how much arriving work will “boost past” the tagged job" | Single server, W is the stationary workload at the boosted arrival, not the same job's FCFS wait on the same input; no maximum-waiting-time rule. |
| Fu, Zhu, Su, Qiao, Stoica, Zhang, "Efficient LLM Scheduling by Learning to Rank", arXiv:2408.15792 (2024); refs.bib fu2024ltr | Section 4.3 and Algorithm 1 in the arXiv HTML v1 | StarvationThreshold on a per-request count of steps not scheduled; then a priority quantum. | None; the effect is measured (max_waiting_time reduced up to 3.4x). | "When a request’s starvation count reaches a pre-defined threshold, we will promote this request’s priority by allocating “quantum” to this request." | Counts scheduling steps, not wall-clock age; no bound. |
| Wu et al., "Fast Distributed Inference Serving for Large Language Models" (FastServe), arXiv:2305.05920v3 (2023/2024) | LaTeX Section 4.1 (arxiv MCP) | Starved jobs (starveTime >= alpha) promoted to the top MLFQ queue; alpha from the SLO, 300 ms default. | None. | "the scheduler periodically examines the starved jobs and ... promotes them to the highest priority queue" | Preemptive token-level MLFQ; no bound. |
| Luo et al., "Autellix: An Efficient Serving Engine for LLM Agents as General Programs", arXiv:2502.13965v1 (2025) | algorithm and Anti-Starvation paragraph in the arXiv HTML v1 | Promote a call when wait/service >= beta. | None. | "Simple anti-starvation techniques—such as promoting calls that have waited past a threshold—reduces Autellix to naive MLFQ" | A ratio threshold, not an age; no bound. |
| OpenPBS forum, "Replace starving with eligible_time", first post by Bhroam, 2021-01-14 | thread JSON | help_starving_jobs: a job flagged starving jumps to top priority; replaced by eligible_time in job_sort_formula. | None. | "One second a job is not starving and has low priority. The next second it has super high priority." | Batch-system knob; no bound. That max_starve is the age threshold is from a search summary of the design page, which could not be fetched. |

Kleinrock 1964 (kleinrock1964delay) and the accumulating priority queue (stanford2014apq),
both in refs.bib, give expected or distributional waits under aging, not pathwise bounds;
not re-read in the second run.

Consequence for the text. The related-work sentence at paper/sections/02_related_work.tex:28,
"Production systems otherwise avoid starvation with aging counters and maximum waiting
times, without proofs", has no citation. The sources above support it for the rules they
describe: cite fu2024ltr, wu2023fastserve and luo2025autellix there (bib_entries.bib), and
openpbs2021starving only if the PBS administrator's guide is not read in its place. The
sentence should not be read as "no anti-starvation rule has a proof": li2026tailaware A.2
sketches one for Boost against FCFS in M/G/1, and the clock section should say how P-clock
differs (pathwise, same input, k servers, any base policy, a maximum-waiting-time rule).

## Queries run in the second run

Web search (WebSearch): `PBS Professional help_starving_jobs max_starve starving job
definition waited longer`; `LLM serving scheduler starvation threshold provable bound
waiting time relative to FCFS arXiv 2025`; `network calculus service curve work-conserving
multiple parallel servers non-preemptive maximum packet length (m-1) latency term
aggregate`; `Brumelle 1971 "Some inequalities for parallel-server queues" Operations
Research abstract`; `Gusfield 1984 "Bounds for naive multiple machine scheduling with
release times and deadlines" Journal of Algorithms`; `Gusfield list scheduling release
times maximum lateness "(2-1/m)" p_max bound identical machines`; `Grosof Scully
Harchol-Balter "SRPT for multiserver systems" pdf`; `"maximum waiting time" threshold
scheduling rule serve oldest job worst-case per-job delay bound relative to FIFO proof
non-preemptive multiserver` (the tool ran four reformulations of it).

scholar-search (`hpr scholar search`, OpenAlex + Crossref): `multiserver queue work in
system bound single fast server sample path`; `starvation threshold maximum waiting time
scheduling bound relative to FCFS`; `aggregate multiserver service curve network calculus
parallel servers delay bound`. No hit closer than the tables above.

arxiv MCP: two `search_papers` calls failed (HTTP 406 and an empty error), so arXiv
papers were reached by ID (2305.05920, 2404.08826) and by the arXiv HTML pages
(2408.15792, 2502.13965, 2606.18431) and PDF (1805.07686v1).

Metadata: Crossref for every DOI above (`out_crossref_check.txt`,
`out_crossref_check_resume.txt`); OpenAlex DOI lookups for the Brumelle, Wolff 1977 and
Gusfield abstracts (OpenAlex's anonymous daily budget ran out afterwards); Crossref
bibliographic search for Scheller-Wolf and Sigman; api.datacite.org for the two arXiv
DOIs of FastServe and Autellix.

The first run's network-calculus queries were not logged; its readings of Cruz, Le
Boudec-Thiran and Leontyev et al. are recorded in the x-verified fields of
`bib_entries.bib`.
