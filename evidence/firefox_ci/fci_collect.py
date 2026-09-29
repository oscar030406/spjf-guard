"""Collect a continuous window of one or two Firefox CI hardware worker pools.

    uv run --with requests --with pandas --with pyarrow python fci_collect.py [stage]

Stages (each writes to data/mozilla_firefox_ci/raw/ and can be resumed):
  workers  - the current worker list of every pool (Taskcluster queue.listWorkers)
  repos    - which Treeherder repositories feed each pool, and the push-id range of the
             collection window (push ids are global and monotone in Treeherder)
  jobs     - Treeherder job rows for every (pool worker x repository), push-id chunked;
             gives task id, run id (retry_id), label, push, repo, created (submit), and
             Treeherder's own start/end timestamps
  status   - Taskcluster queue.statuses in batches of 500 for every collected task id;
             gives taskQueueId, priority, deadline, retriesLeft and every run with
             scheduled / started / resolved / workerId / state / reasonResolved
  runtime  - payload.maxRunTime per distinct label, from a sample of task definitions
  assemble - one parquet per pool with one row per RUN (a run is one service)

Why this route.  queue.listTaskQueues and the per-pool task listings need credentials;
queue.listWorkers, queue.status(es), queue.task and all of Treeherder do not.  Hardware
workers only ever claim tasks of their own pool (verified in out_collect.txt), so
enumerating Treeherder by machine_name over the pool's worker list enumerates the pool.
Treeherder's submit_timestamp is Taskcluster `created`, NOT `scheduled` (verified, see
out_collect.txt); the pure queue wait therefore has to come from the status call.
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True

import fci_common as C

# repositories that could plausibly feed a gecko hardware pool; the `repos` stage
# probes each one and keeps those that actually do.
CANDIDATE_REPOS = ["autoland", "try", "mozilla-central", "mozilla-beta", "mozilla-release",
                   "mozilla-esr140", "mozilla-esr153", "mozilla-esr115", "ash", "birch",
                   "cedar", "cypress", "elm", "holly", "jamun", "larch", "maple", "oak",
                   "pine", "toolchains", "comm-central", "comm-beta", "comm-esr140"]
TH_COUNT = 2000
STATUS_BATCH = 500


def pool_tag(pool):
    return pool.replace("/", "__")


# --------------------------------------------------------------------- workers
def stage_workers(fh):
    out = {}
    for pool in C.POOLS:
        prov, wt = pool.split("/")
        got, cont = [], None
        while True:
            p = {"limit": 500}
            if cont:
                p["continuationToken"] = cont
            j = C.get(f"{C.QUEUE}/provisioners/{prov}/worker-types/{wt}/workers", params=p)
            if "workers" not in j:
                C.log(fh, f"  ! {pool}: {str(j)[:200]}")
                break
            got.extend(j["workers"])
            cont = j.get("continuationToken")
            if not cont:
                break
        out[pool] = got
        quar = sum(1 for w in got if w.get("quarantineUntil"))
        C.log(fh, f"  {pool}: {len(got)} workers listed, {quar} quarantined now")
    with open(os.path.join(C.RAW, "workers.json"), "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


# ----------------------------------------------------------------------- repos
def push_range(fh):
    """Global push-id range covering the (widened) collection window."""
    lo, hi = None, None
    for repo in ("autoland", "try", "mozilla-central"):
        a = C.get(f"{C.TREEHERDER}/project/{repo}/push/",
                  params={"startdate": C.PUSH_START_DATE, "enddate": C.PUSH_START_DATE,
                          "count": 1000})
        b = C.get(f"{C.TREEHERDER}/project/{repo}/push/",
                  params={"startdate": C.PUSH_END_DATE, "enddate": C.PUSH_END_DATE,
                          "count": 1000})
        ra, rb = a.get("results", []), b.get("results", [])
        if ra:
            lo = min(x["id"] for x in ra) if lo is None else min(lo, min(x["id"] for x in ra))
        if rb:
            hi = max(x["id"] for x in rb) if hi is None else max(hi, max(x["id"] for x in rb))
    C.log(fh, f"  push-id range for {C.PUSH_START_DATE}..{C.PUSH_END_DATE}: {lo}..{hi}")
    return lo, hi


def stage_repos(fh, workers):
    lo, hi = push_range(fh)
    live = {}
    for pool in C.POOLS:
        ws = [w["workerId"] for w in workers[pool]]
        probe = ws[::max(1, len(ws) // 4)][:4]
        keep = []
        for repo in CANDIDATE_REPOS:
            n = 0
            for m in probe:
                j = C.get(f"{C.TREEHERDER}/project/{repo}/jobs/",
                          params={"machine_name": m, "push_id__gte": lo,
                                  "push_id__lte": hi, "count": 5, "return_type": "list"})
                n += len(j.get("results", []))
                if n:
                    break
            if n:
                keep.append(repo)
        live[pool] = keep
        C.log(fh, f"  {pool}: repositories that feed it = {keep}")
        C.log(fh, f"     (probed {len(CANDIDATE_REPOS)} candidates with "
                  f"{len(probe)} sample workers; the rest returned no job)")
    meta = {"push_lo": lo, "push_hi": hi, "repos": live}
    with open(os.path.join(C.RAW, "repos.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta


# ------------------------------------------------------------------------ jobs
def fetch_worker_repo(repo, machine, lo, hi, fh, depth=0):
    """All Treeherder job rows for one worker in one repo, push-id chunked.

    If a query returns exactly TH_COUNT rows the push range is halved and both halves
    are fetched, so no row can be silently dropped by the server-side limit.
    """
    j = C.get(f"{C.TREEHERDER}/project/{repo}/jobs/",
              params={"machine_name": machine, "push_id__gte": lo, "push_id__lte": hi,
                      "count": TH_COUNT, "return_type": "list"})
    if "results" not in j:
        C.log(fh, f"    ! {repo}/{machine} [{lo},{hi}]: {str(j)[:160]}")
        return []
    names = j.get("job_property_names")
    rows = [dict(zip(names, r)) for r in j["results"]] if names else j["results"]
    if len(rows) >= TH_COUNT and hi > lo and depth < 24:
        mid = (lo + hi) // 2
        return (fetch_worker_repo(repo, machine, lo, mid, fh, depth + 1)
                + fetch_worker_repo(repo, machine, mid + 1, hi, fh, depth + 1))
    return rows


def stage_jobs(fh, workers, meta):
    lo, hi = meta["push_lo"], meta["push_hi"]
    for pool in C.POOLS:
        tag = pool_tag(pool)
        d = os.path.join(C.RAW, "th_jobs", tag)
        os.makedirs(d, exist_ok=True)
        ws = [w["workerId"] for w in workers[pool]]
        C.log(fh, f"  {pool}: {len(ws)} workers x {len(meta['repos'][pool])} repos")
        done = 0
        for i, m in enumerate(ws):
            path = os.path.join(d, f"{m}.jsonl.gz")
            if os.path.exists(path):
                done += 1
                continue
            rows = []
            for repo in meta["repos"][pool]:
                for r in fetch_worker_repo(repo, m, lo, hi, fh):
                    r["_repo"] = repo
                    rows.append(r)
            C.write_jsonl_gz(path, rows)
            done += 1
            if done % 20 == 0 or done == len(ws):
                st = C.stats()
                C.log(fh, f"    {done}/{len(ws)} workers   {st['requests']} requests  "
                          f"{st['bytes']/1e6:.1f} MB decoded / {st['wire']/1e6:.1f} MB wire")


# ---------------------------------------------------------------------- status
def collect_task_ids(pool, restrict=True):
    """Task ids of a pool, optionally pre-filtered to the pool's own window.

    The filter uses Treeherder's own timestamps (submit = Taskcluster `created`, start =
    the run's start).  A run scheduled inside [w0, w1) must have started at or after w0,
    so keeping start in [w0, w1 + 2 days] (or submit inside the window, for runs that
    never started) cannot drop one; the exact `scheduled` filter is applied later, in
    stage_assemble, once the real scheduled times are known.
    """
    tag = pool_tag(pool)
    d = os.path.join(C.RAW, "th_jobs", tag)
    w0iso, w1iso, _ = C.window(pool)
    w0, w1 = C.iso_to_epoch(w0iso), C.iso_to_epoch(w1iso)
    # only pools with an explicit narrowed window are pre-filtered; for the others the
    # id list must stay exactly what the already-downloaded status batches were cut from
    restrict = restrict and pool in C.POOL_WINDOW
    ids = set()
    for fn in os.listdir(d):
        for r in C.read_jsonl_gz(os.path.join(d, fn)):
            tid = r.get("task_id")
            if not tid:
                continue
            if restrict:
                st = r.get("start_timestamp") or 0
                sb = r.get("submit_timestamp") or 0
                if not ((w0 <= st <= w1 + 2 * 86400) or (w0 <= sb < w1)):
                    continue
            ids.add(tid)
    return sorted(ids)


def stage_status(fh):
    for pool in C.POOLS:
        tag = pool_tag(pool)
        ids = collect_task_ids(pool)
        d = os.path.join(C.RAW, "status", tag)
        os.makedirs(d, exist_ok=True)
        C.log(fh, f"  {pool}: {len(ids)} distinct task ids")
        for b in range(0, len(ids), STATUS_BATCH):
            path = os.path.join(d, f"{b:08d}.jsonl.gz")
            if os.path.exists(path):
                continue
            batch = ids[b:b + STATUS_BATCH]
            j = C.post(f"{C.QUEUE}/tasks/status", {"taskIds": batch})
            st = j.get("statuses")
            if st is None:
                C.log(fh, f"    ! batch {b}: {str(j)[:200]}")
                st = []
            C.write_jsonl_gz(path, [s["status"] for s in st if "status" in s])
            if (b // STATUS_BATCH) % 40 == 0:
                s = C.stats()
                C.log(fh, f"    {b}/{len(ids)}   {s['requests']} requests  "
                          f"{s['bytes']/1e6:.1f} MB decoded / {s['wire']/1e6:.1f} MB wire")


# --------------------------------------------------------------------- runtime
def stage_runtime(fh):
    """maxRunTime is a property of the task label (the taskgraph sets it per label).

    Sample up to 3 tasks per distinct label and record every maxRunTime seen, so that
    the assembly step can both map label -> maxRunTime and report how often a label is
    not single-valued.
    """
    import random
    for pool in C.POOLS:
        tag = pool_tag(pool)
        path = os.path.join(C.RAW, f"maxruntime_{tag}.json")
        done_path = path + ".done"
        if os.path.exists(done_path):
            C.log(fh, f"  {pool}: maxRunTime map already complete on disk")
            continue
        out = {}
        if os.path.exists(path):
            out = json.load(open(path, encoding="utf-8"))
            C.log(fh, f"  {pool}: resuming, {len(out)} labels already sampled")
        # the label -> task-id index costs minutes to rebuild from the job pages, and
        # this stage is restarted many times, so it is cached
        lab_path = os.path.join(C.RAW, f"labels_{tag}.json")
        if os.path.exists(lab_path):
            by_label = json.load(open(lab_path, encoding="utf-8"))
        else:
            by_label = defaultdict(list)
            d = os.path.join(C.RAW, "th_jobs", tag)
            for fn in os.listdir(d):
                for r in C.read_jsonl_gz(os.path.join(d, fn)):
                    if r.get("task_id") and r.get("job_type_name"):
                        by_label[r["job_type_name"]].append(r["task_id"])
            by_label = {k: v[:4] for k, v in by_label.items()} | {
                "__counts__": {k: len(v) for k, v in by_label.items()}}
            with open(lab_path, "w", encoding="utf-8") as f:
                json.dump(by_label, f)
        counts = by_label.pop("__counts__", None) or {k: len(v) for k, v in by_label.items()}
        rnd = random.Random(C.SEED)
        # labels sorted by how many runs they carry; sample until 95% of the runs are
        # covered (capped), so the download stays small and the covered share is known.
        order = sorted(by_label.items(), key=lambda kv: -counts[kv[0]])
        total = sum(counts.values())
        # maxRunTime is descriptive here (the guarantees use L' = train p99.9 of the
        # realised service, frozen in fci_build.py), and one GET per task was costing
        # 15-30 s on this connection, so the sample is capped and the covered share of
        # runs is reported instead of pretending to full coverage.
        cap = 200 if pool not in C.POOL_WINDOW else 40
        acc, chosen = 0, []
        for lab, tids in order:
            if acc / total >= 0.95 or len(chosen) >= cap:
                break
            chosen.append((lab, tids))
            acc += counts[lab]
        C.log(fh, f"  {pool}: {len(by_label)} distinct labels, {total} job rows; "
                  f"sampling maxRunTime for the {len(chosen)} biggest labels, which "
                  f"carry {acc/total*100:.1f}% of the rows")
        for i, (lab, tids) in enumerate(chosen):
            if lab in out:
                continue
            rnd.shuffle(tids)
            vals, deadlines = [], []
            for t in tids[:2]:
                j = C.get(f"{C.QUEUE}/task/{t}")
                if "payload" in j:
                    vals.append(j["payload"].get("maxRunTime"))
                    deadlines.append(C.iso_to_epoch(j["deadline"])
                                     - C.iso_to_epoch(j["created"]))
            out[lab] = {"maxRunTime": vals, "deadline_span": deadlines,
                        "n": counts[lab]}
            if (i + 1) % 25 == 0:        # checkpoint: the stage runs in bounded restarts
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(out, f)
                s = C.stats()
                C.log(fh, f"    {i+1}/{len(chosen)} labels  {s['requests']} requests  "
                          f"{s['bytes']/1e6:.1f} MB decoded / {s['wire']/1e6:.1f} MB wire")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f)
        open(done_path, "w").close()


# -------------------------------------------------------------------- assemble
def stage_assemble(fh):
    import numpy as np
    import pandas as pd

    for pool in C.POOLS:
        w0iso, w1iso, _ = C.window(pool)
        t0, t1 = C.iso_to_epoch(w0iso), C.iso_to_epoch(w1iso)
        tag = pool_tag(pool)
        # --- treeherder side: task_id -> label / repo / push / created / tier
        th = {}
        d = os.path.join(C.RAW, "th_jobs", tag)
        for fn in os.listdir(d):
            for r in C.read_jsonl_gz(os.path.join(d, fn)):
                tid = r.get("task_id")
                if not tid:
                    continue
                # keep run 0's row: its submit_timestamp is the task's `created`
                # (Treeherder writes one job row per run, each with its own submit time)
                prev = th.get(tid)
                if prev is None or r.get("retry_id", 0) < prev.get("retry_id", 0):
                    th[tid] = r
        mp = os.path.join(C.RAW, f"maxruntime_{tag}.json")
        mrt = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
        lab2mrt, multi = {}, 0
        for lab, v in mrt.items():
            vals = [x for x in v["maxRunTime"] if x]
            if not vals:
                continue
            if len(set(vals)) > 1:
                multi += 1
            lab2mrt[lab] = float(max(set(vals), key=vals.count))
        C.log(fh, f"  {pool}: {len(lab2mrt)} labels with a maxRunTime, "
                  f"{multi} labels where the sampled tasks disagreed")

        rows = []
        sd = os.path.join(C.RAW, "status", tag)
        n_task, n_other_pool = 0, 0
        for fn in sorted(os.listdir(sd)):
            for st in C.read_jsonl_gz(os.path.join(sd, fn)):
                n_task += 1
                if st["taskQueueId"] != pool:
                    n_other_pool += 1
                    continue
                meta = th.get(st["taskId"], {})
                lab = meta.get("job_type_name")
                for run in st.get("runs", []):
                    rows.append(dict(
                        task_id=st["taskId"], run_id=run.get("runId"),
                        pool=st["taskQueueId"], worker=run.get("workerId"),
                        worker_group=run.get("workerGroup"),
                        scheduled=C.iso_to_epoch(run.get("scheduled")),
                        started=C.iso_to_epoch(run.get("started")),
                        resolved=C.iso_to_epoch(run.get("resolved")),
                        created=float(meta.get("submit_timestamp") or "nan"),
                        deadline=C.iso_to_epoch(st.get("deadline")),
                        state=run.get("state"), reason_created=run.get("reasonCreated"),
                        reason_resolved=run.get("reasonResolved"),
                        priority=st.get("priority"), retries_left=st.get("retriesLeft"),
                        label=lab, repo=meta.get("_repo"), push_id=meta.get("push_id"),
                        tier=meta.get("tier"), th_result=meta.get("result"),
                        max_run_time=lab2mrt.get(lab, float("nan"))))
        df = pd.DataFrame(rows)
        C.log(fh, f"  {pool}: {n_task} task statuses ({n_other_pool} in another queue, "
                  f"dropped), {len(df)} runs before the window filter")
        keep = (df.scheduled >= t0) & (df.scheduled < t1)
        df = df[keep].sort_values(["scheduled", "task_id", "run_id"],
                                  kind="mergesort").reset_index(drop=True)
        p = os.path.join(C.DATA, f"runs_{tag}.parquet")
        df.to_parquet(p, index=False)
        C.log(fh, f"  {pool}: {len(df)} runs inside [{w0iso}, {w1iso}) "
                  f"-> {p} ({os.path.getsize(p)/1e6:.1f} MB)")


# -------------------------------------------------------------------- coverage
def stage_coverage(fh, meta, n_push=6):
    """How complete is the machine_name enumeration?

    Enumerating by the pool's CURRENT worker list can only miss (a) tasks that ran on a
    machine that has since dropped out of the list and (b) tasks that never ran at all
    (cancelled or superseded while pending, or failed to be claimed).  Both are measured
    here from the other direction: take whole pushes, list EVERY job of the push
    regardless of machine, ask Taskcluster which of them belong to the pool, and see how
    many of those we hold.
    """
    import random
    rnd = random.Random(C.SEED)
    lo, hi = meta["push_lo"], meta["push_hi"]
    held = {pool: set(collect_task_ids(pool)) for pool in C.POOLS}
    for pool in C.POOLS:
        C.log(fh, f"  {pool}: holding {len(held[pool])} task ids")
    # NOTE: the push endpoint ignores push_id__gte / push_id__lte (measured: it returned
    # today's pushes), exactly like the submit_timestamp filter on the jobs endpoint.
    # startdate / enddate do work -- the response echoes them back as
    # push_timestamp__gte / __lt -- so the window is expressed that way, and every
    # returned push id is checked against the collected range as well.
    picks = []
    for repo, day in (("autoland", "2026-09-02"), ("autoland", "2026-09-08"),
                      ("mozilla-central", "2026-09-04")):
        j = C.get(f"{C.TREEHERDER}/project/{repo}/push/",
                  params={"startdate": day, "enddate": day, "count": 200})
        res = [x["id"] for x in j.get("results", []) if lo <= x["id"] <= hi]
        if res:
            rnd.shuffle(res)
            picks += [(repo, p) for p in res[:1]]
    C.log(fh, f"  checking {len(picks)} whole pushes: {picks}")
    tot = {pool: [0, 0, 0] for pool in C.POOLS}     # in-pool, held, never-ran
    for repo, pid in picks:
        ids = []
        for off in range(0, 12000, 2000):
            j = C.get(f"{C.TREEHERDER}/project/{repo}/jobs/",
                      params={"push_id": pid, "count": 2000, "offset": off,
                              "return_type": "list"})
            names = j.get("job_property_names")
            rr = j.get("results", [])
            if not rr:
                break
            rows = [dict(zip(names, x)) for x in rr] if names else rr
            ids += [x["task_id"] for x in rows if x.get("task_id")]
            if len(rr) < 2000:
                break
        ids = list(dict.fromkeys(ids))
        stats_ = []
        for b in range(0, len(ids), STATUS_BATCH):
            j = C.post(f"{C.QUEUE}/tasks/status", {"taskIds": ids[b:b + STATUS_BATCH]})
            stats_ += [s["status"] for s in j.get("statuses", []) if "status" in s]
        for pool in C.POOLS:
            mine = [s for s in stats_ if s["taskQueueId"] == pool]
            have = sum(1 for s in mine if s["taskId"] in held[pool])
            never = sum(1 for s in mine
                        if not any(r.get("started") for r in s.get("runs", [])))
            tot[pool][0] += len(mine)
            tot[pool][1] += have
            tot[pool][2] += never
        C.log(fh, f"    {repo} push {pid}: {len(ids)} tasks; "
                  + "; ".join(f"{p.split('/')[1]}: "
                              f"{sum(1 for s in stats_ if s['taskQueueId']==p)} in pool, "
                              f"{sum(1 for s in stats_ if s['taskQueueId']==p and s['taskId'] in held[p])} held"
                              for p in C.POOLS))
    for pool in C.POOLS:
        a, b, c = tot[pool]
        C.log(fh, f"  COVERAGE {pool}: {b}/{a} = "
                  f"{(b/a*100 if a else float('nan')):.2f}% of the pool's tasks in these "
                  f"pushes are in our collection; {c} of the {a} never started a run "
                  f"({(c/a*100 if a else float('nan')):.2f}%, these are cancelled / "
                  f"superseded / never-claimed tasks and carry no service)")
    with open(os.path.join(C.RAW, "coverage.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in tot.items()}, f)


def main():
    try:
        return _main()
    except C.Recycle as e:
        print(f"[recycle] {e}", flush=True)
        sys.exit(3)
    except C.Budget as e:
        print(f"[budget] {e}", flush=True)
        sys.exit(4)


def _main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    mode = "a" if os.path.exists(os.path.join(C.HERE, "out_collect.txt")) else "w"
    with open(os.path.join(C.HERE, "out_collect.txt"), mode, encoding="utf-8") as fh:
        C.log(fh, f"\n=== collection stage '{stage}' ===")
        C.log(fh, f"pools: {C.POOLS}")
        C.log(fh, f"windows: " + "; ".join(f"{p} {C.window(p)[0]}..{C.window(p)[1]}" for p in C.POOLS))
        wpath = os.path.join(C.RAW, "workers.json")
        if stage in ("workers", "all") or not os.path.exists(wpath):
            C.log(fh, "-- workers --")
            workers = stage_workers(fh)
        else:
            workers = json.load(open(wpath, encoding="utf-8"))
        rpath = os.path.join(C.RAW, "repos.json")
        if stage in ("repos", "all") or not os.path.exists(rpath):
            C.log(fh, "-- repos --")
            meta = stage_repos(fh, workers)
        else:
            meta = json.load(open(rpath, encoding="utf-8"))
        if stage in ("jobs", "all"):
            C.log(fh, "-- jobs --")
            stage_jobs(fh, workers, meta)
        if stage in ("status", "all"):
            C.log(fh, "-- status --")
            stage_status(fh)
        if stage in ("runtime", "all"):
            C.log(fh, "-- runtime --")
            stage_runtime(fh)
        if stage in ("coverage", "all"):
            C.log(fh, "-- coverage --")
            stage_coverage(fh, meta)
        if stage in ("assemble", "all"):
            C.log(fh, "-- assemble --")
            stage_assemble(fh)
        s = C.stats()
        C.log(fh, f"done: {s['requests']} requests, {s['bytes']/1e6:.1f} MB decoded, "
                  f"{s['wire']/1e6:.1f} MB on the wire")


if __name__ == "__main__":
    main()
