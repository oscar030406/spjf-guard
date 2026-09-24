"""Overtake-budget guard with late charges: a standalone check of derivation.md.

Integer time, k identical servers, non-preemptive and work-conserving.  The FCFS
reference is the Kiefer-Wolfowitz recursion.  The base policy is "smallest predicted
key first, ties by rank" with adversarial keys.  The guard is Algorithm 1 of the paper,
except that the charge of a completion reaches the counter late:

  U   one shared counter; the charge of job c, completed at f_c, is applied at
      f_c + d_c with 0 <= d_c <= delta.
  A1  as U, and in addition a server applies its own last completion to the shared
      counter immediately before it pulls its next job (report-before-pull).
  A2  each server dispatches from its own view: its own completions are in it at once,
      another server's completion c enters it at f_c + d_c.
  UN  as U, and a waiting job also fires once it has waited theta (guard OR clock);
      delta = INF means every report is lost and the guard never fires.  UN serves the
      minimum-rank member of the union, i.e. the head if aged, otherwise Algorithm 1.
  UG  guard-first union (the guard's pick, else the aged head, else the base); used only
      by check_union_rule.py to reproduce the counterexample to that reading.

A charge applied at instant t is seen by every dispatch at t (the paper's order:
completions, then arrivals, then dispatches).  delta = 0 is Algorithm 1 exactly.

For every job i the checks are the numbered claims of derivation.md:
  EXCESS  k*excess_i  <  Bmax + (3k-2)L + X          (X = extra of the model)
  IN      In_i        <  Bmax + kL + X
  IDENT   |k*excess_i - (In_i - Out_i)| <= 2(k-1)L, strict for k >= 2, zero at k = 1
  GUARD   charged part at the last overtaker's dispatch < budget(i, t)
  SUM     charged + stale + in service + C_last == In_i
  STALE   per-server stale work within the cap of the model
  INSERV  at most one in-service overtaker per server, none on the dispatching server
  A2REF   A2: a server holding an in-service overtaker has stale work < Bmax
  CLOCK   UN: k*excess_i < k*theta + (3k-2)L
  CLKIN   UN: In_i < k(theta + L)
  FLUID   every model: k*W_i <= V_i^- + (k-1)L + In_i  (V^- = rate-k fluid backlog)
X = k(L+delta) for U and UN, (k-1)(L+delta) for A2, 0 for A1, and 0 for every model
at delta = 0.

Run from the repository root:
  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 \
    OMP_NUM_THREADS=4 uv run --no-sync python evidence/stale_charging/sim_stale.py \
    > evidence/stale_charging/out_sim_stale.txt
Exhaustive part alone up to n: append the arguments "<n> exhaustive".
"""

import itertools
import sys
import time

import numpy as np
from numba import njit, prange, set_num_threads

set_num_threads(2)  # at most two workers, per the task's resource rule

U, A1, A2, UN, UG = 0, 1, 2, 3, 4  # UG: guard-first union, the refuted reading (check_union_rule.py only)
MODEL_NAMES = ("U", "A1", "A2", "UN", "UG")
CHECKS = ("EXCESS", "IN", "IDENT", "GUARD", "SUM", "STALE", "INSERV", "A2REF", "CLOCK", "CLKIN", "FLUID")
NCHK = len(CHECKS)
BIG_KEY = 1.0e9
INF = 1 << 40  # a delay or theta that never elapses within any instance here


# ---------------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------------


@njit(cache=True)
def fcfs_starts(k, a, C, fs, free):
    n = a.shape[0]
    for s in range(k):
        free[s] = a[0]
    for i in range(n):
        m = 0
        for s in range(1, k):
            if free[s] < free[m]:
                m = s
        st = a[i] if a[i] > free[m] else free[m]
        fs[i] = st
        free[m] = st + C[i]


@njit(cache=True)
def budget(q, t, a, nq, k, B0, gam, eta, Bmax):
    b = B0 + gam * nq[q] + eta * k * (t - a[q])
    return b if b < Bmax else float(Bmax)


@njit(cache=True)
def apply_charge(view, c, C):
    for q in range(c):
        view[q] += C[c]


@njit(cache=True)
def sim_guard(k, a, C, key, B0, gam, eta, Bmax, model, delay, sorder, theta, w):
    """Run the guard.  w is a tuple of work arrays, filled in place.  theta = INF
    switches the clock off (every model but UN is run that way)."""
    (start, fin, srv, seq, nq, done, waiting, sjob, busy, pend, appg, app2, overg, over2) = w
    n = a.shape[0]
    for j in range(n):
        done[j] = False
        waiting[j] = False
        appg[j] = -1
        overg[j] = 0
    for s in range(k):
        sjob[s] = -1
        pend[s] = -1
        for j in range(n):
            app2[s, j] = -1
            over2[s, j] = 0
    nxt = 0
    ndisp = 0
    nwait = 0
    t = a[0]
    while ndisp < n:
        # 1. completions at t
        for s in range(k):
            j = sjob[s]
            if j >= 0 and busy[s] == t:
                fin[j] = t
                done[j] = True
                sjob[s] = -1
                if model == A2:
                    apply_charge(over2[s], j, C)
                    app2[s, j] = ndisp
                elif model == A1:
                    pend[s] = j
        # 2. lagged charges due by t
        for c in range(nxt):
            if done[c] and fin[c] + delay[c] <= t:
                if model == A2:
                    for s in range(k):
                        if app2[s, c] < 0:
                            apply_charge(over2[s], c, C)
                            app2[s, c] = ndisp
                elif appg[c] < 0:
                    apply_charge(overg, c, C)
                    appg[c] = ndisp
        # 3. arrivals at t
        while nxt < n and a[nxt] == t:
            nq[nxt] = nwait
            waiting[nxt] = True
            nwait += 1
            nxt += 1
        # 4. dispatch phase
        while nwait > 0:
            s = -1
            if sorder == 0:
                for x in range(k):
                    if sjob[x] < 0:
                        s = x
                        break
            else:
                for x in range(k - 1, -1, -1):
                    if sjob[x] < 0:
                        s = x
                        break
            if s < 0:
                break
            if model == A1 and pend[s] >= 0:
                c = pend[s]
                pend[s] = -1
                if appg[c] < 0:
                    apply_charge(overg, c, C)
                    appg[c] = ndisp
            jsel = -1
            if model == UG:
                # guard-first: the guard's minimum-rank pick, else the head if aged
                for q in range(nxt):
                    if waiting[q] and overg[q] >= budget(q, t, a, nq, k, B0, gam, eta, Bmax):
                        jsel = q
                        break
                if jsel < 0:
                    for q in range(nxt):
                        if waiting[q] and t - a[q] >= theta:
                            jsel = q
                            break
            for q in range(nxt):
                if jsel >= 0:
                    break
                if waiting[q]:
                    # minimum-rank member of E(t) union A_theta(t); A_theta is a prefix of the
                    # waiting set, so this is "the head if aged, otherwise Algorithm 1"
                    v = over2[s, q] if model == A2 else overg[q]
                    if v >= budget(q, t, a, nq, k, B0, gam, eta, Bmax) or t - a[q] >= theta:
                        jsel = q
                        break
            if jsel < 0:
                for q in range(nxt):
                    if waiting[q] and (jsel < 0 or key[q] < key[jsel]):
                        jsel = q
            waiting[jsel] = False
            nwait -= 1
            start[jsel] = t
            srv[jsel] = s
            seq[jsel] = ndisp
            ndisp += 1
            sjob[s] = jsel
            busy[s] = t + C[jsel]
        if ndisp == n:
            break
        tn = a[nxt] if nxt < n else (1 << 62)
        for s in range(k):
            if sjob[s] >= 0 and busy[s] < tn:
                tn = busy[s]
        t = tn
    for j in range(n):
        fin[j] = start[j] + C[j]


@njit(cache=True)
def model_extra(model, k, L, delta):
    if delta == 0 or model == A1:
        return 0
    if model == A2:
        return (k - 1) * (L + delta)
    return k * (L + delta)


@njit(cache=True)
def check_run(k, L, delta, a, C, fs, B0, gam, eta, Bmax, model, theta, w, viol, sc, res):
    """Check every job.  res[0] = worst excess/bound, res[1] = its job, res[2] = excess,
    res[3] = k*bound (so bound = res[3]/k).  The bound is the guard bound of the model,
    and for UN the clock bound k*theta + (3k-2)L."""
    (start, fin, srv, seq, nq, done, waiting, sjob, busy, pend, appg, app2, overg, over2) = w
    stale_s, insv_s, insv_n = sc
    n = a.shape[0]
    X = model_extra(model, k, L, delta)
    kbound = Bmax + (3 * k - 2) * L + X
    bound_in = Bmax + k * L + X
    kclock = k * theta + (3 * k - 2) * L
    vminus = 0
    for i in range(n):
        if i > 0:
            vminus = vminus + C[i - 1] - k * (a[i] - a[i - 1])
            if vminus < 0:
                vminus = 0
        exc = start[i] - fs[i]
        In = 0
        Out = 0
        jl = -1
        for c in range(i + 1, n):
            if seq[c] < seq[i]:
                In += C[c]
                if jl < 0 or seq[c] > seq[jl]:
                    jl = c
        for c in range(i):
            if seq[c] > seq[i]:
                Out += C[c]
        dlt = k * exc - (In - Out)
        if k == 1:
            if dlt != 0:
                viol[2] += 1
        elif not (abs(dlt) < 2 * (k - 1) * L):
            viol[2] += 1
        if not (k * exc < kbound):
            viol[0] += 1
        if not (k * (start[i] - a[i]) <= vminus + (k - 1) * L + In):
            viol[10] += 1
        if model == UN or model == UG:
            if not (k * exc < kclock):
                viol[8] += 1
            if jl >= 0 and not (In < k * (theta + L)):
                viol[9] += 1
            r = (k * exc) / kclock
            kb_rep = kclock
        else:
            r = (k * exc) / kbound
            kb_rep = kbound
        if r > res[0]:
            res[0] = r
            res[1] = i
            res[2] = exc
            res[3] = kb_rep
        if jl < 0:
            continue
        if not (In < bound_in):
            viol[1] += 1
        t = start[jl]
        sj = srv[jl]
        d = seq[jl]
        for s in range(k):
            stale_s[s] = 0
            insv_s[s] = 0
            insv_n[s] = 0
        charged = 0
        bad_c = False
        for c in range(i + 1, n):
            if seq[c] < seq[i] and c != jl:
                if fin[c] <= t:
                    if model == A2:
                        vis = app2[sj, c] >= 0 and app2[sj, c] <= d
                    else:
                        vis = appg[c] >= 0 and appg[c] <= d
                    if vis:
                        charged += C[c]
                    else:
                        stale_s[srv[c]] += C[c]
                        if fin[c] <= t - delta:
                            bad_c = True
                        if model == A1 and fin[c] != t:
                            bad_c = True
                else:
                    insv_s[srv[c]] += C[c]
                    insv_n[srv[c]] += 1
        if not (charged < budget(i, t, a, nq, k, B0, gam, eta, Bmax)):
            viol[3] += 1
        tot = charged + C[jl]
        for s in range(k):
            tot += stale_s[s] + insv_s[s]
        if tot != In:
            viol[4] += 1
        bad_stale = bad_c
        for s in range(k):
            if insv_n[s] > 1 or (s == sj and insv_n[s] > 0):
                viol[6] += 1
            if delta == 0:
                cap = 0
            elif model == A2:
                cap = 0 if s == sj else L + delta - 1
            elif model == A1:
                cap = 0 if (s == sj or insv_n[s] > 0) else L
            else:
                cap = L + delta - 1
            if stale_s[s] > cap:
                bad_stale = True
            if model == A2 and insv_n[s] > 0 and not (stale_s[s] < Bmax):
                viol[7] += 1
        if bad_stale:
            viol[5] += 1


@njit(cache=True)
def make_work_nb(n, k):
    i64 = np.int64
    w = (
        np.zeros(n, i64),  # start
        np.zeros(n, i64),  # fin
        np.zeros(n, i64),  # srv
        np.zeros(n, i64),  # seq
        np.zeros(n, i64),  # nq
        np.zeros(n, np.bool_),  # done
        np.zeros(n, np.bool_),  # waiting
        np.zeros(k, i64),  # sjob
        np.zeros(k, i64),  # busy
        np.zeros(k, i64),  # pend
        np.zeros(n, i64),  # appg
        np.zeros((k, n), i64),  # app2
        np.zeros(n, i64),  # overg
        np.zeros((k, n), i64),  # over2
    )
    sc = (np.zeros(k, i64), np.zeros(k, i64), np.zeros(k, i64))
    return w, sc


# ---------------------------------------------------------------------------------
# exhaustive small instances
# ---------------------------------------------------------------------------------


@njit(cache=True)
def family_key(oi, n, C, key):
    """Adversarial keys for n >= 6: for each victim v, v last and the others ordered by
    one of four rules; then the four rules with no victim singled out."""
    nv = 4 * n
    typ = oi % 4 if oi < nv else oi - nv
    for j in range(n):
        if typ == 0:
            key[j] = -j  # newest first
        elif typ == 1:
            key[j] = C[j] * 64 - j  # shortest first, newest first on ties
        elif typ == 2:
            key[j] = -C[j] * 64 - j  # longest first, newest first on ties
        else:
            key[j] = j  # arrival order
    if oi < nv:
        key[oi // 4] = BIG_KEY


@njit(cache=True)
def fill_delay(delay, n, delta, full_delay, p, si, ai, oi, B):
    if delta == 0 or delta == INF:
        for j in range(n):
            delay[j] = delta
    elif full_delay:
        x = p
        for j in range(n):
            delay[j] = x % (delta + 1)
            x //= delta + 1
    elif p == 0:
        for j in range(n):
            delay[j] = delta
    else:
        for j in range(n):
            h = (si * 7919 + ai * 104729 + oi * 131 + j * 31 + B * 17) % 1000003
            delay[j] = (h * 2654435761 % 4294967291) % (delta + 1)


@njit(cache=True)
def enum_block(n, si0, sizes_all, arr_all, perms, use_perms, full_delay, L, Bs, thetas, res, arg, viol, cnt):
    """Index di: delta = 0, 1, 2, and 3 for INF (UN only).  Models at delta = 0: U (the
    three late-charge models coincide there) and UN; at delta = 1, 2: all four.
    res[ki, m, di] worst ratio; arg[ki, m, di, :] = (si, ai, oi, B, pattern, sorder, job,
    theta); viol[ki, m, di, check]; cnt[ki, m, di]."""
    nsz = sizes_all.shape[0]
    nar = arr_all.shape[0]
    nord = perms.shape[0] if use_perms else 4 * n + 4
    key = np.zeros(n, np.float64)
    delay = np.zeros(n, np.int64)
    fs = np.zeros(n, np.int64)
    free = np.zeros(2, np.int64)
    r = np.zeros(4, np.float64)
    vtmp = np.zeros(NCHK, np.int64)
    for ki in range(2):
        k = ki + 1
        w, sc = make_work_nb(n, k)
        nso = 1 if k == 1 else 2
        for si in range(nsz):
            C = sizes_all[si]
            for ai in range(nar):
                a = arr_all[ai]
                fcfs_starts(k, a, C, fs, free)
                for oi in range(nord):
                    if use_perms:
                        for j in range(n):
                            key[j] = perms[oi, j]
                    else:
                        family_key(oi, n, C, key)
                    for di in range(4):
                        delta = INF if di == 3 else di
                        if delta == 0 or delta == INF:
                            npat = 1
                        elif full_delay:
                            npat = (delta + 1) ** n
                        else:
                            npat = 2
                        for m in range(4):
                            if di == 0 and (m == A1 or m == A2):
                                continue
                            if di == 3 and m != UN:
                                continue
                            nth = thetas.shape[0] if m == UN else 1
                            for bi in range(Bs.shape[0]):
                                B = Bs[bi]
                                for p in range(npat):
                                    fill_delay(delay, n, delta, full_delay, p, si0 + si, ai, oi, B)
                                    for ti in range(nth):
                                        th = thetas[ti] if m == UN else INF
                                        for so in range(nso):
                                            sim_guard(k, a, C, key, float(B), 0.0, 0.0, B, m, delay, so, th, w)
                                            r[0] = -1.0
                                            for c in range(NCHK):
                                                vtmp[c] = 0
                                            check_run(k, L, delta, a, C, fs, float(B), 0.0, 0.0, B, m, th, w, vtmp, sc, r)
                                            cnt[ki, m, di] += 1
                                            for c in range(NCHK):
                                                viol[ki, m, di, c] += vtmp[c]
                                            if r[0] > res[ki, m, di]:
                                                res[ki, m, di] = r[0]
                                                arg[ki, m, di, 0] = si0 + si
                                                arg[ki, m, di, 1] = ai
                                                arg[ki, m, di, 2] = oi
                                                arg[ki, m, di, 3] = B
                                                arg[ki, m, di, 4] = p
                                                arg[ki, m, di, 5] = so
                                                arg[ki, m, di, 6] = int(r[1])
                                                arg[ki, m, di, 7] = th


@njit(parallel=True, cache=True)
def enum_par(n, sizes_all, arr_all, perms, use_perms, full_delay, L, Bs, thetas, res_s, arg_s, viol_s, cnt_s):
    """One enum_block per size vector, spread over the numba threads; per-vector outputs."""
    for si in prange(sizes_all.shape[0]):
        enum_block(n, si, sizes_all[si : si + 1], arr_all, perms, use_perms, full_delay, L, Bs, thetas,
                   res_s[si], arg_s[si], viol_s[si], cnt_s[si])


def run_exhaustive(out, nmax=7):
    L = 3
    Bs = np.array([1, 2, 3], np.int64)
    thetas = np.array([0, 1, 2, 4, 6], np.int64)
    tot_res = np.full((2, 4, 4), -1.0)
    tot_viol = np.zeros((2, 4, 4, NCHK), np.int64)
    tot_cnt = np.zeros((2, 4, 4), np.int64)
    worst = {}
    out.write("== EXHAUSTIVE small instances: sizes {1,2,3}, L = 3, arrivals 0..4 (first at 0), B in {1,2,3},\n")
    out.write("   delta in {0,1,2} and INF (UN only), theta in {0,1,2,4,6} (UN only), both server orders at k = 2\n")
    out.write("   n <= 4: all key orders x all delay vectors {0..delta}^n\n")
    out.write("   n = 5 : all key orders x delay patterns {all delta, hashed per job}\n")
    out.write("   n = 6,7: 4n+4 adversarial key orders (victim-last families) x the same two patterns\n")
    for n in range(1, nmax + 1):
        t0 = time.time()
        sizes_all = np.array(list(itertools.product((1, 2, 3), repeat=n)), np.int64)
        arr_all = np.array([c for c in itertools.combinations_with_replacement(range(5), n) if c[0] == 0], np.int64)
        use_perms = n <= 5
        perms = (
            np.array([[p.index(j) for j in range(n)] for p in itertools.permutations(range(n))], np.float64)
            if use_perms
            else np.zeros((1, n), np.float64)
        )
        full_delay = n <= 4
        nsz = len(sizes_all)
        res_s = np.full((nsz, 2, 4, 4), -1.0)
        arg_s = np.zeros((nsz, 2, 4, 4, 8), np.int64)
        viol_s = np.zeros((nsz, 2, 4, 4, NCHK), np.int64)
        cnt_s = np.zeros((nsz, 2, 4, 4), np.int64)
        enum_par(n, sizes_all, arr_all, perms, use_perms, full_delay, L, Bs, thetas, res_s, arg_s, viol_s, cnt_s)
        best = res_s.argmax(axis=0)
        res = np.take_along_axis(res_s, best[None], axis=0)[0]
        arg = np.take_along_axis(arg_s, best[None, ..., None], axis=0)[0]
        viol = viol_s.sum(axis=0)
        cnt = cnt_s.sum(axis=0)
        for ki in range(2):
            for m in range(4):
                for di in range(4):
                    if cnt[ki, m, di] and res[ki, m, di] > tot_res[ki, m, di]:
                        tot_res[ki, m, di] = res[ki, m, di]
                        a_ = arg[ki, m, di]
                        order = perms[a_[2]].tolist() if use_perms else f"family#{a_[2]}"
                        worst[(ki, m, di)] = (
                            n,
                            sizes_all[a_[0]].tolist(),
                            arr_all[a_[1]].tolist(),
                            order,
                            int(a_[3]),
                            int(a_[4]),
                            int(a_[5]),
                            int(a_[6]),
                            "off" if a_[7] == INF else int(a_[7]),
                        )
        tot_viol += viol
        tot_cnt += cnt
        out.write(
            f"   n={n}: {len(sizes_all)} size vectors x {len(arr_all)} arrival vectors, "
            f"{int(cnt.sum())} runs, {time.time() - t0:.1f} s, violations {int(viol.sum())}\n"
        )
        out.flush()
    out.write("   ratio column: excess over the model's guard bound; for UN over the clock bound theta + (3-2/k)L\n")
    out.write("   k  model  delta       runs  worst ratio  violations(by check)   worst instance\n")
    for ki in range(2):
        for m in range(4):
            for di in range(4):
                if tot_cnt[ki, m, di] == 0:
                    continue
                vv = " ".join(f"{CHECKS[c]}={tot_viol[ki, m, di, c]}" for c in range(NCHK) if tot_viol[ki, m, di, c])
                w_ = worst[(ki, m, di)]
                dl = "INF" if di == 3 else str(di)
                out.write(
                    f"   {ki + 1}  {MODEL_NAMES[m]:5s}  {dl:>5s}  {tot_cnt[ki, m, di]:10d}  {tot_res[ki, m, di]:11.4f}"
                    f"  {vv if vv else 'none':20s}  n={w_[0]} C={w_[1]} a={w_[2]} key={w_[3]} B={w_[4]}"
                    f" pat={w_[5]} sorder={w_[6]} job={w_[7]} theta={w_[8]}\n"
                )
    out.write(f"   TOTAL runs {int(tot_cnt.sum())}, TOTAL violations {int(tot_viol.sum())}\n\n")
    return tot_cnt, tot_viol, tot_res


# ---------------------------------------------------------------------------------
# random instances
# ---------------------------------------------------------------------------------


@njit(cache=True)
def gen_random(n, L, a, C, key, delay, delta):
    smode = np.random.randint(0, 3)
    pL = np.random.random()
    for j in range(n):
        if smode == 0:
            C[j] = np.random.randint(1, L + 1)
        elif smode == 1:
            C[j] = L if np.random.random() < pL else 1
        else:
            C[j] = L if np.random.random() < pL else np.random.randint(1, 3)
    amode = np.random.randint(0, 3)
    span = 0 if amode == 0 else (L if amode == 1 else n * L // 2 + 1)
    for j in range(n):
        a[j] = np.random.randint(0, span + 1)
    a.sort()
    a0 = a[0]
    for j in range(n):
        a[j] -= a0
    kmode = np.random.randint(0, 6)
    perm = np.random.permutation(n)
    for j in range(n):
        if kmode == 0 or kmode == 5:
            key[j] = perm[j]
        elif kmode == 1:
            key[j] = C[j] * 64 - j
        elif kmode == 2:
            key[j] = -C[j] * 64 - j
        else:
            key[j] = -j
    if kmode >= 4:
        key[np.random.randint(0, n)] = BIG_KEY
    dmode = np.random.randint(0, 3)
    for j in range(n):
        if delta == INF or dmode == 0:
            delay[j] = delta
        elif dmode == 1:
            delay[j] = np.random.randint(0, delta + 1)
        else:
            delay[j] = delta if np.random.random() < 0.5 else 0


@njit(cache=True)
def run_random_nb(nrun, seed, res, viol, cnt, arg):
    """res[m, k-1], viol[m, k-1, check], cnt[m, k-1]; arg[m, k-1] = run index of the worst."""
    np.random.seed(seed)
    Ls = np.array([3, 4, 6, 10])
    vtmp = np.zeros(NCHK, np.int64)
    r = np.zeros(4, np.float64)
    for it in range(nrun):
        k = np.random.randint(1, 5)
        n = np.random.randint(2, 41)
        L = Ls[np.random.randint(0, 4)]
        delta = np.random.randint(0, 2 * L + 1) if np.random.random() < 0.85 else 0
        model = np.random.randint(0, 4)
        theta = INF
        if model == UN:
            theta = np.random.randint(0, 3 * L + 1)
            if np.random.random() < 0.25:
                delta = INF
        so = np.random.randint(0, 2)
        a = np.zeros(n, np.int64)
        C = np.zeros(n, np.int64)
        key = np.zeros(n, np.float64)
        delay = np.zeros(n, np.int64)
        gen_random(n, L, a, C, key, delay, delta)
        if np.random.random() < 0.5:
            Bmax = np.random.randint(0, 4 * L + 1)
            B0 = float(Bmax)
            gam = 0.0
            eta = 0.0
        else:
            Bmax = np.random.randint(0, 6 * L + 1)
            B0 = float(np.random.randint(0, Bmax + 1))
            gam = np.array([0.0, 0.5, 1.0, 2.0])[np.random.randint(0, 4)]
            eta = np.array([0.0, 0.25, 0.5, 0.75])[np.random.randint(0, 4)]
        fs = np.zeros(n, np.int64)
        free = np.zeros(k, np.int64)
        fcfs_starts(k, a, C, fs, free)
        w, sc = make_work_nb(n, k)
        sim_guard(k, a, C, key, B0, gam, eta, Bmax, model, delay, so, theta, w)
        r[0] = -1.0
        for c in range(NCHK):
            vtmp[c] = 0
        check_run(k, L, delta, a, C, fs, B0, gam, eta, Bmax, model, theta, w, vtmp, sc, r)
        cnt[model, k - 1] += 1
        for c in range(NCHK):
            viol[model, k - 1, c] += vtmp[c]
        if r[0] > res[model, k - 1]:
            res[model, k - 1] = r[0]
            arg[model, k - 1] = it


def run_random(out, nrun=200_000, seed=20260923):
    t0 = time.time()
    res = np.full((4, 4), -1.0)
    viol = np.zeros((4, 4, NCHK), np.int64)
    cnt = np.zeros((4, 4), np.int64)
    arg = np.zeros((4, 4), np.int64)
    run_random_nb(nrun, seed, res, viol, cnt, arg)
    out.write(f"== RANDOM instances: {nrun} runs, seed {seed}, k in 1..4, n in 2..40, L in {{3,4,6,10}},\n")
    out.write("   delta in 0..2L, constant or shaped budget (B0 + gam*n_q + eta*k*age, capped), 6 key rules,\n")
    out.write("   3 delay rules, 2 server orders; model drawn per run; UN: theta in 0..3L, delta = INF in 1/4 of runs\n")
    out.write("   ratio column: excess over the model's guard bound; for UN over the clock bound\n")
    out.write("   model  k      runs  worst ratio  violations(by check)\n")
    for m in range(4):
        for k in range(4):
            vv = " ".join(f"{CHECKS[c]}={viol[m, k, c]}" for c in range(NCHK) if viol[m, k, c])
            out.write(f"   {MODEL_NAMES[m]:5s}  {k + 1}  {cnt[m, k]:8d}  {res[m, k]:11.4f}  {vv if vv else 'none'}\n")
    out.write(f"   TOTAL runs {int(cnt.sum())}, TOTAL violations {int(viol.sum())}, {time.time() - t0:.1f} s\n\n")
    return cnt, viol, res


# ---------------------------------------------------------------------------------
# explicit lower-bound instances
# ---------------------------------------------------------------------------------


class Inst:
    """Jobs in rank order: arrival, size, key, delay."""

    def __init__(self):
        self.a, self.C, self.key, self.d, self.tag = [], [], [], [], []

    def add(self, a, C, key, d=0, tag=""):
        self.a.append(a)
        self.C.append(C)
        self.key.append(key)
        self.d.append(d)
        self.tag.append(tag)
        return len(self.a) - 1

    def arrays(self):
        return (
            np.array(self.a, np.int64),
            np.array(self.C, np.int64),
            np.array(self.key, np.float64),
            np.array(self.d, np.int64),
        )


def run_inst(inst, k, L, delta, Bmax, model, theta=INF, sorder=0):
    a, C, key, d = inst.arrays()
    n = len(a)
    w, sc = make_work_nb(n, k)
    fs = np.zeros(n, np.int64)
    fcfs_starts(k, a, C, fs, np.zeros(k, np.int64))
    sim_guard(k, a, C, key, float(Bmax), 0.0, 0.0, Bmax, model, d, sorder, theta, w)
    viol = np.zeros(NCHK, np.int64)
    r = np.array([-1.0, 0, 0, 0])
    check_run(k, L, delta, a, C, fs, float(Bmax), 0.0, 0.0, Bmax, model, theta, w, viol, sc, r)
    return w, fs, viol, r


def decompose(inst, w, k, i, model):
    """Victim i: In, Out, and the split of In at its last overtaker's dispatch."""
    start, fin, srv, seq = w[0], w[1], w[2], w[3]
    appg, app2 = w[10], w[11]
    C = inst.C
    n = len(C)
    ov = [c for c in range(i + 1, n) if seq[c] < seq[i]]
    In = sum(C[c] for c in ov)
    Out = sum(C[c] for c in range(i) if seq[c] > seq[i])
    jl = max(ov, key=lambda c: seq[c])
    t, sj, dd = start[jl], srv[jl], seq[jl]
    charged, stale, insv = 0, [0] * k, [0] * k
    for c in ov:
        if c == jl:
            continue
        if fin[c] <= t:
            vis = (0 <= app2[sj, c] <= dd) if model == A2 else (0 <= appg[c] <= dd)
            if vis:
                charged += C[c]
            else:
                stale[srv[c]] += C[c]
        else:
            insv[srv[c]] += C[c]
    return In, Out, charged, stale, insv, C[jl], sj, int(t - inst.a[i])


def lb_k1(L, B, delta):
    """k = 1: charged part B-1, a stale job of size L, delta-1 unit jobs, the last overtaker L."""
    inst = Inst()
    v = inst.add(0, L, BIG_KEY, 0, "victim")
    for _ in range(B - 1):
        inst.add(0, 1, 1, 0, "charged unit")
    inst.add(0, L, 2, delta, "stale L")
    for _ in range(max(delta - 1, 0)):
        inst.add(0, 1, 3, delta, "stale unit")
    inst.add(0, L, 4, 0, "last overtaker")
    return inst, v


def cascade(k, m, inst):
    """Lemma S8.1 of the paper: m rounds, L = k^m; returns f and T_m."""
    L = k**m
    for j in range(m):
        T = j * L
        for _ in range(k - 1):
            inst.add(T, L, 1, 0, "cascade long")
        for _ in range(L):
            inst.add(T, 1, 0, 0, "cascade short")
    f = L - L * (k - 1) ** m // k**m
    return L, f, m * L


def lb_paper(k, m):
    """The instance of the paper's Proposition S8.3(ii), unchanged (delta = 0)."""
    inst = Inst()
    L, f, T = cascade(k, m, inst)
    for _ in range(k - 1):
        inst.add(T, L, 3, 0, "new long")
    v = inst.add(T, L, BIG_KEY, 0, "victim")
    inst.add(T, f, 2, 0, "sync")
    inst.add(T, L, 3, 0, "pre")
    for _ in range(k):
        inst.add(T, L, 6, 0, "final")
    return inst, v, L, f, f + L + 1


def lb_cascade_stale(k, m, delta, variant):
    """Cascade, then sync and pre (charged), then on every server a stale job of size L
    and delta-1 unit jobs whose charges are late, then k finals.
    variant 'U': B = f + L + 1.  variant 'A2': B = f + 2L + delta (each server sees its
    own window work, never the other servers')."""
    inst = Inst()
    L, f, T = cascade(k, m, inst)
    for _ in range(k - 1):
        inst.add(T, L, 3, 0, "new long")
    v = inst.add(T, L, BIG_KEY, 0, "victim")
    inst.add(T, f, 2, 0, "sync")
    inst.add(T, L, 3, 0, "pre")
    for _ in range(k):
        inst.add(T, L, 4, delta, "stale L")
    for _ in range(k * max(delta - 1, 0)):
        inst.add(T, 1, 5, delta, "stale unit")
    for _ in range(k):
        inst.add(T, L, 6, 0, "final")
    B = f + L + 1 if variant == "U" else f + 2 * L + delta
    return inst, v, L, f, B


def lb_clock_flat(k, L, theta):
    """Clock with every report lost: at time 0 the victim (rank 0) and, per server,
    theta-1 unit jobs then one job of size L, all preferred by the base policy."""
    inst = Inst()
    v = inst.add(0, L, BIG_KEY, INF, "victim")
    for _ in range(k * (theta - 1)):
        inst.add(0, 1, 1, INF, "unit")
    for _ in range(k):
        inst.add(0, L, 2, INF, "long")
    return inst, v


def report_inst(out, name, inst, v, k, L, delta, B, model, expect=None, theta=INF):
    w, fs, viol, r = run_inst(inst, k, L, delta, B, model, theta)
    start = w[0]
    exc = int(start[v] - fs[v])
    if model == UN or model == UG:
        kb = k * theta + (3 * k - 2) * L
    else:
        kb = B + (3 * k - 2) * L + int(model_extra(model, k, L, delta))
    In, Out, charged, stale, insv, cl, sj, age = decompose(inst, w, k, v, model)
    dl = "INF" if delta == INF else str(delta)
    th = "" if theta == INF else f" theta={theta}"
    line = (
        f"   {name:28s} k={k} L={L:4d} delta={dl:>4s} B={B:5d}{th} {MODEL_NAMES[model]:2s} n={len(inst.C):5d}"
        f" | victim excess {exc:5d}  bound {kb / k:9.2f}  ratio {k * exc / kb:.4f}"
        f" | In {In} = charged {charged} + stale {stale} + in-service {insv} + last {cl} (server {sj},"
        f" age {age}); Out {Out} | worst job ratio {r[0]:.4f} | violations {int(viol.sum())}"
    )
    if expect is not None:
        line += f" | expected excess {expect}: {'OK' if expect == exc else 'MISMATCH'}"
    out.write(line + "\n")
    return exc, kb, int(viol.sum()), age


def run_lower_bounds(out):
    out.write("== LOWER-BOUND INSTANCES (victim = the job singled out by the construction)\n")
    out.write("-- reproduction of the paper's Proposition S8.3(ii), delta = 0 (Theorem 3 bound)\n")
    nv = 0
    for k, m in ((2, 6), (2, 7), (3, 4), (4, 3)):
        inst, v, L, f, B = lb_paper(k, m)
        nv += report_inst(out, f"paper S8.3 m={m}", inst, v, k, L, 0, B, U, f + 2 * L)[2]
    out.write("-- k = 1, model U: expect excess B + 2L + delta - 2 against the bound B + 2L + delta\n")
    for L, B, delta in ((3, 1, 1), (3, 1, 2), (3, 3, 2), (30, 30, 1), (30, 30, 30), (300, 300, 1), (300, 300, 300), (300, 300, 600)):
        inst, v = lb_k1(L, B, delta)
        nv += report_inst(out, "k1 stale", inst, v, 1, L, delta, B, U, B + 2 * L + delta - 2)[2]
    out.write("-- the same k = 1 instances under A1 and A2 (expect the Theorem 3 value B - 1 + L)\n")
    for L, B, delta in ((30, 30, 30), (300, 300, 300)):
        inst, v = lb_k1(L, B, delta)
        for model in (A1, A2):
            nv += report_inst(out, "k1 stale", inst, v, 1, L, delta, B, model, B - 1 + L)[2]
    out.write("-- k >= 2, model U, cascade + stale finale: expect excess f + 3L + delta - 1, bound B/k + (4-2/k)L + delta\n")
    for k, m, deltas in ((2, 4, (1, 8, 16)), (2, 6, (1, 32, 64, 128)), (2, 8, (1, 128, 256, 512)), (3, 4, (1, 81)), (3, 5, (1, 243)), (4, 4, (1, 256))):
        for delta in deltas:
            inst, v, L, f, B = lb_cascade_stale(k, m, delta, "U")
            nv += report_inst(out, f"cascade-stale U m={m}", inst, v, k, L, delta, B, U, f + 3 * L + delta - 1)[2]
    out.write("-- the U instances under A1 (expect the Theorem 3 value f + 2L: the stale jobs are reported on pull)\n")
    for k, m, delta in ((2, 6, 64), (2, 8, 256), (3, 5, 243)):
        inst, v, L, f, B = lb_cascade_stale(k, m, delta, "U")
        nv += report_inst(out, f"cascade-stale U m={m}", inst, v, k, L, delta, B, A1, f + 2 * L)[2]
    out.write("-- k >= 2, model A2, cascade + symmetric stale finale: expect excess f + 3L + delta - 1,\n")
    out.write("   bound B/k + (3-2/k)L + (1-1/k)(L+delta) with B = f + 2L + delta\n")
    for k, m, deltas in ((2, 4, (1, 8, 16)), (2, 6, (1, 32, 64, 128)), (2, 8, (1, 128, 256, 512)), (3, 5, (1, 243)), (4, 4, (1, 256))):
        for delta in deltas:
            inst, v, L, f, B = lb_cascade_stale(k, m, delta, "A2")
            nv += report_inst(out, f"cascade-stale A2 m={m}", inst, v, k, L, delta, B, A2, f + 3 * L + delta - 1)[2]
    out.write("-- UN with every report lost (delta = INF), flat instance: expect excess theta + L - 1,\n")
    out.write("   bound theta + (3-2/k)L\n")
    for k, L, theta in ((1, 3, 3), (1, 30, 30), (1, 30, 3000), (2, 3, 3), (2, 30, 30), (2, 30, 3000), (4, 30, 3000)):
        inst, v = lb_clock_flat(k, L, theta)
        nv += report_inst(out, "clock flat", inst, v, k, L, INF, 1, UN, theta + L - 1, theta)[2]
    out.write("-- UN, delta = INF, on the paper's S8.3 cascade: theta = (victim age at its last overtaker's\n")
    out.write("   dispatch when the clock is off) + 1, so the clock does not change the victim's overtakers\n")
    for k, m in ((2, 6), (2, 8), (3, 5)):
        inst, v, L, f, B = lb_paper(k, m)
        for j in range(len(inst.d)):
            inst.d[j] = INF
        age = report_inst(out, f"S8.3 clock off m={m}", inst, v, k, L, INF, B, UN, None, INF)[3]
        nv += report_inst(out, f"S8.3 clock on m={m}", inst, v, k, L, INF, B, UN, None, age + 1)[2]
    out.write(f"   lower-bound instances: total violations {nv}\n\n")
    return nv


def main():
    out = sys.stdout
    nmax = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    if len(sys.argv) > 2 and sys.argv[2] == "exhaustive":
        # resume mode: the lower-bound and random sections were already written by an earlier run
        t0 = time.time()
        _, viol_e, _ = run_exhaustive(out, nmax)
        out.write(f"SUMMARY exhaustive-only run: violations {int(viol_e.sum())}; wall {time.time() - t0:.0f} s\n")
        return
    out.write("sim_stale.py: guard with late charges (derivation.md)\n")
    out.write("bounds checked:  U  k*excess < B + (3k-2)L + k(L+delta)       In < B + kL + k(L+delta)\n")
    out.write("                 A1 k*excess < B + (3k-2)L                    In < B + kL\n")
    out.write("                 A2 k*excess < B + (3k-2)L + (k-1)(L+delta)   In < B + kL + (k-1)(L+delta)\n")
    out.write("                 UN k*excess < k*theta + (3k-2)L              In < k(theta+L), every delta incl. INF\n")
    out.write("                    (and the U bounds as well when delta is finite)\n")
    out.write("                 every model at delta = 0: Theorem 3 of the paper\n\n")
    t0 = time.time()
    nv_lb = run_lower_bounds(out)
    out.flush()
    _, viol_r, _ = run_random(out)
    out.flush()
    _, viol_e, _ = run_exhaustive(out, nmax)
    out.write(
        f"SUMMARY violations: lower-bound instances {nv_lb}, random {int(viol_r.sum())}, exhaustive {int(viol_e.sum())};"
        f" wall {time.time() - t0:.0f} s\n"
    )


if __name__ == "__main__":
    main()
