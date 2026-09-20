# 封存学期那一次：怎么跑（2026-09-24）

这份文件只讲操作：冻结之前要检查什么，冻结怎么做，那一次运行是哪几条命令，台账写什么，要多久、占多少盘，中途崩了怎么办。为什么这么设计见 ADR 0003（选参规则）与 ADR 0004（封存保护）；每个产物的来源见 `GENERATED.md`。

范围：**只有 CodeBench 的三个封存学期 2023-1 / 2023-2 / 2024-1**。ACcoding 编号 80%–100% 与 OULAD 2014 不在这一次里（代码还没搬进包，见 README「不在这个包里的东西」）。

命令前缀同 README；路径不用设环境变量，全部来自 `configs/main.yaml` 的 `data` 段：

```bash
export UV="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync"
```

## 一 冻结之前要检查的（全部在开发数据上，可以反复跑）

| # | 命令 | 期望 |
|---|---|---|
| 0 | `$UV python scripts/parse_archive.py --semesters 2022-1 --compare` | 五张表 40 列全等（约 11 秒） |
| 0b | `$UV python scripts/build_cache.py --pool development --compare data/derived/codebench_cache_r4/ev.parquet` | 58 列全部相等 |
| 1 | `$UV ruff check src tests scripts` / `$UV mypy` / `$UV python -m pytest -q` | 全绿 |
| 2 | `$UV python scripts/check_overlays.py` | 本包产的叠加与 v3.1 逐数组相等 |
| 3 | `$UV python scripts/fit_scores.py --repeat` | 两遍分数逐位相同 |
| 4 | `$UV python scripts/select_parameters.py --workers 3`，十五格齐了再 `--from-grid` | 三个家族各自的最好点与联合胜者，与 `configs/main.yaml` 的 `family_best` / `selected` 相同；`$UV python scripts/compare_selection.py` 与 v3.2 的九个家族选点逐个相同 |
| 5 | `$UV python scripts/run_main.py --selection outputs/selection_v3/selected_parameters.csv --out-dir outputs/dev_tables` | 开发期全表出齐，且开头**没有** `selection mismatch` 那一行 |
| 6 | `$UV python scripts/emit_paper_tables.py` | 六张表写出，`numbers.csv` 里每个数要么有来源要么有理由 |
| 7 | `$UV python scripts/check_paper_numbers.py` | 论文表体与本包逐值相同、正文数字重算得出、有来源的行仍然印着 |
| 8 | `$UV python scripts/check_generated.py` | 产物清单、论文数字、论文印的值、机器路径、配置锁五项都过 |
| 9 | `$UV python scripts/run_main.py --config configs/main.yaml --dry-run-sealed` | 打印计划；末行 `verdict REFUSED: no frozen protocol_lock.json exists` |

第 9 步是彩排：它打印封存学期名单、五条叠加 × 三档负载、16 条策略、每个承诺 G 对应的 B0、**会读哪些文件**、台账路径与锁的状态，然后退出。它一个文件都不打开，可以随便跑。

封存学期的解析缓存现在由本包的 `scripts/build_cache.py` 从 `data/codebench/parquet/` 建（第三轮搬进来的），在开发学期上与旧缓存 58 列逐列相等。封存那一次的第 1 步就是它。

## 一·A 那批 per-semester parquet：已经在盘上，封存那一次不需要重新解析

第四轮把归档解析也搬进了包：`scripts/parse_archive.py` + `src/spjf_guard/data/archive.py`，从 `data/codebench/archives/cb_dataset_<学期>_v1.81.tar.gz` 流式解析出 `assessments / events / logins / codemirror / users` 五张表。验证方式是在开发学期 **2022-1** 上重解析一遍再与盘上的 parquet 逐列比对：**40 列全等**，11 秒（`scripts/parse_archive.py --semesters 2022-1 --compare`，测试 `tests/test_archive_parse.py`，标了 `slow`）。

**封存那一次不跑这一步**。十八个学期的 parquet 是 2026-09-18 一次性解析出来的（`data/codebench/parquet/_parse_stats.csv` 记着每个学期的行数、字节数与耗时），三个封存学期的六个文件当时就已经在盘上：

```text
data/codebench/parquet/events/2023-1.parquet        data/codebench/archives/cb_dataset_2023_1_v1.81.tar.gz
data/codebench/parquet/code_features/2023-1.parquet data/codebench/archives/cb_dataset_2023_2_v1.81.tar.gz
data/codebench/parquet/assessments/2023-1.parquet   data/codebench/archives/cb_dataset_2024_1_v1.81.tar.gz
… 2023-2 与 2024-1 同样三张
```

也就是九个 parquet 加三个归档，共十二个文件。**冻结时对这十二个文件按字节求 sha256 并记进锁里**，由 `scripts/freeze_protocol.py` 做，不由任何人手动做。这件事本身是一次「打开」：求哈希要把字节读进来。所以：

- 求哈希**不解析内容**——不读表、不看行数、不做任何统计，读到的只有字节流；
- 每个文件在 `docs/sealed_access_log.md` 里**各占一行**，写明「只读取字节求 sha256、未解析内容」和文件大小；
- 这十二行是冻结那一刻写的，不是运行那一刻。封存运行自己的台账行照旧另写。

钉住哈希的用处：封存运行结束之后，任何人都能重算这十二个 sha256，确认那一次读的就是冻结时那批文件，中间没有换过数据。

## 二 冻结

```bash
# 1 写草稿：代码、配置、输入产物的 sha256，加上方案要求钉死的全部选择
$UV python scripts/make_protocol_lock.py

# 2 人读一遍草稿：学期划分、可见性协议、预测器与种子、排序分数、护栏家族与选择规则、
#   选好的三组参数、三档负载与 k 的取法、主指标、bootstrap 设置
less protocol_lock.draft.json

# 3 先提交。锁里要记 commit，工作区脏或者一个 commit 都没有，冻结会被拒绝
git add -A && git commit -m "..."

# 4 空跑一遍：查提交状态、跑全部闸门、列出会被求哈希的十二个封存文件，什么都不写
$UV python scripts/freeze_protocol.py --dry-run

# 5 真冻结。--yes 是那个人的决定，脚本不会自己替他做
$UV python scripts/freeze_protocol.py --yes

# 6 记下指纹，后面判断「是不是同一个锁」靠它
sha256sum protocol_lock.json
```

第 5 步做四件事，顺序固定，任何一件不过就停下：工作区必须是干净的且有 commit；`ruff` / `ruff format --check` / `mypy` / `pytest` / `check_generated.py` / `check_paper_numbers.py` 六个闸门必须全绿；十二个封存文件按字节求 sha256，每个写一行台账；然后把草稿加上 commit id 和这十二个哈希写成 `protocol_lock.json`，草稿原样留着。脚本本身在一个临时克隆里连同假的封存目录测过：干净树上写出锁与十二行台账，脏树被拒，已经冻结的仓库上再跑一次会直接说「已经冻结」。

冻结之后 `tests/test_sealed_data.py::test_no_frozen_lock_exists_yet` 会失败——这条测试就是用来防止意外冻结的，真冻结之后它失败是对的，改测试之前先想清楚。

冻结之后**不要**再改 `src/`、`scripts/`、`configs/main.yaml`。改了就是另一份方法，锁里的 sha256 会对不上。

## 三 那一次运行

四条命令，按顺序，每条都要 `--unseal`：

```bash
# 1 解析缓存：三个封存学期的事件表，从盘上已有的 parquet 建（不重新解析归档）
$UV python scripts/build_cache.py --pool sealed --unseal

# 2 封存池的叠加轨迹：与 primary 同一个函数，只是学期名单换成 pools.sealed
$UV python scripts/build_overlays.py --pool sealed --unseal

# 3 封存学期的排序分数：训练集仍然只有它之前的学期，滚动起点不变
$UV python scripts/fit_scores.py --pool sealed \
    --out data/derived/package_ranking_scores/sealed_scores.parquet --unseal

# 4 主运行：策略集与参数全部来自冻结的配置，不重新选参
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables --workers 3 --unseal
```

四条命令每条跑完自己往 `docs/sealed_access_log.md` 追加一行，格式是那张表已有的六列：

```text
| 2026-09-24 | `scripts/run_main.py` | 封存学期 2023-1, 2023-2, 2024-1 | <产出了什么> | 运行者 | 否 |
```

「是否影响设计」默认写「否」。如果看了这次结果之后真的改了方法，那一行要改成「是」，并且在论文里说明——这才是台账存在的意义。

产物就是配置锁里 `run.sealed_tables` 钉死的那一份清单，一个不多一个不少：`main_cells.csv`（逐格）、`main_table.csv`（按叠加聚合）、`main_table.tex`、`paired_differences.csv`（成对差与区间）、`bound_checks.csv`（逐任务断言查了多少个任务、最坏用掉允许量的几成）、`identity_residuals.csv`（第一条叠加上的恒等残差）、`policy_parameters.csv`（每格每条策略实际用的 B0、η、γ、上限、N）、`manifest.json`。「一个不多一个不少」不是口头约定：`--pool sealed` 的运行在写完之后自己比对写出的文件名集合与这份清单，对不上就报错退出。开发期的表在 `outputs/dev_tables/`，两边不覆盖。

报告口径：封存学期上实际达到的利用率如实报告，**不回头调 k 去凑目标值**；承诺 G 与选好的 (B0, η) 是冻结的，不因为封存学期上的结果重选。

## 四 要多久、占多少盘

在这台机器上（4 个工作进程，每个进程单线程）实测：

| 步骤 | 时间 | 盘 |
|---|---|---|
| 叠加轨迹（5 条） | 拷贝数探针 6 s + 每条约 3 s，连读缓存带写盘约 2 分钟 | 每条约 790 MB，5 条约 4.0 GB |
| 排序分数 | 83 s（6 个开发目标学期；封存池只有 3 个，更快。加 `--repeat` 翻倍） | 约 30 MB |
| 主运行 15 格 | 每格 53–57 s（16 条策略 + 2,000 次成对 bootstrap，4 个工作进程），连读叠加共约 16 分钟 | 表格 < 5 MB；每格临时约 750 MB，跑完即删 |
| 合计 | 约 20 分钟 | 峰值约 5 GB |

这些是开发池（17.6 M job／条）上的实测值，封存池的三个学期规模相近，量级应当一样。对照：验证集选参跑 15 格要约 48 分钟（每格 190 s，48 个网格点），那一步在冻结之前做完，不属于封存那一次。

临时文件默认落在系统临时目录，用 `--scratch <dir>` 指到别处；`--workers` 控制进程数。

## 五 中途崩了怎么办

规矩是「看结果之前不能改方法」，不是「文件只能打开一次」。所以技术性重跑允许，条件有三条：

1. **锁没变。** 重跑前核对 `sha256sum protocol_lock.json` 与第二节记下的指纹一致。不一致就不是同一份方法，停下来。
2. **代码与配置没变。** 崩了不要「顺手修一下再跑」。真发现必须改的 bug，那就是新的一份方法：说明情况、重新冻结、在台账里写清楚前一次读过什么。
3. **每一次都记台账。** 崩掉的那一次也记一行，输出栏写「运行在第 N 格中断，未产出汇总表」。台账要能看出总共开过几次、每次看到了什么。

具体怎么重跑：

- **叠加或分数那一步崩了**：原样重跑整条命令，它们是确定性的，产物会被覆盖成同样的内容。
- **主运行中途崩了**：原样重跑整条命令。主运行不逐格落盘（选参才逐格落盘），所以会从头再跑一遍 15 格，约 16 分钟——比补格子省事。真要补某几格，用 `--reps` / `--levels` 指定，再把两次的 `main_cells.csv` 合起来，但那样出来的表得自己核对行数。
- **机器内存不够被杀**（表现是进程直接消失、没有 traceback）：把 `--workers` 降到 2 再重跑。本轮开发期就遇到过一次：另一个重活同时在跑，选参跑到第 3 格时进程被杀，没有任何报错，原样重跑即过。

不允许的做法：看完一部分结果之后改承诺 G、改 (B0, η)、改策略集、改指标、改聚合方式，然后再跑一次。那不是重跑，那是重选。
