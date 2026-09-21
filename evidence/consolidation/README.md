# Dedicated containers versus a shared evaluator pool

**Question.** Nobody has measured the idle rate of a per-student container, and nobody
has computed how many dedicated containers it takes to match a shared pool of size k at
the same wait percentile. Both numbers are computed here from the existing CodeBench
development trace, with no new data.

**Paper items.** Supports the shared-pool framing of the manuscript; no individual number
of the paper is read from this folder, and `out_SUMMARY.txt` states in its own words what
may and may not be claimed from it.

**Inputs.** `data/codebench/parquet/{events,logins}/<semester>.parquet` and the parse
cache of `evidence/codebench_service_v2/`. Only the six 60 s-limit development semesters
are used; the sealed semesters are never opened.

**Status.** Current.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# 专属容器 vs 共享执行器池（consolidation）

回答 `docs/related_work/shared_queue_evidence.md` §4.6 与 §5.3 指出的那块空白：没有人测过
"每学生一个容器" 的空闲率，也没有人算过 "同等等待分位下，专属容器数 vs 共享池 k"。本目录
用现有的 CodeBench 开发学期轨迹把这两个数算出来，不引入任何新数据。

## 里面有什么

| 文件 | 是什么 |
|---|---|
| `containers.py` | 测量一：专属容器的并发数与利用率。脚本头部的 docstring 写了全部定义 |
| `pool_k.py` | 测量二：在同一条需求上，FCFS / SPJF-M4 / SPJF+护栏 达到截止窗口 p99 等待 ≤ 1/5/30 秒所需的最小 k |
| `summarize.py` | 测量三与结论：把两个 json 合成 `out_SUMMARY.txt` |
| `out_dedicated.txt` | `containers.py` 的运行日志 |
| `out_pool_k.txt` | `pool_k.py` 的运行日志（含整条 k 扫描曲线） |
| `out_SUMMARY.txt` | 数字、论文能说的一句话、论文不能说的几句话 |
| `dedicated.json`, `pool_k.json` | 上面两个脚本的机读结果，`summarize.py` 的输入 |

新文件只进本目录。其余目录只读。

## 数据范围

只用开发学期，且只用 60 秒时限期的六个学期 —— 2020-ERE、2020-2、2021-1、2021-2、
2022-1、2022-2，也就是方案 §2.4 的主叠加池（40 个班次—学期）。封存学期 2023-1、2023-2、
2024-1 全程没有打开；`docs/sealed_access_log.md` 不需要新增记录。

## 重跑

命令前缀统一是

```bash
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run \
    --with numpy --with pandas --with scipy --with pyarrow --with lightgbm --with numba
```

顺序与耗时（2026-09-19，机器上另有实验在跑）：

```
python containers.py   >  out_dedicated.txt      15 s
python pool_k.py       >  out_pool_k.txt         82 s   （其中 k 扫描 73 s）
python summarize.py    >  /dev/null              1 s    （写 out_SUMMARY.txt）
```

- 源：`data/codebench/parquet/{events,logins}/<学期>.parquet`，以及
  `evidence/codebench_service_v2` 的解析缓存（缓存目录的 `cb_v2_cache_r4`，路径写死在
  两个脚本顶部；缓存不在就按 `evidence/codebench_service_v2/README.md` 重建）。
- 叠加轨迹由 `service_precheck_v2.p2_inputs / ms_entries / overlay / rebase / level_ks`
  重建（只读导入），队列内核用 `evidence/guard_variants/guardkern.py`，都不是这里新写的。
  `pool_k.py` 会把重建出的轨迹缓存到 缓存目录的 `consol_inputs/rep0.npz`，删掉即重建。
- 检查：`out_SUMMARY.txt` 第 0 节把 k = 8 上的四个等待分位与
  `evidence/guard_variants/pareto_tables.txt`（另一个脚本、另一份独立重建的叠加）逐个
  对照，四个数完全相同才说明这里跑的是同一条轨迹、同一个队列。

## 一路上发现的两件事（会影响别处）

1. **`logins.log` 是按用户的全平台历史，不是本学期本班的记录。** 同一个用户的登录行会原样
   出现在他所在的每一个班级目录里，而且回溯到 2016 年 —— 2022-2 的归档里有 2016-05 的行。
   所以计数前必须按 `(user, timestamp, kind)` 去重并裁到本学期的事件窗口内，容器的计数单位
   是 `(学期, 用户)` 而不是 `(学期, 班级, 用户)`。`evidence/codebench/out_parse.txt` 里的
   `n_logins` 是去重前的行数。
2. **登出只写了一小部分。** 各学期只有 11%–35% 的登录后面跟着一条 logout，所以 "真实会话"
   只能重建、不能直接测。`out_SUMMARY.txt` 第 1 节给了六种口径，p99 并发容器数在 1003 到
   2525 之间，这个区间就是诚实的不确定度。
