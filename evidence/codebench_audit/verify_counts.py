"""Independent check of the CodeBench v1.81 count reconciliation (counts_reconcile.py).

Re-implements the counting rules from scratch on the raw archives, without reusing the
earlier parser or counts_reconcile.py. DEV semesters only (2016-1..2022-2); sealed
semesters are never opened.

Stages (each one run in the foreground, results cached in the cache directory):
  parse <sem> [<sem> ...]   stream archive(s), cache per-semester tables (hashes only, no code text)
  report                    compare cached counts with the official table -> verify_counts.txt

Privacy: code text is never stored or printed; blocks are kept as 64-bit hashes.
user.data is only checked for presence. codemirror logs are read for timestamps and
event-type names only.
"""
import hashlib, io, json, os, re, subprocess, sys, tarfile, time, zlib
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = r"<repo-root>"
ARCH = os.path.join(ROOT, r"data\codebench\archives")
PARQ = os.path.join(ROOT, r"data\codebench\parquet")
OUT = os.path.join(ROOT, r"evidence\codebench_audit\verify_counts.txt")
SCRATCH = r"<cache-dir>"
CACHE = os.path.join(SCRATCH, "verify_cache")
PAGE = os.path.join(SCRATCH, "verify_dataset_page.html")
PAGE_URL = "https://codebench.icomp.ufam.edu.br/dataset/"

SEMS = ["2016-1", "2016-2", "2017-1", "2017-2", "2018-1", "2018-2", "2019-1", "2019-2",
        "2020-ERE", "2020-1", "2020-2", "2021-1", "2021-2", "2022-1", "2022-2",
        "2023-1", "2023-2", "2024-1"]
SEALED = {"2023-1", "2023-2", "2024-1"}
DEV = [s for s in SEMS if s not in SEALED]
FULL_CM_SCAN = {"2019-2"}  # full codemirror event-type byte count only where the truncation claim needs it

HDR = re.compile(rb"^== (SUBMITION|TEST) \(([^)\n]*)\)[^\n]*$", re.M)
HDR_ANY = re.compile(rb"== (?:SUBMITION|TEST) \(\d{4}-")
SECTION = re.compile(rb"^-- (?:CODE|EXECUTION TIME|TEST CASE \d+|OUTPUT|ERROR|GRADE):[ \t]*\r?$", re.M)
TS = re.compile(rb"\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d\d:\d\d")
CM_LINE = re.compile(rb"^(\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d\d:\d\d)(?:\.\d+)?#([A-Za-z_]+)", re.M)
TS_PARTS = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d\d):(\d\d)")
PADDED = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
MM_TS = re.compile(rb'"(\d{1,2})/(\d{1,2})/(\d{4})@(\d{1,2}):(\d\d):(\d\d)')  # mousemove logs: D/M/YYYY@H:MM:SS:mmm


def norm_ts(s):
    """Zero-pad a timestamp so string order equals time order (some logs write 2019-9-19)."""
    if isinstance(s, bytes):
        s = s.decode()
    m = TS_PARTS.match(s)
    return "%s-%02d-%02d %02d:%s:%s" % (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5), m.group(6)) if m else s
MASK_D, MASK_A = re.compile(rb"\d"), re.compile(rb"[A-Za-z]")


def mask(b):
    return MASK_A.sub(b"a", MASK_D.sub(b"9", b[:32])).decode("ascii", errors="replace")


def h64(b):
    return int.from_bytes(hashlib.blake2b(b, digest_size=8).digest(), "little", signed=True)


class MultiGz(io.RawIOBase):
    """Decompress every gzip member in a file (tarfile's own r|gz reader stops after the first)."""

    def __init__(self, path):
        self.f = open(path, "rb")
        self.d = zlib.decompressobj(wbits=31)
        self.members = 1
        self.buf = b""
        self.pos = 0
        self.trailing_garbage = 0

    def readable(self):
        return True

    def _fill(self):
        if self.pos >= len(self.buf):
            self.buf, self.pos = b"", 0
        while not self.buf:
            if self.d.eof:
                rest = self.d.unused_data
                if not rest:
                    rest = self.f.read(1 << 20)
                if not rest:
                    return False
                if rest[:2] != b"\x1f\x8b":
                    self.trailing_garbage += len(rest) + len(self.f.read())
                    return False
                self.members += 1
                self.d = zlib.decompressobj(wbits=31)
                self.buf = self.d.decompress(rest)
                continue
            chunk = self.f.read(1 << 20)
            if not chunk:
                return False
            self.buf = self.d.decompress(chunk)
        return True

    def read(self, n=-1):
        out = []
        need = n if n is not None and n >= 0 else 1 << 62
        while need > 0 and self._fill():
            take = self.buf[self.pos:self.pos + need]
            self.pos += len(take)
            out.append(take)
            need -= len(take)
        return b"".join(out)


def split_blocks(data):
    """Return list of (kind, ts, block_bytes) plus preamble bytes before the first header."""
    ms = list(HDR.finditer(data))
    pre = data[: ms[0].start()] if ms else data
    blocks = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(data)
        blocks.append((m.group(1).decode(), m.group(2).decode(errors="replace"), data[m.start():end]))
    return pre, blocks


def sections(block):
    """Map section name -> bytes body (first occurrence), for CODE and EXECUTION TIME."""
    marks = list(SECTION.finditer(block))
    out = {}
    for i, m in enumerate(marks):
        name = m.group(0).split(b":")[0][3:].decode()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
        out.setdefault(name, (m.end(), end))
    return out


def parse_assessment(data):
    txt = data.decode("utf-8", errors="replace")
    f = {}
    for key in ("type", "total_exercises", "start", "end"):
        m = re.search(r"^---- %s:\s*(.*?)\s*$" % key, txt, re.M)
        f[key] = m.group(1) if m else None
    ex = re.findall(r"^---- exercise \d+:\s*(\d+)\s*$", txt, re.M)
    return f, ex


def parse_semester(sem):
    assert sem not in SEALED, "sealed semester"
    path = os.path.join(ARCH, "cb_dataset_%s_v1.81.tar.gz" % sem.replace("-", "_"))
    t0 = time.time()
    gz = MultiGz(path)
    tar = tarfile.open(fileobj=gz, mode="r|", ignore_zeros=True)
    shape_n, shape_b = Counter(), Counter()
    level2 = defaultdict(set)
    names_seen = Counter()
    assess, users, execf, codef, cmf, blocks = [], set(), [], [], [], []
    has_ud, has_login = set(), set()
    cls_exec_max, cls_cm_max, cls_login_max, cls_mm_max = {}, {}, {}, {}
    date_memo, month_n = {}, Counter()
    cm_type_bytes, cm_type_n = Counter(), Counter()
    stats = Counter()
    fid = 0
    for m in tar:
        names_seen[m.name] += 1
        parts = m.name.strip("/").split("/")
        typ = "file" if m.isfile() else "dir" if m.isdir() else "lnk" if m.islnk() else "sym" if m.issym() else "other"
        if len(parts) >= 2:
            level2[parts[1]].add(typ)
        ci = next((i for i in range(len(parts) - 1) if parts[i].isdigit() and parts[i + 1] in ("assessments", "users")), None)
        if typ != "file":
            shape_n["%s:%s" % (typ, "classtree" if ci is not None else "/".join(p if not p.isdigit() else "N" for p in parts[:3]))] += 1
            continue
        cls = parts[ci] if ci is not None else None
        rest = parts[ci + 1:] if ci is not None else parts
        if cls is not None and rest[0] == "assessments" and len(rest) == 2 and rest[1].endswith(".data"):
            shape = "assessment"
        elif cls is not None and rest[0] == "users" and len(rest) >= 3:
            sub = rest[2]
            shape = {"executions": "exec", "codes": "code", "codemirror": "cm", "grades": "grade",
                     "logins.log": "logins", "user.data": "userdata"}.get(sub, "user_other:" + sub)
            if len(rest) == 4 and sub in ("executions", "codes", "codemirror", "grades"):
                pass
            elif len(rest) != 3 or sub not in ("logins.log", "user.data"):
                shape = shape if len(rest) == 4 else shape + ":depth%d" % len(rest)
        else:
            shape = "stray:" + m.name
        shape_n[shape] += 1
        shape_b[shape] += m.size
        f = tar.extractfile(m)
        data = f.read() if f is not None else b""
        if f is None:
            stats["unreadable_file"] += 1
        if shape == "assessment":
            fl, ex = parse_assessment(data)
            assess.append(dict(cls=cls, aid=rest[1][:-5], type=fl["type"], total_exercises=fl["total_exercises"],
                               start=fl["start"], end=fl["end"], n_listed=len(ex), exercises=",".join(ex)))
            continue
        if cls is None or rest[0] != "users":
            continue
        uid = rest[1]
        users.add((cls, uid))
        if shape == "userdata":
            has_ud.add((cls, uid))
        elif shape == "logins":
            has_login.add((cls, uid))
            ts = TS.findall(data)
            if ts:
                mx = max(norm_ts(x) for x in ts)
                cls_login_max[cls] = max(cls_login_max.get(cls, ""), mx)
        elif shape == "exec":
            stem = rest[3].rsplit(".", 1)[0]
            a, _, e = stem.partition("_")
            execf.append((cls, uid, a, e, rest[3]))
            fid += 1
            stats["hdr_anywhere"] += len(HDR_ANY.findall(data))
            pre, bl = split_blocks(data)
            if pre.strip():
                stats["preamble_nonempty"] += 1
            for j, (kind, ts, b) in enumerate(bl):
                if not PADDED.match(ts):
                    stats["exec_ts_unpadded"] += 1
                    ts = norm_ts(ts)
                if len(HDR_ANY.findall(b)) != 1:
                    stats["block_multi_hdr"] += 1
                sec = sections(b)
                cs, ce = sec.get("CODE", (0, 0))
                code = b[cs:ce]
                es, ee = sec.get("EXECUTION TIME", (0, 0))
                et = b[es:ee]
                noexec = b[:es] + b[ee:] if "EXECUTION TIME" in sec else b
                blocks.append((cls, uid, a, e, fid, j, kind, ts, h64(b), h64(noexec), h64(code),
                               not code.strip(), bool(et.strip()), "CODE" in sec))
                if ts > cls_exec_max.get(cls, ""):
                    cls_exec_max[cls] = ts
        elif shape == "code":
            codef.append((cls, uid, rest[3].rsplit(".", 1)[0], rest[3].rsplit(".", 1)[-1]))
        elif shape == "user_other:mousemove" and sem in FULL_CM_SCAN:
            lines = [x for x in data[-4096:].split(b"\n") if x.strip()]
            if lines:
                stats["mm_last_line_shape:" + mask(lines[-1])] += 1
            ts = ["%s-%02d-%02d %02d:%s:%s" % (y.decode(), int(mo), int(d), int(h), mi.decode(), s.decode())
                  for d, mo, y, h, mi, s in MM_TS.findall(data[-4096:])]
            stats["mm_month_field_gt12"] += sum(int(x[1]) > 12 for x in MM_TS.findall(data[-4096:]))
            stats["mm_day_field_gt12"] += sum(int(x[0]) > 12 for x in MM_TS.findall(data[-4096:]))
            if ts:
                t = max(ts)
                stats["mousemove_files_with_ts"] += 1
                if t > cls_mm_max.get(cls, ""):
                    cls_mm_max[cls] = t
        elif shape == "cm":
            cmf.append((cls, uid, rest[3].rsplit(".", 1)[0]))
            if sem in FULL_CM_SCAN:
                for line in data.split(b"\n"):
                    mm = CM_LINE.match(line)
                    if mm:
                        cm_type_n[mm.group(2).decode()] += 1
                        cm_type_bytes[mm.group(2).decode()] += len(line) + 1
                        d, _, tm = mm.group(1).partition(b" ")
                        if d not in date_memo:
                            y, mo, dd = d.split(b"-")
                            date_memo[d] = "%s-%02d-%02d" % (y.decode(), int(mo), int(dd))
                        t = date_memo[d] + " " + tm.decode() if len(tm) == 8 else norm_ts(mm.group(1))
                        if t > cls_cm_max.get(cls, ""):
                            cls_cm_max[cls] = t
                        month_n[t[:7]] += 1
                    else:
                        cm_type_bytes["<continuation>"] += len(line) + 1
                        if line.strip():
                            stats["cm_unmatched_shape:" + mask(line)] += 1
            else:
                tail = CM_LINE.findall(data[-4096:])
                if tail:
                    t = max(norm_ts(x[0]) for x in tail)
                    if t > cls_cm_max.get(cls, ""):
                        cls_cm_max[cls] = t
    tar.close()
    os.makedirs(CACHE, exist_ok=True)
    bcols = ["cls", "uid", "a", "e", "fid", "idx", "kind", "ts", "h_full", "h_noexec", "h_code", "code_empty", "et_nonempty", "has_code_sec"]
    pd.DataFrame(blocks, columns=bcols).to_parquet(os.path.join(CACHE, sem + "_blocks.parquet"))
    pd.DataFrame(execf, columns=["cls", "uid", "a", "e", "fname"]).to_parquet(os.path.join(CACHE, sem + "_execf.parquet"))
    pd.DataFrame(codef, columns=["cls", "uid", "stem", "ext"]).to_parquet(os.path.join(CACHE, sem + "_codef.parquet"))
    pd.DataFrame(cmf, columns=["cls", "uid", "stem"]).to_parquet(os.path.join(CACHE, sem + "_cmf.parquet"))
    pd.DataFrame(assess).to_parquet(os.path.join(CACHE, sem + "_assess.parquet"))
    udf = pd.DataFrame(sorted(users), columns=["cls", "uid"])
    udf["has_userdata"] = [(c, u) in has_ud for c, u in sorted(users)]
    udf["has_logins"] = [(c, u) in has_login for c, u in sorted(users)]
    udf.to_parquet(os.path.join(CACHE, sem + "_users.parquet"))
    summ = dict(sem=sem, seconds=round(time.time() - t0, 1), gzip_members=gz.members, trailing_garbage=gz.trailing_garbage,
                dup_tar_paths=sum(1 for v in names_seen.values() if v > 1), shape_n=dict(shape_n), shape_bytes=dict(shape_b),
                level2={k: sorted(v) for k, v in level2.items()}, stats=dict(stats),
                cls_exec_max=cls_exec_max, cls_cm_max=cls_cm_max, cls_login_max=cls_login_max, cls_mm_max=cls_mm_max,
                cm_type_bytes=dict(cm_type_bytes), cm_type_n=dict(cm_type_n), cm_month_n=dict(month_n))
    with open(os.path.join(CACHE, sem + "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summ, fh, ensure_ascii=False)
    print("%-8s %6.1fs blocks=%d execf=%d codef=%d users=%d gz_members=%d" % (
        sem, time.time() - t0, len(blocks), len(execf), len(codef), len(users), gz.members), flush=True)


# ---------------------------------------------------------------- report
ROWS = ["classes", "students", "hw", "exam", "codes", "execs"]


def official_table():
    if not os.path.exists(PAGE):
        subprocess.run(["curl", "-s", "-m", "60", PAGE_URL, "-o", PAGE], check=True)
    html = open(PAGE, encoding="utf-8", errors="replace").read()
    tbl = re.search(r"<table.*?</table>", html, re.S).group(0)
    cells = [re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tbl, re.S)]
    labels = ["CS1 classes", "Total number of students", "Homework exercises", "Exam exercises",
              "Codes (developed by students)", "Tests and submissions of codes"]
    off = {}
    for key, lab in zip(ROWS, labels):
        i = cells.index(lab)
        vals = [int(v.replace(",", "").replace(".", "")) for v in cells[i + 1:i + 1 + len(SEMS) + 1]]
        off[key] = dict(zip(SEMS + ["Total"], vals))
    return off


def load(sem, name):
    return pd.read_parquet(os.path.join(CACHE, "%s_%s.parquet" % (sem, name)))


def dup_breakdown(b):
    """Nested duplicate counts inside (cls,uid,a,e,ts,kind) groups."""
    key = ["cls", "uid", "a", "e", "ts", "kind"]
    n = len(b)
    u_key = len(b.drop_duplicates(key))
    u_code = len(b.drop_duplicates(key + ["h_code"]))
    u_noexec = len(b.drop_duplicates(key + ["h_noexec"]))
    u_full = len(b.drop_duplicates(key + ["h_full"]))
    return dict(key_dup=n - u_key, byte_ident=n - u_full, only_exectime=u_full - u_noexec,
                same_code_diff_out=u_noexec - u_code, diff_code=u_code - u_key)


def report(sems):
    off = official_table()
    L = []
    p = L.append
    p("verify_counts.py report, %s. Semesters parsed here: %s" % (time.strftime("%Y-%m-%d %H:%M"), ", ".join(sems)))
    p("")
    p("== 1. Official v1.81 table (parsed from %s)" % PAGE_URL)
    p("%-9s" % "row" + "".join("%9s" % s[2:] for s in SEMS) + "%9s%9s" % ("Total", "colsum"))
    for k in ROWS:
        cs = sum(off[k][s] for s in SEMS)
        p("%-9s" % k + "".join("%9d" % off[k][s] for s in SEMS) + "%9d%9d%s" % (off[k]["Total"], cs, "" if cs == off[k]["Total"] else "  <-- Total != colsum"))
    p("")
    res = {}
    for sem in sems:
        S = json.load(open(os.path.join(CACHE, sem + "_summary.json"), encoding="utf-8"))
        b, ef, cf, cm = load(sem, "blocks"), load(sem, "execf"), load(sem, "codef"), load(sem, "cmf")
        A, U = load(sem, "assess"), load(sem, "users")
        A["te"] = pd.to_numeric(A.total_exercises, errors="coerce")
        r = {}
        # classes
        lvl2_dirs = [k for k, v in S["level2"].items() if "dir" in v]
        lvl2_all = list(S["level2"].keys())
        r["cls_level2_all"] = len(lvl2_all)
        r["cls_level2_dirs"] = len(lvl2_dirs)
        r["cls_with_assess"] = A.cls.nunique()
        r["cls_with_users"] = U.cls.nunique()
        r["stray"] = [k for k in S["shape_n"] if k.startswith("stray:")]
        r["cls_no_users"] = sorted(set(A.cls) - set(U.cls))
        # students
        r["user_dirs"] = len(U)
        r["distinct_uid"] = U.uid.nunique()
        r["distinct_uid_userdata"] = U[U.has_userdata].uid.nunique()
        r["distinct_uid_exec"] = ef.uid.nunique()
        r["distinct_uid_block"] = b.uid.nunique()
        multi = U.groupby("uid").cls.nunique()
        r["uid_in_2plus_classes"] = int((multi > 1).sum())
        shared = 0
        for uid in multi[multi > 1].index:
            g = ef[ef.uid == uid].groupby("cls").fname.apply(set).tolist()
            if len(g) > 1:
                shared += len(set.intersection(*g))
        r["dual_uid_shared_exec_names"] = shared
        # exercises
        for t in ("homework", "exam"):
            At = A[A.type == t]
            r[t + "_sum_total"] = int(At.te.sum())
            r[t + "_listed"] = int(At.n_listed.sum())
            ids = set(x for s in At.exercises for x in s.split(",") if x)
            r[t + "_distinct_ids"] = len(ids)
        r["types"] = dict(Counter(A.type))
        r["n_assess"] = len(A)
        # codes
        r["code_files"] = len(cf)
        r["exec_files"] = len(ef)
        r["cm_files"] = len(cm)
        ks = lambda d, c: set(map(tuple, d[["cls", "uid", c]].values))
        r["union_code_exec_cm"] = len(ks(cf, "stem") | set((c, u, f.rsplit(".", 1)[0]) for c, u, f in ef[["cls", "uid", "fname"]].values) | ks(cm, "stem"))
        r["code_exts"] = dict(Counter(cf.ext))
        # executions
        r["blocks"] = len(b)
        r["hdr_anywhere"] = S["stats"].get("hdr_anywhere", 0)
        r["preamble_nonempty"] = S["stats"].get("preamble_nonempty", 0)
        r["block_multi_hdr"] = S["stats"].get("block_multi_hdr", 0)
        r["submit"] = int((b.kind == "SUBMITION").sum())
        r["test"] = int((b.kind == "TEST").sum())
        r["code_empty"] = int(b.code_empty.sum())
        r["no_code_section"] = int((~b.has_code_sec).sum())
        r.update(dup_breakdown(b))
        r["rows_in_dup_groups"] = int(b.duplicated(["cls", "uid", "a", "e", "ts", "kind"], keep=False).sum())
        r["exec_files_no_block"] = len(ef) - b.fid.nunique()
        bt = b[b.kind == "TEST"]
        r["test_byte_ident"] = dup_breakdown(bt)["byte_ident"]
        r["test_byte_share"] = r["test_byte_ident"] / max(1, len(bt))
        bs = b[b.kind == "SUBMITION"]
        dsub = dup_breakdown(bs)
        r["sub_byte_ident"], r["sub_only_exectime"] = dsub["byte_ident"], dsub["only_exectime"]
        r["sub_et_filled_share"] = round(float(bs.et_nonempty.mean()), 3) if len(bs) else 0.0
        # adjacency of byte-identical copies
        bb = b.sort_values(["fid", "idx"])
        prev_same = (bb.fid.values[1:] == bb.fid.values[:-1]) & (bb.h_full.values[1:] == bb.h_full.values[:-1])
        r["byte_ident_adjacent"] = int(prev_same.sum())
        # window
        Aw = A.assign(aid=A.aid.astype(str))[["cls", "aid", "start", "end"]]
        bw = b.merge(Aw, left_on=["cls", "a"], right_on=["cls", "aid"], how="left")
        inw = (bw.ts >= bw.start.fillna("9") + ":00") & (bw.ts <= bw.end.fillna("0") + ":59")
        r["in_window"] = int(inw.sum())
        # exec files whose exercise is not listed in the assessment
        lst = set((c, a_, x) for c, a_, s in A[["cls", "aid", "exercises"]].values for x in s.split(",") if x)
        r["exec_unlisted_ex"] = int(sum((c, a_, e_) not in lst for c, a_, e_ in ef[["cls", "a", "e"]].values))
        # parquet row count from the earlier parser
        pf = os.path.join(PARQ, "events", sem + ".parquet")
        r["parquet_rows"] = pq.ParquetFile(pf).metadata.num_rows if os.path.exists(pf) else None
        r["gzip_members"] = S["gzip_members"]
        r["trailing_garbage"] = S["trailing_garbage"]
        r["dup_tar_paths"] = S["dup_tar_paths"]
        r["nonfile_members"] = {k: v for k, v in S["shape_n"].items() if not (k.startswith("dir:") or k in ("assessment", "exec", "code", "cm", "grade", "logins", "userdata"))}
        r["uncompressed_mb"] = round(sum(S["shape_bytes"].values()) / 2**20, 1)
        r["S"] = S
        r["A"] = A
        res[sem] = r

    p("== 2. Independent counts vs official (official / ours; rule named in the header)")
    p("%-8s %7s %7s %9s %9s %9s %9s %11s %11s %9s %13s %13s %8s" % (
        "sem", "cls:ass", "cls:all", "stu:dist", "stu:dirs", "hw:sumTE", "ex:sumTE", "hw:listed", "hw:dist_id", "codes", "codes_off", "blocks", "Δblk%"))
    for sem in sems:
        r = res[sem]
        o = {k: off[k][sem] for k in ROWS}
        p("%-8s %3d/%-3d %3d/%-3d %4d/%-4d %4d/%-4d %4d/%-4d %4d/%-4d %11d %11d %9d %13d %13d %+8.2f" % (
            sem, o["classes"], r["cls_with_assess"], o["classes"], r["cls_level2_all"], o["students"], r["distinct_uid"],
            o["students"], r["user_dirs"], o["hw"], r["homework_sum_total"], o["exam"], r["exam_sum_total"],
            r["homework_listed"], r["homework_distinct_ids"], r["code_files"], o["codes"], r["blocks"],
            100.0 * (r["blocks"] - o["execs"]) / o["execs"]))
    p("  (cls:ass = class dirs holding assessment files; cls:all = every entry at level 2 of the tar)")
    p("")
    p("== 3. Rule checks per semester")
    hdr = ["sem", "exact:cls", "stu", "hw", "exam", "codes", "execs", "Δcodes%", "Δexec%", "stu_alt(dirs/ud/exec)"]
    p("%-8s %9s %4s %3s %4s %5s %5s %8s %8s  %s" % tuple(hdr))
    for sem in sems:
        r = res[sem]
        o = {k: off[k][sem] for k in ROWS}
        p("%-8s %9s %4s %3s %4s %5s %5s %+8.2f %+8.2f  %d/%d/%d" % (
            sem, r["cls_with_assess"] == o["classes"], r["distinct_uid"] == o["students"], r["homework_sum_total"] == o["hw"],
            r["exam_sum_total"] == o["exam"], r["code_files"] == o["codes"], r["blocks"] == o["execs"],
            100.0 * (r["code_files"] - o["codes"]) / o["codes"], 100.0 * (r["blocks"] - o["execs"]) / o["execs"],
            r["user_dirs"], r["distinct_uid_userdata"], r["distinct_uid_exec"]))
    p("")
    p("== 4. Archive integrity and parser cross-check")
    p("%-8s %4s %6s %5s %10s %10s %10s %6s %5s %5s %6s %9s  %s" % (
        "sem", "gzM", "trail", "dupP", "blocks", "hdr_any", "parquet", "pre", "mhdr", "noCS", "emptyC", "unc_MB", "non-standard members"))
    for sem in sems:
        r = res[sem]
        p("%-8s %4d %6d %5d %10d %10d %10s %6d %5d %5d %6d %9.1f  %s" % (
            sem, r["gzip_members"], r["trailing_garbage"], r["dup_tar_paths"], r["blocks"], r["hdr_anywhere"], r["parquet_rows"],
            r["preamble_nonempty"], r["block_multi_hdr"], r["no_code_section"], r["code_empty"], r["uncompressed_mb"],
            r["nonfile_members"] or "-"))
    p("")
    p("== 5. Duplicates inside (class,user,assessment,exercise,ts,kind) groups")
    p("%-8s %8s %8s %8s %8s %8s %8s %9s %9s %8s %9s %9s %7s %8s %6s" % (
        "sem", "key_dup", "byteId", "onlyET", "sameCd", "diffCd", "adjac", "sub:byte", "sub:ET", "ETfill", "in_window",
        "test:byte", "t:byte%", "inGroups", "f0blk"))
    tot = Counter()
    for sem in sems:
        r = res[sem]
        p("%-8s %8d %8d %8d %8d %8d %8d %9d %9d %8.3f %9d %9d %7.2f %8d %6d" % (
            sem, r["key_dup"], r["byte_ident"], r["only_exectime"], r["same_code_diff_out"], r["diff_code"], r["byte_ident_adjacent"],
            r["sub_byte_ident"], r["sub_only_exectime"], r["sub_et_filled_share"], r["in_window"],
            r["test_byte_ident"], 100 * r["test_byte_share"], r["rows_in_dup_groups"], r["exec_files_no_block"]))
        for k in ("blocks", "submit", "test", "key_dup", "byte_ident", "only_exectime", "same_code_diff_out", "diff_code",
                  "byte_ident_adjacent", "code_empty", "code_files", "user_dirs", "distinct_uid", "in_window",
                  "test_byte_ident", "sub_byte_ident", "rows_in_dup_groups", "exec_files_no_block"):
            tot[k] += r[k]
        if sem >= "2018-1":
            tot["sub_byte_ET_era"] += r["sub_byte_ident"]
            tot["sub_onlyET_ET_era"] += r["sub_only_exectime"]
    p("sum      " + ", ".join("%s=%d" % kv for kv in tot.items()))
    p("")
    p("== 6. Semester-specific claims")
    for sem in sems:
        r, S, A = res[sem], res[sem]["S"], res[sem]["A"]
        if sem == "2019-2":
            p("2019-2 last exec ts per class: %s" % ", ".join("%s:%s" % kv for kv in sorted(S["cls_exec_max"].items())))
            p("2019-2 last codemirror ts per class: %s" % ", ".join("%s:%s" % kv for kv in sorted(S["cls_cm_max"].items())))
            p("2019-2 last login ts per class: %s" % ", ".join("%s:%s" % kv for kv in sorted(S["cls_login_max"].items())))
            p("2019-2 last mousemove ts per class: %s" % ", ".join("%s:%s" % kv for kv in sorted(S.get("cls_mm_max", {}).items())))
            um = sorted(((k, v) for k, v in S["stats"].items() if k.startswith("cm_unmatched_shape:")), key=lambda kv: -kv[1])[:4]
            p("2019-2 unmatched codemirror line shapes (masked, top4): %s" % um)
            p("2019-2 codemirror events by month (zero-padded): %s" % sorted(S.get("cm_month_n", {}).items()))
            mm = sorted(((k, v) for k, v in S["stats"].items() if k.startswith("mm_last_line_shape:")), key=lambda kv: -kv[1])[:3]
            p("2019-2 mousemove last-line shapes (masked, top3): %s; files with a date-time stamp: %d; stamps with month field >12: %d, with day field >12: %d" % (
                mm, S["stats"].get("mousemove_files_with_ts", 0), S["stats"].get("mm_month_field_gt12", 0), S["stats"].get("mm_day_field_gt12", 0)))
            p("2019-2 assessments=%d, end range %s..%s, ends after 2019-09-19: %d; types=%s" % (
                len(A), A.end.min(), A.end.max(), int((A.end > "2019-09-19 23:59").sum()), r["types"]))
            cb = S["cm_type_bytes"]
            p("2019-2 uncompressed MB by kind: %s" % {k: round(v / 2**20, 1) for k, v in S["shape_bytes"].items()})
            top = sorted(cb.items(), key=lambda kv: -kv[1])[:5]
            p("2019-2 codemirror MB by event type (top5): %s" % ", ".join("%s=%.1f" % (k, v / 2**20) for k, v in top))
        if sem == "2020-1":
            g = A.groupby("cls").agg(n=("aid", "size"), last_end=("end", "max"))
            p("2020-1 assessments per class: %s" % ", ".join("%s:%d(%s)" % (c, x.n, x.last_end) for c, x in g.iterrows()))
        if sem == "2022-2":
            p("2022-2 classes with assessments but no users: %s (n_assess=%s)" % (
                r["cls_no_users"], [int((A.cls == c).sum()) for c in r["cls_no_users"]]))
        if r["stray"]:
            p("%s stray files: %s (bytes %s); level-2 entries=%d, of which tar dir members=%d" % (
                sem, r["stray"], [S["shape_bytes"][k] for k in r["stray"]], r["cls_level2_all"], r["cls_level2_dirs"]))
        p("%s: exec header ts not zero-padded=%d, user dirs minus distinct ids=%d" % (
            sem, S["stats"].get("exec_ts_unpadded", 0), r["user_dirs"] - r["distinct_uid"]))
        p("%s: uid in 2+ classes=%d, shared exec file names across those classes=%d, exec files with unlisted exercise=%d (%.1f%%), union code/exec/cm keys=%d, code exts=%s" % (
            sem, r["uid_in_2plus_classes"], r["dual_uid_shared_exec_names"], r["exec_unlisted_ex"],
            100.0 * r["exec_unlisted_ex"] / max(1, r["exec_files"]), r["union_code_exec_cm"], r["code_exts"]))
    p("")
    p("== 7. Cross-semester ids (DEV only), parquet key-dup cross-check, server sizes")
    ids = {s: set(load(s, "users").uid) for s in sems}
    ids_ex = {s: set(load(s, "blocks").uid) for s in sems}
    cnt = Counter(u for s in sems for u in ids[s])
    cnt_ex = Counter(u for s in sems for u in ids_ex[s])
    p("DEV: distinct ids=%d, student-semesters=%d, ids in 2+ semesters=%d | with >=1 block: ids=%d, student-semesters=%d" % (
        len(cnt), sum(cnt.values()), sum(1 for v in cnt.values() if v > 1), len(cnt_ex), sum(cnt_ex.values())))
    key = ["class", "user", "assessment", "exercise", "ts", "kind"]
    pk = []
    for s in sems:
        ev = pd.read_parquet(os.path.join(PARQ, "events", s + ".parquet"), columns=key)
        pk.append("%s:%d/%d" % (s, int(ev.duplicated(key).sum()), res[s]["key_dup"]))
    p("parquet key dups / ours: " + ", ".join(pk))
    heads = []
    for s in sems:
        fn = "cb_dataset_%s_v1.81.tar.gz" % s.replace("-", "_")
        h = subprocess.run(["curl", "-sI", "-m", "30", PAGE_URL + "files/" + fn], capture_output=True, text=True).stdout
        cl = re.search(r"(?im)^content-length:\s*(\d+)", h)
        lm = re.search(r"(?im)^last-modified:\s*(.+?)\s*$", h)
        loc = os.path.getsize(os.path.join(ARCH, fn))
        heads.append("%s:%s%s" % (s, "=" if cl and int(cl.group(1)) == loc else "!=(%s vs %d)" % (cl.group(1) if cl else None, loc),
                                   "@" + (lm.group(1)[5:16] if lm else "?")))
    p("server Content-Length vs local size: " + ", ".join(heads))
    txt = "\n".join(L) + "\n"
    open(OUT, "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    if sys.argv[1] == "parse":
        for s in sys.argv[2:]:
            parse_semester(s)
    elif sys.argv[1] == "report":
        have = [s for s in DEV if os.path.exists(os.path.join(CACHE, s + "_summary.json"))]
        report(have)
