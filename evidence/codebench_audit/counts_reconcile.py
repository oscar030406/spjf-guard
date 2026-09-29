"""Reconcile our CodeBench v1.81 counts with the official per-semester statistics table.

Stage A streams every archive (tarfile "r|gz", nothing extracted) and caches, per
semester, a member inventory (paths and sizes only) and per-execution-file block
statistics (counts only; block bytes are hashed in memory for duplicate detection
and never stored).  Stage B compares candidate counting rules with the official
table and prints compact tables.

Sealed semesters (2023-1, 2023-2, 2024-1) contribute plain per-semester counts only.
No source code, keystroke content or personal attribute is stored or printed.

Usage (from any directory; clear PYTHONHOME/PYTHONPATH/UV_INTERNAL__PYTHONHOME first):
    uv run --with pandas --with numpy --with pyarrow python counts_reconcile.py --stage hz --cache DIR
    uv run --with pandas --with numpy --with pyarrow python counts_reconcile.py --stage ab --cache DIR
Stage h sends one HEAD request per archive to compare sizes with the server; stage z
(about 5 min, 6 workers) checks that tarfile "r|gz" sees every member of every
archive; stage a (about 1 min) streams the archives into the cache; stage b (about 1 min)
reads the cache plus data/codebench/parquet and writes out_counts_reconcile.txt next to
this script.  The cache holds counts and paths only and can live outside the project.
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import argparse
import hashlib
import re
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
ARCHIVES = os.path.join(ROOT, "data", "codebench", "archives")
PARQUET = os.path.join(ROOT, "data", "codebench", "parquet")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "out_counts_reconcile.txt")
DEFAULT_CACHE = os.path.join(os.environ.get("TEMP", HERE), "codebench_counts_cache")

SEMS = ["2016-1", "2016-2", "2017-1", "2017-2", "2018-1", "2018-2", "2019-1", "2019-2",
        "2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2",
        "2023-1", "2023-2", "2024-1"]
SEALED = {"2023-1", "2023-2", "2024-1"}

# Official v1.81 table, https://codebench.icomp.ufam.edu.br/dataset/ (read 2026-09-18)
OFFICIAL = pd.DataFrame({
    "semester": SEMS,
    "classes": [9, 5, 10, 5, 9, 5, 9, 7, 3, 7, 6, 7, 8, 8, 9, 7, 7, 8],
    "students": [471, 172, 463, 177, 465, 180, 489, 297, 492, 228, 200, 224, 219, 238, 196,
                 255, 222, 241],
    "hw_ex": [681, 447, 1278, 556, 1550, 893, 1559, 1116, 420, 1008, 882, 962, 1180, 1158,
              1257, 1009, 1157, 1192],
    "exam_ex": [124, 110, 163, 103, 182, 107, 176, 138, 8, 12, 8, 154, 195, 188, 240, 212,
                208, 216],
    "codes": [30140, 9501, 38304, 10942, 47969, 13458, 38417, 28348, 45491, 19246, 17848,
              19022, 19627, 19457, 17403, 24834, 22880, 26928],
    "execs": [322500, 126286, 419603, 125848, 455484, 163821, 540537, 308340, 457404, 214208,
              177364, 191238, 226982, 210502, 166694, 244538, 213190, 243025],
}).set_index("semester")
OFFICIAL_TOTALS = {"classes": 129, "students": 5229, "hw_ex": 18553, "exam_ex": 2544,
                   "codes": 449815, "execs": 4561318}

SEP = b"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*"
RE_HEAD = re.compile(rb"==\s+(SUBMITION|TEST)\s+\((\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})\)")
RE_HEAD_LINE = re.compile(rb"(?m)^==\s+(SUBMITION|TEST)\s+\(")
RE_ANY_HEAD_LINE = re.compile(rb"(?m)^== [A-Z]")
RE_CODE = re.compile(rb"(?m)^-- CODE:[ \t]*$")
RE_NEXT_SECT = re.compile(rb"(?m)^-- (EXECUTION TIME|OUTPUT|ERROR|GRADE|TEST CASE \d+):[ \t]*$")
RE_EXEC_TIME = re.compile(rb"(?m)^-- EXECUTION TIME:[ \t]*$")


# --------------------------------------------------------------------------- #
# Stage A: stream one archive
# --------------------------------------------------------------------------- #
def exec_file_stats(raw: bytes) -> dict:
    """Counts only.  Block bytes are hashed in memory and discarded."""
    segs = [s for s in raw.split(SEP) if s.strip()]
    st = dict(n_seg=len(segs), n_seg_nohead=0, n_sub=0, n_test=0,
              n_head_lines=len(RE_HEAD_LINE.findall(raw)),
              n_any_head_lines=len(RE_ANY_HEAD_LINE.findall(raw)),
              n_multi_head_seg=0, n_dup_exact=0, n_dup_exact_adjacent=0,
              n_dup_exact_sub=0, n_dup_exact_test=0,
              n_dup_tskind=0, n_dup_tskind_diff=0, n_empty_code=0, n_no_code=0,
              n_empty_code_sub=0, n_empty_code_test=0,
              n_dup_notime=0, n_dup_notime_sub=0, n_dup_notime_test=0,
              n_dup_notime_adjacent=0, n_dup_samecode=0)
    seen_hash = set()
    seen_notime = set()
    seen_code = set()
    seen_tk: dict = {}
    prev_hash = prev_notime = None
    for s in segs:
        h = RE_HEAD.search(s)
        if h is None:
            st["n_seg_nohead"] += 1
            prev_hash = prev_notime = None
            continue
        if len(RE_HEAD_LINE.findall(s)) > 1:
            st["n_multi_head_seg"] += 1
        is_sub = h.group(1) == b"SUBMITION"
        st["n_sub" if is_sub else "n_test"] += 1
        body = b""
        m = RE_CODE.search(s, h.end())
        if m is None:
            st["n_no_code"] += 1
        else:
            n = RE_NEXT_SECT.search(s, m.end())
            body = s[m.end(): n.start() if n else len(s)]
            if not body.strip():
                st["n_empty_code"] += 1
                st["n_empty_code_sub" if is_sub else "n_empty_code_test"] += 1
        # same block apart from the EXECUTION TIME value (header, code, outputs, grade equal)
        et = RE_EXEC_TIME.search(s, h.end())
        if et is None:
            s_nt = s.strip()
        else:
            n2 = RE_NEXT_SECT.search(s, et.end())
            s_nt = (s[:et.end()] + (s[n2.start():] if n2 else b"")).strip()
        d_nt = hashlib.blake2b(s_nt, digest_size=16).digest()
        if d_nt in seen_notime:
            st["n_dup_notime"] += 1
            st["n_dup_notime_sub" if is_sub else "n_dup_notime_test"] += 1
            if d_nt == prev_notime:
                st["n_dup_notime_adjacent"] += 1
        seen_notime.add(d_nt)
        prev_notime = d_nt
        d_code = hashlib.blake2b(h.group(0) + b"\x00" + body.strip(), digest_size=16).digest()
        if d_code in seen_code:
            st["n_dup_samecode"] += 1
        seen_code.add(d_code)
        dig = hashlib.blake2b(s.strip(), digest_size=16).digest()
        if dig in seen_hash:
            st["n_dup_exact"] += 1
            st["n_dup_exact_sub" if is_sub else "n_dup_exact_test"] += 1
            if dig == prev_hash:
                st["n_dup_exact_adjacent"] += 1
        seen_hash.add(dig)
        tk = (h.group(2), is_sub)
        if tk in seen_tk:
            st["n_dup_tskind"] += 1
            if dig not in seen_tk[tk]:
                st["n_dup_tskind_diff"] += 1
            seen_tk[tk].add(dig)
        else:
            seen_tk[tk] = {dig}
        prev_hash = dig
    return st


def scan_archive(path: str, cache: str) -> str:
    t0 = time.time()
    inv, ex = [], []
    sem = None
    tf = tarfile.open(path, "r|gz")
    for m in tf:
        parts = m.name.strip("/").split("/")
        sem = sem or parts[0]
        rec = dict(path=m.name, isfile=m.isfile(), size=int(m.size), depth=len(parts),
                   top=parts[0], cls=parts[1] if len(parts) > 1 else "",
                   area=parts[2] if len(parts) > 2 else "",
                   uid=parts[3] if len(parts) > 3 and len(parts) > 2 and parts[2] == "users" else "",
                   sub=parts[4] if len(parts) > 4 else "",
                   leaf=parts[-1])
        inv.append(rec)
        if (m.isfile() and len(parts) == 6 and parts[2] == "users" and parts[4] == "executions"):
            raw = tf.extractfile(m).read()
            st = exec_file_stats(raw)
            st.update(cls=parts[1], uid=parts[3], leaf=parts[5], nbytes=len(raw))
            ex.append(st)
    tf.close()
    tag = os.path.basename(path).replace("cb_dataset_", "").replace("_v1.81.tar.gz", "")
    pd.DataFrame(inv).to_parquet(os.path.join(cache, f"inv_{tag}.parquet"), index=False)
    pd.DataFrame(ex).to_parquet(os.path.join(cache, f"exec_{tag}.parquet"), index=False)
    return f"{tag} {time.time() - t0:.0f}s members={len(inv)} execfiles={len(ex)}"


def stream_check(path: str) -> dict:
    """How much of the archive does tarfile "r|gz" actually see?

    Counts gzip members and decompressed bytes over the whole file (multi-member
    aware), then the members tarfile yields in plain "r|gz" mode versus reading the
    multi-member-aware gzip stream with ignore_zeros=True.
    """
    import gzip
    import zlib
    tag = os.path.basename(path).replace("cb_dataset_", "").replace("_v1.81.tar.gz", "")
    total = 0
    with open(path, "rb") as fh:
        d = zlib.decompressobj(31)
        n_gz = 1
        while True:
            chunk = fh.read(1 << 22)
            if not chunk:
                break
            data = chunk
            while data:
                out = d.decompress(data)
                total += len(out)
                if d.eof:
                    data = d.unused_data
                    d = zlib.decompressobj(31)
                    if data:
                        n_gz += 1
                else:
                    data = b""
    tf = tarfile.open(path, "r|gz")
    n1 = sum(1 for _ in tf)
    end1 = tf.offset
    tf.close()
    with gzip.open(path, "rb") as g:
        tf = tarfile.open(fileobj=g, mode="r|", ignore_zeros=True)
        n2 = sum(1 for _ in tf)
        end2 = tf.offset
        tf.close()
    return dict(archive=tag, compressed=os.path.getsize(path), gzip_members=n_gz,
                decompressed=total, rgz_members=n1, rgz_end_offset=end1,
                full_members=n2, full_end_offset=end2)


def stage_z(cache: str, workers: int, only: str = ""):
    paths = [os.path.join(ARCHIVES, f) for f in sorted(os.listdir(ARCHIVES))
             if f.endswith("_v1.81.tar.gz") and (not only or any(o in f for o in only.split(",")))]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(stream_check, paths))
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(df.to_string(index=False))
    os.makedirs(cache, exist_ok=True)
    for r in rows:
        pd.DataFrame([r]).to_parquet(os.path.join(cache, f"z_{r['archive']}.parquet"), index=False)


def stage_h(cache: str):
    """HEAD request per archive (through the proxy in HTTPS_PROXY): server size vs local size."""
    import urllib.request
    base = "https://codebench.icomp.ufam.edu.br/dataset/files/"
    rows = []
    for f in sorted(os.listdir(ARCHIVES)):
        if not f.endswith("_v1.81.tar.gz"):
            continue
        req = urllib.request.Request(base + f, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                size, mod = int(r.headers.get("Content-Length", -1)), r.headers.get("Last-Modified", "")
        except Exception as e:  # network failure is reported, not fatal
            size, mod = -1, f"error: {type(e).__name__}"
        rows.append(dict(archive=f, local=os.path.getsize(os.path.join(ARCHIVES, f)),
                         server=size, server_last_modified=mod))
    df = pd.DataFrame(rows)
    df["identical_size"] = df.local.eq(df.server)
    os.makedirs(cache, exist_ok=True)
    df.to_parquet(os.path.join(cache, "h_server_sizes.parquet"), index=False)
    print(df.to_string(index=False))


def stage_a(cache: str, workers: int):
    os.makedirs(cache, exist_ok=True)
    todo = []
    for f in sorted(os.listdir(ARCHIVES)):
        if not f.endswith("_v1.81.tar.gz"):
            continue
        tag = f.replace("cb_dataset_", "").replace("_v1.81.tar.gz", "")
        if not (os.path.exists(os.path.join(cache, f"inv_{tag}.parquet"))
                and os.path.exists(os.path.join(cache, f"exec_{tag}.parquet"))):
            todo.append(os.path.join(ARCHIVES, f))
    print(f"stage A: {len(todo)} archives to stream (cache {cache})", flush=True)
    if todo:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for msg in pool.map(scan_archive, todo, [cache] * len(todo)):
                print("  ", msg, flush=True)


def load_cache(cache: str):
    inv, ex = [], []
    for s in SEMS:
        tag = s.replace("-", "_")
        a = pd.read_parquet(os.path.join(cache, f"inv_{tag}.parquet"))
        a["semester"] = s
        inv.append(a.rename(columns={"sub": "subdir"}))
        b = pd.read_parquet(os.path.join(cache, f"exec_{tag}.parquet"))
        b["semester"] = s
        ex.append(b)
    return pd.concat(inv, ignore_index=True), pd.concat(ex, ignore_index=True)


# --------------------------------------------------------------------------- #
# Stage B: reconcile
# --------------------------------------------------------------------------- #
class Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        self.f.write(s + "\n")


def cmp_block(P, title, cand: pd.DataFrame, off: pd.Series):
    """cand: rows=semester, cols=candidate rules.  Prints residual = candidate - official."""
    P(f"\n=== {title}: official vs candidates (value, then candidate - official) ===")
    t = cand.reindex(SEMS).copy()
    t.insert(0, "official", off.reindex(SEMS))
    tot = t.sum(numeric_only=True)
    t.loc["SUM"] = tot
    P(t.to_string())
    d = cand.reindex(SEMS).sub(off.reindex(SEMS), axis=0)
    d.loc["exact_sems"] = (d == 0).sum()
    d.loc["sum_abs"] = d.iloc[:-1].abs().sum()
    P("-- residuals:")
    P(d.to_string())


def stage_b(cache: str):
    P = Tee(OUT_TXT)
    pd.set_option("display.width", 250, "display.max_columns", 60, "display.max_rows", 200)
    P("counts_reconcile.py output,", time.strftime("%Y-%m-%d %H:%M"))
    inv, ex = load_cache(cache)

    # ---- official table self-consistency -------------------------------- #
    P("\n=== official table: column sums vs printed Total ===")
    for c, v in OFFICIAL_TOTALS.items():
        P(f"  {c:9s} sum_of_semesters={int(OFFICIAL[c].sum()):>9,d} printed_total={v:>9,d} "
          f"diff={int(OFFICIAL[c].sum()) - v:+,d}")

    # ---- archive layout -------------------------------------------------- #
    P("\n=== archive layout checks ===")
    f = inv[inv.isfile]
    wrong_top = (inv.top != inv.semester).sum()
    dup_paths = inv.duplicated(subset=["semester", "path"]).sum()
    P(f"  members={len(inv):,d} files={len(f):,d} top-dir != semester: {wrong_top}; "
      f"duplicate member paths: {dup_paths}")
    k = "OTHER:" + f.area + "/" + f.subdir
    k = k.mask(f.area.eq("users") & f.depth.eq(5), "user_file:" + f.leaf)
    k = k.mask(f.area.eq("users") & f.subdir.isin(["executions", "codes", "codemirror", "grades"])
               & f.depth.eq(6), f.subdir)
    k = k.mask(f.area.eq("assessments") & f.depth.eq(4), "assessments")
    kinds = f.assign(k=k)
    kt = kinds.pivot_table(index="semester", columns="k", values="size", aggfunc="size", fill_value=0)
    P(kt.reindex(SEMS).to_string())
    other = kinds[kinds.k.str.startswith("OTHER") | kinds.k.str.startswith("user_file:")
                  & ~kinds.k.isin(["user_file:user.data", "user_file:logins.log",
                                   "user_file:final_grade.data"])]
    if len(other):
        P("  unexpected member kinds (first 15):")
        P(other.groupby(["semester", "k"]).size().head(15).to_string())
    sz = kinds.pivot_table(index="semester", columns="k", values="size", aggfunc="sum", fill_value=0)
    P("  uncompressed MB by member kind:")
    P((sz.reindex(SEMS) / 1e6).round(0).astype(int).to_string())

    hp = os.path.join(cache, "h_server_sizes.parquet")
    if os.path.exists(hp):
        h = pd.read_parquet(hp)
        P(f"  server HEAD check (stage h): {int(h.identical_size.sum())}/{len(h)} local archives have the "
          f"server's Content-Length; server Last-Modified dates:",
          h.server_last_modified.str[5:16].value_counts().to_dict())
    zf = [os.path.join(cache, x) for x in sorted(os.listdir(cache)) if x.startswith("z_")]
    if zf:
        z = pd.concat([pd.read_parquet(x) for x in zf], ignore_index=True)
        z["same_members"] = z.rgz_members.eq(z.full_members)
        P("  stream check (stage z): gzip members, decompressed bytes, members seen by tarfile 'r|gz'")
        P("  vs a multi-member gzip reader with ignore_zeros=True:")
        P(z.to_string(index=False))

    # ---- classes --------------------------------------------------------- #
    d_cls = inv[inv.depth.ge(2)].groupby("semester").cls.nunique()
    c_ass = f[f.area.eq("assessments")].groupby("semester").cls.nunique()
    c_usr = f[f.area.eq("users")].groupby("semester").cls.nunique()
    c_both = (f[f.area.eq("assessments")][["semester", "cls"]].drop_duplicates()
              .merge(f[f.area.eq("users")][["semester", "cls"]].drop_duplicates())
              .groupby("semester").size())
    cmp_block(P, "CS1 classes", pd.DataFrame({"class_dirs": d_cls, "with_assessments": c_ass,
                                              "with_users": c_usr, "with_both": c_both}),
              OFFICIAL["classes"])

    # ---- students -------------------------------------------------------- #
    udir = inv[inv.area.eq("users") & inv.uid.ne("")][["semester", "cls", "uid"]].drop_duplicates()
    uf = f[f.area.eq("users") & f.uid.ne("")]

    def users_with(mask):
        return uf[mask][["semester", "cls", "uid"]].drop_duplicates()

    has_exec = users_with(uf["subdir"].eq("executions"))
    has_code = users_with(uf["subdir"].eq("codes"))
    has_grade = users_with(uf["subdir"].eq("grades"))
    has_final = users_with(uf.leaf.eq("final_grade.data") & uf.depth.eq(5))
    has_udata = users_with(uf.leaf.eq("user.data") & uf.depth.eq(5))
    has_login = users_with(uf.leaf.eq("logins.log") & uf.depth.eq(5))
    exu = ex.groupby(["semester", "cls", "uid"])[["n_sub", "n_test"]].sum().reset_index()
    has_block = exu[(exu.n_sub + exu.n_test) > 0][["semester", "cls", "uid"]]
    has_sub = exu[exu.n_sub > 0][["semester", "cls", "uid"]]
    cls_ass = f[f.area.eq("assessments")][["semester", "cls"]].drop_duplicates()
    in_cls_ass = udir.merge(cls_ass)
    # users with an execution file whose assessment id exists in the class's assessments
    ass_ids = f[f.area.eq("assessments")].assign(aid=lambda x: x.leaf.str.replace(r"\.\w+$", "", regex=True))
    ex_aid = ex.assign(aid=ex.leaf.str.split("_").str[0])
    ex_in = ex_aid.merge(ass_ids[["semester", "cls", "aid"]].drop_duplicates())
    has_exec_ass = ex_in[["semester", "cls", "uid"]].drop_duplicates()

    def n(df):
        return df.groupby("semester").size()

    stud = pd.DataFrame({
        "user_dirs": n(udir),
        "distinct_uid": udir.groupby("semester").uid.nunique(),
        "user.data": n(has_udata),
        "logins.log": n(has_login),
        "final_grade": n(has_final),
        "grades_dir": n(has_grade),
        "codes_dir": n(has_code),
        "exec_file": n(has_exec),
        "exec_block": n(has_block),
        "submit>=1": n(has_sub),
        "cls_w_ass": n(in_cls_ass),
        "exec_in_ass": n(has_exec_ass),
    }).fillna(0).astype(int)
    cmp_block(P, "students", stud, OFFICIAL["students"])

    # ---- exercises ------------------------------------------------------- #
    ass = pd.concat([pd.read_parquet(os.path.join(PARQUET, "assessments", f"{s}.parquet"))
                     .assign(semester=s) for s in SEMS], ignore_index=True)
    P("\n  assessment type values:", ass["type"].value_counts(dropna=False).to_dict())
    ass["ex_list"] = ass.exercise_ids.fillna("").str.split(",").apply(lambda v: [x for x in v if x])
    ass["n_list"] = ass.ex_list.str.len()
    ex_long = ass[["semester", "class", "assessment", "type", "ex_list"]].explode("ex_list").dropna(
        subset=["ex_list"])
    rows = {}
    for typ, key in (("homework", "hw_ex"), ("exam", "exam_ex")):
        a = ass[ass["type"].eq(typ)]
        e = ex_long[ex_long["type"].eq(typ)]
        rows[key] = pd.DataFrame({
            "sum_total_ex": a.groupby("semester").n_exercises.sum(),
            "sum_listed": a.groupby("semester").n_list.sum(),
            "distinct_ex": e.groupby("semester").ex_list.nunique(),
            "distinct_cls_ex": e[["semester", "class", "ex_list"]].drop_duplicates().groupby("semester").size(),
            "n_assessments": a.groupby("semester").size(),
        }).fillna(0).astype(int)
    cmp_block(P, "homework exercises", rows["hw_ex"], OFFICIAL["hw_ex"])
    cmp_block(P, "exam exercises", rows["exam_ex"], OFFICIAL["exam_ex"])
    allx = pd.DataFrame({
        "sum_total_ex_all": ass.groupby("semester").n_exercises.sum(),
        "sum_listed_all": ass.groupby("semester").n_list.sum()}).fillna(0).astype(int)
    cmp_block(P, "homework+exam exercises (official hw+exam)", allx,
              OFFICIAL["hw_ex"] + OFFICIAL["exam_ex"])

    # ---- codes ----------------------------------------------------------- #
    def trip(sub):
        x = uf[uf["subdir"].eq(sub) & uf.depth.eq(6)]
        return x.assign(key=x.leaf.str.replace(r"\.\w+$", "", regex=True))[["semester", "cls", "uid", "key"]]

    t_code, t_exec, t_cm = trip("codes"), trip("executions"), trip("codemirror")
    union = pd.concat([t_code, t_exec, t_cm]).drop_duplicates()
    codes = pd.DataFrame({
        "code_files": n(t_code),
        "code_files_nonempty": n(uf[uf["subdir"].eq("codes") & uf.depth.eq(6) & uf["size"].gt(0)]),
        "exec_files": n(t_exec),
        "codemirror_files": n(t_cm),
        "union_3": n(union),
        "exec_files_w_block": n(ex[(ex.n_sub + ex.n_test) > 0]),
    }).fillna(0).astype(int)
    cmp_block(P, "codes", codes, OFFICIAL["codes"])

    # ---- executions ------------------------------------------------------ #
    es = ex.groupby("semester")[[c for c in ex.columns if c.startswith("n_")]].sum()
    evp = {s: pd.read_parquet(os.path.join(PARQUET, "events", f"{s}.parquet"),
                              columns=["class", "user", "assessment", "exercise", "ts", "kind"])
           for s in SEMS}
    ev_rows = pd.Series({s: len(v) for s, v in evp.items()})
    ev_dup = pd.Series({s: int(v.duplicated(subset=["class", "user", "assessment", "exercise", "ts",
                                                    "kind"]).sum()) for s, v in evp.items()})
    blocks = es.n_sub + es.n_test
    execs = pd.DataFrame({
        "parquet_rows": ev_rows,
        "raw_blocks": blocks,
        "head_lines": es.n_head_lines,
        "any_head_lines": es.n_any_head_lines,
        "segments": es.n_seg,
        "minus_exact_dup": blocks - es.n_dup_exact,
        "minus_tskind_dup": blocks - es.n_dup_tskind,
        "minus_empty_code": blocks - es.n_empty_code,
        "minus_dup_and_empty": blocks - es.n_dup_exact - es.n_empty_code,
        "minus_notime_dup": blocks - es.n_dup_notime,
        "minus_samecode_dup": blocks - es.n_dup_samecode,
        "submit_only": es.n_sub,
    }).astype(int)
    cmp_block(P, "tests and submissions", execs, OFFICIAL["execs"])

    P("\n=== raw block diagnostics per semester ===")
    P("  dup_exact: byte-identical to an earlier block of the same file; dup_notime: identical except the")
    P("  EXECUTION TIME value; dup_samecode: same header (kind+ts) and same code; dup_tskind: same kind+ts;")
    P("  parquet_dup_key: rows duplicated on (class,user,assessment,exercise,ts,kind) in events parquet")
    diag = es[["n_seg_nohead", "n_multi_head_seg", "n_sub", "n_test", "n_dup_exact",
               "n_dup_exact_adjacent", "n_dup_exact_sub", "n_dup_notime", "n_dup_notime_sub",
               "n_dup_notime_adjacent", "n_dup_samecode", "n_dup_tskind", "n_empty_code",
               "n_no_code"]].copy()
    diag["parquet_dup_key"] = ev_dup
    P(diag.reindex(SEMS).rename(columns=lambda c: c.replace("n_", "", 1)).to_string())
    P("  totals:", {k.replace("n_", "", 1): int(v) for k, v in diag.sum().items()})

    # ---- where the missing executions could be (DEV only) ---------------- #
    P("\n=== DEV calendar: assessments and last event per semester ===")
    evl = pd.Series({s: evp[s].ts.max() for s in SEMS if s not in SEALED})
    evf = pd.Series({s: evp[s].ts.min() for s in SEMS if s not in SEALED})
    cal = ass[~ass.semester.isin(SEALED)].groupby("semester").agg(
        n_ass=("assessment", "size"), first_start=("start", "min"), last_end=("end", "max"))
    cal["first_event"], cal["last_event"] = evf, evl
    cm_last = {}
    for s in SEMS:
        if s in SEALED:
            continue
        cm = pd.read_parquet(os.path.join(PARQUET, "codemirror", f"{s}.parquet"), columns=["minute"])
        cm_last[s] = cm.minute.max()
    cal["last_keystroke_minute"] = pd.Series(cm_last)
    P(cal.reindex([s for s in SEMS if s not in SEALED]).to_string())
    P("\n  per class, the two DEV semesters that miss official exercises (2019-2, 2020-1):")
    for s in ("2019-2", "2020-1"):
        a = ass[ass.semester.eq(s)]
        pc = a.pivot_table(index="class", columns="type", values="n_exercises", aggfunc="sum",
                           fill_value=0).add_prefix("ex_")
        pc["n_ass"] = a.groupby("class").size()
        pc["last_end"] = a.groupby("class").end.max()
        pc["users"] = udir[udir.semester.eq(s)].groupby("cls").size()
        e = evp[s]
        pc["blocks"] = e.groupby("class").size()
        pc["last_event"] = e.groupby("class").ts.max()
        P(f"  {s}:")
        P(pc.to_string())
    mm = inv[inv.isfile & inv.subdir.eq("mousemove") & ~inv.semester.isin(SEALED)]
    if len(mm):
        P("  mousemove files (DEV): depth values", mm.depth.value_counts().to_dict(),
          "| leaf name pattern", mm.leaf.str.replace(r"\d+", "N", regex=True).value_counts().head(3).to_dict())

    P("\n=== execution files whose assessment / exercise is not in the class's assessment files ===")
    alist = ex_long.assign(key=ex_long["class"] + "/" + ex_long["assessment"] + "_" + ex_long["ex_list"])
    exk = ex_aid.assign(ex_id=ex_aid.leaf.str.replace(r"\.\w+$", "", regex=True).str.split("_").str[1],
                        akey=ex_aid.cls + "/" + ex_aid.aid)
    exk["key"] = exk.akey + "_" + exk.ex_id
    akeys = set((ass["semester"] + ":" + ass["class"] + "/" + ass["assessment"]).tolist())
    ekeys = set((alist["semester"] + ":" + alist["key"]).tolist())
    exk["ass_known"] = (exk.semester + ":" + exk.akey).isin(akeys)
    exk["ex_listed"] = (exk.semester + ":" + exk.key).isin(ekeys)
    orphan = exk.groupby("semester").agg(exec_files=("leaf", "size"),
                                         assessment_missing=("ass_known", lambda x: int((~x).sum())),
                                         exercise_not_listed=("ex_listed", lambda x: int((~x).sum())))
    P(orphan.reindex(SEMS).to_string())

    P("\n=== uids enrolled in two classes of one semester: are their execution files copies? ===")
    mc = udir.groupby(["semester", "uid"]).cls.nunique()
    mc = mc[mc > 1].reset_index()[["semester", "uid"]]
    exm = ex.merge(mc)
    same_leaf = exm.groupby(["semester", "uid", "leaf"]).agg(n_cls=("cls", "nunique"),
                                                          n_bytes=("nbytes", "nunique"))
    P(f"  (semester,uid) in >1 class: {len(mc)}; their execution files: {len(exm):,d}; "
      f"file names present in >1 class: {int((same_leaf.n_cls > 1).sum())} "
      f"(of which byte-size identical: {int(((same_leaf.n_cls > 1) & (same_leaf.n_bytes == 1)).sum())})")
    cls_counts = exm.groupby(["semester", "uid"]).cls.nunique()
    P(f"  of those (semester,uid), with execution files in >1 class: {int((cls_counts > 1).sum())}")

    # ---- assessment window (DEV and sealed: counts only) ------------------ #
    P("\n=== events outside their assessment's [start, end] window (counts only) ===")
    ass_w = ass[["semester", "class", "assessment", "start", "end"]]
    wrows = []
    for s in SEMS:
        v = evp[s].merge(ass_w[ass_w.semester.eq(s)].drop(columns="semester"),
                         on=["class", "assessment"], how="left")
        no_ass = int(v.start.isna().sum())
        before = int((v.ts < v.start).sum())
        after = int((v.ts > v.end + pd.Timedelta(seconds=59)).sum())
        wrows.append(dict(semester=s, rows=len(v), no_assessment=no_ass, before_start=before,
                          after_end=after, inside=len(v) - no_ass - before - after))
    w = pd.DataFrame(wrows).set_index("semester")
    P(w.to_string())
    cmp_block(P, "tests and submissions, window rules", pd.DataFrame({
        "inside_window": w.inside, "not_before_start": w.rows - w.no_assessment - w.before_start}),
        OFFICIAL["execs"])

    # ---- student ids across semesters ------------------------------------ #
    P("\n=== student ids across semesters (entity counts) ===")
    u = udir.copy()
    P(f"  (semester,class,uid) dirs={len(u):,d}; distinct (semester,uid)="
      f"{len(u[['semester', 'uid']].drop_duplicates()):,d}; distinct uid={u.uid.nunique():,d}")
    multi_cls = u.groupby(["semester", "uid"]).size()
    P(f"  uids in >1 class within one semester: {int((multi_cls > 1).sum())}")
    nsem = u[["semester", "uid"]].drop_duplicates().groupby("uid").size()
    P("  distinct uids by number of semesters they appear in:", nsem.value_counts().sort_index().to_dict())
    dev = u[~u.semester.isin(SEALED)]
    nsd = dev[["semester", "uid"]].drop_duplicates().groupby("uid").size()
    P("  DEV only: distinct uids", dev.uid.nunique(), "by #semesters:", nsd.value_counts().sort_index().to_dict())
    ub = has_block[["semester", "uid"]].drop_duplicates()
    nsb = ub.groupby("uid").size()
    P(f"  with >=1 block: distinct uid={ub.uid.nunique():,d}, (semester,uid)={len(ub):,d}, "
      f"by #semesters: {nsb.value_counts().sort_index().to_dict()}")
    P("  official students total 5,229 vs distinct (semester,uid) with a user dir:",
      len(u[["semester", "uid"]].drop_duplicates()))
    sealed_ids = set(u[u.semester.isin(SEALED)].uid)
    dev_ids = set(dev.uid)
    P(f"  uids in sealed semesters: {len(sealed_ids)}; of these also in a DEV semester: "
      f"{len(sealed_ids & dev_ids)}")
    stray = inv[inv.isfile & inv.area.eq("")]
    P("  files outside <class>/<area>/ layout:", stray[["semester", "path", "size"]].to_dict("records"))
    nousers = (f[f.area.eq("assessments")][["semester", "cls"]].drop_duplicates()
               .merge(f[f.area.eq("users")][["semester", "cls"]].drop_duplicates(), how="left",
                      indicator=True))
    nousers = nousers[nousers._merge.eq("left_only")]
    for _, r in nousers.iterrows():
        k = int(((f.semester == r.semester) & (f.cls == r.cls) & f.area.eq("assessments")).sum())
        P(f"  class with assessments but no users: {r.semester}/{r.cls} ({k} assessment files)")

    # ---- summary: best rule per official row ------------------------------ #
    best = pd.DataFrame({
        "classes": c_ass,
        "students": stud["distinct_uid"],
        "hw_ex": rows["hw_ex"]["sum_total_ex"],
        "exam_ex": rows["exam_ex"]["sum_total_ex"],
        "codes": codes["code_files"],
        "execs": execs["raw_blocks"],
    }).reindex(SEMS)
    res = best - OFFICIAL[best.columns]
    pct = (100 * res / OFFICIAL[best.columns]).round(2)
    P("\n=== SUMMARY: best rule per official row; ours, residual (ours - official), residual % ===")
    P("  classes=class dirs with assessment files; students=distinct user ids in the semester;")
    P("  hw/exam=sum of total_exercises over assessments of that type; codes=files under users/*/codes;")
    P("  execs=all SUBMITION+TEST blocks in executions/*.log, no deduplication")
    best.loc["SUM"] = best.sum()
    res.loc["SUM"] = res.sum()
    pct.loc["SUM"] = (100 * res.loc["SUM"] / OFFICIAL[best.columns].sum()).round(2)
    out = pd.concat({"ours": best.astype(int), "resid": res.astype(int), "pct": pct}, axis=1)
    P(out.to_string())
    P("  exact semesters per row:", {c: int((res.loc[SEMS, c] == 0).sum()) for c in res.columns})
    P("  (SUM pct is against the column sums of the official table, not its printed Total row)")
    P("\ndone.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--stage", default="ab",
                    help="any of h (server sizes), z (stream check), a (stream), b (reconcile)")
    ap.add_argument("--only", default="", help="stage z: comma separated archive tags, e.g. 2019_2")
    args = ap.parse_args()
    if "h" in args.stage:
        stage_h(args.cache)
    if "z" in args.stage:
        stage_z(args.cache, args.workers, args.only)
    if "a" in args.stage:
        stage_a(args.cache, args.workers)
    if "b" in args.stage:
        stage_b(args.cache)


if __name__ == "__main__":
    main()
