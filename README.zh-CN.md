> 这是作者的工作副本，英文版 `README.md` 是发布版本，两份命令相同。本文件里提到的 `docs/research_plan.md`、`docs/repo_build_status.md`、`docs/archive/` 与 `prechecks/` 是不进版本库的工作材料，公开仓库里打不开；论文引用到的那部分预检已经清理后复制进 `evidence/`。

# 异质图 × 教育场景网络负载研究

目标期刊：MDPI Mathematics 特刊 Computer Networks and Distributed Systems，截稿 2026-09-30。

选题取舍顺序（2026-09-18 定）：第一，符合特刊收录范围；第二，用到异质图神经网络，作为对比方法也可以；第三，体现教育应用背景。想法要从问题情景推出来，故事要闭环。

论文的问题是：多门课程共用固定数量评测机时，按预测开销排序能把截止高峰的等待压下去，但个别任务会比先来先服务多等近 6,000 秒，运营者不敢用。我们给任意底层调度器套一个包装器，限制「后来者插到一个等待任务前面的总工作量」，从而给出逐任务的承诺 `W ≤ W_FCFS + G`，并证明这类工作量预算既充分又必要。

## 目录

- `src/spjf_guard/`：正式代码。`sim/` 仿真器与两条定理的逐任务核验，`data/` 时钟与封存保护，`features/` 因果特征，`predict/` 排序分数，`experiment/` 叠加、选参、指标、报表。
- `tests/`：先于实现写的正确性测试（研究方案 §7.2 那一组）。
- `configs/main.yaml`：配置锁要钉死的每一项都在这里。
- `scripts/`：跑主实验、写配置锁草稿、复现验收、生成物检查。
- `prechecks/`：各候选方向的预检脚本与输出。**只读**，正式代码不依赖它，只有两个交叉验证的测试会导入它的内核做对照。
- `evidence/`：上一行那些预检里、论文真正引用到的那部分，清理后的可发布副本，一个研究一个子目录。论文里凡是不由 `src/` 产出的数字，都能在这里找到跑它的脚本和它的日志；路径对照见 `evidence/PATHS.md`。
- `paper/`：论文源码。表格数字只从 `outputs/` 复制过来，脚本不写进 `paper/`。
- `docs/`：方案文档、ADR、封存读取台账。`docs/archive/` 放已被推翻的方案。
- `data/`：原始数据，每个数据集一个子目录，不改动原始文件。

术语见 `CONTEXT.md`；难以撤销的决定见 `docs/adr/`；每个生成文件的来源与重生成命令见 `GENERATED.md`。

## 环境

Python 3.12，依赖由 `uv` 锁在项目本地的 `.venv`（不进版本库）：

```bash
uv sync --extra dev
```

所有命令都要清掉 uv 自己的 `PYTHONHOME`，否则子进程会加载错的标准库：

```bash
export UV="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync"
```

**不需要设任何路径变量。** 数据的位置全部写在 `configs/main.yaml` 的 `data` 段里，相对仓库根目录，由 `Config.data_path` 解析：

| 配置项 | 指向 | 谁产的 |
|---|---|---|
| `archive_dir` | `data/codebench/archives/` | 数据发布方的每学期归档 |
| `raw_parquet_dir` | `data/codebench/parquet/` | `scripts/parse_archive.py` |
| `cache_dir` | `data/derived/codebench_cache_r4/` | `scripts/build_cache.py`（`ev.parquet`） |
| `overlay_dir` | `data/derived/overlay_traces/` | `scripts/build_overlays.py` |
| `score_dir` | `data/derived/package_ranking_scores/` | `scripts/fit_scores.py` |
| `score_predictions_file` | `data/derived/ranking_score_predictions/rs_pred_ires0.parquet` | 预检留下的对照预测 |

`data/` 不进版本库，每个子目录的来源见 `data/derived/README.md`。字符串里仍然支持 `${NAME}`，留给必须把某个输入指到别处的机器用；本仓库自带的配置一个都没用。仓库里任何文件都不许出现只在某台机器上存在的路径，`scripts/check_generated.py --only paths` 是那道闸门。

## 复现开发期的表

```bash
# 1 闸门：静态检查、类型检查、快测试
$UV ruff check src tests scripts
$UV mypy
$UV python -m pytest -q -m "not slow and not crosscheck"

# 2 与预检内核逐任务对照（会只读导入 prechecks/ 的两个内核）
$UV python -m pytest -q -m crosscheck

# 3 从归档解析出每学期五张表（stage 0；盘上已经有就跳过，--compare 只比不写）
$UV python scripts/parse_archive.py --semesters 2022-1 --compare

# 3b 从 parquet 建解析缓存
$UV python scripts/build_cache.py --pool development

# 3c 重建实验的三个输入：叠加轨迹、排序分数、护栏参数（路径都来自配置）
$UV python scripts/build_overlays.py --pool primary
$UV python scripts/build_overlays.py --pool validation
$UV python scripts/build_overlays.py --single-server            # k = 1 那条
$UV python scripts/fit_scores.py --repeat
$UV python scripts/select_parameters.py --workers 2             # 只用验证叠加
$UV python scripts/select_aging.py --workers 2                  # 无保证的简单 aging 基线

# 4 主实验：五次叠加 × 三档负载，写 outputs/dev_tables/ 下的 CSV 与 .tex
$UV python scripts/run_main.py --selection outputs/selection_v3/selected_parameters.csv \
    --out-dir outputs/dev_tables --workers 2

# 4b 单服务器那条（恒等式在 k = 1 严格相等）
$UV python scripts/run_main.py --prefix k1 --reps 0 --levels 0 \
    --selection outputs/selection_v3/selected_parameters.csv --out-dir outputs/dev_tables/k1

# 4c 排序分数当预测器看：逐目标学期的 AUROC、AP、log1p 尺度 RMSE、Spearman 与按用户分块的区间
$UV python scripts/eval_scores.py --pool primary                    # 写 outputs/dev_predictor/

# 4d 原时钟暴露 + conservative/static，对 Guard 参数不重选
$UV python scripts/run_visibility.py --pool primary --workers 2     # 写 outputs/dev_visibility/

# 5 验收与对照
$UV python scripts/check_reproduction.py --overlay-dir data/derived/overlay_traces
$UV python scripts/check_overlays.py                                # 叠加数组对上 v3.1
$UV python scripts/diff_dev_tables.py                               # 印出来的数字差在哪
$UV python scripts/emit_paper_tables.py                             # 论文六张表 + numbers.csv
$UV python scripts/check_paper_numbers.py                           # 论文印的就是本包产的
$UV python scripts/check_generated.py                               # 生成物没被手改、没有机器路径
```

选参跑的是三张预先写定的网格（常数预算 42 点、随等待放宽 162 点、随队列长度放宽 54 点，见 ADR 0005），展开共 258 点、在一个 server count 下去重为 243 条调度。本机 `--workers 2` 的 conservative 单格实测约 29 分钟，十五格约 7.3 小时。逐 cell 落盘：崩了原样重跑会跳过已测的格，`--from-grid` 只重算规则不重跑仿真，`--part i --nparts n` 把一个 cell 拆成几段。分段命令写进同一个 `--out-dir` 后，用 `--from-grid` 对齐十五格一次性出选择；**分开跑的每条命令自己写出的 `selected_parameters.csv` 只看得到它测过的格，不是最终结果**。

第 4 步里每一次带护栏的仿真都在运行中对**每一个** job 断言定理二的上界，不是事后在汇总量上查。第 5 步把这份代码的逐任务等待和 `prechecks/` 内核的逐任务等待对齐，并把汇总数字和 `prechecks/main_v3/v31/table_main_primary.csv` 对照。

`check_reproduction.py` 目前退出码是 1，这是设计如此：只要有一条逐任务等待不等就失败。当前的不等来自旧内核的 float64 时钟（本仓库的时钟是精确整数微秒，见 ADR 0001），15.9 亿次比较里有 0.0043% 不同，聚合之后论文印出的数字只有满载档 SPJF-E 的截止窗口 p99 从 62.91 秒变成 62.92 秒，缺口收回比例一行未变。详情与判别实验见 `docs/repo_build_status.md`。

`outputs/main_table.tex` 的每个数字都包在 `\devnum{}` 里，`paper/sections/08_experiments.tex` 直接取用；开发期数字和封存学期数字因此在排版上可以一眼分开。

## 冻结之后：封存学期那一次

封存的是 CodeBench 2023-1 / 2023-2 / 2024-1、ACcoding 编号 80%–100%、OULAD 2014。在冻结之前，任何会读到它们的调用都会抛 `SealedDataError`，而且拒绝发生在打开文件之前（`src/spjf_guard/data/sealed.py`，理由见 ADR 0004）。

```bash
# 0 先彩排：打印会读哪些文件、锁的状态、策略与参数，但一个文件都不打开
$UV python scripts/run_main.py --config configs/main.yaml --dry-run-sealed

# 1 写配置锁草稿：代码、配置、输入产物的 sha256，加上方案要求钉死的全部选择
$UV python scripts/make_protocol_lock.py

# 2 冻结：先提交，再空跑，最后带 --yes。脏树、没有 commit、闸门不过都会被拒
git add -A && git commit -m "..."
$UV python scripts/freeze_protocol.py --dry-run
$UV python scripts/freeze_protocol.py --yes
git add protocol_lock.json docs/sealed_access_log.md    # 锁与冻结写的十二行台账一起提交
git commit -m "Freeze the protocol"

# 3 只此一次，打开封存学期（八步都要 --unseal）
$UV python scripts/build_cache.py --pool sealed --unseal          # 写 ev_sealed.parquet
$UV python scripts/build_overlays.py --pool sealed --no-scores --unseal
$UV python scripts/fit_scores.py --pool sealed \
    --out data/derived/package_ranking_scores/sealed_scores.parquet --unseal
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables --workers 2 --unseal
$UV python scripts/run_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_visibility --workers 2 --unseal
$UV python scripts/build_overlays.py --pool sealed --single-server --no-scores --unseal
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --prefix sealed_k1 --reps 0 --levels 0 \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables/k1 --unseal
$UV python scripts/eval_scores.py --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_predictor --unseal

# 4 出表与核对（不读封存数据，不要 --unseal）
$UV python scripts/emit_paper_tables.py --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor \
    --sealed-visibility-dir outputs/sealed_visibility
$UV python scripts/check_paper_numbers.py --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor \
    --sealed-visibility-dir outputs/sealed_visibility
```

封存学期的解析缓存是自己的一份 `ev_sealed.parquet`，开发期的 `ev.parquet` 原样留着：每个滚动起点的训练集都在开发缓存里，覆盖掉它封存运行就没有训练行了。这八条命令每条跑完自己往 `docs/sealed_access_log.md` 追加一行（日期、脚本、读了哪些封存学期、产出了什么、谁看过、是否影响设计），冻结时对十二个封存输入文件求哈希也各记一行。要防的是「看了测试结果再改方法」，不是文件只能打开一次。封存学期上实际达到的利用率如实报告，不回头调 k 去凑目标值——单机轨迹的拷贝数也一样，沿用开发池选出的 321 份，见 ADR 0006。详细步骤见 `docs/sealed_run_procedure.md`。

逐步的前置检查、耗时与磁盘占用、中途崩了怎么重跑，见 `docs/sealed_run_procedure.md`。

## 不在这个包里的东西

ACcoding 与跨域轨迹（OULAD 及其它）暂时留在 `prechecks/` 里，没有进正式包：封存保护已经按编号区间和学年写好（`guard_id_block`、`guard_oulad_year`，有测试），但解析、特征与叠加还没有搬过来。所以 2026-09-24 那一次封存运行只覆盖 CodeBench 的三个封存学期；ACcoding 80%–100% 与 OULAD 2014 在冻结之后要不要开、由谁的代码开，是另一件事，现在不做。

## 已有结论

- 原方案（关系感知鲁棒预缓存，OULAD）已被推翻，见 `docs/archive/` 文件顶部说明和 `prechecks/oulad/`。
- 当前仓库的建设状态、验证过哪些命令、还差什么，见 `docs/repo_build_status.md`。
