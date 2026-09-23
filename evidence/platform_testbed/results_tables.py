"""Assemble the full-run tables from the per-cell artefacts.

Reads `records/summary.json` (one row per cell, written by the platform's summarize
step), `records/simulator_replay.json` (the paper simulator's per-job comparison),
`records/manifest-<cell>.json` (what the generator was told to do) and
`records/usage-<cell>.log` (the engine's token lines for that cell), and prints the
Markdown tables that go into `results.md`.

Nothing here recomputes a measurement; it only joins and formats what the run wrote.

    env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
        uv run --no-sync python evidence/platform_testbed/results_tables.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RECORDS = Path(__file__).resolve().parent / "records"
PREFIX = "full-"

CELL_LABEL = {
    "full-fcfs-r2": "1 fcfs / 闭环(ii)",
    "full-spjf-r2": "2 spjf / 闭环(ii)",
    "full-guard-completed-r2": "3 guard 已完成计费 / 闭环(ii)",
    "full-guard-reservation-r2": "4 guard 预留计费 / 闭环(ii)",
    "full-guard-completed-r1open": "5 guard 已完成计费 / 开环(i)",
    "full-guard-completed-r3": "6 guard 已完成计费 / 闭环(iii)",
}
ORDER = list(CELL_LABEL)


def load(name: str):
    path = RECORDS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def usage_of(cell: str) -> dict:
    path = RECORDS / f"usage-{cell}.log"
    if not path.exists():
        return {"calls": 0, "prompt": 0, "completion": 0, "deadline_hits": 0, "by_agent": {}}
    text = path.read_text(encoding="utf-8-sig")
    by_agent: dict[str, list[int]] = {}
    prompt = completion = calls = 0
    for line in text.splitlines():
        match = re.search(r"agent=(\S+).*prompt_tokens=(\d+) completion_tokens=(\d+)", line)
        if not match:
            continue
        agent, p, c = match.group(1), int(match.group(2)), int(match.group(3))
        row = by_agent.setdefault(agent, [0, 0, 0])
        row[0] += 1
        row[1] += p
        row[2] += c
        prompt += p
        completion += c
        calls += 1
    return {
        "calls": calls,
        "prompt": prompt,
        "completion": completion,
        "deadline_hits": text.count("call deadline"),
        "by_agent": by_agent,
    }


def main() -> None:
    summary = {row["cell"]: row for row in load("summary.json")}
    replay = {row["cell"]: row for row in load("simulator_replay.json")}
    cells = [c for c in ORDER if c in summary]
    if not cells:
        raise SystemExit("no full-run cells in summary.json yet")

    print("## 每个 cell\n")
    print("| cell | n | rho | 跨度 | 平均等待 | p90 等待 | 最大 excess | excess/G | 闸开火 | 模拟器最大逐 job 偏差 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cell in cells:
        row = summary[cell]
        sim = replay.get(cell, {})
        print(
            f"| {CELL_LABEL[cell]} | {row['jobs']} | {row['load']['rho']} | "
            f"{row['load']['makespanS']:.0f} s | {row['waitS']['mean']:.1f} s | "
            f"{row['waitS']['p90']:.1f} s | {row['boundCheck']['maxExcessS']:.2f} s | "
            f"{row['boundCheck']['ratio']:.4f} | {row['guardFirings']} | "
            f"{sim.get('max_abs_error_s', float('nan')) * 1000:.1f} ms |"
        )

    print("\n## 实测服务时间（秒）\n")
    print("| cell | 类 | n | 中位数 | p90 | 最大 | CV | 触顶 | 超上限最大值 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for cell in cells:
        for name, info in summary[cell]["classes"].items():
            service = info["serviceS"]
            print(
                f"| {CELL_LABEL[cell]} | {name} | {info['n']} | {service['median']} | "
                f"{service['p90']} | {service['max']} | {service['cv']} | "
                f"{info['timedOut']} | {info['capExceededMsMax']} ms |"
            )

    print("\n## 派发器开销与边界检查\n")
    print("| cell | dispatch epoch 平均 | 最大 | 超出承诺的 job | 重放 FCFS 平均 / 最大等待 |")
    print("|---|---:|---:|---:|---|")
    for cell in cells:
        row = summary[cell]
        print(
            f"| {CELL_LABEL[cell]} | {row['dispatchEpochUs']['mean']} µs | "
            f"{row['dispatchEpochUs']['max']} µs | {row['boundCheck']['jobsOverPromise']} | "
            f"{row['replayFcfsWaitS']['mean']:.1f} / {row['replayFcfsWaitS']['max']:.1f} s |"
        )

    print("\n## token 与墙钟\n")
    print("| cell | 记到的模型调用 | input | output | 上限截停次数 | 墙钟 |")
    print("|---|---:|---:|---:|---:|---:|")
    totals = [0, 0, 0, 0, 0.0]
    for cell in cells:
        use = usage_of(cell)
        manifest = load(f"manifest-{cell}.json")
        wall = manifest.get("wallSeconds", 0.0) if isinstance(manifest, dict) else 0.0
        totals[0] += use["calls"]
        totals[1] += use["prompt"]
        totals[2] += use["completion"]
        totals[3] += use["deadline_hits"]
        totals[4] += wall
        print(
            f"| {CELL_LABEL[cell]} | {use['calls']} | {use['prompt']:,} | "
            f"{use['completion']:,} | {use['deadline_hits']} | {wall / 60:.0f} min |"
        )
    print(
        f"| **合计** | **{totals[0]}** | **{totals[1]:,}** | **{totals[2]:,}** | "
        f"**{totals[3]}** | **{totals[4] / 3600:.2f} h** |"
    )

    print("\n## 每类的 token 单价（实测）\n")
    combined: dict[str, list[int]] = {}
    for cell in cells:
        for agent, row in usage_of(cell)["by_agent"].items():
            acc = combined.setdefault(agent, [0, 0, 0])
            acc[0] += row[0]
            acc[1] += row[1]
            acc[2] += row[2]
    print("| 调用 | n | 平均 input | 平均 output |")
    print("|---|---:|---:|---:|")
    for agent, (n, p, c) in sorted(combined.items()):
        print(f"| {agent} | {n} | {p / n:.0f} | {c / n:.0f} |")

    print("\n## 原始行\n")
    print("```json")
    print(json.dumps([summary[c] for c in cells], indent=1, ensure_ascii=False))
    print("```")


if __name__ == "__main__":
    main()
