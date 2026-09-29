"""Parse the ACcoding MySQL dumps (data/accoding/raw/*.sql) into parquet.

Streaming parser: statements are read line by line; a statement that does not
close (odd number of unescaped quotes) is joined with the following lines, so
commas / quotes / newlines inside the `detail` text cannot shift columns.

The `detail` text itself is NOT stored. We keep its length, an empty flag, and
the per-test numbers it contains (n / sum ms / max ms / max KB) -- those are
used ONLY to answer "what does time_cost mean" in the precheck; they are known
after judging and must never be used as a feature.

Run:
  uv run --with pandas --with numpy --with pyarrow python parse_sql.py
"""

import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RAW = r"<repo-root>\data\accoding\raw"
OUT = r"<repo-root>\data\accoding\parquet"

LANGS = ["c++", "c", "python", "java", "python2", "python3"]
RESULTS = ["WT", "JG", "AC", "WA", "CE", "REG", "MLE", "REP", "PE",
           "TLE", "IFNR", "OFNR", "EFNR", "OE"]
ACCESS = ["private", "protect", "public"]

_ESC = re.compile(r"\\(.)", re.DOTALL)
_ESC_MAP = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "b": "\b", "Z": "\x1a"}


def unescape(s):
    return _ESC.sub(lambda m: _ESC_MAP.get(m.group(1), m.group(1)), s)


# ---------------------------------------------------------------- generic path

_QUOTED = re.compile(r"'(?:[^'\\]++|\\.)*+'", re.DOTALL)


def _closes(stmt):
    """True when every quote in the statement body is closed."""
    return _QUOTED.sub("", stmt).count("'") == 0


_FIELD = re.compile(r"\s*(?:'((?:[^'\\]++|\\.)*+)'|([^,]*?))\s*(?:,|$)", re.DOTALL)


def split_fields(body):
    out, pos = [], 0
    n = len(body)
    while pos <= n:
        m = _FIELD.match(body, pos)
        if m is None or m.end() == m.start():
            break
        if m.group(1) is not None:
            out.append(unescape(m.group(1)))
        else:
            v = m.group(2)
            out.append(None if v == "NULL" else v)
        pos = m.end()
        if pos > n:
            break
    return out


def iter_rows(table, n_fields):
    """Yield field lists for `INSERT INTO table VALUES (...)` statements."""
    path = os.path.join(RAW, table + ".sql")
    prefix = "INSERT INTO `%s` VALUES (" % table
    buf = ""
    stmts = 0
    with open(path, "r", encoding="utf-8", newline="") as f:
        for line in f:
            if buf:
                buf += line
            elif line.startswith(prefix):
                buf = line
            else:
                continue
            s = buf.rstrip("\r\n ")
            if s.endswith(");") and _closes(s):
                body = s[len(prefix):-2]
                fields = split_fields(body)
                if len(fields) != n_fields:
                    raise ValueError("column shift in %s: %r" % (table, body[:200]))
                stmts += 1
                yield fields
                buf = ""
    sys.stderr.write("  %s: %d statements\n" % (table, stmts))


def raw_insert_count(table):
    """Count `INSERT INTO <table> VALUES` occurrences straight from the bytes."""
    needle = ("INSERT INTO `%s` VALUES" % table).encode()
    n = 0
    tail = b""
    with open(os.path.join(RAW, table + ".sql"), "rb") as f:
        while True:
            chunk = f.read(1 << 24)
            if not chunk:
                break
            buf = tail + chunk
            n += buf.count(needle)
            tail = buf[-(len(needle) - 1):]   # overlap, minus 1 -> no double count
    return n


def to_i(v):
    return np.nan if v is None or v == "NULL" else int(v)


def to_f(v):
    return np.nan if v is None or v == "NULL" else float(v)


# ------------------------------------------------------------- small tables

def parse_users():
    ids, last = [], []
    for f in iter_rows("users", 2):
        ids.append(int(f[0]))
        last.append(f[1])
    df = pd.DataFrame({"id": np.asarray(ids, dtype=np.int32),
                       "last_login": pd.to_datetime(last, errors="coerce")})
    return df


def parse_contests():
    rows = {"id": [], "start_time": [], "end_time": [], "access_level": [],
            "updated_at": []}
    for f in iter_rows("contests", 5):
        rows["id"].append(int(f[0]))
        rows["start_time"].append(f[1])
        rows["end_time"].append(f[2])
        rows["access_level"].append(f[3])
        rows["updated_at"].append(f[4])
    df = pd.DataFrame(rows)
    df["id"] = df["id"].astype(np.int32)
    for c in ("start_time", "end_time", "updated_at"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def parse_tags():
    ids, content = [], []
    for f in iter_rows("tags", 2):
        ids.append(int(f[0]))
        content.append(f[1])
    return pd.DataFrame({"id": np.asarray(ids, dtype=np.int32), "content": content})


def parse_problem_tags():
    t, p, w = [], [], []
    for f in iter_rows("problem_tags", 3):
        t.append(int(f[0]))
        p.append(int(f[1]))
        w.append(to_f(f[2]))
    return pd.DataFrame({"tag_id": np.asarray(t, dtype=np.int32),
                         "problem_id": np.asarray(p, dtype=np.int32),
                         "weight": np.asarray(w, dtype=np.float32)})


def parse_problems():
    rows = {"id": [], "access_level": [], "difficulty": [], "creator_id": [],
            "updated_at": [], "n_tests": [], "time_limit": [], "memory_limit": [],
            "n_supported_langs": [], "has_special_judge": [], "partial_score": [],
            "test_weight_sum": [], "test_setting_ok": []}
    for f in iter_rows("problems", 6):
        rows["id"].append(int(f[0]))
        rows["access_level"].append(f[1])
        rows["difficulty"].append(to_f(f[3]))
        rows["updated_at"].append(f[4])
        rows["creator_id"].append(to_i(f[5]))
        try:
            js = json.loads(f[2])
            data = js.get("data") or []
            rows["n_tests"].append(len(data))
            rows["time_limit"].append(to_f(js.get("time_limit")))
            rows["memory_limit"].append(to_f(js.get("memory_limit")))
            langs = (js.get("supported_languages") or "").strip()
            rows["n_supported_langs"].append(len([x for x in langs.split(",") if x]))
            rows["has_special_judge"].append(bool((js.get("special_judge") or "").strip()))
            rows["partial_score"].append(bool(js.get("partial_score")))
            ws = 0.0
            for d in data:
                try:
                    ws += float(d.get("weight") or 0)
                except (TypeError, ValueError):
                    pass
            rows["test_weight_sum"].append(ws)
            rows["test_setting_ok"].append(True)
        except Exception:
            for k, v in (("n_tests", np.nan), ("time_limit", np.nan),
                         ("memory_limit", np.nan), ("n_supported_langs", np.nan),
                         ("has_special_judge", False), ("partial_score", False),
                         ("test_weight_sum", np.nan), ("test_setting_ok", False)):
                rows[k].append(v)
    df = pd.DataFrame(rows)
    df["id"] = df["id"].astype(np.int32)
    df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
    for c in ("difficulty", "time_limit", "memory_limit", "test_weight_sum"):
        df[c] = df[c].astype(np.float32)
    for c in ("n_tests", "n_supported_langs"):
        df[c] = df[c].astype("Int32")
    df["creator_id"] = df["creator_id"].astype("Int32")
    return df


# --------------------------------------------------------------- submissions

SUB_RE = re.compile(
    r"INSERT INTO `submissions` VALUES \("
    r"(\d+), "                                # 1 id
    r"'([^']*)', "                            # 2 lang
    r"'([^']*)', "                            # 3 result
    r"([^,]*), "                              # 4 score
    r"([^,]*), "                              # 5 time_cost
    r"([^,]*), "                              # 6 memory_cost
    r"([^,]*), "                              # 7 code_length
    r"(?:NULL|'((?:[^'\\]++|\\.)*+)'), "      # 8 detail
    r"([^,]*), "                              # 9 creator_id
    r"([^,]*), "                              # 10 problem_id
    r"([^,)]*)\);",                           # 11 contest_id
    re.DOTALL)

# "Accepted | 1 * (1 / 5) | 29 ms | 8240 KB"
CASE_RE = re.compile(r"\| (\d+) ms \| (\d+) KB")

SUB_SCHEMA = pa.schema([
    ("id", pa.int32()), ("lang", pa.int8()), ("result", pa.int8()),
    ("score", pa.float32()), ("time_cost", pa.int32()),
    ("memory_cost", pa.int32()), ("code_length", pa.int32()),
    ("detail_len", pa.int32()), ("detail_empty", pa.bool_()),
    ("detail_n_cases", pa.int16()), ("detail_sum_ms", pa.int32()),
    ("detail_max_ms", pa.int32()), ("detail_max_kb", pa.int32()),
    ("creator_id", pa.int32()), ("problem_id", pa.int32()),
    ("contest_id", pa.int32()),
])

CHUNK = 1_000_000
NA_I = -1          # sentinel for NULL ints (validated: no real id is negative)


def parse_submissions():
    path = os.path.join(RAW, "submissions.sql")
    writer = pq.ParquetWriter(os.path.join(OUT, "submissions.parquet"), SUB_SCHEMA,
                              compression="zstd")
    lang_ix = {v: i for i, v in enumerate(LANGS)}
    res_ix = {v: i for i, v in enumerate(RESULTS)}

    cols = [[] for _ in range(16)]
    stats = {"rows": 0, "slow_path": 0, "bad_lang": 0, "bad_result": 0,
             "null_time": 0, "null_mem": 0, "null_codelen": 0, "null_score": 0,
             "null_creator": 0, "null_problem": 0, "null_contest": 0,
             "detail_null": 0, "detail_unparsed_cases": 0, "id_not_increasing": 0}
    last_id = -1
    t0 = time.time()

    def flush():
        if not cols[0]:
            return
        arrays = [
            pa.array(cols[0], type=pa.int32()), pa.array(cols[1], type=pa.int8()),
            pa.array(cols[2], type=pa.int8()), pa.array(cols[3], type=pa.float32()),
            pa.array(cols[4], type=pa.int32()), pa.array(cols[5], type=pa.int32()),
            pa.array(cols[6], type=pa.int32()), pa.array(cols[7], type=pa.int32()),
            pa.array(cols[8], type=pa.bool_()), pa.array(cols[9], type=pa.int16()),
            pa.array(cols[10], type=pa.int32()), pa.array(cols[11], type=pa.int32()),
            pa.array(cols[12], type=pa.int32()), pa.array(cols[13], type=pa.int32()),
            pa.array(cols[14], type=pa.int32()), pa.array(cols[15], type=pa.int32()),
        ]
        writer.write_table(pa.Table.from_arrays(arrays, schema=SUB_SCHEMA))
        for c in cols:
            c.clear()

    def emit(sid, lang, result, score, tc, mc, cl, detail_raw,
             creator, problem, contest):
        nonlocal last_id
        if sid <= last_id:
            stats["id_not_increasing"] += 1
        last_id = sid
        cols[0].append(sid)
        li = lang_ix.get(lang, -1)
        if li < 0:
            stats["bad_lang"] += 1
        cols[1].append(li)
        ri = res_ix.get(result, -1)
        if ri < 0:
            stats["bad_result"] += 1
        cols[2].append(ri)
        if score is None or score == "NULL":
            stats["null_score"] += 1
            cols[3].append(None)
        else:
            cols[3].append(float(score))
        for raw, key, ix in ((tc, "null_time", 4), (mc, "null_mem", 5),
                             (cl, "null_codelen", 6)):
            if raw is None or raw == "NULL":
                stats[key] += 1
                cols[ix].append(NA_I)
            else:
                cols[ix].append(int(raw))
        if detail_raw is None:
            stats["detail_null"] += 1
            cols[7].append(0)
            cols[8].append(True)
            cols[9].append(0)
            cols[10].append(NA_I)
            cols[11].append(NA_I)
            cols[12].append(NA_I)
        else:
            txt = unescape(detail_raw)
            cols[7].append(len(txt))
            cols[8].append(len(txt) == 0)
            cases = CASE_RE.findall(detail_raw)
            if cases:
                ms = [int(a) for a, _ in cases]
                kb = [int(b) for _, b in cases]
                cols[9].append(min(len(ms), 32767))
                cols[10].append(sum(ms))
                cols[11].append(max(ms))
                cols[12].append(max(kb))
            else:
                if txt:
                    stats["detail_unparsed_cases"] += 1
                cols[9].append(0)
                cols[10].append(NA_I)
                cols[11].append(NA_I)
                cols[12].append(NA_I)
        for raw, key, ix in ((creator, "null_creator", 13),
                             (problem, "null_problem", 14),
                             (contest, "null_contest", 15)):
            if raw is None or raw == "NULL":
                stats[key] += 1
                cols[ix].append(NA_I)
            else:
                cols[ix].append(int(raw))
        stats["rows"] += 1
        if len(cols[0]) >= CHUNK:
            flush()
            sys.stderr.write("    %d rows, %.0fs\n" % (stats["rows"], time.time() - t0))
            sys.stderr.flush()

    prefix = "INSERT INTO `submissions` VALUES ("
    buf = ""
    with open(path, "r", encoding="utf-8", newline="") as f:
        for line in f:
            if buf:
                buf += line
            else:
                if not line.startswith(prefix):
                    continue
                m = SUB_RE.match(line)
                if m is not None:
                    g = m.group
                    emit(int(g(1)), g(2), g(3), g(4), g(5), g(6), g(7), g(8),
                         g(9), g(10), g(11))
                    continue
                buf = line
            # slow path: statement spans lines (unescaped newline in detail)
            s = buf.rstrip("\r\n ")
            if s.endswith(");") and _closes(s):
                m = SUB_RE.match(s)
                stats["slow_path"] += 1
                if m is not None:
                    g = m.group
                    emit(int(g(1)), g(2), g(3), g(4), g(5), g(6), g(7), g(8),
                         g(9), g(10), g(11))
                else:
                    fl = split_fields(s[len(prefix):-2])
                    if len(fl) != 11:
                        raise ValueError("column shift: %r" % s[:200])
                    emit(int(fl[0]), fl[1], fl[2], fl[3], fl[4], fl[5], fl[6],
                         fl[7], fl[8], fl[9], fl[10])
                buf = ""
    if buf.strip():
        raise ValueError("unterminated statement at EOF: %r" % buf[:200])
    flush()
    writer.close()
    stats["secs"] = round(time.time() - t0, 1)
    return stats


def main():
    os.makedirs(OUT, exist_ok=True)
    rep_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_parse.txt")
    fh = open(rep_path, "w", encoding="utf-8")

    def w(line=""):
        print(line)
        fh.write(line + "\n")
        fh.flush()

    w("=" * 72)
    w("ACcoding SQL -> parquet")
    w("=" * 72)

    for name, fn in (("users", parse_users), ("contests", parse_contests),
                     ("tags", parse_tags), ("problem_tags", parse_problem_tags),
                     ("problems", parse_problems)):
        t = time.time()
        df = fn()
        df.to_parquet(os.path.join(OUT, name + ".parquet"), index=False)
        raw_n = raw_insert_count(name)
        w("%-13s rows=%-8d raw_INSERT=%-8d match=%s  %.1fs"
          % (name, len(df), raw_n, len(df) == raw_n, time.time() - t))
        if "id" in df.columns:
            w("              id: min=%d max=%d unique=%d"
              % (df["id"].min(), df["id"].max(), df["id"].nunique()))
        if name == "problems":
            w("              test_setting parsed ok: %d / %d"
              % (int(df["test_setting_ok"].sum()), len(df)))
            bad = set(df["access_level"].unique()) - set(ACCESS)
            w("              access_level illegal values: %s" % (bad or "none"))
        if name == "contests":
            bad = set(df["access_level"].unique()) - set(ACCESS)
            w("              access_level illegal values: %s" % (bad or "none"))
            w("              end<start: %d" % int((df.end_time < df.start_time).sum()))

    w()
    w("submissions (streaming) ...")
    st = parse_submissions()
    raw_n = raw_insert_count("submissions")
    w("submissions   rows=%d raw_INSERT=%d match=%s  %ss"
      % (st["rows"], raw_n, st["rows"] == raw_n, st["secs"]))
    for k in ("slow_path", "bad_lang", "bad_result", "id_not_increasing",
              "null_score", "null_time", "null_mem", "null_codelen",
              "null_creator", "null_problem", "null_contest", "detail_null",
              "detail_unparsed_cases"):
        w("              %-22s %d" % (k, st[k]))

    sub = pd.read_parquet(os.path.join(OUT, "submissions.parquet"),
                          columns=["id", "lang", "result"])
    w("              id: min=%d max=%d unique=%d rows=%d  (rows/max_id=%.4f)"
      % (sub.id.min(), sub.id.max(), sub.id.nunique(), len(sub),
         len(sub) / sub.id.max()))
    w("              id strictly increasing in file order: %s"
      % bool((np.diff(sub.id.values) > 0).all()))
    w("              lang codes in range: %s"
      % bool(sub.lang.between(0, len(LANGS) - 1).all()))
    w("              result codes in range: %s"
      % bool(sub.result.between(0, len(RESULTS) - 1).all()))
    w()
    w("wrote parquet to %s" % OUT)
    fh.close()


if __name__ == "__main__":
    main()
