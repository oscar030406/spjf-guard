"""Stage 1: stream the DEV archives 2018-1 .. 2022-2 and cache two tables per semester.

cache/blocks_<sem>.parquet  one row per SUBMITION / TEST block of users/<uid>/executions/*.log
    class, user, assessment, exercise, seq (block order inside the file), kind, ts (header,
    epoch seconds, naive local time), exec_time (float64, NaN if absent), exec_ndec (digits
    after the decimal point, -1 if absent), n_tc, n_tc_empty_out (test cases whose user output
    is empty), grade, has_error, err_class (none|Killed|<ExceptionName>|Other|Empty)
cache/cm_<sem>.parquet      one row per selected codemirror event
    class, user, assessment, exercise, etype (submit|saida_testar|kill_program|testar),
    ts (epoch seconds with ms), fb (for submit only: correct|wrong|partial|other), ms_digits

Privacy: no code, no program output, no keystroke payload is stored.  For codemirror only the
timestamp and the event type are read; for "submit" the system feedback message is mapped to
one of four classes and discarded.  Sealed semesters (2023-1, 2023-2, 2024-1) are refused.

Usage: uv run --with pandas --with numpy --with pyarrow python build_cache.py [SEM_TAG ...]
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
ARCHIVES = os.path.join(ROOT, "data", "codebench", "archives")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
SEALED = ("2023_1", "2023_2", "2024_1")
DEV_EXEC = ["2018_1", "2018_2", "2019_1", "2019_2", "2020_ERE", "2020_1", "2020_2",
            "2021_1", "2021_2", "2022_1", "2022_2"]

SEP = b"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*"
RE_HEAD = re.compile(rb"==\s+(SUBMITION|TEST)\s+\((\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2}):(\d{1,2})\)")
RE_SECT = re.compile(rb"(?m)^-- (CODE|EXECUTION TIME|OUTPUT|ERROR|GRADE|TEST CASE \d+):[ \t]*$")
RE_UOUT = re.compile(rb"(?m)^---- user output:[ \t]*$")
RE_ERRTYPE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Interrupt|Warning|Exit))\b")
RE_CM = re.compile(rb"(?m)^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?"
                   rb"#(submit|saida_testar|kill_program|testar)#(.{0,16})")


def epoch(y, mo, d, h, mi, s) -> int:
    return timegm((int(y), int(mo), int(d), int(h), int(mi), int(s), 0, 0, 0))


def parse_blocks(raw: bytes):
    out = []
    seq = 0
    for blk in raw.split(SEP):
        h = RE_HEAD.search(blk)
        if h is None:
            continue
        kind = "submit" if h.group(1) == b"SUBMITION" else "test"
        ts = epoch(*h.groups()[1:])
        exec_t, ndec, grade = np.nan, -1, np.nan
        n_tc = n_empty = 0
        has_err, err_class = False, "none"
        marks = list(RE_SECT.finditer(blk, h.end()))
        for i, m in enumerate(marks):
            name = m.group(1)
            body = blk[m.end() + 1: marks[i + 1].start() if i + 1 < len(marks) else len(blk)]
            if name == b"EXECUTION TIME":
                s = body.strip()
                if s:
                    try:
                        exec_t = float(s)
                        ndec = len(s.split(b".")[1]) if b"." in s else 0
                    except ValueError:
                        pass
            elif name == b"GRADE":
                try:
                    grade = float(body.strip().rstrip(b"%"))
                except ValueError:
                    pass
            elif name.startswith(b"TEST CASE"):
                n_tc += 1
                u = RE_UOUT.search(body)
                if u is not None and not body[u.end():].strip():
                    n_empty += 1
            elif name == b"ERROR":
                has_err = True
                lines = [l.strip() for l in body.decode("utf-8", "replace").strip().split("\n") if l.strip()]
                if not lines:
                    err_class = "Empty"
                elif lines[-1] == "Killed":
                    err_class = "Killed"
                else:
                    mm = RE_ERRTYPE.match(lines[-1])
                    err_class = mm.group(1) if mm else "Other"
        out.append((seq, kind, ts, exec_t, ndec, n_tc, n_empty, grade, has_err, err_class))
        seq += 1
    return out


def fb_class(p: bytes) -> str:
    if p.startswith(b"Congrat"):
        return "correct"
    if p.startswith(b"Your code did"):
        return "wrong"
    if p.startswith(b"You'll") or p.startswith(b"You\\'ll") or p.startswith(b"You"):
        return "partial"
    return "other"


def process(tag: str) -> str:
    assert tag not in SEALED
    t0 = time.time()
    path = os.path.join(ARCHIVES, f"cb_dataset_{tag}_v1.81.tar.gz")
    brows, crows = [], []
    tf = tarfile.open(path, "r|gz")
    for m in tf:
        if not m.isfile():
            continue
        parts = m.name.split("/")
        if len(parts) < 6 or parts[2] != "users":
            continue
        cls, uid, sub = parts[1], parts[3], parts[4]
        if sub not in ("executions", "codemirror"):
            continue
        stem = os.path.splitext(parts[-1])[0]
        aid, _, exid = stem.partition("_")
        raw = tf.extractfile(m).read()
        if sub == "executions":
            for r in parse_blocks(raw):
                brows.append((cls, uid, aid, exid) + r)
        else:
            for mm in RE_CM.finditer(raw):
                g = mm.groups()
                ms = g[6]
                ts = epoch(*g[:6]) + (int(ms) / 1000.0 if ms else 0.0)
                et = g[7].decode()
                fb = fb_class(g[8]) if et == "submit" else ""
                crows.append((cls, uid, aid, exid, et, ts, fb, len(ms) if ms else 0))
    tf.close()
    os.makedirs(CACHE, exist_ok=True)
    b = pd.DataFrame(brows, columns=["class", "user", "assessment", "exercise", "seq", "kind", "ts",
                                     "exec_time", "exec_ndec", "n_tc", "n_tc_empty_out", "grade",
                                     "has_error", "err_class"])
    for c in ("class", "user", "assessment", "exercise", "kind", "err_class"):
        b[c] = b[c].astype("category")
    b.to_parquet(os.path.join(CACHE, f"blocks_{tag}.parquet"), index=False)
    c = pd.DataFrame(crows, columns=["class", "user", "assessment", "exercise", "etype", "ts", "fb",
                                     "ms_digits"])
    for k in ("class", "user", "assessment", "exercise", "etype", "fb"):
        c[k] = c[k].astype("category")
    c.to_parquet(os.path.join(CACHE, f"cm_{tag}.parquet"), index=False)
    return (f"{tag:9s} blocks={len(b):>8,} submit={int((b.kind == 'submit').sum()):>7,} "
            f"cm_rows={len(c):>8,} classes={b['class'].nunique():>3} {time.time() - t0:5.1f}s")


def main():
    tags = sys.argv[1:] or DEV_EXEC
    assert not any(t in SEALED for t in tags), "sealed semester requested"
    with ProcessPoolExecutor(max_workers=6) as pool:
        for line in pool.map(process, tags):
            print(line, flush=True)


if __name__ == "__main__":
    main()
