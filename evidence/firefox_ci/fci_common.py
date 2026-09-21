"""Shared setup for the Mozilla Firefox CI (Taskcluster) queue study.

Everything this study writes lives in evidence/firefox_ci/ (scripts, out_*.txt) and
data/mozilla_firefox_ci/ (raw pages + assembled parquet).  Large intermediates go to the
local cache directory.  No education data is read.

Data source: the public, unauthenticated Taskcluster and Treeherder REST APIs of
Mozilla's Firefox CI cluster.  Politeness: one process, <= 4 requests/second, a
descriptive User-Agent, exponential backoff, every page written to disk as it arrives so
a run can be resumed, and a hard cap on the total number of bytes downloaded.
"""
import gzip
import json
import os
import sys
import time

sys.dont_write_bytecode = True

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "mozilla_firefox_ci")
RAW = os.path.join(DATA, "raw")
SCRATCH = os.environ.get(
    "FCI_SCRATCH",
    r"<cache-dir>"
    r"\firefox_ci",
)
for d in (DATA, RAW, SCRATCH):
    os.makedirs(d, exist_ok=True)

QUEUE = "https://firefox-ci-tc.services.mozilla.com/api/queue/v1"
TREEHERDER = "https://treeherder.mozilla.org/api"
UA = ("firefox-ci-queue-study/1.0 (academic queueing-theory research, Nanjing University "
      "of Posts and Telecommunications; public unauthenticated API; <=4 req/s)")

# ---- study parameters, frozen here ---------------------------------------------
POOLS = ["releng-hardware/gecko-t-osx-1500-m4",
         "releng-hardware/gecko-t-linux-talos-2404"]
# continuous window, UTC.  Tasks are kept by their run's `scheduled` time.
WIN_START = "2026-08-24T00:00:00Z"
WIN_END = "2026-09-14T00:00:00Z"
# pushes are enumerated on a wider range so that tasks of a push just outside the
# window but scheduled inside it are not lost.
PUSH_START_DATE = "2026-08-21"
PUSH_END_DATE = "2026-09-16"
# chronological split inside the window, in days from the pool's window start
SPLIT_DAYS = (13, 16, 21)      # train < 13 d, valid [13,16), test [16,21)

# Per-pool window override.  The Taskcluster bulk-status endpoint does NOT gzip its
# response (~1 kB per task, measured), so a 21-day window on both pools would have cost
# ~420 MB and broken the 400 MB download budget.  The first pool keeps the full 21 days
# (255k tasks on its own, above the 200k target); the second is cut to the last 7 days
# and is reported as a secondary check.  This is a budget decision, not a data property.
POOL_WINDOW = {
    "releng-hardware/gecko-t-linux-talos-2404": ("2026-09-07T00:00:00Z",
                                                 "2026-09-14T00:00:00Z", (4, 5, 7)),
}


def window(pool):
    """(start_iso, end_iso, split_days) for a pool."""
    if pool in POOL_WINDOW:
        return POOL_WINDOW[pool]
    return WIN_START, WIN_END, SPLIT_DAYS


def pool_from_tag(tag):
    for p in POOLS:
        if p.replace("/", "__") == tag:
            return p
    raise KeyError(tag)
SEED = 20260919
HOUR = 3600.0
DAY = 86400.0

# The budget is on bytes actually transferred.  Both APIs serve gzip, so the wire size
# is several times smaller than the decoded JSON; both are counted and both are
# reported, and the cap is enforced on the wire size.
MAX_WIRE_BYTES = 380 * 1024 * 1024      # hard cap, below the 400 MB budget
MIN_INTERVAL = 0.26                     # at most ~3.8 requests/second

_STATE = {"bytes": 0, "wire": 0, "requests": 0, "last": 0.0}


def log(fh, *parts):
    line = " ".join(str(p) for p in parts)
    print(line, flush=True)
    if fh is not None:
        fh.write(line + "\n")
        fh.flush()


class Budget(RuntimeError):
    pass


class Recycle(RuntimeError):
    """This process has made enough requests; the driver should start a fresh one.

    Measured on this host: a python process doing these API calls runs at ~0.7 s per
    call for the first few hundred and then degrades to 15-40 s per call, while a
    process started at that moment is fast again.  Every stage is resumable, so the
    cheapest fix is to stop and be restarted.  `timeout(1)` could not be relied on -- it
    kills the `env`/`uv` wrapper and the python grandchild survives -- so the limit is
    enforced here.
    """


REQ_LIMIT = int(os.environ.get("FCI_REQ_LIMIT", "150"))


_SESSION = None


SESSION_EVERY = 150     # recycle the connection pool this often


def session():
    """A short-lived session.

    A single long-lived Session was measured stalling on this host: after a few hundred
    requests the pooled keep-alive connection is dropped somewhere on the path, and the
    next request sits until the read timeout before being retried, which took the bulk
    status stage from ~1.5 s to ~110 s per batch (a fresh process was fast throughout).
    Recycling the pool, and a read timeout short enough that a dead connection costs
    seconds rather than minutes, removes it.
    """
    global _SESSION
    if _SESSION is None or _STATE["requests"] % SESSION_EVERY == 0:
        if _SESSION is not None:
            try:
                _SESSION.close()
            except Exception:                                         # noqa: BLE001
                pass
        _SESSION = requests.Session()
        _SESSION.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip"})
    return _SESSION


def request(method, url, params=None, json_body=None, tries=6):
    """One polite request.  Returns parsed JSON or a dict with __status / __error."""
    global _SESSION
    for attempt in range(tries):
        dt = time.time() - _STATE["last"]
        if dt < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - dt)
        _STATE["last"] = time.time()
        try:
            r = session().request(method, url, params=params, json=json_body,
                                  timeout=(10, 45))
        except Exception as e:                                        # noqa: BLE001
            _SESSION = None          # a timeout means the pooled connection is dead
            if attempt == tries - 1:
                return {"__error": repr(e)[:300]}
            time.sleep(min(30, 2 ** attempt))
            continue
        _STATE["requests"] += 1
        _STATE["bytes"] += len(r.content)
        try:
            _STATE["wire"] += int(r.headers.get("content-length") or len(r.content))
        except (TypeError, ValueError):
            _STATE["wire"] += len(r.content)
        if _STATE["wire"] > MAX_WIRE_BYTES:
            raise Budget(f"download cap reached: {_STATE['wire']/1e6:.1f} MB on the wire")
        if _STATE["requests"] >= REQ_LIMIT:
            raise Recycle(f"{_STATE['requests']} requests made; restarting")
        if r.status_code == 200:
            try:
                return r.json()
            except Exception as e:                                    # noqa: BLE001
                return {"__error": "bad json " + repr(e)[:200]}
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt))
            continue
        return {"__status": r.status_code, "__text": r.text[:300]}
    return {"__error": "retries exhausted"}


def get(url, params=None):
    return request("GET", url, params=params)


def post(url, body):
    return request("POST", url, json_body=body)


def stats():
    return dict(_STATE)


# ---- small on-disk helpers ------------------------------------------------------
def write_jsonl_gz(path, rows):
    """Atomic: a killed process can never leave a half-written page behind.

    Collection runs in bounded restarts (see README.md: a long-lived process on this
    host slows to a crawl after a few hundred requests while a fresh one stays at
    ~0.7 s per call), so a page must be either complete or absent.
    """
    tmp = path + ".part"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def read_jsonl_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def iso_to_epoch(x):
    """'2026-09-01T12:34:56.789Z' -> float seconds.  None-safe."""
    if not x:
        return float("nan")
    y = x.rstrip("Z")
    date, _, rest = y.partition("T")
    h, m, s = rest.split(":")
    yy, mm, dd = (int(v) for v in date.split("-"))
    # days since epoch by the civil-from-days algorithm (no tz handling needed: UTC)
    yy2 = yy - (mm <= 2)
    era = (yy2 if yy2 >= 0 else yy2 - 399) // 400
    yoe = yy2 - era * 400
    doy = (153 * (mm + (-3 if mm > 2 else 9)) + 2) // 5 + dd - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468
    return days * 86400.0 + int(h) * 3600 + int(m) * 60 + float(s)
