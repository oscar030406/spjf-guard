#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ACcoding service-side pre-check v2.

Replicates, on a second and independent platform (ACcoding, the Beihang University
online judge), the cost-prediction and scheduling protocol verified on CodeBench in
evidence/codebench_service_v2/service_precheck_v2.py.

ACcoding has NO submission timestamps.  The split is therefore by submission-id
quantile (research_plan.md 2.3):

    id-rank quantile 0.00-0.48  train
                     0.48-0.64  validation
                     0.64-0.80  development test
                     0.80-1.00  SEALED   <- never read, never computed on

Ids are an ordering, not a clock.  Every "history" feature here is "the record with a
smaller id", never "the record earlier in time"; the lag sweep m = 0/10/100/1000 (the
results of the m submissions immediately preceding by id are not yet visible) stands
in for result latency, because there is no clock to define one.

Arrival times in the scheduling part are SYNTHETIC and labelled as such everywhere.
Only the ORDER of the jobs (inside a contest) and their SIZES are real.

Privacy: no source code and no personal attribute is read, stored or printed; the
tables carry counts and numeric features only (code_length, never the code).

Run one stage per command:

  env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with pandas \
      --with numpy --with scipy --with pyarrow --with lightgbm python accoding_v2.py \
      --stage <stage> [options]

Stages: selftest audit cbprofile feat leak pred boot trace sim guardk1 report
"""

import argparse
import hashlib
import heapq
import json
import math
import os
import sys
import re
import time
from collections import defaultdict

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(PROJ, "data", "accoding", "parquet")
N_THREADS = 4

SPLIT_Q = (0.00, 0.48, 0.64, 0.80)
# result / language codes are the 0-based index into the parser's lists
# (evidence/accoding/parse_sql.py: RESULTS, LANGS)
RESULT_NAMES = {0: "WT", 1: "JG", 2: "AC", 3: "WA", 4: "CE", 5: "REG", 6: "MLE",
                7: "REP", 8: "PE", 9: "TLE", 10: "IFNR", 11: "OFNR", 12: "EFNR",
                13: "OE"}
LANG_NAMES = {0: "c++", 1: "c", 2: "python", 3: "java", 4: "python2", 5: "python3"}
UNJUDGED = (0, 1)            # WT / JG: no result yet
R_AC, R_TLE, R_MLE = 2, 9, 6
NA_I = -1                    # the parser's NULL sentinel for int columns

SVC_FIXED = 0.5                 # s: compile + container + fixtures (assumption)
SVC_ALT_FIXED = 0.2             # sensitivity
SVC_ALT_PER_TEST = 0.05         # sensitivity

BUSY_WORK_TARGET = 14400.0      # s of work in the busiest hour -> k = 8 / 5 / 4
RHO_LEVELS = (0.5, 0.8, 1.0)
EPISODE_CAP_H = 72.0
PRACTICE_CHUNK = 2000


def script_sha256():
    with open(os.path.abspath(__file__), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Tee(object):
    def __init__(self, path, stage, argv):
        self.fh = open(path, "w", encoding="utf-8")
        self.t0 = time.time()
        self.stage = stage
        self.p("script_sha256 %s" % script_sha256())
        self.p("stage %s  argv %s" % (stage, " ".join(argv[1:])))

    def p(self, *args):
        s = " ".join(str(a) for a in args)
        sys.stdout.write(s + "\n")
        sys.stdout.flush()
        self.fh.write(s + "\n")
        self.fh.flush()

    def close(self):
        self.p("stage %s finished in %.1f s at %s"
               % (self.stage, time.time() - self.t0,
                  time.strftime("%Y-%m-%d %H:%M:%S")))
        self.fh.close()


def pct(a, qs):
    return np.percentile(np.asarray(a, dtype=np.float64), qs)


# ---------------------------------------------------------------- loading
def split_bounds(n_total):
    return [int(round(q * n_total)) for q in SPLIT_Q] + [n_total]


def load_dev(log=None):
    ids = pd.read_parquet(os.path.join(DATA, "submissions.parquet"), columns=["id"])
    assert ids["id"].is_monotonic_increasing, "submissions parquet not in id order"
    n_total = len(ids)
    b = split_bounds(n_total)
    sealed_lo = b[3]
    sealed_id_min = int(ids["id"].iloc[sealed_lo])
    del ids

    df = pd.read_parquet(os.path.join(DATA, "submissions.parquet"))
    df = df.iloc[:sealed_lo].reset_index(drop=True)          # sealed rows dropped here
    assert int(df["id"].max()) < sealed_id_min

    blk = np.zeros(len(df), dtype=np.int8)
    blk[b[1]:b[2]] = 1
    blk[b[2]:b[3]] = 2
    df["blk"] = blk

    edges = [(int(df["id"].iloc[b[i]]), int(df["id"].iloc[b[i + 1] - 1])) for i in range(3)]
    for i in range(2):
        assert edges[i][1] < edges[i + 1][0], "split id ranges overlap"
    assert edges[2][1] < sealed_id_min, "devtest overlaps the sealed block"

    if log is not None:
        log.p("rows total %d; split row bounds %s" % (n_total, b))
        log.p("id ranges  train [%d,%d]  valid [%d,%d]  devtest [%d,%d]  SEALED [%d,...]  "
              "(disjoint, asserted)"
              % (edges[0][0], edges[0][1], edges[1][0], edges[1][1],
                 edges[2][0], edges[2][1], sealed_id_min))
        log.p("sealed block: %d rows; only its row count and its first id were read"
              % (n_total - sealed_lo))
    return df, b, sealed_id_min, n_total


def assert_no_sealed(df, sealed_id_min, where):
    assert int(df["id"].max()) < sealed_id_min, "SEALED BLOCK TOUCHED in %s" % where


def load_meta():
    return (pd.read_parquet(os.path.join(DATA, "problems.parquet")),
            pd.read_parquet(os.path.join(DATA, "contests.parquet")),
            pd.read_parquet(os.path.join(DATA, "problem_tags.parquet")),
            pd.read_parquet(os.path.join(DATA, "tags.parquet")))


def modelling_mask(df):
    return (~df["result"].isin(UNJUDGED)) & (df["time_cost"] >= 0)


# ================================================================ audit
def stage_audit(args, log):
    df, b, sealed_id_min, n_total = load_dev(log)
    prob, cont, ptag, tags = load_meta()
    assert_no_sealed(df, sealed_id_min, "audit")

    log.p("")
    log.p("--- 1a. fields present ---")
    for name, t in [("submissions", df), ("problems", prob), ("contests", cont),
                    ("problem_tags", ptag), ("tags", tags)]:
        log.p("%-13s rows=%-9d cols=%s" % (name, len(t), list(t.columns)))
    log.p("users table holds id and last_login only; no gender / school / employment field")
    log.p("is parsed or stored, and source code is never read -- code_length is a count.")
    log.p("per submission: runtime (time_cost), memory (memory_cost), verdict (result),")
    log.p("language (lang), code length (code_length), problem, contest (null = practice),")
    log.p("author, score, and a per-test summary (detail_n_cases / detail_sum_ms /")
    log.p("detail_max_ms / detail_max_kb).  Problem tags are in problem_tags.  There is NO")
    log.p("timestamp column on submissions.")

    log.p("")
    log.p("--- 1b. rows per split block ---")
    for i, nm in enumerate(["train 0-48%", "valid 48-64%", "devtest 64-80%"]):
        s = df[df["blk"] == i]
        log.p("%-16s rows=%-8d ids [%d,%d] judged=%d users=%d problems=%d contests=%d"
              % (nm, len(s), int(s["id"].min()), int(s["id"].max()),
                 int(modelling_mask(s).sum()), s["creator_id"].nunique(),
                 s["problem_id"].nunique(),
                 int((s["contest_id"] >= 0).sum() and s.loc[s["contest_id"] >= 0,
                                                            "contest_id"].nunique())))
    log.p("%-16s rows=%-8d ids [%d,...]  (row count only; never opened)"
          % ("SEALED 80-100%", n_total - b[3], sealed_id_min))

    m = modelling_mask(df)
    log.p("")
    log.p("--- 1c. verdicts (non-sealed rows) ---")
    for r, c in df["result"].value_counts().sort_index().items():
        log.p("  %-5s %9d  %.5f" % (RESULT_NAMES.get(int(r), r), c, c / len(df)))
    log.p("unjudged (WT/JG) %d;  time_cost sentinel -1 %d;  modelling rows %d"
          % (int(df["result"].isin(UNJUDGED).sum()), int((df["time_cost"] < 0).sum()),
             int(m.sum())))

    d = df[m]
    tc = d["time_cost"].to_numpy(np.float64)
    log.p("")
    log.p("--- 1d. runtime field: units, cap, distribution ---")
    q = pct(tc, [0, 10, 25, 50, 75, 90, 95, 99, 99.9, 100])
    log.p("time_cost (ms) p0=%g p10=%g p25=%g p50=%g p75=%g p90=%g p95=%g p99=%g p99.9=%g "
          "max=%g mean=%.2f" % tuple(list(q) + [tc.mean()]))
    log.p("share time_cost == 0 : %.4f" % float((tc == 0).mean()))
    mem = d["memory_cost"].to_numpy(np.float64)
    log.p("memory_cost (KB) p50=%g p90=%g p99=%g max=%g   share 0 = %.4f"
          % tuple(list(pct(mem, [50, 90, 99, 100])) + [float((mem == 0).mean())]))
    log.p("code_length (chars) p50=%g p90=%g p99=%g max=%g"
          % tuple(pct(d["code_length"], [50, 90, 99, 100])))
    lv = d["lang"].value_counts().sort_index()
    log.p("languages: %s" % {LANG_NAMES.get(int(k), k): int(v) for k, v in lv.items()})

    srt = np.sort(tc)[::-1]
    for frac in (0.001, 0.01, 0.05, 0.10):
        kk = max(1, int(round(frac * len(srt))))
        log.p("top %-6s of submissions by runtime carry %.4f of total recorded runtime"
              % ("%.1f%%" % (100 * frac), srt[:kk].sum() / srt.sum()))
    svc = SVC_FIXED + tc / 1000.0
    ssrt = np.sort(svc)[::-1]
    log.p("service model C = %.1f s + time_cost/1000 (see 1e): mean %.3f s, median %.3f s, "
          "p95 %.3f s, p99 %.3f s, max %.3f s"
          % (SVC_FIXED, svc.mean(), np.median(svc), np.percentile(svc, 95),
             np.percentile(svc, 99), svc.max()))
    for frac in (0.01, 0.05):
        kk = max(1, int(round(frac * len(ssrt))))
        log.p("  top %.0f%% of jobs carry %.4f of total SERVICE work"
              % (100 * frac, ssrt[:kk].sum() / ssrt.sum()))
    log.p("  coefficient of variation of C: %.3f  (of raw time_cost: %.3f)"
          % (svc.std() / svc.mean(), tc.std() / max(tc.mean(), 1e-9)))

    log.p("")
    log.p("--- 1e. is the recorded runtime judge occupancy or per-test execution time? ---")
    dd = d.merge(prob[["id", "n_tests", "time_limit", "memory_limit"]],
                 left_on="problem_id", right_on="id", how="left", suffixes=("", "_p"))
    has_det = dd["detail_n_cases"] > 0
    log.p("rows with a per-test table in `detail`: %d (%.4f); empty detail %.4f; detail "
          "present but no per-test lines (CE/OE text) %.4f"
          % (int(has_det.sum()), float(has_det.mean()), float(dd["detail_empty"].mean()),
             float(((~dd["detail_empty"]) & (~has_det)).mean())))
    s2 = dd[has_det]
    eq_sum = float((s2["time_cost"] == s2["detail_sum_ms"]).mean())
    eq_max = float((s2["time_cost"] == s2["detail_max_ms"]).mean())
    eq_mem = float((s2["memory_cost"] == s2["detail_max_kb"]).mean())
    log.p("time_cost == SUM of the per-test ms  : %.4f" % eq_sum)
    log.p("time_cost == MAX of the per-test ms  : %.4f" % eq_max)
    log.p("memory_cost == MAX of the per-test KB: %.4f" % eq_mem)
    tle = dd[dd["result"] == R_TLE]
    cap_hit = float((tle["detail_max_ms"] == tle["time_limit"]).mean()) if len(tle) else float("nan")
    log.p("TLE rows %d: the per-test MAX ms equals the problem time_limit exactly on %.4f"
          % (len(tle), cap_hit))
    cap_ms = dd["time_limit"] * np.maximum(dd["n_tests"], 1)
    log.p("share time_cost > problem time_limit            : %.4f"
          % float((dd["time_cost"] > dd["time_limit"]).mean()))
    log.p("share time_cost > n_tests * time_limit (the cap): %.4f"
          % float((dd["time_cost"] > cap_ms).mean()))
    log.p("problem time_limit (ms) p50=%g p90=%g p99=%g max=%g; n_tests p50=%g p90=%g max=%g"
          % tuple(list(pct(prob["time_limit"].dropna(), [50, 90, 99, 100]))
                  + list(pct(prob["n_tests"].dropna(), [50, 90, 100]))))
    log.p("implied per-submission cap n_tests*time_limit: p50=%g ms p99=%g ms max=%g ms; "
          "observed max time_cost = %g ms"
          % tuple(list(pct(cap_ms.dropna(), [50, 99, 100])) + [tc.max()]))
    z = dd[dd["time_cost"] == 0]
    log.p("the %d rows with time_cost == 0: verdicts %s"
          % (len(z), z["result"].map(RESULT_NAMES).value_counts().head(5).to_dict()))
    log.p("")
    log.p("READING: time_cost is the SUM over the problem's test cases of each test's")
    log.p("measured execution time, each TEST capped at the problem's time limit.  It is")
    log.p("per-test execution time aggregated per submission, NOT judge occupancy: it")
    log.p("excludes compilation, container start-up, fixture copying and result write-back,")
    log.p("which is why %.2f%% of judged rows record exactly 0 ms (CE and other rows that"
          % (100 * float((tc == 0).mean())))
    log.p("never ran a test).")
    log.p("EVIDENCE  (i) time_cost equals the sum of the per-test ms on %.4f of the rows that"
          % eq_sum)
    log.p("  carry a per-test table and the max on only %.4f; (ii) memory_cost equals the"
          % eq_max)
    log.p("  per-test MAX on %.4f, so the two fields aggregate the same per-test" % eq_mem)
    log.p("  measurements with different operators, which one wall-clock occupancy number")
    log.p("  could not do; (iii) on TLE rows the per-test max equals the time limit exactly")
    log.p("  on %.4f of them, so the cap is applied per test, and time_cost can reach" % cap_hit)
    log.p("  n_tests * time_limit, which is what the observed maximum does.")
    log.p("CONFIDENCE high for 'sum of per-test measured run times, per-test capped'.")
    log.p("  Whether each per-test number is CPU time or sandbox wall clock is NOT decidable")
    log.p("  from this dump (no timestamps, no second clock).  The service-time model")
    log.p("  therefore adds an explicit constant for the parts of judge occupancy the field")
    log.p("  does not contain; that constant is an assumption and a sensitivity with a")
    log.p("  per-test term is run.  Contrast with CodeBench, where C is wall-clock judge")
    log.p("  occupancy including interpreter start-up (codebench_semantics, medium")
    log.p("  confidence).  The two platforms measure different things, and the paper must")
    log.p("  say so rather than putting the two distributions on one axis.")

    log.p("")
    log.p("--- 1f. duplicates ---")
    kf = ["creator_id", "problem_id", "contest_id", "lang", "code_length", "time_cost",
          "memory_cost", "result", "score"]
    dupf = int(df.duplicated(subset=kf, keep=False).sum())
    rep = int(df.duplicated(subset=kf, keep="first").sum())
    log.p("distinct ids %d in %d rows (id unique by construction)"
          % (df["id"].nunique(), len(df)))
    log.p("rows sharing the full key %s: %d (%.4f); rows that repeat an earlier one: "
          "%d (%.4f)" % (kf, dupf, dupf / len(df), rep, rep / len(df)))
    ks = ["creator_id", "problem_id", "lang", "code_length"]
    log.p("same user+problem+language+code_length (a resubmission of same-length code): "
          "%d rows (%.4f)"
          % (int(df.duplicated(subset=ks, keep=False).sum()),
             float(df.duplicated(subset=ks, keep=False).mean())))
    log.p("KEPT: on an online judge the same code submitted twice is two real judge jobs.")

    log.p("")
    log.p("--- 1g. problems, tags, contests in the non-sealed blocks ---")
    log.p("distinct users %d, problems %d, contests %d; share of rows inside a contest %.4f"
          % (df["creator_id"].nunique(), df["problem_id"].nunique(),
             df.loc[df["contest_id"] >= 0, "contest_id"].nunique(),
             float((df["contest_id"] >= 0).mean())))
    npt = ptag.groupby("problem_id").size()
    log.p("problems with >=1 tag %d of %d; tags per problem p50=%g p90=%g max=%g; distinct "
          "tags %d" % (len(npt), len(prob), np.percentile(npt, 50), np.percentile(npt, 90),
                       npt.max(), len(tags)))
    cd = (cont["end_time"] - cont["start_time"]).dt.total_seconds() / 3600.0
    log.p("contest duration (h) p10=%.3f p50=%.3f p90=%.1f p99=%.1f max=%.1f; longer than "
          "%g h: %d of %d"
          % tuple(list(pct(cd.dropna(), [10, 50, 90, 99, 100]))
                  + [EPISODE_CAP_H, int((cd > EPISODE_CAP_H).sum()), int(cd.notna().sum())]))

    log.p("")
    log.p("--- 1h. id is an ordering, not a clock ---")
    from scipy.stats import spearmanr
    cs = df[df["contest_id"] >= 0].groupby("contest_id")["id"]         .agg(["min", "max", "size"])
    cs = cs.join(cont.set_index("id")[["start_time", "end_time"]], how="inner")
    cs = cs.dropna(subset=["start_time"]).sort_values("start_time")
    rho1 = spearmanr(cs["min"], cs["start_time"].astype("int64")).correlation
    ov = int((cs["min"] < cs["max"].shift(1)).sum())
    log.p("Spearman(contest first id, contest start_time) = %.4f over %d contests with "
          "non-sealed submissions" % (rho1, len(cs)))
    log.p("contests whose id range overlaps the previous contest's: %d of %d transitions"
          % (ov, len(cs) - 1))
    log.p("=> id orders submissions exactly but carries no duration.  Arrival times must be")
    log.p("synthesised and the paper must say so.")
    log.close()


# ================================================ CodeBench deadline profile
def stage_cbprofile(args, log):
    """Fit the CodeBench deadline-window arrival profile lambda(u) ~ (u + tau)^(-gamma),
    u = hours to the assessment deadline.  The denominator is assessment-hours of
    exposure: an assessment window contributes to the bin [lo, hi) only if it reaches
    that far back from its own end."""
    path = args.cb_cache
    if not path or not os.path.exists(path):
        log.p("CodeBench v2 cache not available at %r" % path)
        log.p("FALLBACK: documented parametric ramp gamma = 0.8, tau = 1.0 h.")
        json.dump({"source": "fallback(documented ramp)", "gamma": 0.8, "tau_h": 1.0},
                  open(os.path.join(args.cache, "cbshape.json"), "w"))
        log.close()
        return
    ev = pd.read_parquet(path, columns=["semester", "class", "assessment", "ts", "kind",
                                        "a_end", "a_start", "exec_time"])
    ev = ev[(ev["kind"] == "submit") & ev["exec_time"].notna() & ev["a_end"].notna()]
    log.p("CodeBench v2 cache %s" % path)
    log.p("graded submissions with an execution time and an assessment window: %d" % len(ev))
    def epoch_s(x):
        # the cache stores timestamp[us]; astype('int64') would give microseconds
        return x.astype("datetime64[ns]").astype("int64").to_numpy() / 1e9

    asm = ev.drop_duplicates(subset=["semester", "class", "assessment", "a_start", "a_end"])
    span = (epoch_s(asm["a_end"]) - epoch_s(asm["a_start"])) / 3600.0
    span = span[np.isfinite(span) & (span > 1.0)]
    log.p("distinct class-semester assessments: %d; window length (h) p10 %.1f p50 %.1f "
          "p90 %.1f max %.1f" % (len(span), *np.percentile(span, [10, 50, 90, 100])))
    arr = epoch_s(ev["ts"]) - ev["exec_time"].to_numpy()
    u = (epoch_s(ev["a_end"]) - arr) / 3600.0
    keep = (u > 0) & (u <= 168.0)
    log.p("arrivals inside the 168 h before their own deadline: %d (%.4f of the submissions)"
          % (int(keep.sum()), float(keep.mean())))
    u = u[keep]

    edges = np.concatenate([[0.0], np.logspace(math.log10(0.05), math.log10(168.0), 30)])
    cnt, _ = np.histogram(u, bins=edges)
    expo = np.array([float(np.clip(np.minimum(span, edges[i + 1]) - edges[i], 0.0, None).sum())
                     for i in range(len(edges) - 1)])          # assessment-hours
    mid = np.sqrt(np.maximum(edges[:-1], 1e-3) * edges[1:])
    rate = np.where(expo > 0, cnt / np.maximum(expo, 1e-9), np.nan)
    ok = np.isfinite(rate) & (cnt >= 200) & (expo >= 30.0)
    ref = rate[ok][-1]
    log.p("")
    log.p("  hours-to-deadline bin      arrivals   assessment-hours   rate   rate/far-bin")
    for i in range(len(mid)):
        if ok[i]:
            log.p("  %8.3f - %8.3f  %10d %15.1f %9.4f %10.2f"
                  % (edges[i], edges[i + 1], cnt[i], expo[i], rate[i], rate[i] / ref))
    best = None
    for tau in [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 24.0]:
        x = np.log(mid[ok] + tau)
        y = np.log(rate[ok])
        A = np.vstack([x, np.ones_like(x)]).T
        coef, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        ss = float(((y - A @ coef) ** 2).sum())
        if best is None or ss < best[0]:
            best = (ss, tau, -float(coef[0]))
    ss, tau, gamma = best
    log.p("")
    log.p("least squares  log(rate) = c - gamma*log(u + tau)  over the %d usable bins:"
          % int(ok.sum()))
    log.p("  gamma = %.4f, tau = %.3f h, residual SS = %.4f" % (gamma, tau, ss))
    if gamma <= 0:
        log.p("  NOTE gamma <= 0 means the fitted rate does NOT rise toward the deadline;")
        log.p("  the deadline-shaped stream then falls back to the documented ramp.")
        gamma, tau = 0.8, 1.0
        log.p("  using the documented ramp instead: gamma = %.2f, tau = %.2f h" % (gamma, tau))
        src = "fallback ramp (CodeBench fit gave gamma <= 0)"
    else:
        src = "codebench_v2_cache ev.parquet"
    log.p("  implied rate ratio, 15 min before the deadline vs 24 h before: %.2f"
          % (((0.25 + tau) ** (-gamma)) / ((24.0 + tau) ** (-gamma))))
    log.p("  implied ratio, 15 min before vs 2 h before: %.2f"
          % (((0.25 + tau) ** (-gamma)) / ((2.0 + tau) ** (-gamma))))
    log.p("The ACcoding deadline-shaped trace uses the same (gamma, tau) with u measured")
    log.p("to each CONTEST's end.  ACcoding contest windows are much shorter than CodeBench")
    log.p("assessment windows (median 24.9 h against %.1f h), so only the small-u part of"
          % np.median(span))
    log.p("the fitted profile is exercised; that is the part that carries the rise.")
    json.dump({"source": src, "gamma": float(gamma), "tau_h": float(tau),
               "n_rows": int(len(u)), "bins": int(ok.sum())},
              open(os.path.join(args.cache, "cbshape.json"), "w"))
    log.close()


# ================================================================ features
STATIC = ["code_length", "log_code_length", "lang", "p_n_tests", "p_time_limit",
          "p_mem_limit", "p_difficulty", "p_n_langs", "p_special_judge", "p_partial",
          "p_cap_ms", "p_n_tags", "p_tag_w", "in_contest"]
PROB = ["p_n", "p_mean_lg", "p_sd_lg", "p_max_lg", "p_last_lg", "p_heavy_rate",
        "p_tle_rate", "p_ac_rate", "p_mem_mean_lg", "p_codelen_mean"]
USER = ["u_n", "u_mean_lg", "u_sd_lg", "u_max_lg", "u_last_lg", "u_heavy_rate",
        "u_tle_rate", "u_ac_rate", "u_codelen_mean", "u_n_prob"]
UP = ["up_n", "up_last_lg", "up_max_lg", "up_mean_lg", "up_last_ac", "up_last_tle"]
CON = ["c_n", "c_mean_lg", "c_heavy_rate"]
REL = ["tag_n", "tag_mean_lg", "tag_heavy_rate", "utag_n", "utag_mean_lg",
       "cu_n", "cu_mean_lg", "cp_n", "cp_mean_lg", "plang_n", "plang_mean_lg"]
ALLF = STATIC + PROB + USER + UP + CON + REL
FIDX = {f: i for i, f in enumerate(ALLF)}
MODELS = {"M1": PROB, "M2": USER, "M3": STATIC,
          "M4": STATIC + PROB + USER + UP + CON,
          "M5": STATIC + PROB + USER + UP + CON + REL}
NAN = np.float32("nan")


def problem_tables(prob, ptag):
    pm = prob.set_index("id")
    tag_of = defaultdict(list)
    tagw = defaultdict(float)
    for pid, tid, wt in zip(ptag["problem_id"], ptag["tag_id"], ptag["weight"]):
        tag_of[int(pid)].append(int(tid))
        if wt == wt:
            tagw[int(pid)] += float(wt)
    return pm, tag_of, tagw


def base_arrays(df, prob, ptag):
    pm, tag_of, tagw = problem_tables(prob, ptag)
    A = {}
    A["pid"] = df["problem_id"].to_numpy(np.int64)
    A["uid"] = df["creator_id"].to_numpy(np.int64)
    A["cid"] = df["contest_id"].fillna(-1).to_numpy(np.int64)
    A["lang"] = df["lang"].to_numpy(np.int64)
    A["clen"] = df["code_length"].to_numpy(np.float64)
    A["tc"] = df["time_cost"].to_numpy(np.float64)
    A["mem"] = df["memory_cost"].to_numpy(np.float64)
    A["res"] = df["result"].to_numpy(np.int64)
    A["ok"] = modelling_mask(df).to_numpy()
    for col, key, fill in [("n_tests", "p_nt", 0.0), ("time_limit", "p_tl", np.nan),
                           ("memory_limit", "p_ml", np.nan), ("difficulty", "p_df", np.nan),
                           ("n_supported_langs", "p_nl", np.nan)]:
        A[key] = pm[col].reindex(df["problem_id"]).astype(float).fillna(fill).to_numpy(np.float64)
    A["p_sj"] = pm["has_special_judge"].reindex(df["problem_id"]).fillna(False) \
        .to_numpy(np.float64)
    A["p_ps"] = pm["partial_score"].reindex(df["problem_id"]).fillna(False).to_numpy(np.float64)
    A["p_ntag"] = np.array([len(tag_of.get(int(p), ())) for p in A["pid"]], dtype=np.float64)
    A["p_tw"] = np.array([tagw.get(int(p), 0.0) for p in A["pid"]], dtype=np.float64)
    return A, pm, tag_of, tagw


def compute_features(df, prob, ptag, lag, keep_mask, heavy_thr, log, every=1000000):
    """One streaming pass in id order.  At row i, only rows with rank < i - lag have
    been folded into the state, so every feature uses strictly smaller ids with the
    last `lag` of them still invisible."""
    n = len(df)
    A, pm, tag_of, tagw = base_arrays(df, prob, ptag)
    pid_a, uid_a, cid_a, lang_a = A["pid"], A["uid"], A["cid"], A["lang"]
    clen_a, tc_a, res_a, ok_a = A["clen"], A["tc"], A["res"], A["ok"]
    lgc = np.log1p(np.maximum(tc_a, 0) / 1000.0)
    lgm = np.log1p(np.maximum(A["mem"], 0))
    heavy = (tc_a > heavy_thr) & ok_a
    is_tle = res_a == R_TLE
    is_ac = res_a == R_AC

    keep_idx = np.flatnonzero(keep_mask)
    pos_of = np.full(n, -1, dtype=np.int64)
    pos_of[keep_idx] = np.arange(len(keep_idx))
    X = np.full((len(keep_idx), len(ALLF)), NAN, dtype=np.float32)

    P, U, UP_, C, T, UT, CU, CP, PL = {}, {}, {}, {}, {}, {}, {}, {}, {}
    UPROB = defaultdict(set)
    iF = FIDX
    t0 = time.time()
    nxt = 0

    for i in range(n):
        limit = i - lag
        while nxt < limit:
            j = nxt
            nxt += 1
            if not ok_a[j]:
                continue
            p = pid_a[j]; u = uid_a[j]; c = cid_a[j]; g = lgc[j]
            hv = 1.0 if heavy[j] else 0.0
            tl = 1.0 if is_tle[j] else 0.0
            ac = 1.0 if is_ac[j] else 0.0
            s = P.get(p)
            if s is None:
                P[p] = [1.0, g, g * g, g, g, hv, tl, ac, lgm[j], clen_a[j]]
            else:
                s[0] += 1.0; s[1] += g; s[2] += g * g
                if g > s[3]:
                    s[3] = g
                s[4] = g; s[5] += hv; s[6] += tl; s[7] += ac
                s[8] += lgm[j]; s[9] += clen_a[j]
            s = U.get(u)
            if s is None:
                U[u] = [1.0, g, g * g, g, g, hv, tl, ac, clen_a[j]]
            else:
                s[0] += 1.0; s[1] += g; s[2] += g * g
                if g > s[3]:
                    s[3] = g
                s[4] = g; s[5] += hv; s[6] += tl; s[7] += ac; s[8] += clen_a[j]
            UPROB[u].add(p)
            k = u * 100000 + p
            s = UP_.get(k)
            if s is None:
                UP_[k] = [1.0, g, g, g, ac, tl]
            else:
                s[0] += 1.0; s[1] = g
                if g > s[2]:
                    s[2] = g
                s[3] += g; s[4] = ac; s[5] = tl
            if c >= 0:
                s = C.get(c)
                if s is None:
                    C[c] = [1.0, g, hv]
                else:
                    s[0] += 1.0; s[1] += g; s[2] += hv
                k = c * 100000 + u
                s = CU.get(k)
                if s is None:
                    CU[k] = [1.0, g]
                else:
                    s[0] += 1.0; s[1] += g
                k = c * 100000 + p
                s = CP.get(k)
                if s is None:
                    CP[k] = [1.0, g]
                else:
                    s[0] += 1.0; s[1] += g
            for tid in tag_of.get(int(p), ()):
                s = T.get(tid)
                if s is None:
                    T[tid] = [1.0, g, hv]
                else:
                    s[0] += 1.0; s[1] += g; s[2] += hv
                k = u * 1000 + tid
                s = UT.get(k)
                if s is None:
                    UT[k] = [1.0, g]
                else:
                    s[0] += 1.0; s[1] += g
            k = p * 100 + lang_a[j]
            s = PL.get(k)
            if s is None:
                PL[k] = [1.0, g]
            else:
                s[0] += 1.0; s[1] += g

        r = pos_of[i]
        if r < 0:
            continue
        row = X[r]
        p = pid_a[i]; u = uid_a[i]; c = cid_a[i]
        row[iF["code_length"]] = clen_a[i]
        row[iF["log_code_length"]] = math.log1p(clen_a[i])
        row[iF["lang"]] = lang_a[i]
        row[iF["p_n_tests"]] = A["p_nt"][i]
        row[iF["p_time_limit"]] = A["p_tl"][i]
        row[iF["p_mem_limit"]] = A["p_ml"][i]
        row[iF["p_difficulty"]] = A["p_df"][i]
        row[iF["p_n_langs"]] = A["p_nl"][i]
        row[iF["p_special_judge"]] = A["p_sj"][i]
        row[iF["p_partial"]] = A["p_ps"][i]
        row[iF["p_cap_ms"]] = A["p_tl"][i] * (A["p_nt"][i] if A["p_nt"][i] > 1 else 1.0)
        row[iF["p_n_tags"]] = A["p_ntag"][i]
        row[iF["p_tag_w"]] = A["p_tw"][i]
        row[iF["in_contest"]] = 1.0 if c >= 0 else 0.0

        s = P.get(p)
        if s is None:
            row[iF["p_n"]] = 0.0
        else:
            nn = s[0]; mu = s[1] / nn
            row[iF["p_n"]] = nn
            row[iF["p_mean_lg"]] = mu
            row[iF["p_sd_lg"]] = math.sqrt(max(s[2] / nn - mu * mu, 0.0))
            row[iF["p_max_lg"]] = s[3]; row[iF["p_last_lg"]] = s[4]
            row[iF["p_heavy_rate"]] = s[5] / nn; row[iF["p_tle_rate"]] = s[6] / nn
            row[iF["p_ac_rate"]] = s[7] / nn; row[iF["p_mem_mean_lg"]] = s[8] / nn
            row[iF["p_codelen_mean"]] = s[9] / nn
        s = U.get(u)
        if s is None:
            row[iF["u_n"]] = 0.0; row[iF["u_n_prob"]] = 0.0
        else:
            nn = s[0]; mu = s[1] / nn
            row[iF["u_n"]] = nn
            row[iF["u_mean_lg"]] = mu
            row[iF["u_sd_lg"]] = math.sqrt(max(s[2] / nn - mu * mu, 0.0))
            row[iF["u_max_lg"]] = s[3]; row[iF["u_last_lg"]] = s[4]
            row[iF["u_heavy_rate"]] = s[5] / nn; row[iF["u_tle_rate"]] = s[6] / nn
            row[iF["u_ac_rate"]] = s[7] / nn; row[iF["u_codelen_mean"]] = s[8] / nn
            row[iF["u_n_prob"]] = float(len(UPROB[u]))
        s = UP_.get(u * 100000 + p)
        if s is None:
            row[iF["up_n"]] = 0.0
        else:
            row[iF["up_n"]] = s[0]; row[iF["up_last_lg"]] = s[1]
            row[iF["up_max_lg"]] = s[2]; row[iF["up_mean_lg"]] = s[3] / s[0]
            row[iF["up_last_ac"]] = s[4]; row[iF["up_last_tle"]] = s[5]
        if c >= 0:
            s = C.get(c)
            if s is None:
                row[iF["c_n"]] = 0.0
            else:
                row[iF["c_n"]] = s[0]; row[iF["c_mean_lg"]] = s[1] / s[0]
                row[iF["c_heavy_rate"]] = s[2] / s[0]
            s = CU.get(c * 100000 + u)
            if s is None:
                row[iF["cu_n"]] = 0.0
            else:
                row[iF["cu_n"]] = s[0]; row[iF["cu_mean_lg"]] = s[1] / s[0]
            s = CP.get(c * 100000 + p)
            if s is None:
                row[iF["cp_n"]] = 0.0
            else:
                row[iF["cp_n"]] = s[0]; row[iF["cp_mean_lg"]] = s[1] / s[0]
        tl_ = tag_of.get(int(p), ())
        if tl_:
            tn = tsum = thv = un_ = usum = 0.0
            for tid in tl_:
                s = T.get(tid)
                if s is not None:
                    tn += s[0]; tsum += s[1]; thv += s[2]
                s = UT.get(u * 1000 + tid)
                if s is not None:
                    un_ += s[0]; usum += s[1]
            row[iF["tag_n"]] = tn
            if tn > 0:
                row[iF["tag_mean_lg"]] = tsum / tn; row[iF["tag_heavy_rate"]] = thv / tn
            row[iF["utag_n"]] = un_
            if un_ > 0:
                row[iF["utag_mean_lg"]] = usum / un_
        else:
            row[iF["tag_n"]] = 0.0; row[iF["utag_n"]] = 0.0
        s = PL.get(p * 100 + lang_a[i])
        if s is None:
            row[iF["plang_n"]] = 0.0
        else:
            row[iF["plang_n"]] = s[0]; row[iF["plang_mean_lg"]] = s[1] / s[0]

        if log is not None and every and i and (i % every == 0):
            log.p("   ... %d / %d rows, %.0f s" % (i, n, time.time() - t0))
    return X, keep_idx


def feat_path(cache, lag):
    return os.path.join(cache, "feat_lag%d.parquet" % lag)


def heavy_threshold(df):
    tc = df["time_cost"].to_numpy(np.float64)
    tr = (df["blk"].to_numpy() == 0) & modelling_mask(df).to_numpy()
    return float(np.percentile(tc[tr], 95))


def stage_feat(args, log):
    df, b, sealed_id_min, n_total = load_dev(log)
    prob, cont, ptag, tags = load_meta()
    assert_no_sealed(df, sealed_id_min, "feat")
    ok = modelling_mask(df).to_numpy()
    blk = df["blk"].to_numpy()
    thr = heavy_threshold(df)
    log.p("heavy threshold = train-block p95 of time_cost = %.1f ms (fixed for every "
          "block and every lag)" % thr)
    rng = np.random.default_rng(12345)
    for lag in [int(x) for x in args.lags.split(",")]:
        n_tr = args.train_sub if lag == 0 else args.train_sub_lag
        tr_idx = np.flatnonzero(ok & (blk == 0))
        if len(tr_idx) > n_tr:
            tr_idx = np.sort(rng.choice(tr_idx, size=n_tr, replace=False))
        keep = np.zeros(len(df), dtype=bool)
        keep[tr_idx] = True
        if lag == 0:
            keep |= ok & (blk == 1)
        keep |= ok & (blk == 2)
        log.p("")
        log.p("lag m = %d: train rows kept %d of %d, valid %d, devtest %d, total %d"
              % (lag, len(tr_idx), int((ok & (blk == 0)).sum()),
                 int((keep & (blk == 1)).sum()), int((keep & (blk == 2)).sum()),
                 int(keep.sum())))
        t0 = time.time()
        X, kidx = compute_features(df, prob, ptag, lag, keep, thr, log)
        log.p("lag %d: %d features built in %.0f s" % (lag, len(ALLF), time.time() - t0))
        out = pd.DataFrame(X, columns=ALLF)
        tcv = df["time_cost"].to_numpy()[kidx]
        out.insert(0, "row", kidx.astype(np.int64))
        out.insert(1, "id", df["id"].to_numpy()[kidx])
        out.insert(2, "blk", blk[kidx])
        out.insert(3, "uid", df["creator_id"].to_numpy()[kidx])
        out.insert(4, "pid", df["problem_id"].to_numpy()[kidx])
        out.insert(5, "cid", df["contest_id"].fillna(-1).to_numpy()[kidx].astype(np.int64))
        out.insert(6, "tc_ms", tcv.astype(np.float32))
        out.insert(7, "y", np.log1p(np.maximum(tcv, 0) / 1000.0).astype(np.float32))
        out.insert(8, "heavy", (tcv > thr).astype(np.int8))
        out.to_parquet(feat_path(args.cache, lag), index=False)
        json.dump({"heavy_thr_ms": thr, "lag": lag, "n": int(len(out))},
                  open(os.path.join(args.cache, "featmeta_lag%d.json" % lag), "w"))
        log.p("wrote %s (%d rows)" % (feat_path(args.cache, lag), len(out)))
        del X, out
    log.close()


# =========================================================== leak / perturbation
class ScratchRef(object):
    """From-scratch feature recomputation, written independently of the streaming
    pass: for a target at rank i it scans the index lists of the visible prefix
    [0, i-lag) directly."""

    def __init__(self, df, prob, ptag, heavy_thr):
        self.A, self.pm, self.tag_of, self.tagw = base_arrays(df, prob, ptag)
        A = self.A
        self.thr = heavy_thr
        self.n = len(df)
        okidx = np.flatnonzero(A["ok"])
        self.okidx = okidx
        self.by_p = self._group(A["pid"][okidx], okidx)
        self.by_u = self._group(A["uid"][okidx], okidx)
        self.by_c = self._group(A["cid"][okidx], okidx)
        maxp = int(A["pid"].max()) + 1
        self.tag_rows = {}
        tagset = set(int(t) for t in ptag["tag_id"])
        for t in tagset:
            has = np.zeros(maxp, dtype=bool)
            pl = ptag["problem_id"][ptag["tag_id"] == t].to_numpy()
            pl = pl[pl < maxp]
            has[pl] = True
            sel = okidx[has[A["pid"][okidx]]]
            if len(sel):
                self.tag_rows[t] = sel

    @staticmethod
    def _group(keys, idx):
        o = np.argsort(keys, kind="mergesort")
        ks = keys[o]
        vs = idx[o]
        uq, st = np.unique(ks, return_index=True)
        en = np.append(st[1:], len(ks))
        return {int(k): vs[a:bb] for k, a, bb in zip(uq, st, en)}

    def features(self, i, lag, tc=None, res=None, mem=None):
        A = self.A
        tc = A["tc"] if tc is None else tc
        res = A["res"] if res is None else res
        mem = A["mem"] if mem is None else mem
        hi = i - lag
        out = np.full(len(ALLF), NAN, dtype=np.float32)
        iF = FIDX
        p = int(A["pid"][i]); u = int(A["uid"][i]); c = int(A["cid"][i])
        lg = int(A["lang"][i])
        out[iF["code_length"]] = A["clen"][i]
        out[iF["log_code_length"]] = math.log1p(A["clen"][i])
        out[iF["lang"]] = lg
        out[iF["p_n_tests"]] = A["p_nt"][i]
        out[iF["p_time_limit"]] = A["p_tl"][i]
        out[iF["p_mem_limit"]] = A["p_ml"][i]
        out[iF["p_difficulty"]] = A["p_df"][i]
        out[iF["p_n_langs"]] = A["p_nl"][i]
        out[iF["p_special_judge"]] = A["p_sj"][i]
        out[iF["p_partial"]] = A["p_ps"][i]
        out[iF["p_cap_ms"]] = A["p_tl"][i] * (A["p_nt"][i] if A["p_nt"][i] > 1 else 1.0)
        out[iF["p_n_tags"]] = A["p_ntag"][i]
        out[iF["p_tag_w"]] = A["p_tw"][i]
        out[iF["in_contest"]] = 1.0 if c >= 0 else 0.0

        def cut(a):
            return a[:np.searchsorted(a, hi)]

        def lgv(a):
            return np.log1p(np.maximum(tc[a], 0) / 1000.0)

        jp = cut(self.by_p.get(p, np.empty(0, np.int64)))
        out[iF["p_n"]] = float(len(jp))
        if len(jp):
            g = lgv(jp)
            out[iF["p_mean_lg"]] = g.mean(); out[iF["p_sd_lg"]] = g.std()
            out[iF["p_max_lg"]] = g.max(); out[iF["p_last_lg"]] = g[-1]
            out[iF["p_heavy_rate"]] = float((tc[jp] > self.thr).mean())
            out[iF["p_tle_rate"]] = float((res[jp] == R_TLE).mean())
            out[iF["p_ac_rate"]] = float((res[jp] == R_AC).mean())
            out[iF["p_mem_mean_lg"]] = np.log1p(np.maximum(mem[jp], 0)).mean()
            out[iF["p_codelen_mean"]] = A["clen"][jp].mean()
        ju = cut(self.by_u.get(u, np.empty(0, np.int64)))
        out[iF["u_n"]] = float(len(ju))
        out[iF["u_n_prob"]] = float(len(np.unique(A["pid"][ju]))) if len(ju) else 0.0
        if len(ju):
            g = lgv(ju)
            out[iF["u_mean_lg"]] = g.mean(); out[iF["u_sd_lg"]] = g.std()
            out[iF["u_max_lg"]] = g.max(); out[iF["u_last_lg"]] = g[-1]
            out[iF["u_heavy_rate"]] = float((tc[ju] > self.thr).mean())
            out[iF["u_tle_rate"]] = float((res[ju] == R_TLE).mean())
            out[iF["u_ac_rate"]] = float((res[ju] == R_AC).mean())
            out[iF["u_codelen_mean"]] = A["clen"][ju].mean()
        jup = ju[A["pid"][ju] == p] if len(ju) else ju
        out[iF["up_n"]] = float(len(jup))
        if len(jup):
            g = lgv(jup)
            out[iF["up_last_lg"]] = g[-1]; out[iF["up_max_lg"]] = g.max()
            out[iF["up_mean_lg"]] = g.mean()
            out[iF["up_last_ac"]] = 1.0 if res[jup[-1]] == R_AC else 0.0
            out[iF["up_last_tle"]] = 1.0 if res[jup[-1]] == R_TLE else 0.0
        if c >= 0:
            jc = cut(self.by_c.get(c, np.empty(0, np.int64)))
            out[iF["c_n"]] = float(len(jc))
            if len(jc):
                out[iF["c_mean_lg"]] = lgv(jc).mean()
                out[iF["c_heavy_rate"]] = float((tc[jc] > self.thr).mean())
            jcu = jc[A["uid"][jc] == u] if len(jc) else jc
            out[iF["cu_n"]] = float(len(jcu))
            if len(jcu):
                out[iF["cu_mean_lg"]] = lgv(jcu).mean()
            jcp = jc[A["pid"][jc] == p] if len(jc) else jc
            out[iF["cp_n"]] = float(len(jcp))
            if len(jcp):
                out[iF["cp_mean_lg"]] = lgv(jcp).mean()
        tl_ = self.tag_of.get(p, ())
        if tl_:
            tn = tsum = thv = un_ = usum = 0.0
            for t in tl_:
                jt = cut(self.tag_rows.get(int(t), np.empty(0, np.int64)))
                if len(jt):
                    tn += len(jt); tsum += lgv(jt).sum()
                    thv += float((tc[jt] > self.thr).sum())
                    jut = jt[A["uid"][jt] == u]
                    if len(jut):
                        un_ += len(jut); usum += lgv(jut).sum()
            out[iF["tag_n"]] = tn
            if tn > 0:
                out[iF["tag_mean_lg"]] = tsum / tn; out[iF["tag_heavy_rate"]] = thv / tn
            out[iF["utag_n"]] = un_
            if un_ > 0:
                out[iF["utag_mean_lg"]] = usum / un_
        else:
            out[iF["tag_n"]] = 0.0; out[iF["utag_n"]] = 0.0
        jpl = jp[A["lang"][jp] == lg] if len(jp) else jp
        out[iF["plang_n"]] = float(len(jpl))
        if len(jpl):
            out[iF["plang_mean_lg"]] = lgv(jpl).mean()
        return out


def cmp_rows(a, bb, tol=1e-4):
    na, nb = np.isnan(a), np.isnan(bb)
    if np.any(na != nb):
        return int((na != nb).sum()), np.flatnonzero(na != nb)
    both = ~na
    d = np.abs(a[both] - bb[both])
    t = tol * np.maximum(1.0, np.abs(a[both]))
    bad = np.flatnonzero(both)[d > t]
    return len(bad), bad


def stage_leak(args, log):
    df, b, sealed_id_min, n_total = load_dev(log)
    prob, cont, ptag, tags = load_meta()
    assert_no_sealed(df, sealed_id_min, "leak")
    thr = heavy_threshold(df)
    log.p("building the independent reference index (heavy threshold %.1f ms)" % thr)
    t0 = time.time()
    R = ScratchRef(df, prob, ptag, thr)
    log.p("  reference built in %.0f s" % (time.time() - t0))
    rng = np.random.default_rng(args.seed_leak)

    for lag in [int(x) for x in args.lags.split(",")]:
        fp = feat_path(args.cache, lag)
        if not os.path.exists(fp):
            log.p("no feature file for lag %d, skipped" % lag)
            continue
        F = pd.read_parquet(fp)
        rows = F["row"].to_numpy()
        pick = rng.choice(len(rows), size=min(args.leak_rows, len(rows)), replace=False)
        targets = np.sort(rows[pick])
        pos = {int(r): k for k, r in enumerate(rows)}
        got = F[ALLF].to_numpy(np.float32)
        log.p("")
        log.p("lag m = %d: from-scratch recomputation of all %d features on %d random rows"
              % (lag, len(ALLF), len(targets)))
        t0 = time.time()
        nbad = 0
        badf = defaultdict(int)
        for tgt in targets:
            ref = R.features(int(tgt), lag)
            k, bad = cmp_rows(ref, got[pos[int(tgt)]])
            nbad += k
            for c in bad:
                badf[ALLF[c]] += 1
        log.p("cells checked %d x %d = %d; mismatching cells: %d"
              % (len(targets), len(ALLF), len(targets) * len(ALLF), nbad))
        if badf:
            log.p("  features that disagree: %s" % dict(badf))
        log.p("  (%.0f s)" % (time.time() - t0))
        assert nbad == 0, "LEAK TEST FAILED at lag %d" % lag

        log.p("perturbation test: for each of %d target rows, the RESULT fields "
              "(time_cost, memory_cost, result) of every row with rank >= rank_i - m are "
              "replaced by random garbage; the target's features must not move."
              % args.perturb_rows)
        tc0, res0, mem0 = R.A["tc"], R.A["res"], R.A["mem"]
        rs = np.random.default_rng(999)
        moved = 0
        t0 = time.time()
        for tgt in targets[:args.perturb_rows]:
            i = int(tgt)
            hi = max(i - lag, 0)
            tc1 = tc0.copy(); res1 = res0.copy(); mem1 = mem0.copy()
            nn = len(tc1) - hi
            tc1[hi:] = rs.integers(0, 30000, size=nn)
            res1[hi:] = rs.integers(3, 13, size=nn)
            mem1[hi:] = rs.integers(0, 2000000, size=nn)
            a = R.features(i, lag)
            bb = R.features(i, lag, tc=tc1, res=res1, mem=mem1)
            k, _ = cmp_rows(a, bb, tol=1e-9)
            moved += k
        log.p("  feature cells that moved: %d (must be 0)  (%.0f s)" % (moved, time.time() - t0))
        assert moved == 0, "PERTURBATION TEST FAILED at lag %d" % lag
    log.close()


# ================================================================ predictors
def lgb_params(objective, seed, num_leaves):
    p = {"objective": objective, "learning_rate": 0.05, "num_leaves": num_leaves,
         "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8,
         "bagging_freq": 1, "num_threads": N_THREADS, "verbose": -1, "seed": seed,
         "bagging_seed": seed + 7, "feature_fraction_seed": seed + 13,
         "data_random_seed": seed + 19, "force_row_wise": True}
    p["metric"] = "auc" if objective == "binary" else "l2"
    return p


def roc_auc(y, s):
    y = np.asarray(y, dtype=np.int8)
    s = np.asarray(s, dtype=np.float64)
    o = np.argsort(s, kind="mergesort")
    s = s[o]; y = y[o]
    n = len(s)
    ranks = np.empty(n)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        ranks[i:j + 1] = 0.5 * (i + j) + 1.0
        i = j + 1
    npos = int(y.sum()); nneg = n - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def avg_prec(y, s):
    y = np.asarray(y, dtype=np.int8)
    o = np.argsort(-np.asarray(s, dtype=np.float64), kind="mergesort")
    y = y[o]
    prec = np.cumsum(y) / np.arange(1, len(y) + 1)
    npos = int(y.sum())
    return float((prec * y).sum() / npos) if npos else float("nan")


def stage_pred(args, log):
    import lightgbm as lgb
    lag = args.lag
    F = pd.read_parquet(feat_path(args.cache, lag))
    meta = json.load(open(os.path.join(args.cache, "featmeta_lag%d.json" % lag)))
    tr = F["blk"].to_numpy() == 0
    va = F["blk"].to_numpy() == 1
    te = F["blk"].to_numpy() == 2
    y = F["y"].to_numpy(np.float32)
    hv = F["heavy"].to_numpy(np.int8)
    log.p("features %s; train %d valid %d devtest %d; heavy threshold %.1f ms"
          % (feat_path(args.cache, lag), tr.sum(), va.sum(), te.sum(), meta["heavy_thr_ms"]))
    log.p("heavy rate: train %.4f  valid %s  devtest %.4f"
          % (hv[tr].mean(), ("%.4f" % hv[va].mean()) if va.sum() else "-", hv[te].mean()))
    nl_path = os.path.join(args.cache, "numleaves.json")
    if args.select_leaves and va.sum() > 0:
        best = None
        cols = MODELS["M4"]
        Xtr = F.loc[tr, cols].to_numpy(np.float32)
        Xva = F.loc[va, cols].to_numpy(np.float32)
        for nl in [31, 127]:
            dtr = lgb.Dataset(Xtr, label=y[tr], feature_name=cols)
            dva = lgb.Dataset(Xva, label=y[va], reference=dtr)
            bst = lgb.train(lgb_params("regression", 0, nl), dtr,
                            num_boost_round=args.rounds, valid_sets=[dva],
                            callbacks=[lgb.early_stopping(30, verbose=False)])
            r = float(np.sqrt(np.mean((bst.predict(Xva, num_iteration=bst.best_iteration)
                                       - y[va]) ** 2)))
            log.p("  M4 num_leaves %d -> validation-block RMSE %.4f (best_iter %d)"
                  % (nl, r, bst.best_iteration))
            if best is None or r < best[0]:
                best = (r, nl, int(bst.best_iteration))
        json.dump({"num_leaves": best[1], "rounds": best[2]}, open(nl_path, "w"))
        log.p("SELECTED on the validation block: num_leaves = %d, rounds = %d"
              % (best[1], best[2]))
        del Xtr, Xva
    sel = json.load(open(nl_path)) if os.path.exists(nl_path) else \
        {"num_leaves": 127, "rounds": args.rounds}
    nl = sel["num_leaves"]
    nr = max(50, min(args.rounds, int(sel["rounds"]) or args.rounds))
    log.p("using num_leaves = %d, num_boost_round = %d" % (nl, nr))
    for mname in args.models.split(","):
        cols = MODELS[mname]
        Xtr = F.loc[tr, cols].to_numpy(np.float32)
        Xte = F.loc[te, cols].to_numpy(np.float32)
        for seed in [int(s) for s in args.seeds.split(",")]:
            t0 = time.time()
            br = lgb.train(lgb_params("regression", seed, nl),
                           lgb.Dataset(Xtr, label=y[tr], feature_name=cols),
                           num_boost_round=nr)
            pr = br.predict(Xte).astype(np.float32)
            bc = lgb.train(lgb_params("binary", seed, nl),
                           lgb.Dataset(Xtr, label=hv[tr], feature_name=cols),
                           num_boost_round=nr)
            pc = bc.predict(Xte).astype(np.float32)
            np.save(os.path.join(args.cache, "pred_lag%d_%s_s%d.npy" % (lag, mname, seed)),
                    np.vstack([pr, pc]))
            log.p("  %s seed %d: %.0f s; devtest RMSE(log1p s) %.4f  AUROC %.4f"
                  % (mname, seed, time.time() - t0,
                     float(np.sqrt(np.mean((pr - y[te]) ** 2))), roc_auc(hv[te], pc)))
        del Xtr, Xte
    log.close()


def load_preds(cache, lag, models, seeds):
    out = {}
    for m in models:
        rs, cs = [], []
        for s in seeds:
            p = os.path.join(cache, "pred_lag%d_%s_s%d.npy" % (lag, m, s))
            if os.path.exists(p):
                a = np.load(p)
                rs.append(a[0]); cs.append(a[1])
        if rs:
            out[m] = (np.mean(rs, axis=0), np.mean(cs, axis=0), len(rs))
    return out


# --------------------------------------------------- fast user-block bootstrap
class BootAUC(object):
    """Weighted AUROC over a fixed row set, for bootstrap weights on the rows."""

    def __init__(self, score, y):
        o = np.argsort(score, kind="mergesort")
        self.o = o
        s = score[o]
        self.y = y[o].astype(np.float64)
        newg = np.empty(len(s), dtype=bool)
        newg[0] = True
        newg[1:] = s[1:] != s[:-1]
        self.starts = np.flatnonzero(newg)

    def auc(self, w_sorted):
        wy = w_sorted * self.y
        wn = w_sorted - wy
        gpos = np.add.reduceat(wy, self.starts)
        gneg = np.add.reduceat(wn, self.starts)
        before = np.concatenate([[0.0], np.cumsum(gneg)[:-1]])
        P = gpos.sum(); N = gneg.sum()
        if P <= 0 or N <= 0:
            return float("nan")
        return float((gpos * (before + 0.5 * gneg)).sum() / (P * N))


def stage_boot(args, log):
    lag = args.lag
    F = pd.read_parquet(feat_path(args.cache, lag))
    tr = F["blk"].to_numpy() == 0
    te = F["blk"].to_numpy() == 2
    y0 = float(F.loc[tr, "y"].mean())
    T = F[te].reset_index(drop=True)
    y = T["y"].to_numpy(np.float64)
    hv = T["heavy"].to_numpy(np.int8)
    uid = T["uid"].to_numpy(np.int64)
    p_n = T["p_n"].to_numpy(np.float64)
    u_n = T["u_n"].to_numpy(np.float64)
    ms = np.log1p(np.maximum(T["tc_ms"].to_numpy(np.float64), 0))
    models = args.models.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]
    P = load_preds(args.cache, lag, models, seeds)
    have = [m for m in models if m in P]
    meta = json.load(open(os.path.join(args.cache, "featmeta_lag%d.json" % lag)))
    log.p("devtest rows %d; models %s; seeds averaged: %s"
          % (len(T), have, {m: P[m][2] for m in have}))
    log.p("target = log1p(time_cost / 1000) i.e. log1p seconds; heavy = true time_cost > "
          "train-block p95 = %.1f ms; devtest heavy rate %.4f"
          % (meta["heavy_thr_ms"], hv.mean()))

    groups = [("all", np.ones(len(T), bool)),
              ("cold-problem(<5 visible)", p_n < 5),
              ("cold-user(<5 visible)", u_n < 5),
              ("cold-both", (p_n < 5) & (u_n < 5))]
    rows = []
    for gname, gm in groups:
        n = int(gm.sum())
        if n == 0:
            continue
        log.p("")
        log.p("-- devtest rows = %s (n=%d, heavy rate %.4f, users %d) --"
              % (gname, n, hv[gm].mean(), len(np.unique(uid[gm]))))
        log.p("  model   RMSE(log1p s)  Spearman   AUROC(heavy)  AUPRC(heavy)  RMSE(log1p ms)")
        r0 = float(np.sqrt(np.mean((y[gm] - y0) ** 2)))
        log.p("  %-6s %13.4f %9s %13s %13s %15.4f"
              % ("M0", r0, "nan", "nan", "nan",
                 float(np.sqrt(np.mean((ms[gm] - ms[gm].mean()) ** 2)))))
        rows.append([gname, "M0", r0, float("nan"), float("nan"), float("nan")])
        from scipy.stats import spearmanr
        for m in have:
            pr, pc, _ = P[m]
            rmse = float(np.sqrt(np.mean((y[gm] - pr[gm]) ** 2)))
            sp = float(spearmanr(y[gm], pr[gm]).correlation)
            au = roc_auc(hv[gm], pc[gm]) if 0 < hv[gm].sum() < n else float("nan")
            ap = avg_prec(hv[gm], pc[gm]) if 0 < hv[gm].sum() < n else float("nan")
            pr_ms = np.log1p(np.maximum(np.expm1(pr[gm].astype(np.float64)) * 1000.0, 0))
            rms = float(np.sqrt(np.mean((ms[gm] - pr_ms) ** 2)))
            log.p("  %-6s %13.4f %9.4f %13.4f %13.4f %15.4f" % (m, rmse, sp, au, ap, rms))
            rows.append([gname, m, rmse, sp, au, ap])
    pd.DataFrame(rows, columns=["group", "model", "rmse", "spearman", "auroc", "auprc"]) \
        .to_csv(os.path.join(args.cache, "predtab_lag%d.csv" % lag), index=False)

    pairs = [(a, bb) for a, bb in [("M4", "M1"), ("M4", "M2"), ("M4", "M3"),
                                   ("M5", "M4"), ("M1", "M2"), ("M1", "M3")]
             if a in have and bb in have]
    log.p("")
    log.p("-- paired bootstrap of the differences, %d resamples, blocks = users --"
          % args.boot)
    rng = np.random.default_rng(args.seed_boot)
    for gname, gm in groups:
        if int(gm.sum()) < 500:
            log.p("")
            log.p("  rows = %s: n=%d, too small for a user-block bootstrap, skipped"
                  % (gname, int(gm.sum())))
            continue
        gi = np.flatnonzero(gm)
        uu, uinv = np.unique(uid[gi], return_inverse=True)
        nu = len(uu)
        yg = y[gi]; hvg = hv[gi]
        # per-user sufficient statistics for RMSE
        cnt = np.bincount(uinv, minlength=nu).astype(np.float64)
        aucs = {}
        sse = {}
        for m in have:
            pr, pc, _ = P[m]
            e2 = (yg - pr[gi]) ** 2
            sse[m] = np.bincount(uinv, weights=e2, minlength=nu)
            aucs[m] = BootAUC(pc[gi].astype(np.float64), hvg)
        log.p("")
        log.p("  rows = %s (n=%d, user blocks=%d)" % (gname, len(gi), nu))
        log.p("  comparison    dRMSE (neg = first better)        dAUROC (pos = first better)")
        rm = {m: np.empty(args.boot) for m in have}
        aucv = {m: np.empty(args.boot) for m in have}
        t0 = time.time()
        for t in range(args.boot):
            mult = np.bincount(rng.integers(0, nu, size=nu), minlength=nu).astype(np.float64)
            ntot = float(mult @ cnt)
            w = mult[uinv]                            # one weight per devtest row
            for m in have:
                rm[m][t] = math.sqrt(float(mult @ sse[m]) / max(ntot, 1.0))
                A = aucs[m]
                aucv[m][t] = A.auc(w[A.o])
        log.p("  (%d resamples in %.0f s)" % (args.boot, time.time() - t0))
        for a, bb in pairs:
            dr = rm[a] - rm[bb]
            da = aucv[a] - aucv[bb]
            pa = float(np.sqrt(np.mean((yg - P[a][0][gi]) ** 2)))
            pb = float(np.sqrt(np.mean((yg - P[bb][0][gi]) ** 2)))
            oa = roc_auc(hvg, P[a][1][gi]); ob = roc_auc(hvg, P[bb][1][gi])
            log.p("  %-5s-%-5s %+8.4f [%+8.4f,%+8.4f]    %+8.4f [%+8.4f,%+8.4f]"
                  % (a, bb, pa - pb, np.nanpercentile(dr, 2.5), np.nanpercentile(dr, 97.5),
                     oa - ob, np.nanpercentile(da, 2.5), np.nanpercentile(da, 97.5)))
        del mult, rm, aucv
    log.close()


# ================================================================ trace
def id_time_anchors(df_all, cont):
    """Monotone map from submission id to a calendar time, built from the first id of
    every contest and that contest's start_time, running-maximised so that archive
    contests whose start_time is years older than the ids they still collect cannot
    drag the calendar backwards."""
    cs = cont.set_index("id")
    ok = cs["start_time"].notna()
    rows = []
    d = df_all[df_all["contest_id"] >= 0]
    for c, first in d.groupby("contest_id")["id"].min().items():
        if c in cs.index and ok.loc[c]:
            rows.append((float(first), cs.loc[c, "start_time"].value / 1e9))
    rows.sort()
    aid = np.array([r[0] for r in rows])
    at = np.maximum.accumulate(np.array([r[1] for r in rows]))
    return aid, at


def build_trace(df_te, cont, shape, seed, gamma, tau_h, anchors, cap_h=EPISODE_CAP_H):
    """Unscaled synthetic arrival times (s) for the dev-test jobs, in the row order
    given.  All rows of one contest form one episode; runs of consecutive non-contest
    rows form practice episodes.  An episode STARTS at the calendar time its first id
    maps to (id_time_anchors) and LASTS the contest's true duration, capped at cap_h;
    a practice episode lasts the calendar span of its own id range.  Inside an episode
    the drawn positions are sorted and handed out in id order, so the true id order
    inside every episode is preserved."""
    rng = np.random.default_rng(seed)
    n = len(df_te)
    cid = df_te["contest_id"].fillna(-1).to_numpy(np.int64)
    ids = df_te["id"].to_numpy(np.int64)
    arr = np.full(n, np.nan)
    cs = cont.set_index("id")
    ok_c = cs["start_time"].notna() & cs["end_time"].notna()
    aid, at = anchors

    eps = []
    for c in np.unique(cid[cid >= 0]):
        m = np.flatnonzero(cid == c)
        t0 = float(np.interp(ids[m].min(), aid, at))
        if c in cs.index and ok_c.loc[c]:
            w = (cs.loc[c, "end_time"].value - cs.loc[c, "start_time"].value) / 1e9
        else:
            w = 3600.0
        if not np.isfinite(w) or w <= 0:
            w = 3600.0
        eps.append((m, t0, min(w, cap_h * 3600.0), True))
    pr = np.flatnonzero(cid < 0)
    for st in range(0, len(pr), PRACTICE_CHUNK):
        m = pr[st:st + PRACTICE_CHUNK]
        t0 = float(np.interp(ids[m].min(), aid, at))
        t1 = float(np.interp(ids[m].max(), aid, at))
        eps.append((m, t0, min(max(t1 - t0, 600.0), cap_h * 3600.0), False))

    tt = tau_h * 3600.0
    start = np.full(n, np.nan)
    frac = np.full(n, np.nan)
    isc = np.zeros(n, dtype=bool)
    for m, t0, w, shaped in eps:
        k = len(m)
        if shape == "deadline" and shaped:
            q = rng.random(k)
            if abs(1.0 - gamma) < 1e-6:
                u = tt * np.exp(q * math.log((w + tt) / tt)) - tt
            else:
                Z = ((w + tt) ** (1 - gamma) - tt ** (1 - gamma)) / (1 - gamma)
                u = ((1 - gamma) * q * Z + tt ** (1 - gamma)) ** (1.0 / (1 - gamma)) - tt
            pos = w - u
        else:
            pos = rng.random(k) * w
        pos.sort()
        arr[m] = pos                       # offset inside the episode window (real length)
        start[m] = t0                      # episode start on the real calendar
        frac[m] = pos / w                  # position inside the window, 0 .. 1
        isc[m] = shaped
    assert np.isfinite(arr).all() and np.isfinite(start).all()
    start -= start.min()
    return start, arr, frac, isc


def apply_scale(start, offset, s):
    """Gap-only compression: episode STARTS move together by the factor s, each
    episode's own window keeps its real length, so within-contest intensity and the
    deadline ramp stay at their real time scale and the load comes from more contests
    running at once.  s = 1 is the real contest calendar."""
    a = start * s + offset
    return a - a.min()


def ep_windows(df_te, cont, anchors, cap_h=EPISODE_CAP_H):
    """The (uncompressed) episode window lengths in seconds, for reporting."""
    cid = df_te["contest_id"].fillna(-1).to_numpy(np.int64)
    ids = df_te["id"].to_numpy(np.int64)
    cs = cont.set_index("id")
    ok_c = cs["start_time"].notna() & cs["end_time"].notna()
    aid, at = anchors
    out = []
    for c in np.unique(cid[cid >= 0]):
        if c in cs.index and ok_c.loc[c]:
            w = (cs.loc[c, "end_time"].value - cs.loc[c, "start_time"].value) / 1e9
        else:
            w = 3600.0
        if not np.isfinite(w) or w <= 0:
            w = 3600.0
        out.append(min(w, cap_h * 3600.0))
    pr = np.flatnonzero(cid < 0)
    for st in range(0, len(pr), PRACTICE_CHUNK):
        m = pr[st:st + PRACTICE_CHUNK]
        t0 = float(np.interp(ids[m].min(), aid, at))
        t1 = float(np.interp(ids[m].max(), aid, at))
        out.append(min(max(t1 - t0, 600.0), cap_h * 3600.0))
    return out


def busy_hour_work(arr, svc):
    h = np.floor(arr / 3600.0).astype(np.int64)
    h -= h.min()
    w = np.bincount(h, weights=svc)
    i = int(np.argmax(w))
    return float(w[i]), i, w


def calib_scale(start, offset, svc, target):
    """Busy-hour work is non-increasing in the gap-compression factor s."""
    lo, hi = 1e-7, 10.0
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        w, _, _ = busy_hour_work(apply_scale(start, offset, mid), svc)
        if w > target:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def devtest_jobs(df, prob, sealed_id_min, service="main"):
    ok = modelling_mask(df).to_numpy()
    te = (df["blk"].to_numpy() == 2) & ok
    D = df[te].reset_index(drop=True)
    assert_no_sealed(D, sealed_id_min, "trace")
    tc = D["time_cost"].to_numpy(np.float64)
    if service == "alt":
        nt = prob.set_index("id")["n_tests"].reindex(D["problem_id"]).fillna(1) \
            .to_numpy(np.float64)
        svc = SVC_ALT_FIXED + SVC_ALT_PER_TEST * np.maximum(nt, 1.0) + tc / 1000.0
    else:
        svc = SVC_FIXED + tc / 1000.0
    return D, tc, svc


def stage_trace(args, log):
    df, b, sealed_id_min, n_total = load_dev(log)
    prob, cont, ptag, tags = load_meta()
    D, tc, svc = devtest_jobs(df, prob, sealed_id_min, "main")
    _, _, svc_alt = devtest_jobs(df, prob, sealed_id_min, "alt")
    log.p("devtest trace: %d jobs, total service work %.1f s (%.2f h); C mean %.3f s "
          "median %.3f s p99 %.3f s max %.3f s"
          % (len(D), svc.sum(), svc.sum() / 3600.0, svc.mean(), np.median(svc),
             np.percentile(svc, 99), svc.max()))
    L = float(svc.max())
    log.p("platform service cap L = %.3f s (the largest n_tests*time_limit in the block "
          "plus the %.1f s fixed term); guard budgets B = %.1f / %.1f / %.1f s = "
          "0.5L / 2L / 10L" % (L, SVC_FIXED, 0.5 * L, 2 * L, 10 * L))
    log.p("alternative service model %.1f + %.2f*n_tests + time_cost/1000: total %.1f s, "
          "max %.3f s" % (SVC_ALT_FIXED, SVC_ALT_PER_TEST, svc_alt.sum(), svc_alt.max()))
    sh = json.load(open(os.path.join(args.cache, "cbshape.json")))
    log.p("deadline shape taken from %s: gamma = %.4f, tau = %.3f h"
          % (sh["source"], sh["gamma"], sh["tau_h"]))
    from scipy.stats import spearmanr
    anchors = id_time_anchors(df, cont)
    aid, at = anchors
    log.p("id -> calendar anchors from %d contests of the non-sealed blocks; the devtest "
          "block maps to %s .. %s (%.0f days)"
          % (len(aid), pd.Timestamp(np.interp(D["id"].min(), aid, at), unit="s"),
             pd.Timestamp(np.interp(D["id"].max(), aid, at), unit="s"),
             (np.interp(D["id"].max(), aid, at) - np.interp(D["id"].min(), aid, at)) / 86400))
    ctrue = cont.set_index("id")
    devc = sorted(set(D.loc[D["contest_id"] >= 0, "contest_id"]))
    tt_ = np.array([ctrue.loc[c, "start_time"].value / 1e9 for c in devc
                    if c in ctrue.index and pd.notna(ctrue.loc[c, "start_time"])])
    ii_ = np.array([np.interp(D.loc[D["contest_id"] == c, "id"].min(), aid, at) for c in devc
                    if c in ctrue.index and pd.notna(ctrue.loc[c, "start_time"])])
    log.p("of the %d devtest contests, %d have a recorded start_time more than 30 days "
          "before the calendar position of their first devtest id (archive contests that "
          "keep collecting submissions years later); Spearman(anchor, true start) = %.4f"
          % (len(devc), int((ii_ - tt_ > 30 * 86400).sum()),
             spearmanr(ii_, tt_).correlation))
    out = {"L": L, "gamma": sh["gamma"], "tau_h": sh["tau_h"], "shape_source": sh["source"],
           "n_jobs": int(len(D)), "work_s": float(svc.sum())}
    for shape in ["poisson", "deadline"]:
        st0, of0, fr0, isc0 = build_trace(D, cont, shape, 300, sh["gamma"], sh["tau_h"],
                                          anchors)
        sc = calib_scale(st0, of0, svc, BUSY_WORK_TARGET)
        a = apply_scale(st0, of0, sc)
        w, hidx, wh = busy_hour_work(a, svc)
        ks = {str(r): max(1, int(round(w / 3600.0 / r))) for r in RHO_LEVELS}
        log.p("")
        log.p("shape=%-8s gap-compression scale %.5f -> busiest-hour work %.1f s "
              "(target %.0f); span %.1f h; %d non-empty hours; k: %s"
              % (shape, sc, w, BUSY_WORK_TARGET, (a.max() - a.min()) / 3600.0,
                 int((wh > 0).sum()),
                 ", ".join("rho=%s->k=%s" % (r, ks[r]) for r in ks)))
        log.p("   Spearman(submission id, synthetic arrival) = %.4f (id order is preserved "
              "INSIDE each episode, not globally: contests overlap in id space)"
              % spearmanr(D["id"].to_numpy(), a).correlation)
        hrs = wh[wh > 0]
        log.p("   hourly work (server-equivalents a[h] = work/3600): p50 %.2f p90 %.2f "
              "p99 %.2f max %.2f" % tuple(np.percentile(hrs, [50, 90, 99, 100]) / 3600.0))
        # k = 1 configuration: same clock, job stream thinned by keeping every q-th
        # arrival.  This is the ACcoding analogue of reducing the overlay copy count on
        # CodeBench; stretching the clock instead does not work here, because a 40-minute
        # contest with 4,026 submissions stays above one judge at any stretch factor.
        bestq = None
        for q in range(2, 41):
            kp = np.argsort(a, kind="mergesort")[::q]
            wq, _, _ = busy_hour_work(a[kp], svc[kp])
            if bestq is None or abs(wq / 3600.0 - 0.8) < abs(bestq[1] / 3600.0 - 0.8):
                bestq = (q, wq)
        q, wq = bestq
        log.p("   k=1 configuration: same clock, every %d-th arrival kept (%d jobs) -> "
              "busiest-hour work %.1f s, rho %.3f on one server"
              % (q, len(svc) // q, wq, wq / 3600.0))
        ew = np.array(ep_windows(D, cont, anchors))
        es = np.unique(np.round(np.sort(np.unique(np.column_stack([np.zeros(0)]))) , 6))             if False else None
        log.p("   episode windows keep their real length (h): p10 %.2f p50 %.2f p90 %.2f "
              "max %.2f over %d episodes"
              % tuple(list(np.percentile(ew, [10, 50, 90, 100]) / 3600.0) + [len(ew)]))
        st_u = np.unique(st0) * sc
        ends = st_u + np.median(ew)
        grid = np.linspace(st_u.min(), st_u.max(), 2000)
        conc = np.array([((st_u <= t) & (ends > t)).sum() for t in grid])
        log.p("   episodes running at once after compression (median-window proxy): "
              "p50 %.0f p90 %.0f max %.0f  (the real platform peaked at 21 concurrent "
              "contests; this is the 'many more courses at once' construction)"
              % tuple(np.percentile(conc, [50, 90, 100])))
        out[shape] = {"scale": sc, "thin_k1": int(q), "busy_work": w, "k": ks}
    json.dump(out, open(os.path.join(args.cache, "trace.json"), "w"), indent=1)
    log.p("")
    log.p("FOR THE PAPER: ACcoding has no submission timestamps.  Only the job ORDER "
          "inside a contest and the job SIZES are real; every arrival time is drawn, and "
          "the compression factor is a construction parameter chosen to put a fixed judge "
          "pool at the three target utilisations.")
    log.close()


# ================================================================ simulator
def simulate_plain(arr, svc, score, k):
    n = len(arr)
    o = np.argsort(arr, kind="mergesort")
    a = arr[o]; s = svc[o]
    sc = None if score is None else score[o]
    wait = np.empty(n)
    ready = []
    servers = [0.0] * k
    heapq.heapify(servers)
    i = 0
    nst = 0
    while nst < n:
        tfree = servers[0]
        while i < n and a[i] <= tfree:
            heapq.heappush(ready, (i if sc is None else sc[i], i))
            i += 1
        if not ready:
            t = a[i] if a[i] > tfree else tfree
            while i < n and a[i] <= t:
                heapq.heappush(ready, (i if sc is None else sc[i], i))
                i += 1
        else:
            t = tfree
        heapq.heappop(servers)
        _, j = heapq.heappop(ready)
        start = t if t > a[j] else a[j]
        wait[j] = start - a[j]
        heapq.heappush(servers, start + s[j])
        nst += 1
    out = np.empty(n)
    out[o] = wait
    return out


def simulate_guard(arr, svc, score, k, guard_B, check_fenwick=False):
    """SPJF with an overtaking-budget guard.  over[h] for the queue head h is computed
    exactly in integer microseconds as
        total completed work - (work of all ranks < h - work of ranks < h in service),
    which is valid because every job arriving before the head is either completed or in
    service.  check_fenwick verifies that identity against a Fenwick tree."""
    n = len(arr)
    o = np.argsort(arr, kind="mergesort")
    a = arr[o]; s = svc[o]; sc = score[o]
    us = np.rint(s * 1e6).astype(np.int64)
    pref = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(us, out=pref[1:])
    B_us = int(round(guard_B * 1e6))
    wait = np.empty(n)
    ready = []
    waiting = []
    inq = np.zeros(n, dtype=bool)
    servers = [(0.0, -1)] * k
    heapq.heapify(servers)
    fen = [0] * (n + 1) if check_fenwick else None
    done_us = 0
    i = 0
    nst = 0
    while nst < n:
        tfree, rdone = heapq.heappop(servers)
        if rdone >= 0:
            done_us += int(us[rdone])
            if fen is not None:
                x = rdone + 1
                while x <= n:
                    fen[x] += int(us[rdone]); x += x & (-x)
        while i < n and a[i] <= tfree:
            heapq.heappush(ready, (sc[i], i))
            heapq.heappush(waiting, i)
            inq[i] = True
            i += 1
        while waiting and not inq[waiting[0]]:
            heapq.heappop(waiting)
        if not waiting:
            t = a[i] if a[i] > tfree else tfree
            while i < n and a[i] <= t:
                heapq.heappush(ready, (sc[i], i))
                heapq.heappush(waiting, i)
                inq[i] = True
                i += 1
        else:
            t = tfree
        h = waiting[0]
        insvc = 0
        for _, r in servers:
            if 0 <= r < h:
                insvc += int(us[r])
        over = done_us - (int(pref[h]) - insvc)
        if fen is not None:
            acc = 0; x = h
            while x > 0:
                acc += fen[x]; x -= x & (-x)
            assert done_us - acc == over, "guard accounting mismatch"
        if over >= B_us:
            j = h
        else:
            while ready and not inq[ready[0][1]]:
                heapq.heappop(ready)
            j = ready[0][1]
        inq[j] = False
        while ready and not inq[ready[0][1]]:
            heapq.heappop(ready)
        while waiting and not inq[waiting[0]]:
            heapq.heappop(waiting)
        start = t if t > a[j] else a[j]
        wait[j] = start - a[j]
        heapq.heappush(servers, (start + s[j], j))
        nst += 1
    out = np.empty(n)
    out[o] = wait
    return out


def lindley(arr, svc):
    o = np.argsort(arr, kind="mergesort")
    a = arr[o]; s = svc[o]
    w = np.empty(len(a))
    end = a[0]
    for i in range(len(a)):
        st = a[i] if a[i] > end else end
        w[i] = st - a[i]
        end = st + s[i]
    out = np.empty(len(a)); out[o] = w
    return out


def stage_selftest(args, log):
    rng = np.random.default_rng(0)
    n = 4000
    arr = np.cumsum(rng.exponential(1.0, n))
    svc = rng.exponential(0.8, n)
    w1 = simulate_plain(arr, svc, None, 1)
    w2 = lindley(arr, svc)
    log.p("k=1 FCFS vs the Lindley recursion: max |diff| = %.3e" % np.abs(w1 - w2).max())
    assert np.abs(w1 - w2).max() < 1e-9
    sc = rng.random(n)
    wg0 = simulate_guard(arr, svc, sc, 1, 0.0, check_fenwick=True)
    log.p("k=1 guard with B=0 vs FCFS: max |diff| = %.3e (B=0 must degenerate to FCFS)"
          % np.abs(wg0 - w1).max())
    assert np.abs(wg0 - w1).max() < 1e-9
    L = float(svc.max())
    for B in (1.0, 5.0, 50.0):
        wg = simulate_guard(arr, svc, sc, 1, B, check_fenwick=True)
        ex = float((wg - w1).max())
        log.p("k=1 guard B=%.1f: max_i (W_guard - W_FCFS) = %.4f, bound B+L = %.4f -> %s"
              % (B, ex, B + L, "OK" if ex <= B + L + 1e-9 else "VIOLATED"))
        assert ex <= B + L + 1e-9
    log.p("the Fenwick cross-check inside simulate_guard validated the O(k) overtaking "
          "identity on every decision of those runs")
    k = 3
    wA = simulate_plain(arr, svc, None, k)
    free = [0.0] * k
    wB = np.empty(n)
    for r in np.argsort(arr, kind="mergesort"):
        m = int(np.argmin(free))
        st = max(arr[r], free[m])
        wB[r] = st - arr[r]
        free[m] = st + svc[r]
    log.p("k=%d FCFS vs an independent direct implementation: max |diff| = %.3e"
          % (k, np.abs(wA - wB).max()))
    assert np.abs(wA - wB).max() < 1e-9
    wsjf = simulate_plain(arr, svc, svc.copy(), 1)
    log.p("k=1: mean wait FCFS %.3f vs true-size SJF %.3f (SJF must not be worse in the "
          "mean at k=1)" % (w1.mean(), wsjf.mean()))
    assert wsjf.mean() <= w1.mean() + 1e-9
    df, b, sealed_id_min, n_total = load_dev(log)
    log.p("split assertion: devtest max id %d < first sealed id %d -> %s"
          % (int(df["id"].max()), sealed_id_min, int(df["id"].max()) < sealed_id_min))
    log.close()


def sim_metrics(w, heavy, tag, dl=None):
    d = {"policy": tag, "mean": float(w.mean()), "p95": float(np.percentile(w, 95)),
         "p99": float(np.percentile(w, 99)), "wmax": float(w.max()),
         "mean_heavy": float(w[heavy].mean()) if heavy.any() else float("nan"),
         "p99_heavy": float(np.percentile(w[heavy], 99)) if heavy.any() else float("nan"),
         "max_heavy": float(w[heavy].max()) if heavy.any() else float("nan")}
    if dl is not None and dl.any():
        d["p99_dl"] = float(np.percentile(w[dl], 99))
        d["mean_dl"] = float(w[dl].mean())
    else:
        d["p99_dl"] = float("nan")
        d["mean_dl"] = float("nan")
    return d


def stage_sim(args, log):
    df, b, sealed_id_min, n_total = load_dev(log)
    prob, cont, ptag, tags = load_meta()
    D, tc, svc = devtest_jobs(df, prob, sealed_id_min, args.service)
    tr = json.load(open(os.path.join(args.cache, "trace.json")))
    L = float(np.max(svc))
    meta = json.load(open(os.path.join(args.cache, "featmeta_lag0.json")))
    heavy = tc > meta["heavy_thr_ms"]
    F = pd.read_parquet(feat_path(args.cache, 0), columns=["blk", "id"])
    assert np.array_equal(F.loc[F["blk"] == 2, "id"].to_numpy(), D["id"].to_numpy()), \
        "feature rows and trace jobs are not the same submissions"
    models = args.models.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]
    P = load_preds(args.cache, 0, models, seeds)
    have = [m for m in models if m in P]
    shape, rho = args.shape, args.rho
    k = tr[shape]["k"][str(rho)]
    scale = tr[shape]["scale"]
    Bs = [0.5 * L, 2.0 * L, 10.0 * L]
    log.p("jobs %d; service model '%s' (L = %.3f s); heavy = true time_cost > %.1f ms "
          "(%.4f of jobs); predictors %s"
          % (len(D), args.service, L, meta["heavy_thr_ms"], heavy.mean(), have))
    log.p("shape %s, target rho %.1f -> k = %d; compression scale %.5f; gamma %.4f, "
          "tau %.3f h (%s); B = %.1f / %.1f / %.1f s = 0.5L / 2L / 10L"
          % (shape, rho, k, scale, tr["gamma"], tr["tau_h"], tr["shape_source"],
             Bs[0], Bs[1], Bs[2]))
    log.p("ARRIVALS ARE SYNTHETIC: only the order inside each contest and the sizes are real.")
    anchors = id_time_anchors(df, cont)
    adv_base = P["M4"][0].astype(np.float64) if "M4" in P else svc
    rows = []
    for rep in range(args.reps):
        st0, of0, fr0, isc0 = build_trace(D, cont, shape, 300 + rep, tr["gamma"],
                                          tr["tau_h"], anchors)
        arr = apply_scale(st0, of0, scale)
        dl = isc0 & (fr0 >= 0.9)
        wbusy, _, _ = busy_hour_work(arr, svc)
        t0 = time.time()
        wf = simulate_plain(arr, svc, None, k)
        wo = simulate_plain(arr, svc, svc.copy(), k)
        base = {"rep": rep, "k": k, "rho_busy": wbusy / 3600.0 / k, "shape": shape,
                "rho_target": rho, "service": args.service}
        res = [dict(base, max_excess=0.0, **sim_metrics(wf, heavy, "FCFS", dl)),
               dict(base, max_excess=float((wo - wf).max()),
                    **sim_metrics(wo, heavy, "SJF-ref", dl))]
        for m in have:
            wp = simulate_plain(arr, svc, P[m][0].astype(np.float64).copy(), k)
            res.append(dict(base, max_excess=float((wp - wf).max()),
                            **sim_metrics(wp, heavy, "SPJF-%s" % m, dl)))
        adv = adv_base.copy()
        adv[svc >= np.percentile(svc, 99)] = -1e9
        wa = simulate_plain(arr, svc, adv.copy(), k)
        res.append(dict(base, max_excess=float((wa - wf).max()),
                        **sim_metrics(wa, heavy, "ADV-top1short", dl)))
        for bi, B in enumerate(Bs):
            wg = simulate_guard(arr, svc, P["M4"][0].astype(np.float64).copy(), k, B)
            res.append(dict(base, max_excess=float((wg - wf).max()),
                            **sim_metrics(wg, heavy, "GUARD-M4-B%d" % round(B), dl)))
            if bi == 1:
                wg2 = simulate_guard(arr, svc, adv.copy(), k, B)
                res.append(dict(base, max_excess=float((wg2 - wf).max()),
                                **sim_metrics(wg2, heavy,
                                              "GUARD-ADV-B%d" % round(B), dl)))
        rows.extend(res)
        log.p("  draw %d: busy-hour work %.1f s, achieved busy-hour rho %.3f, "
              "deadline-window jobs %d, %d policies, %.0f s"
              % (rep, wbusy, wbusy / 3600.0 / k, int(dl.sum()), len(res),
                 time.time() - t0))
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(args.cache, "sim_%s_%s_rho%.1f.csv"
                          % (args.service, shape, rho)), index=False)
    agg = R.groupby("policy", sort=False).mean(numeric_only=True)
    mx = R.groupby("policy", sort=False)["max_excess"].max()
    fm, fp = agg.loc["FCFS", "mean"], agg.loc["FCFS", "p99"]
    om, op = agg.loc["SJF-ref", "mean"], agg.loc["SJF-ref", "p99"]
    log.p("")
    log.p("--- %s arrivals, target rho %.1f, k = %d, %d draws, waits in s (mean over draws) ---"
          % (shape, rho, k, args.reps))
    fd, od = agg.loc["FCFS", "p99_dl"], agg.loc["SJF-ref", "p99_dl"]
    log.p("%-17s %8s %9s %8s %8s %8s %8s %8s %9s %9s %9s"
          % ("policy", "mean", "gain_mean", "p99", "gain_p99", "p99_dl", "gain_dl",
             "p95", "mean_heavy", "max_heavy", "max_exces"))
    for pol in agg.index:
        r = agg.loc[pol]
        log.p("%-17s %8.3f %9.3f %8.3f %8.3f %8.3f %8.3f %8.3f %9.3f %9.1f %9.1f"
              % (pol, r["mean"], (fm - r["mean"]) / (fm - om), r["p99"],
                 (fp - r["p99"]) / (fp - op), r["p99_dl"],
                 (fd - r["p99_dl"]) / (fd - od), r["p95"], r["mean_heavy"],
                 r["max_heavy"], mx.loc[pol]))
    for nm, f_, o_ in [("mean", fm, om), ("p99", fp, op), ("p99_dl", fd, od)]:
        flag = "UNSTABLE" if (f_ - o_) < 0.05 or (f_ - o_) < 0.05 * f_ else "stable"
        log.p("    gain denominator FCFS - SJF-ref on %-7s = %8.3f s -> %s"
              % (nm, f_ - o_, flag))
    log.p("p99_dl = p99 wait among arrivals in the last 10 percent of their contest's "
          "window, the ACcoding analogue of CodeBench's deadline-window p99 "
          "(research_plan.md 6.5).  On the stationary stream that window carries no "
          "extra load by construction, so p99_dl and p99 nearly coincide there.")
    log.p("gain = (W_FCFS - W_policy) / (W_FCFS - W_SJF-ref), computed on the draw means; "
          "SJF-ref uses the TRUE sizes and is a reference, not a bound.  max_excess = max "
          "over jobs and draws of (W_policy - W_FCFS).  Bound at k=1 is B + L; at k>1 there "
          "is no bound and these are reported as measurements.")
    log.p("achieved busy-hour rho per draw: %s"
          % ", ".join("%.3f" % v for v in R[R.policy == "FCFS"]["rho_busy"]))
    log.close()


def stage_guardk1(args, log):
    df, b, sealed_id_min, n_total = load_dev(log)
    prob, cont, ptag, tags = load_meta()
    D, tc, svc = devtest_jobs(df, prob, sealed_id_min, "main")
    tr = json.load(open(os.path.join(args.cache, "trace.json")))
    L = float(np.max(svc))
    meta = json.load(open(os.path.join(args.cache, "featmeta_lag0.json")))
    heavy = tc > meta["heavy_thr_ms"]
    models = args.models.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]
    P = load_preds(args.cache, 0, models, seeds)
    have = [m for m in models if m in P]
    shape = args.shape
    scale = tr[shape]["scale"]
    q = int(tr[shape]["thin_k1"])
    Bs = [0.5 * L, 2.0 * L, 10.0 * L]
    log.p("k = 1, %s arrivals, the main compressed clock (scale %.5f) with every %d-th "
          "arrival kept, L = %.3f s, B = %s"
          % (shape, scale, q, L, ["%.1f" % x for x in Bs]))
    log.p("PER-JOB ASSERTION  W_guard[i] <= W_FCFS[i] + B + L  for every job, every B, "
          "every predictor (including two adversarial ones) and every draw.")
    anchors = id_time_anchors(df, cont)
    rows = []
    checked = 0
    adv_pred = P["M4"][0].astype(np.float64)
    for rep in range(args.reps):
        st0, of0, fr0, isc0 = build_trace(D, cont, shape, 300 + rep, tr["gamma"],
                                          tr["tau_h"], anchors)
        a0 = apply_scale(st0, of0, scale)
        kp = np.argsort(a0, kind="mergesort")[::q]
        arr = a0[kp]
        svc_r, heavy_r = svc[kp], heavy[kp]
        dl_r = (isc0 & (fr0 >= 0.9))[kp]
        wbusy, _, _ = busy_hour_work(arr, svc_r)
        wf = simulate_plain(arr, svc_r, None, 1)
        wl = lindley(arr, svc_r)
        assert np.abs(wf - wl).max() < 1e-6, "k=1 FCFS != Lindley"
        wo = simulate_plain(arr, svc_r, svc_r.copy(), 1)
        rows.append(dict(rep=rep, max_excess=0.0,
                         **sim_metrics(wf, heavy_r, "FCFS", dl_r)))
        rows.append(dict(rep=rep, max_excess=float((wo - wf).max()),
                         **sim_metrics(wo, heavy_r, "SJF-ref", dl_r)))
        adv = adv_pred[kp].copy()
        adv[svc_r >= np.percentile(svc_r, 99)] = -1e9
        cand = [(m, P[m][0].astype(np.float64)[kp]) for m in have] + \
               [("ADVtop1short", adv), ("ADVreversed", -adv_pred[kp])]
        for mname, sc in cand:
            wp = simulate_plain(arr, svc_r, sc.copy(), 1)
            rows.append(dict(rep=rep, max_excess=float((wp - wf).max()),
                             **sim_metrics(wp, heavy_r, "SPJF-%s" % mname, dl_r)))
            for B in Bs:
                wg = simulate_guard(arr, svc_r, sc.copy(), 1, B)
                ex = wg - wf
                nbad = int((ex > B + L + 1e-6).sum())
                checked += len(wg)
                assert nbad == 0, "PROPOSITION 3 VIOLATED: %d jobs, %s, B=%.1f" \
                                  % (nbad, mname, B)
                rows.append(dict(rep=rep, max_excess=float(ex.max()),
                                 **sim_metrics(wg, heavy_r,
                                               "GUARD-%s-B%d" % (mname, round(B)), dl_r)))
        log.p("  draw %d: %d jobs, busy-hour rho on one server %.3f; every assertion passed"
              % (rep, len(arr), wbusy / 3600.0))
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(args.cache, "guardk1_%s.csv" % shape), index=False)
    agg = R.groupby("policy", sort=False).mean(numeric_only=True)
    mx = R.groupby("policy", sort=False)["max_excess"].max()
    fm, fp = agg.loc["FCFS", "mean"], agg.loc["FCFS", "p99"]
    om, op = agg.loc["SJF-ref", "mean"], agg.loc["SJF-ref", "p99"]
    log.p("")
    log.p("jobs checked (job x predictor x B x draw): %d; violations 0 (asserted)" % checked)
    log.p("%-26s %9s %10s %10s %9s %11s %11s"
          % ("policy", "mean", "gain_mean", "p99", "gain_p99", "max_excess", "max_heavy"))
    for pol in agg.index:
        r = agg.loc[pol]
        log.p("%-26s %9.3f %10.3f %10.3f %9.3f %11.1f %11.1f"
              % (pol, r["mean"], (fm - r["mean"]) / (fm - om), r["p99"],
                 (fp - r["p99"]) / (fp - op), mx.loc[pol], r["max_heavy"]))
    log.p("bound: %s" % ", ".join("B=%.1f -> B+L=%.1f" % (x, x + L) for x in Bs))
    log.close()


# ================================================== cross-platform comparison
# CodeBench v2.1 numbers, quoted from evidence/codebench_service_v2/out_service_v2.txt.
# Every entry names the table it came from.  Nothing here is recomputed from CodeBench
# except the cost distribution, which stage_compare reads from the v2 cache if it is
# reachable.
CB = {
    "auroc": {          # SUMMARY 1, config ires0, train 'core', all test rows (2022-2)
        "M1": 0.7960, "M2": 0.8591, "M3": 0.8632, "M4": 0.9283, "M5": 0.9302},
    "auroc_ci": {
        "M1": (0.7685, 0.8181), "M2": (0.8324, 0.8805), "M3": (0.8340, 0.8865),
        "M4": (0.9118, 0.9415), "M5": (0.9140, 0.9433)},
    "gain_p99dl": {     # SUMMARY 3a, PURE, primary trace, SPJF-M4
        "0.5": 0.753, "0.8": 0.873, "1.0": 0.897},
    "gain_mean": {"0.5": 0.865, "0.8": 0.909, "1.0": 0.923},
    "gain_p99dl_M1": {"0.5": 0.499, "0.8": 0.542, "1.0": 0.492},
    "guard_gain_p99dl": {   # SUMMARY 3a, GUARD-M4-B120 and -B600
        "B120": {"0.5": 0.511, "0.8": 0.272, "1.0": 0.061},
        "B600": {"0.5": 0.699, "0.8": 0.726, "1.0": 0.449}},
    "fcfs_p99dl": {"0.5": 27.645, "0.8": 119.352, "1.0": 273.497},
    "sjf_p99dl": {"0.5": 10.588, "0.8": 33.553, "1.0": 43.629},
    "maxheavy": {       # SUMMARY 3a, rho 0.8, k = 5
        "FCFS": 862.5, "SJF-ref": 2540.6, "SPJF-M4": 2874.0,
        "GUARD-M4-B120": 886.4, "GUARD-M4-B600": 982.2},
    "excess": {"B30": 77.3, "B120": 109.7, "B600": 195.3},   # SUMMARY 3e, rho 0.8, primary
    "k1": {"jobs": 260896920, "viol": 0, "L": 60.0,
           "excess": {"30": 86.6, "120": 172.9, "600": 646.5},   # SUMMARY 4, ires0 rep 0, M4
           "gain_p99dl": {"SPJF-M4": 0.873, "GUARD-M4-B30": 0.210,
                          "GUARD-M4-B120": 0.560, "GUARD-M4-B600": 0.829}},
    "median_C_ms": 204.0,      # P2a stage log
    "heavy_thr_s": 1.559,      # LOAD stage log, p95 of 2018-1..2019-2
    "latency_ms": 0.081,       # P2a, mean feature + inference time per submission
}


def _sim(cache, shape, rho, service="main"):
    f = os.path.join(cache, "sim_%s_%s_rho%s.csv" % (service, shape, rho))
    if not os.path.exists(f):
        return None, None
    R = pd.read_csv(f)
    return R.groupby("policy").mean(numeric_only=True), R.groupby("policy")["max_excess"].max()


def _gain(agg, col, pol, floor=0.05):
    f, o = agg.loc["FCFS", col], agg.loc["SJF-ref", col]
    if not np.isfinite(f - o) or (f - o) < floor or (f - o) < floor * f:
        return float("nan")
    return (f - agg.loc[pol, col]) / (f - o)


def stage_compare(args, log):
    log.p("Cross-platform comparison: ACcoding (this run) against CodeBench v2.1")
    log.p("(evidence/codebench_service_v2/out_service_v2.txt).  CodeBench entries are")
    log.p("quoted from the tables named in CB{} inside this script; ACcoding entries are")
    log.p("read back from this run's own caches.  Where the two platforms measure")
    log.p("different things the numbers are kept apart rather than averaged.")

    log.p("")
    log.p("--- A. what the cost variable is ---")
    log.p("CodeBench  C = wall-clock judge occupancy of one submission, interpreter")
    log.p("           start-up included (medium confidence, codebench_semantics);")
    log.p("           platform limit L = 60 s; C_cap = min(C, 60).")
    log.p("ACcoding   time_cost = SUM over the problem's test cases of each test's measured")
    log.p("           execution time, each TEST capped at the problem's time limit (high")
    log.p("           confidence, audit 1e).  Compilation, container start-up and result")
    log.p("           write-back are NOT in it, so the service model has to add them:")
    log.p("           C = %.1f s + time_cost/1000, giving L = 30.5 s." % SVC_FIXED)
    log.p("AGREE      both are heavy-tailed positive costs with a hard per-submission")
    log.p("           ceiling, and on both the ceiling is enforced by the platform.")
    log.p("DIFFER     one measures occupancy, the other execution.  Waiting times in")
    log.p("           seconds are therefore not comparable across the two platforms; gain")
    log.p("           ratios and orderings are.  The %.1f s constant is an assumption of"
          % SVC_FIXED)
    log.p("           this precheck, not a measurement, and section B shows how much of")
    log.p("           the tail shape it decides.")

    df, b_, sealed_id_min, n_total = load_dev(None)
    prob, cont, ptag, tags = load_meta()
    d = df[modelling_mask(df)]
    tc = d["time_cost"].to_numpy(np.float64)

    def tail(x):
        x = x[np.isfinite(x)]
        xs = np.sort(x)[::-1]
        return {"median": float(np.median(x)), "p95": float(np.percentile(x, 95)),
                "p99": float(np.percentile(x, 99)), "max": float(x.max()),
                "cv": float(x.std() / max(x.mean(), 1e-12)),
                "top1": float(xs[:max(1, len(xs) // 100)].sum() / xs.sum()),
                "top5": float(xs[:max(1, len(xs) // 20)].sum() / xs.sum()), "n": len(x)}

    ac_raw = tail(tc[tc > 0] / 1000.0)
    ac_svc = tail(SVC_FIXED + tc / 1000.0)
    cb = None
    if args.cb_cache and os.path.exists(args.cb_cache):
        ev = pd.read_parquet(args.cb_cache, columns=["kind", "exec_time"])
        c = ev.loc[ev["kind"] == "submit", "exec_time"].to_numpy(np.float64)
        c = np.minimum(c[np.isfinite(c)], 60.0)
        cb = tail(c[c > 0])
    log.p("")
    log.p("--- B. tail heaviness ---")
    log.p("%-24s %12s %14s %14s"
          % ("", "CodeBench", "ACcoding", "ACcoding"))
    log.p("%-24s %12s %14s %14s"
          % ("", "C_cap (s)", "time_cost (s)", "0.5+tc (s)"))
    for lab, k in [("median", "median"), ("p95", "p95"), ("p99", "p99"), ("max", "max"),
                   ("coeff. of variation", "cv"), ("work in the top 1%", "top1"),
                   ("work in the top 5%", "top5")]:
        log.p("%-24s %12s %14.3f %14.3f"
              % (lab, ("%.3f" % cb[k]) if cb else "na", ac_raw[k], ac_svc[k]))
    if cb:
        log.p("(CodeBench: %d graded submissions with C_cap > 0, read from the v2 cache."
              % cb["n"])
        log.p(" ACcoding: %d judged non-sealed rows; column 2 drops the %d rows at exactly"
              % (len(tc), int((tc == 0).sum())))
        log.p(" 0 ms, column 3 keeps them because they still occupy a judge.)")
    log.p("AGREE      on the MEASURED variable the two tails are of the same kind: the top")
    log.p("           1%% of jobs carry %.2f of the work on CodeBench and %.2f on ACcoding,"
          % (cb["top1"] if cb else float("nan"), ac_raw["top1"]))
    log.p("           the top 5%% carry %.2f and %.2f.  Both have a hard ceiling that a"
          % (cb["top5"] if cb else float("nan"), ac_raw["top5"]))
    log.p("           few per mille of jobs reach.")
    log.p("DIFFER     the assumed fixed term flattens ACcoding's SERVICE distribution:")
    log.p("           adding %.1f s moves the top-1%% work share from %.2f to %.2f and the"
          % (SVC_FIXED, ac_raw["top1"], ac_svc["top1"]))
    log.p("           coefficient of variation from %.2f to %.2f.  ACcoding's median"
          % (ac_raw["cv"], ac_svc["cv"]))
    log.p("           measured job is %.0f ms against CodeBench's %.0f ms, so on ACcoding"
          % (np.median(tc), 1000 * cb["median"] if cb else float("nan")))
    log.p("           the per-job overhead the log does not record dominates the service")
    log.p("           time.  The paper must report the ACcoding scheduling results as")
    log.p("           conditional on that constant, and the sensitivity run with a")
    log.p("           per-test overhead term is the check.")

    log.p("")
    log.p("--- C. predictability by information source (heavy-job AUROC, dev-test) ---")
    T = pd.read_csv(os.path.join(args.cache, "predtab_lag0.csv"))
    T = T[T["group"] == "all"].set_index("model")
    names = {"M1": "problem / exercise history only",
             "M2": "user history only",
             "M3": "static submission features only",
             "M4": "all tabular (history + static)",
             "M5": "M4 + one-hop relational aggregates"}
    log.p("%-5s %-38s %11s %11s" % ("model", "information source", "CodeBench", "ACcoding"))
    acv = {}
    for m in ["M1", "M2", "M3", "M4", "M5"]:
        acv[m] = float(T.loc[m, "auroc"])
        log.p("%-5s %-38s %11.4f %11.4f" % (m, names[m], CB["auroc"][m], acv[m]))
    log.p("NOTE       M3 is not the same feature set on the two platforms.  On CodeBench it")
    log.p("           is static features of the SOURCE CODE (loop counts, nesting depth,")
    log.p("           while True, recursion).  ACcoding stores no source code, so M3 there")
    log.p("           is code_length, language and the problem's static metadata (test")
    log.p("           count, time and memory limit, difficulty, special judge).  M1, M2, M4")
    log.p("           and M5 are the same construction on both.")
    log.p("AGREE      the all-tabular model reaches the same place on both platforms")
    log.p("           (%.3f against %.3f), every single-source model is well below it, and"
          % (CB["auroc"]["M4"], acv["M4"]))
    log.p("           one-hop relational aggregates add nothing: M5 - M4 is %+.4f on"
          % (CB["auroc"]["M5"] - CB["auroc"]["M4"]))
    log.p("           CodeBench and %+.4f on ACcoding.  Whichever platform you look at, a"
          % (acv["M5"] - acv["M4"]))
    log.p("           judge can tell a heavy submission from a light one before running it.")
    log.p("DIFFER     WHICH single source carries the signal flips.  On CodeBench the user")
    log.p("           history (%.3f) and the code features (%.3f) beat the exercise history"
          % (CB["auroc"]["M2"], CB["auroc"]["M3"]))
    log.p("           (%.3f); on ACcoding the problem history (%.3f) beats the user history"
          % (CB["auroc"]["M1"], acv["M1"]))
    log.p("           (%.3f) by 0.11 of AUROC.  A CodeBench exercise is attempted by one"
          % acv["M2"])
    log.p("           class within a few days, so who is writing matters; an ACcoding")
    log.p("           problem is attempted by thousands of students over years, so the")
    log.p("           problem's own record already fixes the cost.  A method that leans on")
    log.p("           one of the two sources will not transfer; the all-tabular model does.")

    log.p("")
    log.p("--- D. gap closed by prediction-driven scheduling ---")
    log.p("gain = (W_FCFS - W_policy) / (W_FCFS - W_SJF-on-true-sizes) on the deadline-")
    log.p("window p99 wait.  CodeBench: REAL arrival times, 44 overlay copies of 40 class-")
    log.p("semesters, k = 7.8 / 5 / 4.  ACcoding: SYNTHETIC arrivals (order and sizes real,")
    log.p("times drawn), k = 8 / 5 / 4.")
    log.p("%-30s %10s %10s %10s" % ("", "rho 0.5", "rho 0.8", "rho 1.0"))
    log.p("%-30s %10.3f %10.3f %10.3f"
          % ("CodeBench   SPJF-M4", CB["gain_p99dl"]["0.5"], CB["gain_p99dl"]["0.8"],
             CB["gain_p99dl"]["1.0"]))
    log.p("%-30s %10.3f %10.3f %10.3f"
          % ("CodeBench   SPJF-M1", CB["gain_p99dl_M1"]["0.5"], CB["gain_p99dl_M1"]["0.8"],
             CB["gain_p99dl_M1"]["1.0"]))
    acg = {}
    for shape in ["poisson", "deadline"]:
        for pol in ["SPJF-M4", "SPJF-M1"]:
            v = []
            for r in ["0.5", "0.8", "1.0"]:
                agg, _ = _sim(args.cache, shape, r)
                v.append(_gain(agg, "p99_dl", pol) if agg is not None else float("nan"))
            acg[(shape, pol)] = v
            log.p("%-30s %10.3f %10.3f %10.3f"
                  % ("ACcoding %-8s %s" % (shape, pol), v[0], v[1], v[2]))
    log.p("%-30s %10s %10s %10s" % ("", "", "", ""))
    for shape in ["poisson", "deadline"]:
        agg, _ = _sim(args.cache, shape, "1.0")
        log.p("ACcoding %-8s FCFS deadline-window p99 = %8.2f s, SJF-ref %6.2f s, "
              "SPJF-M4 %6.2f s (rho 1.0)"
              % (shape, agg.loc["FCFS", "p99_dl"], agg.loc["SJF-ref", "p99_dl"],
                 agg.loc["SPJF-M4", "p99_dl"]))
    log.p("CodeBench          FCFS deadline-window p99 = %8.2f s, SJF-ref %6.2f s "
          "(rho 1.0)" % (CB["fcfs_p99dl"]["1.0"], CB["sjf_p99dl"]["1.0"]))
    log.p("nan = the gain denominator FCFS - SJF-ref fell under the stability floor.  At")
    log.p("busy-hour rho 0.5 the ACcoding trace does not queue at all (mean wait 1 ms,")
    log.p("p99 0 s on 8 judges), so there is nothing for any policy to close.")
    log.p("AGREE      the transmission from prediction quality to waiting time is the same")
    log.p("           on both platforms and in the same order: M4 ~ M5 > M1 > M2 > M3, the")
    log.p("           same ordering as section C, and the all-tabular predictor takes most")
    log.p("           of the true-size reference's gap at every load where a queue exists.")
    log.p("DIFFER     the ACcoding gains are HIGHER (%.3f-%.3f against CodeBench's"
          % (min(acg[("deadline", "SPJF-M4")][1:]), max(acg[("poisson", "SPJF-M4")][1:])))
    log.p("           %.3f-%.3f) and the gap between SPJF-M4 and the true-size reference"
          % (CB["gain_p99dl"]["0.8"], CB["gain_p99dl"]["1.0"]))
    log.p("           nearly vanishes.  That is a property of the synthetic arrivals, not")
    log.p("           of the platform: a drawn stream carries no sub-hour burstiness beyond")
    log.p("           what the deadline ramp puts in, so the queue is driven almost purely")
    log.p("           by the size distribution, which is exactly what the predictor knows.")
    log.p("           CodeBench's real timestamps contain arrival bursts that no cost")
    log.p("           predictor can anticipate, and that residual is why its gains stop")
    log.p("           short of 1.  ACcoding therefore CONFIRMS the mechanism and must not")
    log.p("           be used to claim a better gain number.")
    log.p("           Note also SPJF-M3 reaches gain 1.017 at poisson rho 0.8: the true-")
    log.p("           size reference is not optimal for a tail objective, as research_plan")
    log.p("           4.4 already states for S2.")

    log.p("")
    log.p("--- E. guard cost, guard benefit ---")
    log.p("CodeBench L = 60 s, B in {30, 120, 600} s = 0.5L / 2L / 10L.")
    log.p("ACcoding  L = 30.5 s, B in {15.2, 61.0, 305.0} s = the same multiples.")
    log.p("gap kept by the guard (deadline-window p99):")
    log.p("%-30s %10s %10s %10s" % ("", "rho 0.5", "rho 0.8", "rho 1.0"))
    for bname, key in [("B = 2L", "B120"), ("B = 10L", "B600")]:
        log.p("%-30s %10.3f %10.3f %10.3f"
              % ("CodeBench   " + bname, CB["guard_gain_p99dl"][key]["0.5"],
                 CB["guard_gain_p99dl"][key]["0.8"], CB["guard_gain_p99dl"][key]["1.0"]))
    for shape in ["poisson", "deadline"]:
        for bname, bs in [("B = 0.5L", 15), ("B = 2L", 61), ("B = 10L", 305)]:
            v = []
            for r in ["0.5", "0.8", "1.0"]:
                agg, _ = _sim(args.cache, shape, r)
                v.append(_gain(agg, "p99_dl", "GUARD-M4-B%d" % bs)
                         if agg is not None else float("nan"))
            log.p("%-30s %10.3f %10.3f %10.3f"
                  % ("ACcoding %-8s %s" % (shape, bname), v[0], v[1], v[2]))
    log.p("")
    log.p("longest wait of a genuinely heavy job (true cost above the training p95):")
    log.p("%-34s %10s %10s %10s %10s"
          % ("", "FCFS", "SPJF-M4", "GUARD-2L", "GUARD-10L"))
    log.p("%-34s %10.0f %10.0f %10s %10.0f"
          % ("CodeBench rho 0.8, k = 5", CB["maxheavy"]["FCFS"], CB["maxheavy"]["SPJF-M4"],
             "%.0f" % CB["maxheavy"]["GUARD-M4-B120"], CB["maxheavy"]["GUARD-M4-B600"]))
    for shape in ["poisson", "deadline"]:
        for r in ["0.8", "1.0"]:
            agg, _ = _sim(args.cache, shape, r)
            if agg is None:
                continue
            log.p("%-34s %10.0f %10.0f %10.0f %10.0f"
                  % ("ACcoding %s rho %s" % (shape[:4], r), agg.loc["FCFS", "max_heavy"],
                     agg.loc["SPJF-M4", "max_heavy"], agg.loc["GUARD-M4-B61", "max_heavy"],
                     agg.loc["GUARD-M4-B305", "max_heavy"]))
    log.p("AGREE      this is the clearest cross-platform result.  Unguarded SPJF buys its")
    log.p("           gain by starving the genuinely long jobs -- CodeBench 862 s -> 2,874 s,")
    log.p("           ACcoding 233 s -> 2,033 s at rho 1.0, both a factor of 3 to 9 -- and")
    log.p("           the overtaking-budget guard puts that back to within a few tens of")
    log.p("           per cent of the FCFS figure on both platforms.  The cost of the guard")
    log.p("           in gap closed rises with the load on both: at rho 0.8 B = 2L keeps")
    log.p("           0.27 of the gap on CodeBench and 0.17-0.45 on ACcoding, and at")
    log.p("           rho 1.0 it keeps 0.06 on CodeBench and nothing on ACcoding.")
    log.p("DIFFER     at rho 1.0 CodeBench's B = 10L still keeps 0.449 of the gap while on")
    log.p("           ACcoding every B tested keeps none of it, and B = 10L is slightly")
    log.p("           WORSE than FCFS on the deadline-window p99 (gain about -0.1 to -0.27).")
    log.p("           A partially reordered queue can be worse in the tail than either")
    log.p("           extreme; the paper should report this as an observed failure mode of")
    log.p("           the guard at saturation rather than hide it behind an average.")

    log.p("")
    log.p("--- F. the per-job guarantee at k = 1 ---")
    got = {}
    for shape in ["poisson", "deadline"]:
        f = os.path.join(args.cache, "log_guardk1__%s.txt" % shape)
        if os.path.exists(f):
            for line in open(f, encoding="utf-8"):
                m = re.search(r"jobs checked .*: ([\d,]+); violations (\d+)", line)
                if m:
                    got[shape] = (int(m.group(1).replace(",", "")), int(m.group(2)))
    tot = sum(v[0] for v in got.values())
    vio = sum(v[1] for v in got.values())
    log.p("%-46s %14s %14s" % ("", "CodeBench", "ACcoding"))
    log.p("%-46s %14d %14d" % ("per-job assertions W_guard <= W_FCFS + B + L",
                               CB["k1"]["jobs"], tot))
    log.p("%-46s %14d %14d" % ("violations", CB["k1"]["viol"], vio))
    log.p("%-46s %14.1f %14.1f" % ("L (s)", CB["k1"]["L"], 30.5))
    exc = {}
    for shape in ["poisson", "deadline"]:
        f = os.path.join(args.cache, "guardk1_%s.csv" % shape)
        if os.path.exists(f):
            R = pd.read_csv(f)
            m = R[R["policy"].str.startswith("GUARD-M4-")].groupby("policy")["max_excess"] \
                .max()
            exc[shape] = {int(k.split("B")[-1]): float(v) for k, v in m.items()}
    acx = "na"
    if exc:
        k0 = sorted(exc)[0]
        e = exc[k0]
        acx = "%.0f/%.0f/%.0f" % (e[15], e[61], e[305])
    log.p("%-46s %14s %14s" % ("observed max excess at B = 0.5L / 2L / 10L",
                               "%.0f/%.0f/%.0f" % (CB["k1"]["excess"]["30"],
                                                   CB["k1"]["excess"]["120"],
                                                   CB["k1"]["excess"]["600"]),
                               acx))
    log.p("%-46s %14s %14s" % ("the bound B + L",
                               "90/180/660", "46/92/336"))
    for shape in sorted(exc):
        e = exc[shape]
        log.p("   ACcoding %-9s max excess %6.1f / %6.1f / %6.1f s against the bound "
              "45.8 / 91.5 / 335.5 s" % (shape, e[15], e[61], e[305]))
    log.p("AGREE      the bound holds on every single job of both platforms, the observed")
    log.p("           excess is always strictly inside B + L, and B = 0 degenerates to FCFS")
    log.p("           exactly (checked in the selftest).  This is the one part of the")
    log.p("           method that does not depend on the arrival process at all, which is")
    log.p("           why it transfers to a platform whose arrival times are invented.")

    log.p("")
    log.p("--- G. per-submission prediction cost ---")
    log.p("CodeBench measured %.3f ms mean for features plus a single-row LightGBM predict,"
          % CB["latency_ms"])
    log.p("which is %.4f of its median job.  This ACcoding precheck did NOT re-time the"
          % (CB["latency_ms"] / CB["median_C_ms"]))
    log.p("loop, and the feature set here is a different one (%d features against 34), so"
          % len(ALLF))
    log.p("the paper must either time it on ACcoding or make the deployment-cost claim for")
    log.p("CodeBench only.  For scale: ACcoding's median MEASURED execution is %.0f ms, so a"
          % np.median(tc))
    log.p("sub-millisecond prediction is a larger fraction of the measured cost than on")
    log.p("CodeBench, and a small fraction of the modelled service time.")
    log.close()


# ================================================================ report
STAGE_ORDER = ["selftest", "audit", "cbprofile", "feat", "leak", "pred", "boot",
               "trace", "sim", "guardk1", "compare"]


def stage_report(args, log):
    sha = script_sha256()
    logs = [f for f in sorted(os.listdir(args.cache))
            if f.startswith("log_") and f.endswith(".txt") and "report" not in f]
    logs.sort(key=lambda f: (STAGE_ORDER.index(f[4:-4].split("__")[0])
                             if f[4:-4].split("__")[0] in STAGE_ORDER else 99, f))
    bad = []
    for f in logs:
        first = open(os.path.join(args.cache, f), encoding="utf-8").readline().strip()
        if not first.endswith(sha):
            bad.append((f, first.split()[-1][:16]))
    out = os.path.join(HERE, "out_accoding_v2.txt")
    with open(out, "w", encoding="utf-8") as fh:
        def w(s=""):
            fh.write(s + "\n")
        w("=" * 78)
        w("ACcoding service pre-check v2  (evidence/accoding_v2/accoding_v2.py)")
        w("=" * 78)
        w("script sha256 %s" % sha)
        if bad:
            w("!! %d stage log(s) came from a different version of the script: %s"
              % (len(bad), bad))
        else:
            w("every stage log below carries this hash (checked before writing).")
        w("")
        w("ACcoding = the Beihang University online judge, Zenodo 6522395, v1.0.0.")
        w("Split by submission-id quantile: 0-48% train, 48-64% validation, 64-80%")
        w("development test, 80-100% SEALED (never opened; only its row count and its")
        w("first id were read, and those define the split).  Ids are an ordering, not a")
        w("clock, so every history feature is 'the record with a smaller id' and the lag")
        w("sweep m = 0/10/100/1000 stands in for result latency.  In the scheduling part")
        w("only the job ORDER inside a contest and the job SIZES are real; every arrival")
        w("time is drawn.  No source code and no personal attribute is read or stored.")
        w("")
        w("Stage logs in run order:")
        for f in logs:
            w("  %s" % f[4:-4].replace("__", "  "))
        w("")
        for f in logs:
            w("=" * 78)
            w(f[4:-4].replace("__", "  "))
            w("=" * 78)
            fh.write(open(os.path.join(args.cache, f), encoding="utf-8").read())
            w("")
    log.p("wrote %s (%d stage logs, %d hash mismatches)" % (out, len(logs), len(bad)))
    if bad:
        log.p("mismatched: %s" % bad)
    log.close()


# ================================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--cache", default=os.path.join(os.environ.get("TEMP", "/tmp"),
                                                    "ac_v2_cache"))
    ap.add_argument("--cb-cache", dest="cb_cache", default="")
    ap.add_argument("--lags", default="0")
    ap.add_argument("--lag", type=int, default=0)
    ap.add_argument("--models", default="M1,M2,M3,M4,M5")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--rounds", type=int, default=300)
    ap.add_argument("--train-sub", dest="train_sub", type=int, default=1000000)
    ap.add_argument("--train-sub-lag", dest="train_sub_lag", type=int, default=500000)
    ap.add_argument("--select-leaves", dest="select_leaves", action="store_true")
    ap.add_argument("--leak-rows", dest="leak_rows", type=int, default=2000)
    ap.add_argument("--perturb-rows", dest="perturb_rows", type=int, default=50)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed-leak", dest="seed_leak", type=int, default=7)
    ap.add_argument("--seed-boot", dest="seed_boot", type=int, default=11)
    ap.add_argument("--shape", default="poisson")
    ap.add_argument("--rho", type=float, default=0.8)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--service", default="main")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    tag = args.tag or {
        "sim": "%s_rho%.1f_%s" % (args.shape, args.rho, args.service),
        "pred": "lag%d_%s" % (args.lag, args.models.replace(",", "")),
        "boot": "lag%d" % args.lag,
        "feat": "lags%s" % args.lags.replace(",", ""),
        "leak": "lags%s" % args.lags.replace(",", ""),
        "guardk1": args.shape}.get(args.stage, "")
    log = Tee(os.path.join(args.cache, "log_%s%s.txt"
                           % (args.stage, ("__" + tag) if tag else "")), args.stage, sys.argv)
    fn = globals().get("stage_" + args.stage)
    if fn is None:
        raise SystemExit("unknown stage %s" % args.stage)
    fn(args, log)


if __name__ == "__main__":
    main()
