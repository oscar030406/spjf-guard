[English](README.md) | **简体中文**

# 预测驱动的非抢占调度与有界插队

论文 *Prediction-Driven Non-Preemptive Scheduling with Bounded Overtaking for Shared
Execution Services under Deadline-Driven Bursty Load* 的代码、导出表格与运行日志。

编程课的自动评测机是一种共享执行服务，无服务器平台、持续集成池和算力农场也是。这类服务在固定
数量的评测机上跑任务，不抢占，每个任务有一个执行上限 `L`。按预测开销给队列重新排序，能把大多数
任务的等待压下去，同时会把某一个任务甩在很后面：本文用的这条轨迹上，它比先来先服务多等了近
6,000 秒。运营者不会把这样的调度放上线。

论文证明了一条逐路径的恒等式：在任意不抢占、不空转的 k 台评测机策略下，一个任务相对 FCFS 多等
的时间等于它的净插队工作量除以 k，误差在 `(2-2/k)L` 以内。在这条恒等式之上，给任意底层策略套一
个包装器，限制允许插到一个等待任务前面的工作量，把这条界变成逐任务的承诺 `W <= W_FCFS + G`，
它在任意到达过程和任意预测误差下都成立。这个仓库装的是仿真器、预测器和实验驱动脚本，也装着论文
印出的每个数字背后的证据。

这个仓库是复现包，不是可以直接部署的调度器。

## 仓库里有什么

| 路径 | 放什么 |
| --- | --- |
| `src/spjf_guard/` | 正式代码。`sim/` k 台评测机的仿真器与两条定理的逐任务断言；`data/` 时钟与封存保护；`features/` 因果特征；`predict/` 排序分数；`experiment/` 叠加、选参、指标、报表 |
| `tests/` | 正确性测试，先于实现写的 |
| `configs/main.yaml` | 配置锁要钉死的每一项都在这里 |
| `scripts/` | 跑主实验、写配置锁草稿，做复现验收和生成物检查 |
| `evidence/` | 论文里凡是本包不产出的数字，一个研究一个子目录：跑过的脚本、它们的日志和它们写出的表。`evidence/README.md` 是索引，`evidence/PATHS.md` 把论文源码注释里写的路径对到这个目录 |
| `docs/adr/` | 难以撤销的决定，一件一页 |
| `docs/sealed_access_log.md` | 封存学期每读一次记一行 |
| `paper/` | 论文源码。表格数字从 `outputs/` 复制过来，没有脚本写进 `paper/` |
| `CONTEXT.md` | 术语表。一个概念一个词，论文、代码、配置和表格用的是同一个 |
| `GENERATED.md` | 每个由脚本产出的文件：来源、重生成命令、检查命令 |

`README.md` 是这份文件的英文版，命令相同。

这份文件提到的两个目录不在仓库里。`data/` 放原始数据集，不随仓库分发（见下）。`outputs/` 放流水
线写出的表，下面的命令会把它们逐个重新生成，哪条命令写哪个文件见 `GENERATED.md`。

## 环境

Python 3.12，依赖由 [uv](https://docs.astral.sh/uv/) 锁在项目本地的 `.venv` 里：

```bash
uv sync --extra dev
```

每条命令都要清掉 uv 自己的 `PYTHONHOME`，否则子进程会加载错的标准库：

```bash
export UV="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync"
```

**不需要设任何路径变量。** 每个输入位置都写在 `configs/main.yaml` 的 `data` 段里，相对仓库根
目录，由 `Config.data_path` 解析：

| 配置项 | 指向 | 谁写的 |
|---|---|---|
| `archive_dir` | `data/codebench/archives/` | 数据发布方的每学期归档 |
| `raw_parquet_dir` | `data/codebench/parquet/` | `scripts/parse_archive.py` |
| `cache_dir` | `data/derived/codebench_cache_r4/` | `scripts/build_cache.py` |
| `overlay_dir` | `data/derived/overlay_traces/` | `scripts/build_overlays.py` |
| `score_dir` | `data/derived/package_ranking_scores/` | `scripts/fit_scores.py` |

这些字符串里的 `${NAME}` 展开仍然有效，留给必须把某个输入指到别处的机器用；仓库自带的配置一个都
没用到。仓库里任何文件都不许出现只在某一台机器上存在的路径，`scripts/check_generated.py --only
paths` 是那道闸门。

## 数据

**原始数据不随仓库分发。** 跑任何东西之前，先把每个数据集从发布方下载到 `data/<name>/`。下表给
出来源，以及发布方自己写的条款。

| 数据集 | 是什么 | 来源 | 条款 |
|---|---|---|---|
| CodeBench v1.81 | UFAM 的程序设计入门课，2016–2024 共 18 个学期；毫秒级 IDE 事件，assessment 带开始与结束时间。主实验跑在它上面 | <https://codebench.icomp.ufam.edu.br/dataset/> | 页面没写许可协议。用于学术研究并引用，原始归档不转发。发表前先写信给数据集作者 |
| ACcoding v1.0.0 | 在线评测的提交日志，第二个评测平台 | <https://zenodo.org/record/6522395>, doi:10.5281/zenodo.6522395 | 论文写的是 CC BY 4.0，Zenodo 页面写的是 other-open，发表前确认 |
| OULAD | Open University 学习分析数据集，被推翻的那个原方向用的就是它 | <https://analyse.kmi.open.ac.uk/open_dataset>, doi:10.1038/sdata.2017.171 | CC BY 4.0 |
| Azure Functions 2021 | 无服务器调用轨迹，两周，1,980,951 次调用 | <https://github.com/Azure/AzurePublicDataset> (Zhang et al., SOSP 2021) | CC BY 4.0 |
| Intel Netbatch 2012 | 算力农场 pool D，9,054,066 个任务，标准工作负载格式 | <https://www.cs.huji.ac.il/labs/parallel/workload/l_intel_netbatch/> (Shai, Shmueli & Feitelson, JSSPP 2013) | 归档没有给许可协议，只说日志对研究者免费，并要求致谢和引用。致谢 Ohad Shai、Edi Shmueli 和 Nir Antebi（Intel）；文件不转发 |
| LPC-EGEE 2004 | 网格算力农场，六个 walltime 档；研究在 `evidence/lpc_egee_queues/` | <https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/> | 同一归档的条款。致谢 Emmanuel Medernach 提供日志，Dan Tsafrir 做 SWF 转换，以及 Parallel Workloads Archive |
| Mozilla Firefox CI | 两个 Taskcluster 硬件 worker 池，2026-08-24 到 09-14 和 2026-09-07 到 09-14。这里唯一一条记录了排队等待本身的轨迹，仿真器就是对着它验证的 | <https://firefox-ci-tc.services.mozilla.com/api/queue/v1> 与 <https://treeherder.mozilla.org/api>，公开且不需要鉴权 | 没有许可声明。取自公开 API，署名 Mozilla；只留下这次采集的那一段，不转发 |
| UPC Campus Nord Wi-Fi | 接入点占用率，早期的一个方向，论文没有任何结论压在它上面 | <https://data.mendeley.com/datasets/55vx86j8wf/1>, doi:10.17632/55vx86j8wf.1 | CC BY 4.0 |

字节稳定的那些文件的 SHA-256 记在作者工作树的 `data/README.md` 里；Firefox CI 那一段没有校验和，
因为 Taskcluster 的分页会过期，重抓一次的字节对不上。

**没有任何一行数据集记录进入这个仓库。** 提交进来的是代码、配置、汇总表和运行日志。已提交的表里
那些看着像标识符的列，标的是一种配置（策略、负载档、叠加、池、学期、模型、目标），不是人。学生
标识、用户名、邮箱地址、IP 地址和学生源代码都没有提交。

## 复现开发期的表

在仓库根目录下跑，`$UV` 按上面设好。一次只跑一个进程。

```bash
# 1  Gates: lint, types, fast tests
$UV ruff check src tests scripts
$UV mypy
$UV python -m pytest -q -m "not slow and not crosscheck"

# 2  Job-for-job comparison against the study kernels (imports two of them, read-only)
$UV python -m pytest -q -m crosscheck

# 3  Parse the publisher's archives into five tables per semester
$UV python scripts/parse_archive.py --semesters 2022-1 --compare

# 3b Build the parse cache
$UV python scripts/build_cache.py --pool development

# 3c The three experiment inputs: overlay traces, ranking scores, guard parameters
$UV python scripts/build_overlays.py --pool primary
$UV python scripts/build_overlays.py --pool validation
$UV python scripts/build_overlays.py --single-server          # the k = 1 line
$UV python scripts/fit_scores.py --repeat
$UV python scripts/select_parameters.py --workers 2           # validation overlays only
$UV python scripts/select_aging.py --workers 2                # the unguaranteed aging baseline

# 4  Main experiment: five overlays x three load levels
$UV python scripts/run_main.py --selection outputs/selection_v3/selected_parameters.csv \
    --out-dir outputs/dev_tables --workers 2

# 4b The single-server line, where the identity is an equality
$UV python scripts/run_main.py --prefix k1 --reps 0 --levels 0 \
    --selection outputs/selection_v3/selected_parameters.csv --out-dir outputs/dev_tables/k1

# 4c The ranking score read as a predictor: AUROC, AP, RMSE, Spearman, user-blocked intervals
$UV python scripts/eval_scores.py --pool primary

# 4d Original-clock exposure, and the conservative and static score variants
$UV python scripts/run_visibility.py --pool primary --workers 2

# 5  Acceptance
$UV python scripts/check_reproduction.py --overlay-dir data/derived/overlay_traces
$UV python scripts/check_overlays.py
$UV python scripts/diff_dev_tables.py
$UV python scripts/emit_paper_tables.py
$UV python scripts/check_paper_numbers.py
$UV python scripts/check_generated.py
```

选参跑的是三张预先写定的网格（常数预算 42 点，随等待放宽 162 点，随队列长度放宽 54 点，见 ADR
0005），共 258 点，在一个 server count 下去重成 243 条调度。`--workers 2` 下，作者的机器上单格
约 29 分钟，十五格约 7.3 小时。结果逐 cell 落盘，崩了重跑会跳过已经有结果的格；`--from-grid`
只重算规则、不重跑仿真，`--part i --nparts n` 把一个 cell 拆开。**只测了一部分格的命令，写出的
`selected_parameters.csv` 也只看得到这些格，那不是最终选择。** 分段结果要用 `--from-grid` 在同
一个 `--out-dir` 里对齐。

第 4 步在运行当中就对**每一个**仿真任务断言逐任务的界，不是事后在汇总量上查。第 5 步把这份代码
的逐任务等待和研究内核的逐任务等待对齐，再把汇总数字和
`evidence/main_v3/v31/table_main_primary.csv` 对照。

`check_reproduction.py` 的退出码是 1，这是设计如此：只要有一条逐任务等待不相等就算失败。当前的
不等来自旧内核的 float64 时钟，本包用的是精确整数微秒（ADR 0001）。15.9 亿次比较里有 0.0043 %
不同，聚合之后印出来的数字只动了一个：满载档 SPJF-E 的截止窗口 p99 从 62.91 秒变成 62.92 秒。
缺口收回比例一个都没变。

`outputs/main_table.tex` 里每个数字都包在 `\devnum{}` 里，排版出来的论文上，开发池的数字和封存
学期的数字因此一眼能分开。

## 封存数据规则

封存的是 CodeBench 2023-1、2023-2 和 2024-1，ACcoding 提交编号 80–100 % 那一段，以及 OULAD
2014 的两次开课。协议冻结之前，任何会读到它们的调用都会抛 `SealedDataError`，而且拒绝发生在打开
文件之前（`src/spjf_guard/data/sealed.py`，理由见 ADR 0004）。要防的是看过测试结果再回头改方法，
不是限制一个文件能打开几次。

冻结的步骤是先用 `--dry-run-sealed` 彩排，它打印会读哪些文件，一个都不打开；再写配置锁，把代码、
配置和输入产物哈希进去；提交；用 `scripts/freeze_protocol.py` 冻结，脏树、没有提交或者闸门不过
它都会拒；然后带 `--unseal` 把封存池跑一次。这里面每一次运行都往 `docs/sealed_access_log.md`
追加一行，记下日期、脚本、读了哪些封存学期、产出了什么、谁看过、有没有影响设计。
`docs/sealed_run_procedure.md` 里是完整的命令清单、每一步的前置条件、耗时与磁盘占用，还有中途崩
了怎么办。`README.md` 里是同一批命令。

封存学期上实际达到的利用率如实报告，不回头调评测机台数去凑目标值；单机轨迹的拷贝数也沿用开发池
上选出的那个（ADR 0006）。

## evidence/ 里的表从哪来

本包不产出的那些数字来自 `evidence/`，一个研究一个子目录：第二个评测平台、跨域轨迹、CI 验证、
理论笔记、闭环回放，还有算力农场那一项。每个子目录里放着跑过的脚本、它们写出的 `out_*.txt`、
产出的表，以及一份 `README.md`，说明问题是什么、对应论文的哪些条目、输入是什么、现在什么状态。
`evidence/README.md` 索引了全部，并列出哪些东西没复制进来、为什么；`evidence/PATHS.md` 把论文源
码注释里写的路径对到这个目录。

复制过来的副本保留了文件名和目录名，脚本之间是靠这些名字互相 import 的。只在某台机器上存在的绝
对路径换成了 `<repo-root>` 和 `<cache-dir>`，没有改动任何测量值。`out_*.txt` 这些运行日志一个字
都没重写，所以它们打印的工作目录名还是 `prechecks/`，读的时候当作 `evidence/`。

## 约定

- `CONTEXT.md` 是术语表。讨论里定下来的词写进去，论文、代码、配置和表格之后就都用这一个词。
- 难以撤销、以后会让人意外、确实有取舍的决定，在 `docs/adr/` 里占一页。
- 每个生成文件在 `GENERATED.md` 里有一行：来源、重生成命令、检查命令。手改生成文件会让
  `scripts/check_generated.py` 失败，这个脚本由 pre-commit 跑。

## 许可与引用

代码按 MIT 许可，见 `LICENSE`。数据集不在这个许可范围内，各自沿用上面数据表里的条款。
`CITATION.cff` 里是论文标题和占位作者，发布前填好。
