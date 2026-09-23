# Independent mathematical review of the physical stall bound

## Verdict

After one missing simultaneous-event premise was added, no counterexample was
found to the proposed bound

\[
W_P[i] < \min\left\{
 W_F[i]+G+\frac{J(d_i)}{k},
 \frac{W_F[i]+B_0/k+(3-2/k)L+J(d_i)/k}{1-\eta}
\right\}+\ell_i,
\]

where \(G=B_{\max}/k+(3-2/k)L\), \(d_i\) is physical dispatch,
\(\ell_i=s_i-d_i\), and \(F\) is ideal work-conserving FCFS on the same actual
arrivals and measured holding costs.  The proof is valid under the assumptions
now stated in `STALL_BOUND.md`.  It is a conditional, ex post pathwise
certificate; it does not recover the original uncorrected real-time promise.

For \(k=2\), \(L=61\), \(B_0=30\), \(\eta=1/2\), and
\(B_{\max}=356\), the specialization is also correct:

\[
W_P[i] < \min\{W_F[i]+300+J(d_i)/2,
                 2W_F[i]+274+J(d_i)\}+\ell_i.
\]

Both branches hold simultaneously, so taking their minimum is valid.  The
launch delay belongs outside the minimum: the proof bounds
\(W_D=d_i-a_i\), and the equality \(W_P=W_D+\ell_i\) then restores physical
start time.  Dividing \(\ell_i\) by \(k\), or placing it inside the
\((1-\eta)^{-1}\) factor, would be incorrect.

## Issue found and resolved: equal-arrival visibility

The first version required a fixed rank tie rule but did not explicitly require
all arrivals at a decision timestamp to be visible before that decision.  That
condition is necessary for the last-overtaker argument.

To see this, take \(k=1\), \(L=1\), and
\(B_0=B_{\max}=0\).  A victim \(i\) and a higher-ranked unit job \(j\) have the
same arrival time zero, but suppose an event ordering lets \(j\) be dispatched
before \(i\) becomes selectable.  Run \(j\) on \([0,1]\), then dispatch and
start \(i\) at time one.  Ideal FCFS starts \(i\) at zero.  There is no idle
capacity while \(i\) waits, hence \(J(d_i)=0\), and \(\ell_i=0\).  Therefore
\(W_P[i]=1\), while the additive branch demands the strict inequality
\(W_P[i]<W_F[i]+L=1\).  Equivalently, the only overtaker has
\(\mathrm{In}_i=L\), contradicting the proof's strict
\(\mathrm{In}_i<B_{\max}+kL\).  At its decision the victim was absent, so the
guard could not establish that it did not fire.

`STALL_BOUND.md` now requires that all actual arrivals at a common timestamp be
admitted before a decision at that timestamp and, more generally, that every
job with \(a_j\le\theta\) has been admitted at decision clock \(\theta\).
This is the manuscript's completions--arrivals--dispatches convention.  The
physical loop calls `enqueue_due` before entering each decision and admits every
currently due job in one loop.  The proposed checker also compares the arrived
set at every decision with \(\{j:a_j\le\theta\}\), so equal-clock collisions
are tested rather than assumed.  With this addition, the counterexample is
outside the theorem's scope and the last-overtaker proof regains its strict
inequality.

## Accounting review

### The capacity deficit \(J\)

The definition

\[
J(t)=\int_{t_0}^{t}(k-b_P(u))\mathbf 1\{q_*(u)>0\}\,du
\]

uses the needed state.  Here \(b_P\) counts physical holding intervals and
\(q_*\) counts every released but not-yet-started job, including a dispatched
job waiting for IPC or worker startup.  This latter inclusion is essential:
otherwise an empty selectable queue after reservations could hide arbitrary
idle capacity while unfinished work remains.

Let \(D=U_P-U_F\) and \(h=(k-1)L\).  Common arrivals add the same work to both
systems.  Between events, \(D'=b_F-b_P\).  If \(U_P>h\), at least \(k\)
physical jobs remain unfinished.  When \(b_P<k\), non-preemption implies at
least one of them has not started, so \(q_*>0\) and
\(J'=k-b_P\ge b_F-b_P=D'\).  When \(b_P=k\), \(D'\le0=J'\).  Thus
\(D-J\) cannot cross upward through \(h\), proving
\(U_P(t)-U_F(t)\le(k-1)L+J(t)\).  The argument remains valid when physical
start order differs from dispatch order and when completions are received late,
because mathematical remaining holding work becomes zero at \(f_i\), not at
receipt.

The integral is intentionally conservative.  It charges all unused capacity
when even one released job has not started, including capacity that an ideal
system also could not use because fewer than \(k\) jobs exist.  That can loosen
the certificate but cannot invalidate it.  Starting from a common empty
\(t_0\) is necessary: a local integral beginning at \(a_i\) misses backlog
inherited from earlier stalls.

### Dispatch-order identity

Using dispatch order for \(\mathrm{In}_i\) and \(\mathrm{Out}_i\) is correct
even when worker starts occur in another order.  During \([a_i,d_i)\), the
victim is unstarted, so executed holding work is exactly

\[
k(d_i-a_i)-[J(d_i)-J(a_i)].
\]

Every job executing in this interval was assigned before \(i\).  A
previously assigned but not-yet-started job contributes its full cost to the
dispatch-order work sum and its full residual to \(\rho_i^P\), hence zero net
executed work.  A running job contributes cost minus residual; a finished job
contributes cost and zero residual.  A job assigned later cannot have executed
before \(d_i\).  These cases give the exact identity

\[
kW_D[i]=R_i^P+\mathrm{In}_i-\mathrm{Out}_i-\rho_i^P
          +J(d_i)-J(a_i).
\]

At \(a_i\), after all tied arrivals are admitted and before any dispatch at
that timestamp, rank \(i\) and all higher ranks have their full cost in both
systems.  Therefore
\(R_i^P-R_i^F=U_P(a_i)-U_F(a_i)\).  Subtracting the FCFS identity and applying
the workload bound produces

\[
k(W_D-W_F)\le
\mathrm{In}_i-\mathrm{Out}_i+2(k-1)L+J(d_i).
\]

There is exactly one \(J(d_i)\): the prefix term \(J(a_i)\) from the workload
gap and the interval term \(J(d_i)-J(a_i)\) add once.  Neither dropping the
prefix deficit nor adding two copies is justified.

### Delayed completion receipts

At the decision for the last overtaker \(j\), the victim is still selectable
and has smaller rank.  The choice of \(j\) implies that the victim did not fire,
so received overtaking work is strictly below its budget.  Earlier overtakers
whose completions have not been received are not in that completed-work sum.
Under the one-outstanding-assignment-per-worker rule, however, at most
\(k-1\) such assignments exist when a worker is available for \(j\); adding
\(j\) itself yields the \(kL\) allowance.

A finished-but-unreceived job is handled consistently in two different
accounts.  It has zero remaining work in \(\rho_i^P\) and in \(U_P\), but its
full cost remains part of the conservative uncharged-overtaker allowance.  This
is not double counting.  Receipt delay that leaves physical workers idle while
some released job remains unstarted is separately accumulated by \(J\).

The physical controller satisfies the intended reservation discipline: it adds
the received holding cost to the completed-work counters before deleting the
busy assignment and returning that worker to `idle_workers`.  Serial dispatches
then reserve that worker until its next receipt.  Physical non-overlap alone
would be insufficient; a controller that reused a worker before charging old
completions could accumulate arbitrarily many invisible overtakers.

### Final constants

The cap gives
\(\mathrm{In}_i<B_{\max}+kL\).  Substitution into the dispatch inequality,
with \(-\mathrm{Out}_i\le0\), gives

\[
W_D<W_F+B_{\max}/k+(3-2/k)L+J(d_i)/k.
\]

For the age-relative rule, serial decisions give
\(\theta_j\le d_j\le d_i\), so
\(\mathrm{In}_i<B_0+\eta kW_D+kL\).  Moving the
\(\eta W_D\) term to the left gives the second branch.  When there is no
overtaker, the retained positive \(L\) supplies the strict slack in both
branches.  The integer-scaled inequalities stated in `STALL_BOUND.md` match
these formulas.

## Applicability and remaining limitations

The result requires all of the following on the realized trace: one monotone
clock; common actual arrivals and fixed holding costs for physical Guard and
shadow FCFS; \(0<C_i\le L\); non-preemptive, nonoverlapping holding intervals;
serial decisions and dispatches; arrival-before-decision handling including
ties; removal from the selectable queue at assignment; at most one unreceived
assignment per worker; receipt and full-cost charging before worker reuse; and
the exact observed-prefix guard rule.  A failed premise invalidates the
certificate rather than adding another empirical error bar.

The reference is shadow FCFS on the Guard run's actual enqueue times and measured
holding costs.  It is not the separately timed physical FCFS run.  If service
cost changes with policy, worker state, or wall-clock conditions, the theorem
still certifies only the frozen realized cost vector used by the shadow replay.

Finally, \(J(d_i)\) and \(\ell_i\) are observed after execution and have no
deterministic advance bound here.  Both can be arbitrarily large under the
stated physical model.  The corrected inequality can therefore pass while the
original 300-second promise fails, and in a heavily stalled trace its correction
can be too loose to be operationally useful.  Claiming a fixed deployment
promise would require separately enforced ex ante bounds on cumulative
capacity deficit and dispatch-to-start delay.  Until the exact-integer checker
passes on the completed Guard trace, the document establishes the conditional
theorem and its verification protocol, not an empirical result.

This review was static.  No experiment, physical rerun, event-log integration,
or numerical bound check was performed.
