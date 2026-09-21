# CodeBench service side, v2.1: causal cost prediction and the shared pool

**Question.** Can evaluation cost be predicted before the job runs, using only
information available at its arrival, and does a prediction-driven shared evaluator pool
beat first-come first-served on the real arrival times?

**Paper items.** The CodeBench prediction column of
`paper/sections/04_prediction.tex`; the block count before the `C == 0` drop in
Section 7; the AUROC of the CodeBench row in Section 8's cross-domain table; the
sensitivity table (`tab:sens`) of Section 8; the slopes, kill feedback and 60 s
discussion in `paper/supplementary.tex`.

**Status.** Current. It supersedes the first version of this study, which built its
history features by submission order rather than by result-availability time and is
therefore optimistic; that version is not included here.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

CodeBench 服务侧预检 v2.1，取代 `../codebench_service/` 的数字。

`service_precheck_v2.py` 是本目录唯一的脚本（sha256 `47a1f76355a66684639db9e8e23bb2825e4b3a4438929fab494d65dc2edaa0f0`）。它做四件事：按结果可用时刻构造历史特征（主配置 ires0：SUBMITION 头部时刻是结果时刻，到达 = ts' - C，结果对后来的提交可见当且仅当 done + delta <= 其到达时刻）；给每条记录加一个由固定 key 和记录 id 算出的抖动 u ~ U[0,1)，用 ts' = ts + u 代替整秒 ts，堵住 frac(C) 经时间间隔特征泄漏到标签的通道（未抖动的 clock0 作为对照配置保留）；用滚动起点的前向预测驱动反事实共享评测机池仿真，主指标是每次作业截止前 24 小时窗口内到达作业的 p99 等待，区间由 2000 次整周块配对自助法给出；在单评测机配置下逐作业断言 W_guard <= W_FCFS + B + 60。

`out_service_v2.txt` 由 `--stage report` 生成，前半是汇总表，后半是每个阶段的原始日志。每个阶段日志第一行写着当时脚本的 sha256，只要有一个和当前脚本对不上，report 就拒绝出报告。

运行顺序如下，命令前缀统一是

```bash
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME uv run --with pandas \
    --with numpy --with scipy --with pyarrow --with lightgbm python service_precheck_v2.py
```

缓存目录 `--cache DIR` 下面写死了 `DIR=<cache-dir>/cb_v2_cache_r4`，本轮整轮 1 小时 28 分（2026-09-19 05:40 到 07:08，24 逻辑核）：

```
--stage selftest                                          7 s
--stage load                                             18 s
--stage features                                        2.4 min   八个配置一次跑完
--stage leak                                            1.9 min
--stage p1 --configs ires0,clock0                       6.5 min   九个配置分五次，每次至多两个
--stage p1 --configs ires600,ires0_t600                 6.5 min
--stage p1 --configs isub0,isub60                       6.4 min
--stage p1 --configs isub600,isub3600                   6.6 min
--stage p1 --configs v1                                 3.4 min
--stage boot --configs ires0,clock0,ires600,ires0_t600  3.8 min
--stage boot --configs isub0,isub600,v1                 2.7 min
--stage forward --configs ires0                         2.2 min
--stage forward --configs ires600,isub0,clock0,v1       6.9 min
--stage latency                                          52 s
--stage pool                                             45 s     选拷贝数、周集合、最忙小时成分
--stage p2 --configs ires0 --variant base --reps 0      2.5 min   主链路 5 个 rep，分三次
--stage p2 --configs ires0 --variant base --reps 1,2    4.9 min
--stage p2 --configs ires0 --variant base --reps 3,4    4.9 min
--stage p2 --configs ires0 --variant pool19 --reps 0,1,2  62 s
--stage p2 --configs ires0 --variant sbatch --reps 0,1,2 3.8 min
--stage p2 --configs ires0 --variant sdrop  --reps 0,1,2 4.1 min
--stage p2 --configs isub0 --variant base   --reps 0,1,2 3.5 min
--stage p2boot                                            3 s
--stage guardk1 --configs ires0 --reps 0,1,2            6.1 min
--stage guardk1 --configs isub0 --reps 0                1.8 min
--stage report                                            2 s     写 out_service_v2.txt
```

`--variant dedup` 这一轮没跑：主池扣掉 C == 0 的块之后重复提交是 0 条，dedup 轨迹和主轨迹逐行相同，`--stage pool` 的日志里写了这一点。

`verify_review.py` 和 `verify_review.txt` 是上一轮复核留下的文件，不属于上面的流程，也不被任何阶段读取。

重新生成：源是 `data/codebench/parquet/` 下 2018-1..2022-2 的学期表和 `../codebench_service/` 里 v1 的特征定义；产物是本目录的 `out_service_v2.txt`；命令是把上表从 selftest 到 report 全跑一遍；检查是 `--stage report` 会逐个比对阶段日志首行的 sha256，与当前脚本不一致就退出，不出报告。封存学期 2023-1、2023-2、2024-1 全程没有打开。
