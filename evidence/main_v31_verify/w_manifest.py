"""V7: manifest, stage logs, cell completeness, stale-output hunt.  Read-only."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
V31 = os.path.join(ROOT, "evidence", "main_v3", "v31")
MV3 = os.path.join(ROOT, "evidence", "main_v3")
REP = os.path.join(MV3, "out_main_v31.txt")
SCRATCH = r"<cache-dir>"
SIM = os.path.join(SCRATCH, "mv31", "sim")
TR = os.path.join(SCRATCH, "mv31", "traces")

OUT = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    OUT.append(s)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    txt = open(REP, encoding="utf-8").read()

    # ---- 1. recompute the manifest exactly as v31_common.manifest() defines it ---
    say("=" * 96)
    say("1. MANIFEST")
    say("=" * 96)
    core = sorted(f for f in os.listdir(V31)
                  if f.startswith("v31_") and f.endswith(".py") and f != "v31_report.py")
    ext = {
        "guard_variants/guardkern.py":
            os.path.join(ROOT, "evidence", "guard_variants", "guardkern.py"),
        "codebench_service_v2/service_precheck_v2.py":
            os.path.join(ROOT, "evidence", "codebench_service_v2",
                         "service_precheck_v2.py"),
        "guard_variants_referee/refsim.py":
            os.path.join(ROOT, "evidence", "guard_variants_referee", "refsim.py"),
        "ranking_score/rs_fit.py":
            os.path.join(ROOT, "evidence", "ranking_score", "rs_fit.py"),
    }
    tab = [(f, sha(os.path.join(V31, f))) for f in core]
    tab += [(f"[ext] {n}", sha(p)) for n, p in sorted(ext.items())]
    h = hashlib.sha256()
    for f, s in tab:
        h.update(f.encode() + b"\0" + s.encode() + b"\0")
    mine = h.hexdigest()
    printed = re.search(r"manifest of the code that produced every number below: (\w+)",
                        txt).group(1)
    say(f"  core scripts hashed: {len(core)}  {core}")
    say(f"  recomputed manifest {mine}")
    say(f"  report header       {printed}")
    say(f"  MATCH: {mine == printed}")
    bad = 0
    for f, s in tab:
        if f"{s}" not in txt:
            say(f"  !! hash not in report header: {f} {s}")
            bad += 1
        pat = re.search(re.escape(f) + r"\s+(\w{64})", txt)
        if pat and pat.group(1) != s:
            say(f"  !! report prints a different hash for {f}: {pat.group(1)} vs {s}")
            bad += 1
    say(f"  per-file hash lines wrong: {bad}")

    say("  file mtimes (all code a number depends on):")
    for f in core + ["v31_report.py"]:
        p = os.path.join(V31, f)
        say(f"    {f:24s} {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p)))}")
    for n, p in sorted(ext.items()):
        say(f"    [ext] {n:46s} "
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p)))}")

    # data artefacts
    say("  data artefacts:")
    arte = {
        "cb_v2_cache_r4/ev.parquet": os.path.join(SCRATCH, "cb_v2_cache_r4", "ev.parquet"),
        "cb_v2_cache_r4/feat_ires0.parquet":
            os.path.join(SCRATCH, "cb_v2_cache_r4", "feat_ires0.parquet"),
        "cb_v2_cache_r4/forward_ires0.parquet":
            os.path.join(SCRATCH, "cb_v2_cache_r4", "forward_ires0.parquet"),
        "mv3/r1s_forward.parquet": os.path.join(SCRATCH, "mv3", "r1s_forward.parquet"),
        "rank_score/rs_pred_ires0.parquet":
            os.path.join(SCRATCH, "rank_score", "rs_pred_ires0.parquet"),
    }
    nb = 0
    for n, p in sorted(arte.items()):
        if not os.path.exists(p):
            say(f"    !! missing {n}")
            nb += 1
            continue
        s = sha(p)
        pat = re.search(re.escape(n) + r"\s+(\w{64})", txt)
        ok = pat is not None and pat.group(1) == s
        mt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p)))
        say(f"    {n:38s} {s[:16]}... report_match={ok} mtime={mt}")
        nb += 0 if ok else 1
    say(f"  data artefact hash mismatches: {nb}")

    # ---- 2. stage logs -------------------------------------------------------
    say("")
    say("=" * 96)
    say("2. STAGE LOGS")
    say("=" * 96)
    logs = sorted(f for f in os.listdir(V31) if f.startswith("out_") and f.endswith(".txt"))
    say(f"  out_*.txt in v31/: {logs}")
    tot_inv = 0
    for f in logs:
        lines = open(os.path.join(V31, f), encoding="utf-8").read().splitlines()
        starts = [l for l in lines if l.startswith("## 2")]
        dones = [l for l in lines if l.startswith("## done")]
        mans = {re.search(r"manifest=(\w+)", l).group(1) for l in starts}
        tot_inv += len(starts)
        ok = (len(starts) == len(dones)) and mans == {printed}
        say(f"  {f:18s} lines={len(lines):5d} invocations={len(starts):3d} "
            f"done={len(dones):3d} manifests={len(mans)} all_match={mans == {printed}} OK={ok}")
        # section 12 line counts
        m = re.search(r"\s+" + re.escape(f) + r"\s+(\d+) lines", txt)
        if m:
            say(f"      section 12 says {m.group(1)} lines; actual {len(lines)}  "
                f"MATCH={int(m.group(1)) == len(lines)}")
        else:
            say(f"      !! not listed in section 12")
        ct = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getctime(
            os.path.join(V31, f))))
        first = starts[0].split(" manifest")[0][3:] if starts else "-"
        say(f"      ctime {ct}   first logged invocation {first}")
    say(f"  total invocations {tot_inv}")

    # invocation order: select before any 'main' cell
    run = open(os.path.join(V31, "out_run.txt"), encoding="utf-8").read().splitlines()
    sel = open(os.path.join(V31, "out_select.txt"), encoding="utf-8").read().splitlines()
    sel_t = sel[0].split(" manifest")[0][3:]
    grid_t = [l.split(" manifest")[0][3:] for l in run if l.startswith("## 2")
              and "--set grid" in l]
    main_t = [l.split(" manifest")[0][3:] for l in run if l.startswith("## 2")
              and "--set grid" not in l and l.startswith("## 2")]
    say(f"  selection ran at        {sel_t}")
    say(f"  last  grid cell ran at  {max(grid_t) if grid_t else '-'}  ({len(grid_t)} grid)")
    say(f"  first main cell ran at  {min(main_t) if main_t else '-'}  ({len(main_t)} main)")
    say(f"  ORDER OK (all grid < select < all main): "
        f"{max(grid_t) < sel_t < min(main_t)}")

    # ---- 3. cells ------------------------------------------------------------
    say("")
    say("=" * 96)
    say("3. CELLS")
    say("=" * 96)
    files = sorted(f for f in os.listdir(SIM) if f.endswith(".csv"))
    say(f"  csv cells in {SIM}: {len(files)}")
    nv = nm = 0
    for f in files:
        d = pd.read_csv(os.path.join(SIM, f))
        g = d[d.bound_viol >= 0]
        viol = int(g.bound_viol.sum())
        uoa = float(g.used_over_allowed.max())
        mt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(
            os.path.getmtime(os.path.join(SIM, f))))
        tag = "grid" if f.endswith("_grid.csv") else "main"
        nv += tag == "grid"
        nm += tag == "main"
        say(f"  {f:34s} pol={len(d):3d} guarded={len(g):3d} jobs={int(d.n_jobs.iloc[0]):>9,} "
            f"k={int(d.k.iloc[0])} viol={viol} max_used={uoa:.4f} mtime={mt}")
    say(f"  grid cells {nv}, main cells {nm}, total {nv + nm}")
    say(f"  report claims 31 cells: {nv + nm == 31}")

    # bootstrap replicate files
    bws = sorted(f for f in os.listdir(SIM) if f.startswith("bw_"))
    say(f"  bootstrap replicate files: {len(bws)}")
    nfin = []
    for f in bws:
        z = np.load(os.path.join(SIM, f))
        cnt = {q: int(np.isfinite(z[q]).sum()) for q in z.files}
        sz = {len(z[q]) for q in z.files}
        nfin.append((f, len(z.files), sz, min(cnt.values()), max(cnt.values())))
    for f, nk, sz, lo, hi in nfin:
        say(f"    {f:34s} arrays={nk:3d} len={sz} finite[min,max]=[{lo},{hi}]")

    # traces
    say("")
    trs = sorted(os.listdir(TR))
    say(f"  trace npz files: {len(trs)} {trs}")
    for f in trs:
        mt = time.strftime("%Y-%m-%d %H:%M:%S",
                           time.localtime(os.path.getmtime(os.path.join(TR, f))))
        z = np.load(os.path.join(TR, f))
        say(f"    {f:20s} n={len(z['a']):>9,} keys={sorted(z.files)} mtime={mt}")

    # ---- 4. stale output hunt ------------------------------------------------
    say("")
    say("=" * 96)
    say("4. STALE OUTPUT HUNT")
    say("=" * 96)
    rt = os.path.getmtime(REP)
    say(f"  report mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(rt))}")
    for f in sorted(os.listdir(V31)):
        p = os.path.join(V31, f)
        if not os.path.isfile(p):
            continue
        mt = os.path.getmtime(p)
        flag = "  <-- AFTER the report" if mt > rt + 1 else ""
        say(f"    {f:28s} {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mt))}{flag}")
    say("  mv3/ (the v3 study) files younger than the v31 report:")
    for f in sorted(os.listdir(MV3)):
        p = os.path.join(MV3, f)
        if os.path.isfile(p) and os.path.getmtime(p) > rt + 1:
            say(f"    {f}")

    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_manifest.txt"),
         "w", encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
