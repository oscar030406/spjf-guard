"""Independent re-check of what EXECUTION TIME (E) and the '== SUBMITION (...)' header time mean.

Written as a skeptic's replication of t1_lag.py / t2_gaps.py / t3_t4_t5.py.  It shares no code with
them: its own archive parser, its own cache (cache/verify_independent/), its own matching.

Semesters: 2018-2, 2019-2, 2021-2, 2022-1 (every DEV semester with EXECUTION TIME was already
pooled by the primary parse, so no disjoint semester exists; results are therefore also given per
class, each class being a separate replication).  Sealed semesters are refused.

Stage "build"   stream the archives (tarfile r|gz) and cache, per semester:
  vi_blocks_<sem>  one row per SUBMITION/TEST block: file key, seq, kind, header ts, E, n_tc,
                   n_tc with empty user output, grade, has_error, killed
  vi_cm_<sem>      one row per distinct codemirror "submit" event: file key, client ts, verdict
                   class of the system feedback (correct / wrong / p<N> for "hit N%"), and the time
                   from the previous client event of each kind (edit, key, mouse, blur, focus,
                   kill_program, saida_testar, any activity) to this submit event
  vi_kill_<sem>    codemirror kill_program events (file key, client ts)
  vi_fmt_<sem>     counts of zero-padded vs unpadded date fields in codemirror lines
  Only timestamps and event types are read from codemirror; for "submit" the first bytes of the
  system feedback are mapped to a verdict class.  No code, output or keystroke payload is stored.
Stage "analyze" prints the tables (stdout -> verify_independent.txt).

Tests
  V0  clock and format: unpadded date fields in codemirror lines (JS client formatting?)
  V1  per-user clock offset from short runs (E < 1 s): peak of all pairwise lags between
      same-file, same-verdict SUBMITION blocks and codemirror submit feedback events
  V2  long runs (E >= 1 s): is the feedback event at R = header + offset (header = end) or at
      R + E (header = start)?  Neutral matching: the same-verdict event nearest to R + E/2 inside
      [R - 5, R + E + 5]; placebo window at R - E.  By E bin, semester and class.
  V3  client-only quiet gap: time from the last client activity event to the feedback event,
      against E, with a permutation null (E shuffled among matched long runs).  If the click came
      E seconds before the feedback, a gap >= E is frequent; otherwise the gap does not know E.
  V4  kill_program events: at R (header = end) or at R + E (header = start)?
  V5  server-only gaps: previous/next block of the same user against E, with a permutation null
      and a histogram of (pre - E) around 0, per era and class
  V6  E against the number of test cases (correct runs; runs with all outputs empty)
  V7  60-s cap date inside 2019-2; max E per month

Usage (clear PYTHONHOME, PYTHONPATH, UV_INTERNAL__PYTHONHOME first):
  uv run --with pandas --with numpy --with pyarrow python verify_independent.py build
  uv run --with pandas --with numpy --with pyarrow python verify_independent.py analyze > verify_independent.txt
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import re
import sys
import tarfile
import time
from calendar import timegm
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
ARCH = os.path.join(ROOT, "data", "codebench", "archives")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "verify_independent")
SEMS = ["2018_2", "2019_2", "2021_2", "2022_1"]
SEALED = {"2023_1", "2023_2", "2024_1"}
SEED = 20260918
FKEY = ["class", "user", "assessment", "exercise"]

pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 400)

# ------------------------------------------------------------------------------------------ #
# build                                                                                        #
# ------------------------------------------------------------------------------------------ #
HDR = re.compile(rb"(?m)^== (SUBMITION|TEST) \((\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2}):(\d{1,2})\)")
GRADE = re.compile(rb"(?m)^-- GRADE:[ \t]*\r?\n[ \t]*([0-9.]+)\s*%")
CMLINE = re.compile(rb"(?m)^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?#([A-Za-z_\-]+)")
PCT = re.compile(rb"(\d+(?:\.\d+)?)\s*%")   # "You're almost there! Your code is 67% correct, ..."
CAT = {b"change": 0, b"keydown": 1, b"keypress": 1, b"keyup": 1, b"keyHandled": 1,
       b"mousedown": 2, b"touchstart": 2, b"dblclick": 2, b"contextmenu": 2, b"copy": 2,
       b"blur": 3, b"focus": 4, b"kill_program": 5, b"saida_testar": 6, b"tab-click": 7,
       b"submit": 9}
CATNAME = ["edit", "key", "mouse", "blur", "focus", "kill", "test", "tab"]
_DAY: dict = {}


def day0(y, mo, d) -> int:
    k = (y, mo, d)
    v = _DAY.get(k)
    if v is None:
        v = timegm((int(y), int(mo), int(d), 0, 0, 0, 0, 0, 0))
        _DAY[k] = v
    return v


def parse_exec(raw: bytes):
    hs = list(HDR.finditer(raw))
    rows = []
    for i, h in enumerate(hs):
        blk = raw[h.end(): hs[i + 1].start() if i + 1 < len(hs) else len(raw)]
        g = h.groups()
        ts = day0(g[1], g[2], g[3]) + int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6])
        kind = "S" if g[0] == b"SUBMITION" else "T"
        e = np.nan
        j = blk.find(b"\n-- EXECUTION TIME:")
        if j >= 0:
            nxt = blk[j + 19: j + 60].split(b"\n")
            for tok in nxt[1:3] if nxt and not nxt[0].strip() else nxt[:1]:
                tok = tok.strip()
                if tok:
                    try:
                        e = float(tok)
                    except ValueError:
                        pass
                    break
        parts = blk.split(b"\n-- TEST CASE ")
        n_tc = len(parts) - 1
        n_empty = 0
        for p in parts[1:]:
            k = p.find(b"---- user output:")
            if k >= 0:
                rest = p[k + 17:]
                cut = re.search(rb"(?m)^(?:-- (?:GRADE|ERROR|TEST CASE)|\*-\*-\*)", rest)
                if not (rest[: cut.start()] if cut else rest).strip():
                    n_empty += 1
        gm = GRADE.search(blk)
        grade = float(gm.group(1)) if gm else np.nan
        k = blk.find(b"\n-- ERROR:")
        has_err = k >= 0
        killed = False
        if has_err:
            tail = [x.strip() for x in blk[k + 10:].split(b"\n") if x.strip() and not x.startswith(b"*-*-*")]
            killed = bool(tail) and tail[-1] == b"Killed"
        rows.append((i, kind, ts, e, n_tc, n_empty, grade, has_err, killed))
    return rows


def parse_cm(raw: bytes, fmt: np.ndarray):
    ts, cat, fb = [], [], []
    for m in CMLINE.finditer(raw):
        c = CAT.get(m.group(8))
        if c is None:
            continue
        y, mo, d, hh, mi, ss, ms = m.groups()[:7]
        # format evidence: month/day/hour field value < 10 written with one digit?
        if int(mo) < 10:
            fmt[0 if len(mo) == 2 else 1] += 1
        if int(hh) < 10:
            fmt[2 if len(hh) == 2 else 3] += 1
        t = day0(y, mo, d) + int(hh) * 3600 + int(mi) * 60 + int(ss) + (int(ms) / 1000.0 if ms else 0.0)
        ts.append(t)
        cat.append(c)
        if c == 9:
            p = raw[m.end() + 1: m.end() + 80]
            if p.startswith(b"Congrat"):
                fb.append("correct")
            elif p.startswith(b"Your code did"):
                fb.append("wrong")
            else:
                mm = PCT.search(p)
                fb.append(f"p{float(mm.group(1)):g}" if mm else "other")
        else:
            fb.append("")
    if not ts:
        return [], []
    ts = np.asarray(ts)
    cat = np.asarray(cat, dtype=np.int8)
    fb = np.asarray(fb, dtype=object)
    o = np.argsort(ts, kind="stable")
    ts, cat, fb = ts[o], cat[o], fb[o]
    act_idx = np.flatnonzero(cat != 9)
    act = ts[act_idx]
    per = [ts[cat == k] for k in range(8)]
    sub = np.flatnonzero(cat == 9)
    out, seen = [], set()
    for i in sub:
        s = ts[i]
        key = (round(s, 3), fb[i])
        if key in seen:          # exact duplicate line (client resend)
            continue
        seen.add(key)
        gaps = []
        for arr in per:
            j = np.searchsorted(arr, s - 0.0005)       # events strictly before s
            gaps.append(s - arr[j - 1] if j > 0 else np.nan)
        j = np.searchsorted(act, s - 0.0005)
        g_any = s - act[j - 1] if j > 0 else np.nan
        prev_cat = int(cat[act_idx[j - 1]]) if j > 0 else -1
        out.append((s, fb[i], g_any, prev_cat, *gaps))
    kills = list(per[5])
    return out, kills


def build(tag: str) -> str:
    assert tag not in SEALED
    t0 = time.time()
    tf = tarfile.open(os.path.join(ARCH, f"cb_dataset_{tag}_v1.81.tar.gz"), "r|gz")
    B, C, K = [], [], []
    fmt = np.zeros(4, dtype=np.int64)
    for m in tf:
        if not m.isfile():
            continue
        p = m.name.split("/")
        if len(p) < 6 or p[2] != "users" or p[4] not in ("executions", "codemirror"):
            continue
        a, _, x = os.path.splitext(p[-1])[0].partition("_")
        key = (p[1], p[3], a, x)
        raw = tf.extractfile(m).read()
        if p[4] == "executions":
            B += [key + r for r in parse_exec(raw)]
        else:
            rows, kills = parse_cm(raw, fmt)
            C += [key + r for r in rows]
            K += [key + (t,) for t in kills]
    tf.close()
    os.makedirs(OUT, exist_ok=True)
    b = pd.DataFrame(B, columns=FKEY + ["seq", "kind", "ts", "E", "n_tc", "n_empty", "grade", "has_err", "killed"])
    c = pd.DataFrame(C, columns=FKEY + ["s", "fb", "g_any", "prev_cat"] + [f"g_{n}" for n in CATNAME])
    k = pd.DataFrame(K, columns=FKEY + ["t"])
    b.to_parquet(os.path.join(OUT, f"vi_blocks_{tag}.parquet"), index=False)
    c.to_parquet(os.path.join(OUT, f"vi_cm_{tag}.parquet"), index=False)
    k.to_parquet(os.path.join(OUT, f"vi_kill_{tag}.parquet"), index=False)
    pd.DataFrame([fmt], columns=["mo_padded", "mo_unpadded", "hh_padded", "hh_unpadded"]).to_parquet(
        os.path.join(OUT, f"vi_fmt_{tag}.parquet"), index=False)
    return f"{tag}: blocks={len(b):,} cm_submit={len(c):,} kills={len(k):,} {time.time() - t0:.0f}s"


# ------------------------------------------------------------------------------------------ #
# analyze helpers                                                                              #
# ------------------------------------------------------------------------------------------ #
def load(prefix: str) -> pd.DataFrame:
    out = []
    for s in SEMS:
        d = pd.read_parquet(os.path.join(OUT, f"{prefix}_{s}.parquet"))
        d.insert(0, "sem", s)
        out.append(d)
    d = pd.concat(out, ignore_index=True)
    for c in FKEY:
        if c in d:
            d[c] = d[c].astype(str)
    return d


def qs(x, ps=(0.1, 0.25, 0.5, 0.75, 0.9)) -> str:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return "n=0"
    return f"n={x.size:,} " + " ".join(f"p{int(p * 100)}={v:.2f}" for p, v in zip(ps, np.quantile(x, ps)))


def verdict_block(g: pd.Series) -> pd.Series:
    v = np.where(g == 100, "correct", np.where((g > 0) & (g < 100), "p" + g.fillna(0).round().astype(int).astype(str), "wrong"))
    return pd.Series(v, index=g.index)


def verdict_cm(fb: pd.Series) -> pd.Series:
    def f(x):
        if x.startswith("p"):
            try:
                return "p" + str(int(round(float(x[1:]))))
            except ValueError:
                return x
        return x
    return fb.map(f)


EBINS = [1, 2, 5, 10, 20, 40, 60, 200, 1000, 1e6]


# ------------------------------------------------------------------------------------------ #
# V1 offsets                                                                                   #
# ------------------------------------------------------------------------------------------ #
def offsets(sb: pd.DataFrame, cm: pd.DataFrame) -> pd.DataFrame:
    short = sb[sb.E < 1][["sem", "user", "fid", "vc", "ts"]]
    pairs = short.merge(cm[["fid", "vc", "s"]], on=["fid", "vc"])
    pairs["lag"] = pairs.s - pairs.ts
    pairs = pairs[pairs.lag.abs() < 3 * 3600]
    pairs["lb"] = np.floor(pairs.lag).astype(np.int64)
    h = pairs.groupby(["sem", "user", "lb"]).size().rename("n").reset_index()
    # smooth over +-1 s and take the peak per user
    h = h.sort_values(["sem", "user", "lb"])
    hs = []
    for (sem, u), d in h.groupby(["sem", "user"], sort=False):
        lb, n = d.lb.to_numpy(), d.n.to_numpy()
        cs = np.concatenate([[0], np.cumsum(n)])
        sm = cs[np.searchsorted(lb, lb + 1, side="right")] - cs[np.searchsorted(lb, lb - 1, side="left")]
        i = int(np.argmax(sm))
        far = sm[np.abs(lb - lb[i]) > 5]
        hs.append((sem, u, int(lb[i]), int(sm[i]), int(far.max()) if far.size else 0, int(n.sum())))
    pk = pd.DataFrame(hs, columns=["sem", "user", "peak_lb", "peak_n", "second_n", "pairs_n"])
    pairs = pairs.merge(pk[["sem", "user", "peak_lb"]], on=["sem", "user"])
    near = pairs[(pairs.lag >= pairs.peak_lb - 1) & (pairs.lag < pairs.peak_lb + 2)]
    off = near.groupby(["sem", "user"]).lag.median().rename("off")
    pk = pk.merge(off.reset_index(), on=["sem", "user"], how="left")
    pk["ok"] = (pk.peak_n >= 3) & (pk.peak_n >= 2 * pk.second_n)
    return pk


# ------------------------------------------------------------------------------------------ #
# analyze                                                                                      #
# ------------------------------------------------------------------------------------------ #
def analyze():
    rng = np.random.default_rng(SEED)
    b = load("vi_blocks")
    cm = load("vi_cm")
    kl = load("vi_kill")
    fmt = pd.concat([pd.read_parquet(os.path.join(OUT, f"vi_fmt_{s}.parquet")).assign(sem=s) for s in SEMS])
    b["era"] = np.where(b["sem"].str.startswith(("2018", "2019")), "2018-19", "2020-22")
    # integer ids for the file pair (semester, class, user, assessment, exercise) and the verdict
    keys = pd.concat([d[["sem"] + FKEY] for d in (b, cm, kl)], ignore_index=True).astype(str).agg("|".join, axis=1)
    codes, _ = pd.factorize(keys)
    b["fid"], cm["fid"], kl["fid"] = codes[:len(b)], codes[len(b):len(b) + len(cm)], codes[len(b) + len(cm):]
    b["co_n"] = b.groupby(["sem", "user", "ts"]).ts.transform("size")   # blocks of the user ending in the same second
    sb = b[b.kind == "S"].copy()
    sb["v"] = verdict_block(sb.grade)
    cm["v"] = verdict_cm(cm.fb.astype(str))
    vcodes, vuniq = pd.factorize(pd.concat([sb.v, cm.v], ignore_index=True))
    sb["vc"], cm["vc"] = vcodes[:len(sb)], vcodes[len(sb):]

    print("=== V0 coverage (own parser) ===")
    t = pd.DataFrame({
        "blocks": b.groupby("sem").size(), "submits": sb.groupby("sem").size(),
        "E_present": sb.groupby("sem").E.apply(lambda x: x.notna().mean()).round(4),
        "cm_submit_distinct": cm.groupby("sem").size(), "kills": kl.groupby("sem").size(),
        "classes": b.groupby("sem")["class"].nunique(), "users": b.groupby("sem").user.nunique()})
    print(t.to_string())
    print("\n=== V0 codemirror date formatting (a JS client writes unpadded fields; a server strftime pads) ===")
    print(fmt.set_index("sem").to_string())

    # ---------------- V1 ----------------
    pk = offsets(sb, cm)
    good = pk[pk.ok]
    print("\n=== V1 per-user clock offset (client feedback ts - server header ts, short runs E<1 s) ===")
    print(f"  user-semesters with pairs: {len(pk):,}; with a clear peak (>=3 pairs, 2x any other peak): {len(good):,}")
    hr = np.round(good.off / 3600).astype(int)
    print("  offset rounded to whole hours:", hr.value_counts().sort_index().to_dict())
    print("  offset minus whole hours (s):", qs(good.off - 3600 * hr, (0.05, 0.25, 0.5, 0.75, 0.95)))
    for s, d in good.groupby("sem"):
        h = np.round(d.off / 3600).astype(int)
        print(f"   {s}: n={len(d)} share 0h={np.mean(h == 0):.3f} +1h={np.mean(h == 1):.3f} "
              f"-1h={np.mean(h == -1):.3f} other={np.mean(~h.isin([-1, 0, 1])):.3f} "
              f"median residual={np.median(d.off - 3600 * h):.2f}s")

    sb = sb.merge(good[["sem", "user", "off"]], on=["sem", "user"], how="left")
    sb["R"] = sb.ts + sb.off

    # ---------------- V2 ----------------
    print("\n=== V2 where is the same-verdict feedback event of a long run?  R = header + user offset ===")
    L = sb[(sb.E >= 1) & sb.off.notna()].reset_index(drop=True)
    L["bid"] = np.arange(len(L))
    pr = L[["bid", "fid", "vc", "R", "E"]].merge(cm[["fid", "vc", "s"]], on=["fid", "vc"])
    pr["lag"] = pr.s - pr.R
    agg = pr.assign(a0=pr.lag.abs(), aE=(pr.lag - pr.E).abs(), aP=(pr.lag + pr.E).abs())
    mins = agg.groupby("bid")[["a0", "aE", "aP"]].min()
    L = L.join(mins, on="bid")
    # neutral match: nearest to the midpoint R + E/2 inside [R-5, R+E+5]
    w = pr[(pr.lag >= -5) & (pr.lag <= pr.E + 5)].copy()
    w["dm"] = (w.lag - w.E / 2).abs()
    w = w.sort_values(["bid", "dm"]).drop_duplicates("bid")
    L = L.merge(w[["bid", "lag", "s"]], on="bid", how="left")
    L["ratio"] = L.lag / L.E
    L["bin"] = pd.cut(L.E, EBINS, right=False)

    def v2table(d):
        g = d.groupby("bin", observed=True)
        return pd.DataFrame({
            "n": g.size(), "E_med": g.E.median(),
            "hit@R(end)": g.a0.apply(lambda x: np.mean(x < 2)),
            "hit@R+E(start)": g.aE.apply(lambda x: np.mean(x < 2)),
            "hit@R-E(placebo)": g.aP.apply(lambda x: np.mean(x < 2)),
            "neutral_n": g.lag.count(),
            "lag/E<0.25": g.ratio.apply(lambda x: np.mean(x.dropna() < 0.25)),
            "lag/E>0.75": g.ratio.apply(lambda x: np.mean(x.dropna() > 0.75)),
            "lag_med": g.lag.median()}).round(3)

    for era, d in L.assign(era=np.where(L["sem"].str.startswith(("2018", "2019")), "2018-19", "2020-22")).groupby("era"):
        print(f"-- era {era}")
        print(v2table(d).to_string())
    print("-- era 2018-19, solo runs only (no other block of the user ends in the same second)")
    print(v2table(L[L["sem"].str.startswith(("2018", "2019")) & (L.co_n == 1)]).to_string())
    print("-- per class, runs with 5 <= E < 60 s (end = share of neutral matches with lag/E<0.25; start = lag/E>0.75)")
    d = L[(L.E >= 5) & (L.E < 60)]
    pc = d.groupby(["sem", "class"]).agg(n=("E", "size"), matched=("lag", "count"),
                                         end=("ratio", lambda x: np.mean(x.dropna() < 0.25)),
                                         start=("ratio", lambda x: np.mean(x.dropna() > 0.75)),
                                         hit_end=("a0", lambda x: np.mean(x < 2)),
                                         hit_start=("aE", lambda x: np.mean(x < 2))).round(3)
    print(pc[pc.matched >= 5].to_string())
    print(f"  classes with >=5 matches: {int((pc.matched >= 5).sum())}; "
          f"with end > start: {int(((pc.end > pc.start) & (pc.matched >= 5)).sum())}")

    # ---------------- V3 ----------------
    print("\n=== V3 client-only quiet gap before the feedback event (no server clock involved) ===")
    m = L[L.s.notna()].merge(cm[["fid", "s", "g_any", "prev_cat", "g_edit", "g_key", "g_kill", "g_blur"]],
                             on=["fid", "s"], how="left").drop_duplicates("bid")
    m = m[(m.E >= 2) & (m.E < 60)]
    perm = m.groupby("sem").E.transform(lambda x: pd.Series(rng.permutation(x.to_numpy()), index=x.index))
    m = m.assign(Ep=perm)
    m["killed_by_user"] = m.g_kill < 3
    for lab, d in (("all", m), ("no kill_program within 3 s", m[~m.killed_by_user])):
        g = d.groupby(pd.cut(d.E, [2, 5, 10, 20, 40, 60], right=False), observed=True)
        t = pd.DataFrame({
            "n": g.size(), "E_med": g.E.median(), "g_any_med": g.g_any.median(),
            "P(g_any>=E-1)": g.apply(lambda x: np.mean(x.g_any >= x.E - 1), include_groups=False),
            "null P(g_any>=Eperm-1)": g.apply(lambda x: np.mean(x.g_any >= x.Ep - 1), include_groups=False),
            "P(edit inside run)": g.apply(lambda x: np.mean(x.g_edit < x.E - 1), include_groups=False),
            "null edit": g.apply(lambda x: np.mean(x.g_edit < x.Ep - 1), include_groups=False),
            "P(kill<3s)": g.killed_by_user.mean(),
        }).round(3)
        print(f"-- matched long runs (neutral match with lag/E<0.25), {lab}")
        print(t.to_string())
    d = m[~m.killed_by_user & (m.E >= 5)]
    hist_o = np.histogram((d.g_any - d.E).clip(-20, 20), bins=np.arange(-10, 12, 2))[0]
    hist_n = np.histogram((d.g_any - d.Ep).clip(-20, 20), bins=np.arange(-10, 12, 2))[0]
    print("  (g_any - E) histogram, 2-s bins from -10 to +10, E in [5,60), no kill:")
    print("    observed:", hist_o.tolist())
    print("    null    :", hist_n.tolist())
    print("  slope of median g_any on E (bins above, no kill):",
          f"{np.polyfit(*zip(*[(x.E.median(), x.g_any.median()) for _, x in d.groupby(pd.cut(d.E, [5, 10, 20, 30, 40, 50, 60]), observed=True)]), 1)[0]:.2f}")
    print("  previous client event before the feedback (E>=5, no kill):",
          d.prev_cat.map(lambda k: CATNAME[k] if k >= 0 else "none").value_counts(normalize=True).round(3).to_dict())
    short = sb[(sb.E < 1) & sb.off.notna()].sample(min(40000, int(((sb.E < 1) & sb.off.notna()).sum())), random_state=SEED)
    sh = short[["fid", "vc", "R", "E"]].merge(cm[["fid", "vc", "s", "g_any"]], on=["fid", "vc"])
    sh = sh[(sh.s - sh.R).abs() < 2]
    print("  reference, short runs (E<1 s) matched at R: g_any", qs(sh.g_any))
    # verdict agreement: nearest feedback event of ANY verdict within 2 s of R, short runs
    sa = short[["fid", "vc", "R"]].reset_index(drop=True).reset_index().merge(
        cm[["fid", "vc", "s"]].rename(columns={"vc": "vc_cm"}), on="fid")
    sa["a"] = (sa.s - sa.R).abs()
    sa = sa[sa.a < 2].sort_values(["index", "a"]).drop_duplicates("index")
    print(f"  verdict agreement of the nearest feedback within 2 s of R (short runs): {np.mean(sa.vc == sa.vc_cm):.3f} (n={len(sa):,})")
    vu = np.asarray(vuniq, dtype=object)
    sa = sa.assign(bv=vu[sa.vc.to_numpy()], cv=vu[sa.vc_cm.to_numpy()])
    print("  block verdict -> feedback verdict (top rows):",
          sa.groupby(["bv", "cv"]).size().sort_values(ascending=False).head(6).to_dict())

    # ---------------- V4 ----------------
    print("\n=== V4 kill_program events vs the header (client ts - user offset) ===")
    kk = L[["bid", "fid", "R", "E"]].merge(kl[["fid", "t"]], on="fid")
    kk["x"] = kk.t - kk.R
    kk = kk[(kk.x >= -kk.E - 5) & (kk.x <= kk.E + 5)]
    kk["dm"] = (kk.x - kk.E / 2).abs()
    kk = kk.sort_values(["bid", "dm"]).drop_duplicates("bid")
    kk["r"] = kk.x / kk.E
    g = kk[kk.E >= 2].groupby(pd.cut(kk.E, [2, 5, 10, 20, 40, 60, 1e6], right=False), observed=True)
    print(pd.DataFrame({"n": g.size(), "E_med": g.E.median(), "kill-R med": g.x.median(),
                        "share |kill-R|<2": g.x.apply(lambda x: np.mean(x.abs() < 2)),
                        "share |kill-R-E|<2": g.apply(lambda x: np.mean((x.x - x.E).abs() < 2), include_groups=False),
                        "share r<0.25": g.r.apply(lambda x: np.mean(x < 0.25)),
                        "share r>0.75": g.r.apply(lambda x: np.mean(x > 0.75))}).round(3).to_string())

    # ---------------- V5 ----------------
    print("\n=== V5 server-only gaps: previous / next block (any kind) of the same user ===")
    bb = b.drop_duplicates(["sem"] + FKEY + ["kind", "ts", "E", "n_tc", "grade"]).sort_values(["sem", "user", "ts", "seq"])
    gg = bb.groupby(["sem", "user"], sort=False)
    bb["pre"] = bb.ts - gg.ts.shift(1)
    bb["post"] = gg.ts.shift(-1) - bb.ts
    s5 = bb[(bb.kind == "S") & (bb.E >= 5) & (bb.E < 60)].copy()
    s5["Ep"] = s5.groupby("sem").E.transform(lambda x: pd.Series(rng.permutation(x.to_numpy()), index=x.index))
    for era, d in s5.groupby("era"):
        g = d.groupby(pd.cut(d.E, [5, 10, 20, 30, 40, 50, 60], right=False), observed=True)
        t = pd.DataFrame({"n": g.size(), "E_med": g.E.median(), "pre_med": g.pre.median(), "post_med": g.post.median(),
                          "P(pre>=E)": g.apply(lambda x: np.mean(x.pre >= x.E), include_groups=False),
                          "null P(pre>=Ep)": g.apply(lambda x: np.mean(x.pre >= x.Ep), include_groups=False),
                          "P(post>=E)": g.apply(lambda x: np.mean(x.post >= x.E), include_groups=False),
                          "null P(post>=Ep)": g.apply(lambda x: np.mean(x.post >= x.Ep), include_groups=False)}).round(3)
        print(f"-- era {era}")
        print(t.to_string())
        sl_pre = np.polyfit(t.E_med, t.pre_med, 1)[0]
        sl_post = np.polyfit(t.E_med, t.post_med, 1)[0]
        print(f"   slope of median pre on E = {sl_pre:.2f}; of median post on E = {sl_post:.2f}")
        edges = np.arange(-10, 12, 2)
        print("   (pre - E) hist 2-s bins -10..+10  obs:", np.histogram(d.pre - d.E, edges)[0].tolist(),
              " null:", np.histogram(d.pre - d.Ep, edges)[0].tolist())
        print("   (post - E) hist                   obs:", np.histogram(d.post - d.E, edges)[0].tolist(),
              " null:", np.histogram(d.post - d.Ep, edges)[0].tolist())
    print("-- solo SUBMITIONs (no same-second partner), 2 <= E < 60, previous block in an earlier second: (pre - E) in 1-s bins -6..+6")
    bs = bb.copy()
    bs["co_n"] = bs.groupby(["sem", "user", "ts"]).ts.transform("size")
    first = bs.drop_duplicates(["sem", "user", "ts"])          # one row per (user, second)
    gf = first.groupby(["sem", "user"], sort=False)
    first = first.assign(pre_d=first.ts - gf.ts.shift(1), post_d=gf.ts.shift(-1) - first.ts)
    solo = first[(first.kind == "S") & (first.co_n == 1) & (first.E >= 2) & (first.E < 60)].copy()
    solo["Ep"] = solo.groupby("sem").E.transform(lambda x: pd.Series(rng.permutation(x.to_numpy()), index=x.index))
    e1 = np.arange(-6, 7, 1)
    for era, d in solo.groupby("era"):
        print(f"   {era} n={len(d)}  pre-E obs:", np.histogram(d.pre_d - d.E, e1)[0].tolist())
        print(f"   {era}           pre-E null:", np.histogram(d.pre_d - d.Ep, e1)[0].tolist())
        print(f"   {era}          post-E obs:", np.histogram(d.post_d - d.E, e1)[0].tolist())
        print(f"   {era}         post-E null:", np.histogram(d.post_d - d.Ep, e1)[0].tolist())
        print(f"   {era} P(pre>=E)={np.mean(d.pre_d >= d.E):.3f} null={np.mean(d.pre_d >= d.Ep):.3f}; "
              f"P(post>=E)={np.mean(d.post_d >= d.E):.3f} null={np.mean(d.post_d >= d.Ep):.3f}")
    print("-- per class (E in [5,60), classes with >=40 runs): P(pre>=E) - null and P(post>=E) - null")
    pc = s5.groupby(["sem", "class"]).apply(lambda x: pd.Series({
        "n": len(x), "pre_excess": np.mean(x.pre >= x.E) - np.mean(x.pre >= x.Ep),
        "post_excess": np.mean(x.post >= x.E) - np.mean(x.post >= x.Ep)}), include_groups=False)
    pc = pc[pc.n >= 40].round(3)
    print(pc.to_string())
    print("   share of adjacent same-user blocks with identical header second:",
          bb.groupby("era").pre.apply(lambda x: np.mean(x == 0)).round(4).to_dict())

    # ---------------- V6 ----------------
    print("\n=== V6 E against the number of test cases ===")
    ok = sb[(sb.grade == 100) & ~sb.has_err & sb.E.notna() & (sb.E < 5)]
    for era, d in ok.groupby("era"):
        t = d.groupby("n_tc").E.agg(n="size", p10=lambda x: x.quantile(0.1), med="median").round(3)
        t = t[t.n >= 100]
        s_med = np.polyfit(t.index.to_numpy(float), t.med, 1)
        s_p10 = np.polyfit(t.index.to_numpy(float), t.p10, 1)
        print(f"-- era {era}, correct runs: median E = {s_med[1]:.3f} + {s_med[0]:.4f}*n_tc ; "
              f"p10 E = {s_p10[1]:.3f} + {s_p10[0]:.4f}*n_tc")
        print("   ", {int(k): (int(r.n), r.p10, r.med) for k, r in t.iterrows()})
    pcs = []
    for (sem, cl), d in ok.groupby(["sem", "class"]):
        t = d.groupby("n_tc").E.median()
        c = d.groupby("n_tc").size()
        t = t[c >= 30]
        if len(t) >= 3:
            pcs.append((sem, cl, len(d), round(np.polyfit(t.index.to_numpy(float), t.to_numpy(), 1)[0], 4)))
    pcs = pd.DataFrame(pcs, columns=["sem", "class", "n", "slope_med_per_tc"])
    print("   per class slope of median E per extra test case:", qs(pcs.slope_med_per_tc, (0, 0.25, 0.5, 0.75, 1)))
    hung = sb[(sb.n_tc > 0) & (sb.n_empty == sb.n_tc) & (sb.grade == 0) & ~sb.has_err & (sb.E >= 5)]
    for era, d in hung.groupby("era"):
        t = d[d.E < 60].groupby("n_tc").E.agg(n="size", p25=lambda x: x.quantile(0.25), med="median",
                                              p75=lambda x: x.quantile(0.75), max="max").round(2)
        print(f"-- era {era}, runs with every output empty, grade 0, no ERROR, 5<=E<60:")
        print(t[t.n >= 10].to_string())

    # ---------------- V7 ----------------
    print("\n=== V7 max E by month (SUBMITION) ===")
    sb["month"] = pd.to_datetime(sb.ts, unit="s").dt.strftime("%Y-%m")
    t = sb.groupby(["sem", "month"]).E.agg(n="size", max="max", n_ge60=lambda x: int((x >= 60).sum()),
                                           n_50_60=lambda x: int(((x >= 50) & (x < 60)).sum()))
    print(t.round(2).to_string())
    tail = sb.assign(tb=pd.cut(sb.E, [0, 5, 12.45, 60, 1e7], right=False)).groupby(["sem", "month", "tb"], observed=False).size().unstack("tb")
    print("  SUBMITION counts by E band (is Sept 2019 thin only above 60 s, or above 12.45 s too?):")
    print(tail.to_string())
    last = sb[(sb["sem"] == "2019_2") & (sb.E >= 60)].ts.max()
    print("  2019-2: last SUBMITION with E >= 60 s at", pd.to_datetime(last, unit="s"))
    print("  E == 0 SUBMITIONs per semester:", sb[sb.E == 0].groupby("sem").size().to_dict())
    print("  Killed SUBMITIONs per semester:", sb[sb.killed].groupby("sem").size().to_dict(),
          "min E of Killed:", sb[sb.killed].groupby("sem").E.min().round(1).to_dict())

    # ---------------- V8 ----------------
    print("\n=== V8 is E stable over time?  correct runs (grade 100, no error, E<5), by semester-month ===")
    okm = sb[(sb.grade == 100) & ~sb.has_err & (sb.E < 5)]
    print(okm.groupby(["sem", "month"]).E.agg(n="size", p10=lambda x: x.quantile(0.1), med="median",
                                              p90=lambda x: x.quantile(0.9)).round(3).to_string())
    print("\n=== V8b the 5-7 s runs of 2018-19: a narrow spike?  0.25-s histogram of E in [4,8) ===")
    edges = np.arange(4, 8.01, 0.25)
    for s, d in sb.groupby("sem"):
        print(f"  {s}:", np.histogram(d.E, edges)[0].tolist())
    sp = bb[(bb.kind == "S") & (bb.E >= 5) & (bb.E < 7)]
    t = sp.groupby(["sem", pd.to_datetime(sp.ts, unit="s").dt.strftime("%Y-%m")]).agg(
        n=("E", "size"), users=("user", "nunique"), E_med=("E", "median"),
        share_pre0=("pre", lambda x: np.mean(x == 0)), share_post0=("post", lambda x: np.mean(x == 0)),
        grade0=("grade", lambda x: np.mean(x == 0)), grade100=("grade", lambda x: np.mean(x == 100)))
    print(t.round(3).to_string())
    # same-second groups: how many blocks of the same user share one header second, by E class
    bb["same_sec_n"] = bb.groupby(["sem", "user", "ts"]).ts.transform("size")
    x = bb[bb.kind == "S"]
    # parser cross-check against the primary parse's cache (same archives, different parser)
    rows = []
    for s in SEMS:
        p = os.path.join(HERE, "cache", f"blocks_{s}.parquet")
        if os.path.exists(p):
            o = pd.read_parquet(p, columns=["kind", "exec_time", "n_tc", "grade"])
            o = o[o.kind.astype(str) == "submit"]
            mine = sb[sb["sem"] == s]
            rows.append((s, len(o), len(mine), round(o.exec_time.sum(), 1), round(mine.E.sum(), 1),
                         int(o.n_tc.sum()), int(mine.n_tc.sum()), int((o.grade == 100).sum()), int((mine.grade == 100).sum())))
    print("\n=== V9 parser cross-check vs cache/blocks_<sem>.parquet (primary parse) ===")
    print(pd.DataFrame(rows, columns=["sem", "submits_A", "submits_mine", "sumE_A", "sumE_mine", "ntc_A", "ntc_mine",
                                      "grade100_A", "grade100_mine"]).to_string(index=False))
    # V10 does E grow when the same user's runs end together (own concurrent runs in one container)?
    print("\n=== V10 correct runs (grade 100, no error): E by number of the same user's blocks ending in the same second ===")
    grp = bb.groupby(["sem", "user", "ts"])
    bb["co_n"] = grp.ts.transform("size")
    bb["isS"] = (bb.kind == "S").astype(int)
    bb["co_S"] = bb.groupby(["sem", "user", "ts"]).isS.transform("sum")
    bb["co_files"] = grp.fid.transform("nunique")
    okc = bb[(bb.kind == "S") & (bb.grade == 100) & ~bb.has_err & bb.E.notna()].copy()
    okc["co"] = okc.co_n.clip(upper=4)
    t = okc.groupby(["sem", "co"]).E.agg(n="size", p10=lambda x: x.quantile(0.1), med="median",
                                         p90=lambda x: x.quantile(0.9)).round(3)
    print(t.to_string())
    g2 = bb[(bb.co_n >= 2) & (bb.kind == "S")]
    print("  same-second groups containing a SUBMITION: share whose blocks are all in one exercise file:",
          g2.groupby("sem").co_files.apply(lambda x: round(float(np.mean(x == 1)), 3)).to_dict(),
          "; share with >=2 SUBMITIONs:", g2.groupby("sem").co_S.apply(lambda x: round(float(np.mean(x >= 2)), 3)).to_dict())
    # spread of E inside same-second groups of >=2 SUBMITIONs (parallel runs finishing together?)
    gs = bb[(bb.kind == "S") & (bb.co_S >= 2)].groupby(["sem", "user", "ts"]).E.agg(["min", "max", "size"])
    print("  same-second SUBMITION groups: E max-min", qs(gs["max"] - gs["min"]), "; E max", qs(gs["max"]))

    # V11 is the monthly shift of E a change in the exercise mix?  exercise-demeaned log E, solo correct runs
    print("\n=== V11 monthly E of solo correct runs relative to the same exercise (exp of median of log E - exercise median) ===")
    so = okc[(okc.co_n == 1) & (okc.E > 0) & (okc.E < 5)].copy()
    so["month"] = pd.to_datetime(so.ts, unit="s").dt.strftime("%Y-%m")
    so["lx"] = np.log(so.E)
    so["lx_dm"] = so.lx - so.groupby(["sem", "exercise", "n_tc"]).lx.transform("median")
    # only exercises with correct runs in >= 2 months, so the month effect is identified within exercise
    nm = so.groupby(["sem", "exercise"]).month.transform("nunique")
    so = so[nm >= 2]
    t = so.groupby(["sem", "month"]).agg(n=("E", "size"), exercises=("exercise", "nunique"), E_med=("E", "median"),
                                         rel=("lx_dm", lambda x: float(np.exp(x.median()))))
    print(t.round(3).to_string())
    # load in the same months (all SUBMITION blocks per day, median over active days)
    ld = sb.assign(day=(sb.ts // 86400)).groupby(["sem", "month", "day"]).size().groupby(["sem", "month"]).median()
    print("  median SUBMITIONs per active day by month:", {f"{a}/{b}": int(v) for (a, b), v in ld.items()})
    # same exercise, early vs late part of the semester (split at the month where the jump appears)
    so_all = okc[(okc.co_n == 1) & (okc.E > 0) & (okc.E < 5)].copy()
    so_all["month"] = pd.to_datetime(so_all.ts, unit="s").dt.strftime("%Y-%m")
    split = {"2018_2": "2018-11", "2021_2": "2022-08", "2022_1": "2023-02"}
    rows = []
    for s, cut in split.items():
        d = so_all[so_all["sem"] == s].assign(late=lambda x: x.month >= cut)
        g = d.groupby(["exercise", "late"]).E.agg(["median", "size"]).unstack("late")
        g = g[(g[("size", False)] >= 10) & (g[("size", True)] >= 10)]
        rows.append((s, cut, len(g), round(float(g[("median", False)].median()), 3), round(float(g[("median", True)].median()), 3),
                     round(float((g[("median", True)] / g[("median", False)]).median()), 3)))
    print("  same exercise, runs before vs from the jump month:")
    print(pd.DataFrame(rows, columns=["sem", "jump_month", "exercises_both", "E_med_early", "E_med_late", "median_ratio"]).to_string(index=False))
    # by assessment type
    at = []
    for s in SEMS:
        a = pd.read_parquet(os.path.join(ROOT, "data", "codebench", "parquet", "assessments", s.replace("_", "-") + ".parquet"),
                            columns=["class", "assessment", "type"])
        a["sem"] = s
        at.append(a)
    at = pd.concat(at).astype(str).drop_duplicates(["sem", "class", "assessment"])
    so_all = so_all.merge(at, on=["sem", "class", "assessment"], how="left")
    print("  solo correct runs by month and assessment type (median E, n):")
    print(so_all.groupby(["sem", "month", "type"]).E.agg(n="size", med="median").round(3).unstack("type").to_string())

    # V12 platform-level level shift of E: all DEV months from the primary parse's cache (parse validated by V9)
    print("\n=== V12 median E of correct runs (grade 100, no error, E<5) by month, all DEV semesters (cache/blocks_*.parquet) ===")
    allm = []
    for s in ["2018_1", "2018_2", "2019_1", "2019_2", "2020_1", "2020_2", "2020_ERE", "2021_1", "2021_2", "2022_1", "2022_2"]:
        p = os.path.join(HERE, "cache", f"blocks_{s}.parquet")
        if not os.path.exists(p):
            continue
        o = pd.read_parquet(p, columns=["kind", "ts", "exec_time", "grade", "has_error"])
        o = o[(o.kind.astype(str) == "submit") & (o.grade == 100) & ~o.has_error & (o.exec_time < 5)]
        o["month"] = pd.to_datetime(o.ts, unit="s").dt.strftime("%Y-%m")
        allm.append(o.groupby("month").exec_time.agg(n="size", p10=lambda x: x.quantile(0.1), med="median").assign(sem=s))
    allm = pd.concat(allm).reset_index()
    allm = allm[allm.n >= 200]
    print("  " + "; ".join(f"{r.month}({r.sem}) p10={r.p10:.2f} med={r.med:.2f}" for r in allm.itertuples()))

    print("\n=== V13 SUBMITION blocks sharing their header second with >=1 other block of the same user (share, n) by E ===")
    x = x.assign(Eb=pd.cut(x.E, [0, 1, 2, 5, 10, 60, 1e6], right=False))
    t = x.groupby(["sem", "Eb"], observed=True).same_sec_n.agg(share=lambda v: np.mean(v > 1), n="size").round(3).unstack("Eb")
    print(t.to_string())
    # within +-3 s: any other block of the same user (burst), E>=1 s SUBMITIONs
    tt = bb[["sem", "user", "ts"]].drop_duplicates().sort_values(["sem", "user", "ts"])
    gq = tt.groupby(["sem", "user"], sort=False).ts
    tt["d_prev"], tt["d_next"] = tt.ts - gq.shift(1), gq.shift(-1) - tt.ts
    x = x.merge(tt, on=["sem", "user", "ts"], how="left")
    x["burst3"] = (x.same_sec_n > 1) | (x.d_prev <= 3) | (x.d_next <= 3)
    print("  share of SUBMITIONs with another block of the same user within +-3 s, by E bin:")
    print(x.groupby(["sem", "Eb"], observed=True).burst3.mean().round(3).unstack("Eb").to_string())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        tags = sys.argv[2:] or SEMS
        assert not SEALED & set(tags), "sealed semester requested"
        with ProcessPoolExecutor(max_workers=4) as pool:
            for line in pool.map(build, tags):
                print(line, flush=True)
    else:
        analyze()
