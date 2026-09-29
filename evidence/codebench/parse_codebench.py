"""Stream-parse the CodeBench tar.gz archives into compact parquet tables.

Never extracts an archive to disk: every member is read from the gzip stream and
either parsed or discarded.  Keystroke (codemirror) logs are aggregated to
per-minute counts while streaming.

Privacy: from user.data only the degree course id is kept.  No source code text
is stored, only its length in characters and lines.

Usage:
    uv run --with pandas --with numpy --with pyarrow python parse_codebench.py [--only SEM,SEM]
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import argparse
import re
import sys
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = r"<repo-root>"
ARCHIVES = os.path.join(ROOT, "data", "codebench", "archives")
OUT = os.path.join(ROOT, "data", "codebench", "parquet")

SEP = b"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*"
RE_HEAD = re.compile(rb"==\s+(SUBMITION|TEST)\s+\((\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})\)")
RE_SECT = re.compile(rb"(?m)^-- (CODE|EXECUTION TIME|OUTPUT|ERROR|GRADE|TEST CASE \d+):[ \t]*$")
RE_ERRTYPE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Interrupt|Warning|Exit))\s*:")
RE_LOGIN = re.compile(rb"(?m)^(\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})#user/(\w+)")
RE_KV = re.compile(r"^-{2,4} ([^:]+):\s*(.*)$")

EVENT_COLS = [
    "semester", "class", "user", "assessment", "exercise", "ts", "kind",
    "grade", "exec_time", "code_len", "code_lines", "n_testcases",
    "has_error", "error_type",
]


# --------------------------------------------------------------------------- #
# per-file parsers
# --------------------------------------------------------------------------- #
def parse_assessment(raw: bytes) -> dict:
    d, ex = {}, []
    for line in raw.decode("utf-8", "replace").splitlines():
        m = RE_KV.match(line.strip())
        if not m:
            continue
        k, v = m.group(1).strip().lower(), m.group(2).strip()
        if k.startswith("exercise "):
            ex.append(v)
        else:
            d[k] = v
    return {
        "type": d.get("type"),
        "weight": pd.to_numeric(d.get("weight"), errors="coerce"),
        "start": d.get("start"),
        "end": d.get("end"),
        "n_exercises": pd.to_numeric(d.get("total_exercises"), errors="coerce"),
        "exercise_ids": ",".join(ex),
        "class_number": d.get("class number"),
        "language": d.get("language"),
    }


def parse_course_id(raw: bytes) -> str | None:
    """Only the degree course id is read; every other field is ignored."""
    txt = raw.decode("utf-8", "replace")
    head = txt.split("-- HIGH SCHOOL", 1)[0]
    m = re.search(r"course id:\s*(\S+)", head)
    return m.group(1) if m else None


def _nchars(b: bytes) -> int:
    return len(b) if b.isascii() else len(b.decode("utf-8", "replace"))


def parse_executions(raw: bytes):
    """Yield one tuple per SUBMITION/TEST block."""
    out = []
    for blk in raw.split(SEP):
        h = RE_HEAD.search(blk)
        if h is None:
            continue
        kind = "submit" if h.group(1) == b"SUBMITION" else "test"
        ts = h.group(2).decode()
        code_len = code_lines = n_tc = 0
        grade = exec_t = None
        err_type = None
        has_err = False
        marks = list(RE_SECT.finditer(blk, h.end()))
        for i, m in enumerate(marks):
            name = m.group(1)
            body = blk[m.end() + 1: marks[i + 1].start() if i + 1 < len(marks) else len(blk)]
            if name == b"CODE":
                body = body.rstrip(b"\n")
                code_len = _nchars(body)
                code_lines = body.count(b"\n") + 1 if body else 0
            elif name == b"EXECUTION TIME":
                s = body.strip()
                if s:
                    try:
                        exec_t = float(s)
                    except ValueError:
                        exec_t = None
            elif name == b"GRADE":
                s = body.strip().rstrip(b"%")
                try:
                    grade = float(s)
                except ValueError:
                    grade = None
            elif name.startswith(b"TEST CASE"):
                n_tc += 1
            elif name == b"ERROR":
                has_err = True
                lines = [l for l in body.decode("utf-8", "replace").strip().split("\n") if l.strip()]
                if lines:
                    last = lines[-1].strip()
                    mm = RE_ERRTYPE.match(last)
                    if mm:
                        err_type = mm.group(1)
                    elif last.lower().startswith("killed") or "time limit" in last.lower():
                        err_type = "TimeLimit"
                    else:
                        err_type = "Other"
                else:
                    err_type = "Empty"
        out.append((ts, kind, grade, exec_t, code_len, code_lines, n_tc, has_err, err_type))
    return out


DASH, COLON, SPACE = 45, 58, 32


def parse_codemirror_minutes(raw: bytes):
    """Return (minute_key_int YYYYMMDDHHMM, count) arrays without storing keystrokes.

    Timestamps are NOT zero padded in this dataset ("2016-11-3 9:05:03" occurs),
    so month/day/hour widths are detected per line instead of assumed.
    """
    if not raw:
        return None
    a = np.frombuffer(raw, dtype=np.uint8)
    nl = np.flatnonzero(a == 10)
    s = np.empty(nl.size + 1, dtype=np.int64)
    s[0] = 0
    s[1:] = nl + 1
    s = s[s + 20 <= a.size]
    if s.size == 0:
        return None

    def g(off):
        return a[s + off].astype(np.int64)

    d0, d1, d2, d3 = g(0), g(1), g(2), g(3)
    ok = ((d0 >= 48) & (d0 <= 57) & (d1 >= 48) & (d1 <= 57)
          & (d2 >= 48) & (d2 <= 57) & (d3 >= 48) & (d3 <= 57) & (g(4) == DASH))
    year = ((d0 - 48) * 1000 + (d1 - 48) * 100 + (d2 - 48) * 10 + (d3 - 48))

    mw = np.where(g(6) == DASH, 1, 2)                      # month width
    month = np.where(mw == 1, g(5) - 48, (g(5) - 48) * 10 + (g(6) - 48))
    doff = 5 + mw + 1
    dw = np.where(a[s + doff + 1] == SPACE, 1, 2)          # day width
    day = np.where(dw == 1, a[s + doff].astype(np.int64) - 48,
                   (a[s + doff].astype(np.int64) - 48) * 10
                   + (a[s + doff + 1].astype(np.int64) - 48))
    hoff = doff + dw + 1
    hw = np.where(a[s + hoff + 1] == COLON, 1, 2)          # hour width
    hour = np.where(hw == 1, a[s + hoff].astype(np.int64) - 48,
                    (a[s + hoff].astype(np.int64) - 48) * 10
                    + (a[s + hoff + 1].astype(np.int64) - 48))
    moff = hoff + hw + 1
    minute = ((a[s + moff].astype(np.int64) - 48) * 10
              + (a[s + moff + 1].astype(np.int64) - 48))

    ok &= ((month >= 1) & (month <= 12) & (day >= 1) & (day <= 31)
           & (hour >= 0) & (hour <= 23) & (minute >= 0) & (minute <= 59)
           & (a[s + doff - 1] == DASH) & (a[s + hoff - 1] == SPACE)
           & (a[s + moff - 1] == COLON) & (s + moff + 2 <= a.size))
    key = ((((year * 100 + month) * 100 + day) * 100 + hour) * 100 + minute)[ok]
    if key.size == 0:
        return None
    u, c = np.unique(key, return_counts=True)
    return u, c, int(s.size)


def to_dt(ser: pd.Series, fmt: str) -> pd.Series:
    """Parse timestamps, falling back to per-element inference for odd rows."""
    out = pd.to_datetime(ser, format=fmt, errors="coerce")
    bad = out.isna() & ser.notna() & (ser.astype(str).str.len() > 0)
    if bad.any():
        out.loc[bad] = pd.to_datetime(ser[bad], format="mixed", errors="coerce")
    return out


# --------------------------------------------------------------------------- #
# archive worker
# --------------------------------------------------------------------------- #
def process_archive(path: str) -> dict:
    t0 = time.time()
    ev_rows, lg_rows, cm_key, cm_cnt, cm_meta, ass_rows, usr_rows = [], [], [], [], [], [], []
    n_files = {"executions": 0, "codemirror": 0, "logins": 0, "assessments": 0, "users": 0,
               "codes": 0, "grades": 0, "other": 0}
    bytes_read = 0
    sem = None
    exec_time_filled = [0, 0]  # filled, total submissions
    cm_lines = [0, 0]          # candidate lines, lines with a valid timestamp

    tf = tarfile.open(path, "r|gz")
    for m in tf:
        if not m.isfile():
            continue
        parts = m.name.split("/")
        if len(parts) < 4:
            n_files["other"] += 1
            continue
        sem = parts[0]
        cls = parts[1]
        if parts[2] == "assessments":
            raw = tf.extractfile(m).read()
            bytes_read += len(raw)
            n_files["assessments"] += 1
            aid = os.path.splitext(parts[3])[0]
            d = parse_assessment(raw)
            d.update(semester=sem, **{"class": cls}, assessment=aid)
            ass_rows.append(d)
            continue
        if parts[2] != "users" or len(parts) < 5:
            n_files["other"] += 1
            continue
        uid = parts[3]
        leaf = parts[-1]
        sub = parts[4]
        if sub == "user.data":
            raw = tf.extractfile(m).read()
            bytes_read += len(raw)
            n_files["users"] += 1
            usr_rows.append({"semester": sem, "class": cls, "user": uid,
                             "course_id": parse_course_id(raw)})
        elif sub == "logins.log":
            raw = tf.extractfile(m).read()
            bytes_read += len(raw)
            n_files["logins"] += 1
            for mm in RE_LOGIN.finditer(raw):
                lg_rows.append((sem, cls, uid, mm.group(1).decode(), mm.group(2).decode()))
        elif sub == "executions":
            raw = tf.extractfile(m).read()
            bytes_read += len(raw)
            n_files["executions"] += 1
            stem = os.path.splitext(leaf)[0]
            aid, _, exid = stem.partition("_")
            for (ts, kind, grade, exec_t, cl, cli, ntc, herr, et) in parse_executions(raw):
                if kind == "submit":
                    exec_time_filled[1] += 1
                    if exec_t is not None:
                        exec_time_filled[0] += 1
                ev_rows.append((sem, cls, uid, aid, exid, ts, kind, grade, exec_t,
                                cl, cli, ntc, herr, et))
        elif sub == "codemirror":
            raw = tf.extractfile(m).read()
            bytes_read += len(raw)
            n_files["codemirror"] += 1
            r = parse_codemirror_minutes(raw)
            if r is not None:
                u, c, nlines = r
                cm_lines[0] += nlines
                cm_lines[1] += int(c.sum())
                stem = os.path.splitext(leaf)[0]
                aid, _, exid = stem.partition("_")
                cm_key.append(u)
                cm_cnt.append(c)
                cm_meta.append((cls, uid, aid, exid, u.size))
        else:
            n_files[sub if sub in n_files else "other"] += 1
    tf.close()

    # ---- assemble frames -------------------------------------------------- #
    os.makedirs(OUT, exist_ok=True)
    for t in ("assessments", "events", "logins", "codemirror", "users"):
        os.makedirs(os.path.join(OUT, t), exist_ok=True)

    ass = pd.DataFrame(ass_rows)
    if len(ass):
        ass["start"] = to_dt(ass["start"], "%Y-%m-%d %H:%M")
        ass["end"] = to_dt(ass["end"], "%Y-%m-%d %H:%M")
        ass = ass[["semester", "class", "assessment", "type", "weight", "start", "end",
                   "n_exercises", "exercise_ids", "language"]]
    ass.to_parquet(os.path.join(OUT, "assessments", f"{sem}.parquet"), index=False)

    ev = pd.DataFrame(ev_rows, columns=EVENT_COLS)
    if len(ev):
        ev["ts"] = to_dt(ev["ts"], "%Y-%m-%d %H:%M:%S")
        for c in ("grade", "exec_time"):
            ev[c] = pd.to_numeric(ev[c], errors="coerce").astype("float32")
        for c in ("code_len", "code_lines", "n_testcases"):
            ev[c] = pd.to_numeric(ev[c], errors="coerce").astype("int32")
        ev["kind"] = ev["kind"].astype("category")
        ev["error_type"] = ev["error_type"].astype("category")
    ev.to_parquet(os.path.join(OUT, "events", f"{sem}.parquet"), index=False)

    lg = pd.DataFrame(lg_rows, columns=["semester", "class", "user", "ts", "kind"])
    if len(lg):
        lg["ts"] = to_dt(lg["ts"], "%Y-%m-%d %H:%M:%S")
        lg["kind"] = lg["kind"].astype("category")
    lg.to_parquet(os.path.join(OUT, "logins", f"{sem}.parquet"), index=False)

    if cm_key:
        keys = np.concatenate(cm_key)
        cnts = np.concatenate(cm_cnt)
        reps = np.array([x[4] for x in cm_meta], dtype=np.int64)
        cm = pd.DataFrame({
            "semester": sem,
            "class": np.repeat(np.array([x[0] for x in cm_meta], dtype=object), reps),
            "user": np.repeat(np.array([x[1] for x in cm_meta], dtype=object), reps),
            "assessment": np.repeat(np.array([x[2] for x in cm_meta], dtype=object), reps),
            "exercise": np.repeat(np.array([x[3] for x in cm_meta], dtype=object), reps),
            "minute": pd.to_datetime(keys.astype(str), format="%Y%m%d%H%M", errors="coerce"),
            "n_events": cnts.astype("int32"),
        })
    else:
        cm = pd.DataFrame(columns=["semester", "class", "user", "assessment", "exercise",
                                   "minute", "n_events"])
    cm.to_parquet(os.path.join(OUT, "codemirror", f"{sem}.parquet"), index=False)

    us = pd.DataFrame(usr_rows)
    us.to_parquet(os.path.join(OUT, "users", f"{sem}.parquet"), index=False)

    return {
        "semester": sem,
        "seconds": round(time.time() - t0, 1),
        "uncompressed_mb": round(bytes_read / 1e6, 1),
        "n_assessments": len(ass),
        "n_users": len(us),
        "n_classes": int(us["class"].nunique()) if len(us) else 0,
        "n_events": len(ev),
        "n_submit": int((ev["kind"] == "submit").sum()) if len(ev) else 0,
        "n_test": int((ev["kind"] == "test").sum()) if len(ev) else 0,
        "n_logins": len(lg),
        "n_cm_rows": len(cm),
        "cm_events": int(cm["n_events"].sum()) if len(cm) else 0,
        "exec_time_filled_share": round(exec_time_filled[0] / max(1, exec_time_filled[1]), 4),
        "cm_line_coverage": round(cm_lines[1] / max(1, cm_lines[0]), 5),
        "files_exec": n_files["executions"],
        "files_cm": n_files["codemirror"],
        "ev_ts_min": str(ev["ts"].min()) if len(ev) else "",
        "ev_ts_max": str(ev["ts"].max()) if len(ev) else "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated semester tags, e.g. 2016_2")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    archives = sorted(f for f in os.listdir(ARCHIVES) if f.endswith(".tar.gz"))
    if args.only:
        want = set(args.only.split(","))
        archives = [a for a in archives if any(w in a for w in want)]
    paths = [os.path.join(ARCHIVES, a) for a in archives]
    print(f"{len(paths)} archives, {args.workers} workers", flush=True)

    t0 = time.time()
    stats = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for st in pool.map(process_archive, paths):
            stats.append(st)
            print(f"  done {st['semester']:10s} {st['seconds']:7.1f}s "
                  f"{st['uncompressed_mb']:9.1f}MB events={st['n_events']}", flush=True)
    total = time.time() - t0

    df = pd.DataFrame(stats).sort_values("semester")
    pd.set_option("display.width", 250, "display.max_columns", 50)
    print("\n=== PARSE SUMMARY ===")
    print(df[["semester", "seconds", "uncompressed_mb", "n_classes", "n_users", "n_assessments",
              "n_events", "n_submit", "n_test", "n_logins", "n_cm_rows", "cm_events",
              "exec_time_filled_share", "cm_line_coverage"]].to_string(index=False))
    print("\n=== EVENT TIMESTAMP RANGE ===")
    print(df[["semester", "ev_ts_min", "ev_ts_max"]].to_string(index=False))
    print(f"\nwall clock {total/60:.1f} min; total uncompressed "
          f"{df['uncompressed_mb'].sum()/1000:.1f} GB")
    df.to_csv(os.path.join(OUT, "_parse_stats.csv"), index=False)


if __name__ == "__main__":
    main()
