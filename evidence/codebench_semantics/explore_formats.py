"""Stage 0: enumerate log formats in a few DEV archives before the main tests.

Streams each archive (tarfile "r|gz", nothing extracted) and counts:
  * codemirror event types (2nd '#'-field, digits replaced by N) per semester,
  * templates of the payload of codemirror "submit" events (system feedback messages),
  * section header names inside SUBMITION / TEST blocks of executions/*.log,
  * number of decimals of the EXECUTION TIME value,
  * templates of the last line of ERROR sections for slow or kill/limit-like blocks.

Privacy: no source code or keystroke payload is stored.  Every printed template is a
normalised string (digits -> N, quoted text -> S) that occurs >= MIN_N times among
>= MIN_USERS distinct users, so only system-generated messages survive.

Usage: uv run --with pandas --with numpy python explore_formats.py 2018_2 2020_1 2022_2
Output: out_explore_formats.txt (tee the stdout).
"""
from __future__ import annotations

import os

for _v in ("PYTHONHOME", "PYTHONPATH", "UV_INTERNAL__PYTHONHOME"):
    os.environ.pop(_v, None)

import re
import sys
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

ROOT = r"<repo-root>"
ARCHIVES = os.path.join(ROOT, "data", "codebench", "archives")
SEALED = ("2023_1", "2023_2", "2024_1")
MIN_N, MIN_USERS = 20, 5

SEP = b"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*"
RE_HEAD = re.compile(rb"==\s+(SUBMITION|TEST)\s+\((\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2})\)")
RE_H1 = re.compile(rb"(?m)^-- ([A-Z][A-Z ]*?)(?: \d+)?:[ \t]*$")
RE_H2 = re.compile(rb"(?m)^---- ([a-z][a-z ]*?):")
RE_SECT = re.compile(rb"(?m)^-- (CODE|EXECUTION TIME|OUTPUT|ERROR|GRADE|TEST CASE \d+):[ \t]*$")
KW = re.compile(r"(?i)kill|time|limit|tempo|excedi|exceed|timeout|memory|mem[oó]ria")


def templ(s: str) -> str:
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "S", s)
    s = re.sub(r"\d+", "N", s)
    return s.strip()[:140]


def scan(tag: str) -> dict:
    path = os.path.join(ARCHIVES, f"cb_dataset_{tag}_v1.81.tar.gz")
    ev_types = Counter()
    sub_payload = defaultdict(set)
    sub_payload_n = Counter()
    hdr = defaultdict(set)
    hdr_n = Counter()
    decimals = Counter()
    err_last = defaultdict(set)
    err_last_n = Counter()
    n_blocks = Counter()
    tf = tarfile.open(path, "r|gz")
    for m in tf:
        if not m.isfile():
            continue
        parts = m.name.split("/")
        if len(parts) < 6 or parts[2] != "users":
            continue
        uid, sub = parts[3], parts[4]
        if sub == "codemirror":
            raw = tf.extractfile(m).read().decode("utf-8", "replace")
            for line in raw.split("\n"):
                p = line.split("#", 2)
                if len(p) < 2 or not p[0][:1].isdigit():
                    continue
                et = re.sub(r"\d+", "N", p[1])[:40]
                ev_types[et] += 1
                if p[1] == "submit" and len(p) == 3:
                    t = templ(p[2])
                    sub_payload_n[t] += 1
                    sub_payload[t].add(uid)
        elif sub == "executions":
            raw = tf.extractfile(m).read()
            for blk in raw.split(SEP):
                h = RE_HEAD.search(blk)
                if h is None:
                    continue
                kind = h.group(1).decode()
                n_blocks[kind] += 1
                for mm in RE_H1.finditer(blk, h.end()):
                    k = (kind, "--" + mm.group(1).decode())
                    hdr_n[k] += 1
                    hdr[k].add(uid)
                for mm in RE_H2.finditer(blk, h.end()):
                    k = (kind, "----" + mm.group(1).decode())
                    hdr_n[k] += 1
                    hdr[k].add(uid)
                marks = list(RE_SECT.finditer(blk, h.end()))
                exec_t, err_body = None, None
                for i, mk in enumerate(marks):
                    body = blk[mk.end() + 1: marks[i + 1].start() if i + 1 < len(marks) else len(blk)]
                    if mk.group(1) == b"EXECUTION TIME":
                        s = body.strip().decode("ascii", "replace")
                        if s:
                            decimals[(kind, len(s.split(".")[1]) if "." in s else 0)] += 1
                            try:
                                exec_t = float(s)
                            except ValueError:
                                pass
                        else:
                            decimals[(kind, "empty")] += 1
                    elif mk.group(1) == b"ERROR":
                        err_body = body.decode("utf-8", "replace")
                if err_body is not None:
                    lines = [l.strip() for l in err_body.strip().split("\n") if l.strip()]
                    last = lines[-1] if lines else "<empty>"
                    slow = exec_t is not None and exec_t >= 30
                    if slow or KW.search(last):
                        k = (kind, "slow" if slow else "kw", templ(last))
                        err_last_n[k] += 1
                        err_last[k].add(uid)
    tf.close()
    keep = lambda cnt, users: {k: v for k, v in cnt.items() if v >= MIN_N and len(users[k]) >= MIN_USERS}
    return {
        "tag": tag,
        "ev_types": dict(ev_types.most_common(60)),
        "sub_payload": keep(sub_payload_n, sub_payload),
        "hdr": keep(hdr_n, hdr),
        "decimals": dict(decimals),
        "err_last": keep(err_last_n, err_last),
        "n_blocks": dict(n_blocks),
    }


def main():
    tags = sys.argv[1:] or ["2018_2", "2020_1", "2022_2"]
    assert not any(t in SEALED for t in tags), "sealed semester requested"
    with ProcessPoolExecutor(max_workers=len(tags)) as pool:
        res = list(pool.map(scan, tags))
    for r in res:
        print(f"\n######## {r['tag']}  blocks={r['n_blocks']}")
        print("-- codemirror event types (top):")
        for k, v in r["ev_types"].items():
            print(f"   {v:>10,}  {k}")
        print("-- codemirror submit payload templates (>=%d rows, >=%d users):" % (MIN_N, MIN_USERS))
        for k, v in sorted(r["sub_payload"].items(), key=lambda x: -x[1])[:25]:
            print(f"   {v:>9,}  {k}")
        print("-- section headers in execution blocks:")
        for k, v in sorted(r["hdr"].items(), key=lambda x: (x[0][0], -x[1])):
            print(f"   {k[0]:9s} {v:>10,}  {k[1]}")
        print("-- EXECUTION TIME decimals:", sorted(r["decimals"].items(), key=lambda x: str(x[0])))
        print("-- ERROR last-line templates for slow (exec>=30s) or kill/limit-like blocks:")
        for k, v in sorted(r["err_last"].items(), key=lambda x: -x[1])[:30]:
            print(f"   {k[0]:9s} {k[1]:4s} {v:>8,}  {k[2]}")


if __name__ == "__main__":
    main()
