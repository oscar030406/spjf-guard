"""Server crashes with loss of the running job's progress, on the same crash schedule for P
and for FCFS.

Model.  k servers; at a crash time server m goes down for d time units; a job running on it
loses its progress and waits again with its original rank.  Integer times; at each instant:
completions, recoveries, crashes, arrivals, then dispatches (no up and free server idles
while a job waits).  W is the wait until a job's first start.  Phi(t) = integral of the
number of up servers.  Claims checked, for every job i:

(C1) Phi(s_P) - Phi(s_F) - (In - Out) <= 2(k-1)L + L * N_i
(C2) under the guard with cap B:  Phi(s_P) - Phi(s_F) < B + (3k-2)L + L * N_i
     In / Out are counted at i's first dispatch (a job whose attempt was aborted and which
     waits again at that instant counts as waiting); N_i is the number of crashes at times
     in [tau_i, s_P], tau_i the last instant up to a_i at which P's unfinished work, read
     before that instant's arrivals and crashes, was at most (k-1)L.
    python check_crashes.py > out_check_crashes.txt
"""
from random import Random

L = 3


def simulate(jobs, k, crashes, choose_job, choose_server):
    """Returns first start, dispatch sequence number of each attempt, abort times, Phi, and
    the unfinished work read before each instant's arrivals and crashes."""
    n = len(jobs)
    down_until = [0] * k
    running = [None] * k                    # (job, attempt start, attempt seq)
    remaining = [c for _, c in jobs]        # an attempt needs the full cost; 0 once done
    first = [None] * n
    attempts = [[] for _ in range(n)]       # [seq, start, end or None, aborted?]
    done = [False] * n
    waiting, arrived, seq, t = [], 0, 0, 0
    phi, unfinished_before = {0: 0}, {}
    crash_at = {}
    for tc, m, d in crashes:
        crash_at.setdefault(tc, []).append((m, d))
    while not all(done):
        for m in range(k):                  # completions
            if running[m] and running[m][1] + remaining[running[m][0]] <= t:
                j, s, q = running[m]
                done[j] = True
                attempts[j][-1][2] = t
                remaining[j] = 0
                running[m] = None
        unfinished_before[t] = sum(remaining[j] for j in range(arrived) if not done[j]) - sum(
            min(t - s, remaining[j]) for m in range(k) if running[m] for j, s, _ in [running[m]])
        for m, d in crash_at.get(t, ()):    # crashes (recoveries are implicit in down_until)
            if running[m]:
                j, s, q = running[m]
                attempts[j][-1][2] = t
                attempts[j][-1][3] = True
                waiting.append(j)
                running[m] = None
            down_until[m] = max(down_until[m], t + d)
        while arrived < n and jobs[arrived][0] <= t:
            waiting.append(arrived)
            arrived += 1
        waiting.sort()
        while waiting:
            free = [m for m in range(k) if running[m] is None and down_until[m] <= t]
            if not free:
                break
            j = choose_job(t, waiting, attempts, done)
            m = choose_server(free)
            waiting.remove(j)
            running[m] = (j, t, seq)
            attempts[j].append([seq, t, None, False])
            first[j] = t if first[j] is None else first[j]
            seq += 1
        up = sum(down_until[m] <= t for m in range(k))
        phi[t + 1] = phi[t] + up
        t += 1
    return first, attempts, phi, unfinished_before


def in_out(jobs, i, first, attempts):
    """In and Out of job i at its first dispatch."""
    q_i = next(a[0] for a in attempts[i] if a[1] == first[i])
    s_i = first[i]
    inn = outt = 0
    for j in range(len(jobs)):
        if j == i:
            continue
        before = [a for a in attempts[j] if a[0] < q_i]
        active = bool(before) and not (before[-1][3] and before[-1][2] <= s_i)
        if j > i and active:
            inn += jobs[j][1]
        if j < i and not active:
            outt += jobs[j][1]
    return inn, outt


def guard(jobs, B, rng):
    def choose(t, waiting, attempts, done):
        def over(q):
            return sum(jobs[j][1] for j in range(q + 1, len(jobs)) if done[j])
        for q in waiting:
            if over(q) >= B:
                return q
        return rng.choice(waiting)
    return choose


def check(trials, seed, use_guard):
    rng = Random(seed)
    worst, bad, equal = 0.0, 0, 0
    for _ in range(trials):
        k = rng.randint(1, 4)
        n = rng.randint(2, 10)
        jobs = sorted((rng.randint(0, 12), rng.randint(1, L)) for _ in range(n))
        crashes = [(rng.randint(0, 25), rng.randrange(k), rng.randint(1, 4))
                   for _ in range(rng.randint(0, 5))]
        B = rng.randint(0, 6)
        fcfs = simulate(jobs, k, crashes, lambda t, w, a, d: w[0], lambda free: free[0])
        policy = guard(jobs, B, rng) if use_guard else (lambda t, w, a, d: rng.choice(w))
        p = simulate(jobs, k, crashes, policy, lambda free: rng.choice(free))
        first_p, att_p, phi_p, unf_p = p
        first_f, _, phi_f, _ = fcfs
        for i in range(n):
            a_i = jobs[i][0]
            tau = max(t for t in unf_p if t <= a_i and unf_p[t] <= (k - 1) * L)
            n_i = sum(1 for tc, _, _ in crashes if tau <= tc <= first_p[i])
            inn, outt = in_out(jobs, i, first_p, att_p)
            gap = phi_p[first_p[i]] - phi_f[first_f[i]]
            if use_guard:
                bound = B + (3 * k - 2) * L + L * n_i
                worst = max(worst, gap / bound)
                bad += gap >= bound
                equal += gap >= bound - L * n_i          # the crash term was needed
            else:
                lhs, bound = gap - (inn - outt), 2 * (k - 1) * L + L * n_i
                worst = max(worst, lhs / bound if bound else (0 if lhs <= 0 else float("inf")))
                bad += lhs > bound
                equal += lhs > bound - L * n_i           # the crash term was needed
    return worst, bad, equal


def main():
    worst, bad, needed = check(4000, 11, False)
    print(f"C1 identity with crashes: worst (lhs)/(2(k-1)L + L N) = {worst:.3f}, violations {bad}, "
          f"jobs that break the crash-free bound {needed}")
    worst, bad, needed = check(4000, 12, True)
    print(f"C2 guard with crashes: worst gap/(B + (3k-2)L + L N) = {worst:.3f}, violations {bad}, "
          f"jobs that break the crash-free bound {needed}")


if __name__ == "__main__":
    main()
