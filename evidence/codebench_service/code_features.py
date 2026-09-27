"""Static code features per execution, computed while streaming the tar.gz archives.

PRIVACY: no source code text is ever written to disk.  Every block's code is read
from the gzip stream, turned into a fixed vector of counts / flags, and dropped.

Output: data/codebench/parquet/code_features/<sem>.parquet, one row per
SUBMITION/TEST block, keyed by (semester, class, user, assessment, exercise,
blk_i) where blk_i is the block's position inside its executions .log file.  The
events table was written by parse_codebench.py in the same file order, so blk_i
equals the cumcount within that group there; code_len is carried along so the
join can be verified.

Usage:
    uv run python evidence/codebench_service/code_features.py [--only 2018-1,2018-2]
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import argparse
import re
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVES = os.path.join(ROOT, "data", "codebench", "archives")
OUT = os.path.join(ROOT, "data", "codebench", "parquet", "code_features")

SEP = b"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*"
RE_HEAD = re.compile(rb"==\s+(SUBMITION|TEST)\s+\((\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})\)")
RE_SECT = re.compile(rb"(?m)^-- (CODE|EXECUTION TIME|OUTPUT|ERROR|GRADE|TEST CASE \d+):[ \t]*$")

# one pass for all keyword counts
RE_KW = re.compile(
    r"\b(while|for|input|def|if|print|range|try|class|return|import|lambda|"
    r"len|append|sleep|eval|exec|open|recursion)\b")
RE_IMPORT = re.compile(r"(?m)^\s*(?:from\s+([A-Za-z_][\w.]*)|import\s+([A-Za-z_][\w.]*))")
RE_WHILE_TRUE = re.compile(r"while\s*\(?\s*(?:True|1)\s*\)?\s*:")
RE_DEFNAME = re.compile(r"(?m)^\s*def\s+([A-Za-z_]\w*)")
RE_NUM = re.compile(r"\d+")
RE_RANGE = re.compile(r"range\(([^)]{0,80})\)")
RE_LOOPLINE = re.compile(r"^(\s*)(for|while)\b")
RE_COMMENT = re.compile(r"(?m)^\s*#")

IMP_GROUPS = {
    "math": "imp_math", "random": "imp_random", "time": "imp_time",
    "sys": "imp_sys", "os": "imp_os", "numpy": "imp_numpy",
    "itertools": "imp_itertools", "string": "imp_string",
}

FEAT_COLS = [
    "chars", "lines", "nonblank_lines", "max_line_len", "n_comment_lines",
    "n_while", "n_for", "n_input", "n_def", "n_if", "n_print", "n_range",
    "n_try", "n_class", "n_return", "n_lambda", "n_len", "n_append",
    "n_import", "imp_math", "imp_random", "imp_time", "imp_sys", "imp_os",
    "imp_numpy", "imp_itertools", "imp_string", "imp_other",
    "max_indent", "nest_loop_depth", "has_while_true", "has_recursion",
    "max_num_digits", "max_range_digits", "has_sleep", "has_evalexec",
    "has_open",
]
KEY_COLS = ["semester", "class", "user", "assessment", "exercise", "blk_i",
            "kind", "code_len"]


def _nchars(b: bytes) -> int:
    return len(b) if b.isascii() else len(b.decode("utf-8", "replace"))


def code_vector(txt: str) -> list:
    """Fixed-length numeric description of one source file.  Text is discarded."""
    lines = txt.split("\n")
    n_lines = len(lines)
    nonblank = 0
    max_len = 0
    max_indent = 0
    nest = 0
    stack: list[int] = []
    for ln in lines:
        if ln.strip():
            nonblank += 1
        if len(ln) > max_len:
            max_len = len(ln)
        ind = len(ln) - len(ln.lstrip(" \t"))
        ind = ln[:ind].expandtabs(4)
        ind = len(ind)
        if ln.strip():
            if ind > max_indent:
                max_indent = ind
        m = RE_LOOPLINE.match(ln)
        if m:
            cur = len(m.group(1).expandtabs(4))
            while stack and stack[-1] >= cur:
                stack.pop()
            stack.append(cur)
            if len(stack) > nest:
                nest = len(stack)

    kw = {}
    for m in RE_KW.finditer(txt):
        k = m.group(1)
        kw[k] = kw.get(k, 0) + 1

    n_import = 0
    imps = dict.fromkeys(IMP_GROUPS.values(), 0)
    imp_other = 0
    for m in RE_IMPORT.finditer(txt):
        mod = (m.group(1) or m.group(2) or "").split(".")[0]
        n_import += 1
        col = IMP_GROUPS.get(mod)
        if col:
            imps[col] = 1
        else:
            imp_other = 1

    has_wt = 1 if RE_WHILE_TRUE.search(txt) else 0

    has_rec = 0
    names = RE_DEFNAME.findall(txt)
    if names:
        for nm in set(names):
            # a call to nm( that is not the def line itself
            n_def_of = len(re.findall(r"(?m)^\s*def\s+" + re.escape(nm) + r"\s*\(", txt))
            n_call = txt.count(nm + "(")
            if n_call > n_def_of:
                # only counts as recursion if the call appears inside that def's body;
                # cheap proxy: the name is called more often than it is defined AND
                # the call appears after the def line at deeper indentation
                body_calls = len(re.findall(r"(?m)^\s+.*\b" + re.escape(nm) + r"\s*\(", txt))
                if body_calls > 0:
                    has_rec = 1
                    break

    nums = RE_NUM.findall(txt)
    max_num_digits = max((len(x) for x in nums), default=0)
    rng = RE_RANGE.findall(txt)
    max_range_digits = 0
    for r in rng:
        for x in RE_NUM.findall(r):
            if len(x) > max_range_digits:
                max_range_digits = len(x)

    return [
        len(txt), n_lines, nonblank, max_len, len(RE_COMMENT.findall(txt)),
        kw.get("while", 0), kw.get("for", 0), kw.get("input", 0), kw.get("def", 0),
        kw.get("if", 0), kw.get("print", 0), kw.get("range", 0), kw.get("try", 0),
        kw.get("class", 0), kw.get("return", 0), kw.get("lambda", 0),
        kw.get("len", 0), kw.get("append", 0),
        n_import, imps["imp_math"], imps["imp_random"], imps["imp_time"],
        imps["imp_sys"], imps["imp_os"], imps["imp_numpy"], imps["imp_itertools"],
        imps["imp_string"], imp_other,
        min(max_indent, 60), min(nest, 12), has_wt, has_rec,
        min(max_num_digits, 18), min(max_range_digits, 18),
        1 if kw.get("sleep", 0) else 0,
        1 if (kw.get("eval", 0) or kw.get("exec", 0)) else 0,
        1 if kw.get("open", 0) else 0,
    ]


def parse_blocks(raw: bytes):
    out = []
    blk_i = 0
    for blk in raw.split(SEP):
        h = RE_HEAD.search(blk)
        if h is None:
            continue
        kind = "submit" if h.group(1) == b"SUBMITION" else "test"
        code_b = b""
        marks = list(RE_SECT.finditer(blk, h.end()))
        for i, m in enumerate(marks):
            if m.group(1) == b"CODE":
                end = marks[i + 1].start() if i + 1 < len(marks) else len(blk)
                code_b = blk[m.end() + 1: end].rstrip(b"\n")
                break
        txt = code_b.decode("utf-8", "replace")
        out.append((blk_i, kind, _nchars(code_b), code_vector(txt)))
        blk_i += 1
    return out


def process_archive(path: str) -> dict:
    t0 = time.time()
    keys, feats = [], []
    sem = None
    tf = tarfile.open(path, "r|gz")
    for m in tf:
        if not m.isfile():
            continue
        parts = m.name.split("/")
        if len(parts) < 6 or parts[2] != "users" or parts[4] != "executions":
            continue
        sem, cls, uid = parts[0], parts[1], parts[3]
        stem = os.path.splitext(parts[-1])[0]
        aid, _, exid = stem.partition("_")
        raw = tf.extractfile(m).read()
        for (bi, kind, clen, vec) in parse_blocks(raw):
            keys.append((sem, cls, uid, aid, exid, bi, kind, clen))
            feats.append(vec)
    tf.close()

    os.makedirs(OUT, exist_ok=True)
    kdf = pd.DataFrame(keys, columns=KEY_COLS)
    fdf = pd.DataFrame(feats, columns=FEAT_COLS, dtype="int32")
    df = pd.concat([kdf.reset_index(drop=True), fdf], axis=1)
    for c in ("blk_i", "code_len"):
        df[c] = df[c].astype("int32")
    df["kind"] = df["kind"].astype("category")
    df.to_parquet(os.path.join(OUT, f"{sem}.parquet"), index=False)
    return {"semester": sem, "rows": len(df), "seconds": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated semester tags, e.g. 2018-1")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    archives = sorted(f for f in os.listdir(ARCHIVES) if f.endswith(".tar.gz"))
    if a.only:
        want = [w.strip().replace("-", "_") for w in a.only.split(",")]
        archives = [f for f in archives if any("_" + w + "_" in f for w in want)]
    paths = [os.path.join(ARCHIVES, f) for f in archives]
    print(f"{len(paths)} archives, {a.workers} workers", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for st in pool.map(process_archive, paths):
            print(f"  done {st['semester']:10s} {st['seconds']:7.1f}s rows={st['rows']}", flush=True)
    print(f"wall clock {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
