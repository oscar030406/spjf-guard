# Decision records (ADR)

One file per record, numbered upward as `0001-slug.md`. The body may be a single paragraph: what the context was, what was decided, and why.

Write one only when all three conditions hold: the decision is hard to undo; a reader without the background would look at the code and ask "why was it done this way"; there really were other options.
If any of the three is missing, do not write one.

| No. | Decision |
|---|---|
| [0001](0001-integer-microsecond-time.md) | The simulator's clock and accounting use integer microseconds |
| [0002](0002-result-availability-clock-and-jitter.md) | Arrival and visibility are defined by the time the result became available; records in the same second are separated by a deterministic jitter |
| [0003](0003-validation-only-selection-with-harm-constraint.md) | Guard parameters are selected on validation traces only and must satisfy the harm constraint |
| [0004](0004-sealed-data-path-level-protection.md) | Protection of sealed data sits at the path layer and is lifted only by the protocol lock plus an explicit switch |
| [0005](0005-one-guard-three-budget-shapes.md) | The guard is one mechanism and the budget shape is a design freedom; three grids of equal density, winner chosen by one rule |
| [0006](0006-single-server-copies-reused-on-the-sealed-pool.md) | The number of copies in the single-server trace is chosen on the development pool; the sealed pool reuses it and reports the utilisation it actually reaches |
| [0007](0007-policy-consistent-score-visibility.md) | Conservative 3600-second visibility within a class-term as the headline result for predicted ordering |
| [0008](0008-online-replay-headline.md) | The headline result for predicted ordering becomes the online replay: at arrival a job is scored only with same-copy results already completed in this replay; exact becomes an offline certificate |
| [0009](0009-zero-cost-blocks-leave-every-term.md) | Zero-cost blocks leave the simulated trace in the sealed terms as well; the first freeze is void and the protocol is frozen again |
| [0010](0010-post-run-reporting-changes-are-declared.md) | Changes to locked files (checking scripts and tests) after the sealed run are declared one by one with their bytes pinned, without a new freeze |
