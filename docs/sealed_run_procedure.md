# 封存学期那一次：怎么跑（2026-09-24 修订）

这份文件只讲操作：冻结之前要检查什么，冻结怎么做，那一次运行是哪几条命令，台账写什么，要多久、占多少盘，中途崩了怎么办。为什么这么设计见 ADR 0003（选参规则）、ADR 0004（封存保护）与 ADR 0008（online 主结果）；每个产物的来源见 `GENERATED.md`。

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
| 3 | `$UV python scripts/fit_scores.py --repeat` | original / conservative / static 各两列，共六列；两遍逐位相同 |
| 4 | `$UV python scripts/select_parameters.py --workers 2 --out-dir outputs/selection_v4`，十五格齐了再 `--from-grid` | 九个 Guard 选点与 `configs/main.yaml` 的 selected/family_best 一致（2026-09-24 起为 selection_v4；v3 读的是嵌入早期预测的旧 overlay，见配置注释）；`selection_protocol.json` 写出网格、展开点和候选/可行数 |
| 4b | `$UV python scripts/select_aging.py --workers 2` | 11 点网格按同一 validation-only harm 规则选出 `credit_per_s = 0.03`，并写完整候选计数；该基线没有证明保证 |
| 5 | `$UV python scripts/run_main.py --selection outputs/selection_v4/selected_parameters.csv --out-dir outputs/dev_tables --workers 2` | 开发期全表出齐，开头没有 `selection mismatch`；除新增 Aging 行外，既有行列逐位不变 |
| 5b | `$UV python scripts/eval_scores.py --pool primary` | 六个目标学期 × 六个分数 + 六个 pooled 行，共 42 行；heavy 阈值仍为 1.559043 s，2022-2 仍是 40,844 行、536 个重任务。约 11 分钟 |
| 5d | `$UV python scripts/run_visibility.py --pool primary --workers 2` | 十五格写 `outputs/dev_visibility/` 五张 CSV；FCFS 与 Guard 的 3600 秒 lag violation 都是 0，SPJF-E 如实报告；约 35 分钟 |
| 5e | `$UV python scripts/run_consistent_visibility.py --config configs/visibility_development_20260924.yaml --pool primary --workers 2 --resume --controls data/derived/package_ranking_scores/consistent_controls_20260924.npz` | 十五格写 `outputs/dev_consistent_visibility/`；五条冻结策略和 Guard(600) 的另一拷贝语义每格末轮都必须零违规；稀疏分数按 manifest 校验 |
| 5f | `$UV python scripts/assess_consistent_selection.py --config configs/visibility_development_20260922.yaml --out-dir outputs/consistent_selection_final --workers 2` | 固定 12 层的验证池计时，外推完整 15 格重选；计时点不能用于选择参数 |
| 5h | `$UV python scripts/run_online_visibility.py --pool primary --workers 2 --resume` | 十五格 × 五条冻结策略写 `outputs/dev_online_visibility/`；每个 policy-cell 的抽样审计 `mismatches` 为 0，三条 Guard 的逐 job 边界成立；original 行与 5e 的 original 行点估计逐位相同（出表时核对） |
| 5i | `$UV python scripts/select_online.py candidates`，再 `$UV python scripts/run_online_visibility.py --pool validation --variants online --candidates outputs/online_selection/candidates.csv --out-dir outputs/online_selection/validation --workers 2 --resume`，再 `$UV python scripts/select_online.py choose` | 36 个候选在验证池 15 格上的 online 重放；`online_choices.csv` 里 original 那一组必须等于 selection_v4 的九个选点；online 那一组只报告，不写回配置 |
| 5g | `$UV python scripts/check_preserved_outputs.py` | 原 75 张 CSV、18,627 行及全部既有列零字节差异；快照不得覆盖 |
| 5c | `$UV python scripts/build_overlays.py --pool validation --single-server --no-scores --out-dir <临时目录>` | 印 `321 copies (321 copies reused from pool primary)` 与实际忙时利用率（验证池上是 1.0043）。这一步彩排的是沿用拷贝数那条路径，产物不要写进 `data/derived/overlay_traces/` |
| 6 | `$UV python scripts/emit_paper_tables.py` | 既有表与 `outputs/paper_tables/numbers.csv` 逐字节保持原样 |
| 6e | `$UV python scripts/emit_paper_tables.py --dev-exact-dir outputs/dev_consistent_visibility --dev-online-dir outputs/dev_online_visibility --out-dir outputs/consistent_paper_tables` | 在独立目录生成既有表的副本、两张带 online 行的 exact 表和追加 exact/online 来源的数字索引；不覆盖旧目录；online 目录的 original 行与 exact 的不一致会直接退出 |
| 7 | `$UV python scripts/check_paper_numbers.py`，再跑 `$UV python scripts/check_paper_numbers.py --package-dir outputs/consistent_paper_tables --dev-exact-dir outputs/dev_consistent_visibility --dev-online-dir outputs/dev_online_visibility` | 旧论文表/数字仍与旧包一致；新目录的两张 exact 表逐字节符合 CSV recipe，若已贴入论文则逐值相同 |
| 8 | `$UV python scripts/check_generated.py` | exact 证书、旧表保存、产物清单、论文数字、论文印值、机器路径、draft 七项都过 |
| 9 | `$UV python scripts/run_main.py --config configs/main.yaml --dry-run-sealed` | 打印计划；十个阶段、六份产物清单、两个缓存文件名；末行 `verdict REFUSED: no frozen protocol_lock.json exists` |

第 9 步是彩排：它打印封存学期名单、五条叠加 × 三档负载、策略、三个静态 score variant、exact 可见性协议、online 策略名单、每个承诺 G 对应的 B0、**会读哪些文件**、六份输出清单、台账路径与锁的状态，然后退出。它一个文件都不打开，可以随便跑。

封存学期的解析缓存现在由本包的 `scripts/build_cache.py` 从 `data/codebench/parquet/` 建（第三轮搬进来的），在开发学期上与旧缓存 58 列逐列相等。封存那一次的第 1 步就是它。

## 一·A 那批 per-semester parquet：已经在盘上，封存那一次不需要重新解析

第四轮把归档解析也搬进了包：`scripts/parse_archive.py` + `src/spjf_guard/data/archive.py`，从 `data/codebench/archives/cb_dataset_<学期>_v1.81.tar.gz` 流式解析出 `assessments / events / logins / codemirror / users` 五张表。验证方式是在开发学期 **2022-1** 上重解析一遍再与盘上的 parquet 逐列比对：**40 列全等**，11 秒（`scripts/parse_archive.py --semesters 2022-1 --compare`，测试 `tests/test_archive_parse.py`，标了 `slow`）。

**封存那一次不跑这一步**。更正（2026-09-25 冻结空跑发现）：09-18 解析出的是 events 与 assessments；三个封存学期的 `code_features` 当时没有生成（静态代码特征由 `prechecks/codebench_service/code_features.py` 另算，开发期只算了 2018-1 至 2022-2）。冻结前于 2026-09-25 用同一解析器补齐，只算静态代码计数，台账各记一行；该解析器在开发学期 2022-1 上重跑与盘上文件逐列相同。十八个学期的 events/assessments parquet 是 2026-09-18 一次性解析出来的（`data/codebench/parquet/_parse_stats.csv` 记着每个学期的行数、字节数与耗时），三个封存学期的六个文件当时就已经在盘上：

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
#   exact 单调 withholding 与五条策略、online 暂停重放与五条策略、选好的三组参数、三档负载与 k 的取法、主指标、bootstrap 设置
less protocol_lock.draft.json

# 3 先提交。锁里要记 commit，工作区脏或者一个 commit 都没有，冻结会被拒绝
git add -A && git commit -m "..."

# 4 空跑一遍：查提交状态、跑全部闸门、列出会被求哈希的十二个封存文件，什么都不写
$UV python scripts/freeze_protocol.py --dry-run

# 5 真冻结。--yes 是那个人的决定，脚本不会自己替他做
$UV python scripts/freeze_protocol.py --yes

# 6 记下指纹，后面判断「是不是同一个锁」靠它
sha256sum protocol_lock.json

# 7 把锁和台账一起提交。冻结时的树已经在第 3 步那个 commit 里，锁本身还是未跟踪文件；
#   第 5 步给十二个封存输入各写了一行台账，那十二行也还没提交
git add protocol_lock.json docs/sealed_access_log.md
git commit -m "Freeze the protocol"
```

锁里的 `commit` 记的是第 3 步那个提交，也就是被冻结的那棵树；第 7 步是它之后的一个新提交，两者不是同一个 id，这是对的。提交完之后这几项必须仍然全绿，跑一遍再走：

- `$UV python -m pytest -q`：`tests/test_sealed_data.py` 里那条锁的检查这时改查 `protocol_lock.json`，两条「入口点拒绝封存池」的用例这时靠的是没给 `--unseal`（冻结之前靠的是没有锁），`tests/test_repo_hygiene.py` 检查锁要哈希的每个代码文件 git 都跟踪着；
- `$UV python scripts/check_generated.py --only protocol_lock`：锁记的输入哈希与盘上一致；
- `$UV python scripts/check_paper_numbers.py` 与 `$UV python scripts/check_paper_numbers.py --package-dir outputs/consistent_paper_tables --dev-exact-dir outputs/dev_consistent_visibility`：旧数字包保持原样，独立 exact 数字包此时也只来自开发数据；封存那一部分要等运行阶段 4、5、6、7、9、10 跑完才有。

第 5 步做四件事，顺序固定，任何一件不过就停下：工作区必须是干净的且有 commit；`ruff` / `ruff format --check` / `mypy` / `pytest` / `check_generated.py` / `check_paper_numbers.py` 六个闸门必须全绿；十二个封存文件按字节求 sha256，每个写一行台账；然后把草稿加上 commit id 和这十二个哈希写成 `protocol_lock.json`，草稿原样留着。脚本本身在一个临时克隆里连同假的封存目录测过：干净树上写出锁与十二行台账，脏树被拒，已经冻结的仓库上再跑一次会直接说「已经冻结」。

冻结前后同一条测试都要过：`tests/test_sealed_data.py::test_the_protocol_lock_describes_the_tree_it_belongs_to`。冻结之前它检查草稿的代码摘要与配置哈希就是当前工作树的（草稿落后于代码，冻结的就是没人跑过的方法）；冻结之后它改查 `protocol_lock.json` 的同两项，也就是「锁住的路径自冻结起一个字节都没动」，外加台账里每个被求过哈希的封存输入各有一行。**它不是旧的 `test_no_frozen_lock_exists_yet`**：那一条在冻结当天必然变红，已经删掉。

冻结之后**不要**再改 `src/`、`scripts/`、`configs/main.yaml`。改了就是另一份方法，锁里的 sha256 会对不上。

## 三 那一次运行

十条命令，按顺序，每条都要 `--unseal`：

```bash
# 1 解析缓存：三个封存学期的事件表，从盘上已有的 parquet 建（不重新解析归档）。
#   写的是 ev_sealed.parquet，开发期的 ev.parquet 原样不动——后面每一步都要同时读两份：
#   开发缓存是每个滚动起点的训练那一半，覆盖掉它，封存运行就没有训练行了
$UV python scripts/build_cache.py --pool sealed --unseal

# 2 封存池的叠加轨迹：与 primary 同一个函数，只是学期名单换成 pools.sealed。
#   --no-scores 是因为分数要到第 3 步才拟合出来，第 4 步按 job_row 挂上去
$UV python scripts/build_overlays.py --pool sealed --no-scores --unseal

# 3 封存学期的排序分数：训练集仍然只有它之前的学期，滚动起点不变
$UV python scripts/fit_scores.py --pool sealed \
    --out data/derived/package_ranking_scores/sealed_scores.parquet --unseal

# 4 主运行：策略集与参数全部来自冻结的配置，不重新选参
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables --workers 2 --unseal

# 5 committed conservative/static 参照与旧映射暴露审计：参数不重选；写 3600 秒违反数。
$UV python scripts/run_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_visibility --workers 2 --unseal

# 6 exact policy-specific 可见性：冻结原模型权重与参数；--workers 2 为资源上限。
#   最多两个 cell 同时运行，各 worker 内顺序细化；按固定 cell 次序汇总。
#   --resume 只接受输入、代码及产物哈希一致的检查点。
$UV python scripts/run_consistent_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_consistent_visibility --workers 2 --resume --unseal

# 7 online 重放（ADR 0008）：策略、变体与审计样本数只能是配置里钉死的那组，
#   命令行给别的会被拒；--resume 只接受签名一致的检查点。
$UV python scripts/run_online_visibility.py --config configs/main.yaml --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_online_visibility --workers 2 --resume --unseal

# 8 单机轨迹：拷贝数沿用开发池选出的 321 份，利用率如实报告（ADR 0006）。
#   文件叫 sealed_k1_rep0.npz，不会盖掉开发期的 k1_rep0.npz
$UV python scripts/build_overlays.py --pool sealed --single-server --no-scores --unseal

# 9 单机那一次的表：产物清单是 run.sealed_k1_tables，与第 4 步各查各的
$UV python scripts/run_main.py --config configs/main.yaml --pool sealed \
    --prefix sealed_k1 --reps 0 --levels 0 \
    --score-parquet data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_tables/k1 --workers 2 --unseal

# 10 封存学期的预测器指标：逐学期与合并，六个分数各四个指标加区间
$UV python scripts/eval_scores.py --pool sealed \
    --scores data/derived/package_ranking_scores/sealed_scores.parquet \
    --out-dir outputs/sealed_predictor --unseal
```

第 5 步把 fixed-lag 证书状态打印并写入 manifest。若 conservative 的观测 `W > 3600`，该锚必须
标成 `legacy conservative certificate invalid`，不能继续称为已认证的可见性方案。headline 为
online（ADR 0008）时，这个警告不阻断后面的步骤；若 headline 是 conservative，则该情况硬停。第 6 步的
末轮零违规断言、两步的逐 job Guard 边界或 sparse delta 检查失败始终硬停。第 7 步的抽样审计不一致由出表那一步硬停：runner 只打印不一致的份数，`emit_paper_tables.py` 与 `check_paper_numbers.py` 读 `online_audit.csv`，文件缺失或任一行 `mismatches` 非零就拒绝出表。

跑完之后出表与核对（这几条只读 `outputs/`，不读封存数据，也不需要 `--unseal`）：

```bash
$UV python scripts/emit_paper_tables.py --out-dir outputs/consistent_paper_tables \
    --dev-exact-dir outputs/dev_consistent_visibility \
    --dev-online-dir outputs/dev_online_visibility \
    --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor \
    --sealed-visibility-dir outputs/sealed_visibility \
    --sealed-exact-dir outputs/sealed_consistent_visibility \
    --sealed-online-dir outputs/sealed_online_visibility
$UV python scripts/check_paper_numbers.py --package-dir outputs/consistent_paper_tables \
    --dev-exact-dir outputs/dev_consistent_visibility \
    --dev-online-dir outputs/dev_online_visibility \
    --sealed-dir outputs/sealed_tables \
    --sealed-predictor-dir outputs/sealed_predictor \
    --sealed-visibility-dir outputs/sealed_visibility \
    --sealed-exact-dir outputs/sealed_consistent_visibility \
    --sealed-online-dir outputs/sealed_online_visibility
$UV python scripts/check_generated.py     # 看到 outputs/sealed_tables 就自动把封存那部分带上
```

出表写的是 `outputs/consistent_paper_tables/tab_*_sealed.tex`：五张原结果表、两张 visibility 表和两张 exact 表（带 online 行）的标签都加 `_sealed` 后缀，
每个数字包在 `\sealednum{}` 里而不是 `\devnum{}` 里——`\devnum` 的含义就是「这个数来自开发数据，
不是封存学期」，封存的数字不能走它。第 4、9 步自己写的 `main_table.tex` 也一样用 `\sealednum{}`。
**把这些表贴进论文之前，论文要先定义 `\sealednum`**：`\newcommand{\sealednum}[1]{#1}`，
放在已有的 `\newcommand{\devnum}[1]{#1}` 旁边，三个文件都要加——`paper/main.tex`、
`paper/main_article.tex`、`paper/supplementary.tex`。检查脚本认的就是这个宏。

十条命令每条跑完自己往 `docs/sealed_access_log.md` 追加一行，格式是那张表已有的六列：

```text
| 2026-09-24 | `scripts/run_main.py` | 封存学期 2023-1, 2023-2, 2024-1 | <产出了什么> | 运行者 | 否 |
```

「是否影响设计」默认写「否」。如果看了这次结果之后真的改了方法，那一行要改成「是」，并且在论文里说明——这才是台账存在的意义。

产物是配置锁里钉死的**六份**清单，每份都一个不多一个不少，各查各的：

| 命令 | 清单 | 内容 |
|---|---|---|
| 第 4 步 → `outputs/sealed_tables/` | `run.sealed_tables` | `main_cells.csv`（逐格）、`main_table.csv`（按叠加聚合）、`main_table.tex`、`paired_differences.csv`（成对差与区间）、`bound_checks.csv`（逐任务断言查了多少个任务、最坏用掉允许量的几成）、`identity_residuals.csv`（第一条叠加上的恒等残差）、`policy_parameters.csv`（每格每条策略实际用的 B0、η、γ、上限、N）、`manifest.json` |
| 第 5 步 → `outputs/sealed_visibility/` | `run.sealed_visibility_tables` | `visibility_cells.csv`、`visibility_comparison.csv`、`visibility_paired_differences.csv`、`visibility_exposure.csv`、`visibility_waits_and_lag.csv`、`manifest.json` |
| 第 6 步 → `outputs/sealed_consistent_visibility/` | `run.sealed_consistent_visibility_tables` | 十一张固定 CSV：`exact_cells`、`exact_comparison`、`exact_passes`、`same_copy_exposure_cells`、`same_copy_exposure`、`attribution_cells`、`attribution_comparison`、`exact_delta_manifest`、`exact_costs`、`exact_sensitivity_cells`、`exact_sensitivity_comparison`，外加 `manifest.json`；数据依赖的 `deltas/*.npz` 只由 `exact_delta_manifest.csv` 逐个记录路径、字节数和 sha256，不进固定名单 |
| 第 7 步 → `outputs/sealed_online_visibility/` | `run.sealed_online_visibility_tables` | 六张固定 CSV：`online_cells`、`online_comparison`、`online_passes`（每个 policy-cell 的暂停数、内核与重打分耗时）、`online_audit`、`online_delta_manifest`、`online_costs`，外加 `manifest.json`；`deltas/*.npz` 由 delta manifest 记录，不进固定名单 |
| 第 9 步 → `outputs/sealed_tables/k1/` | `run.sealed_k1_tables` | 同上八个文件名，写在子目录里 |
| 第 10 步 → `outputs/sealed_predictor/` | `run.sealed_predictor_tables` | `predictor_metrics.csv`、`manifest.json` |

「一个不多一个不少」不是口头约定：`--pool sealed` 的运行在写完之后自己比对写出的固定文件名集合与对应的那份清单，对不上就报错退出。六份清单不能并成一份，并了每条命令都会不匹配。开发期的表在 `outputs/dev_tables/`、`outputs/dev_visibility/`、`outputs/dev_consistent_visibility/`、`outputs/dev_online_visibility/`、`outputs/dev_predictor/`，两边不覆盖。

报告口径：封存学期上实际达到的利用率如实报告，**不回头调 k 去凑目标值**。`main_cells.csv` 与 `main_table.csv` 里 `rho_target` 旁边多一列 `rho_realised`：前者是这一格按哪一档负载建的、论文印的那个数，后者是这条叠加在这个 k 上忙时真正跑到的利用率（忙时工作量 ÷ 3600k）。两者的差来自 k 取整，只有后者说得清一个数字是在多满的系统上测出来的。承诺 G 与选好的 (B0, η) 是冻结的，不因为封存学期上的结果重选。

拷贝数与 k 是另一回事：第 2 步的拷贝数探针在封存池上重跑，k 由 `server_count_rule` 逐条叠加算出——冻结的是规则，不是它在新数据上算出的数。探针停在多少份只印在屏幕上和台账那一行里，写论文时这个数要说清楚是从封存池的忙时工作量推出来的。k = 1 那条轨迹例外，拷贝数沿用开发池的 321 份（ADR 0006）。

封存那几条命令都不带 `--selection`，所以 `read_selection` 退回默认路径（本仓库的选参结果在 `outputs/selection_v4/`，默认路径没有这个文件），`selection` 为空，参数全部来自冻结的配置——这是要的效果。连带的后果是开头那行 `selection mismatch` 检查在封存运行里不会响，**别把它当成封存运行的保护**：它保护的是第一节第 5 步那次开发期运行。

## 四 要多久、占多少盘

在这台机器上（2 个工作进程，LightGBM 固定 4 线程）实测：

| 步骤 | 时间 | 盘 |
|---|---|---|
| 解析缓存（第 1 步） | 开发期 11 个学期约 5 分钟；封存池三个学期更快 | 开发缓存 `ev.parquet` 约 67 MB，`ev_sealed.parquet` 按学期数按比例，约 15 MB |
| 叠加轨迹（5 条） | 拷贝数探针 6 s + 每条约 3 s，连读缓存带写盘约 2 分钟 | 每条约 790 MB，5 条约 4.0 GB |
| 排序分数 | 开发池六个目标学期、六列约 3.5 分钟；`--repeat` 约 7 分钟。封存池只有 3 个目标学期 | 约 90 MB |
| 主运行 15 格 | 29 条策略、2,000 次成对 bootstrap、2 个工作进程，开发池约 48 分钟 | 表格 < 5 MB；每格临时约 750 MB，跑完即删 |
| 可见性比较（第 5 步） | 15 格、14 条比较策略，加旧历史逐 job 暴露扫描，开发池约 35 分钟 | 五张 CSV + manifest < 20 MB；临时峰值与主运行相近 |
| exact policy-specific 可见性（第 6 步） | 开发池 15 格、2 个工作进程：计算合计 16,690 秒，墙钟 15,593 秒（约 4.3 小时，2026-09-23 实测） | 固定 CSV 很小；90 个 affected-job 压缩 delta 合计 211 MB（开发池） |
| online 重放（第 7 步） | 开发池 15 格 × 五条冻结策略共 75 个 policy-cell，计算合计 33,479 秒，每个 240–728 秒（2026-09-24 实测）；按 2 个工作进程折算约 4.7 小时墙钟（这次分两段续跑，没有连续墙钟） | 六张 CSV + manifest 很小；affected-job 压缩 delta 约 170 MB（开发池）；每个工作进程提交内存约 7.3 GB |
| 单机轨迹（第 8 步） | 开发池上实测 3 分钟（321 份拷贝、320 万个 job） | 约 145 MB |
| 单机那一次（第 9 步） | 一格约 60 s（2 个工作进程） | 表格 < 1 MB |
| 预测器指标（第 10 步） | 开发池 42 行实测约 11 分钟；封存池三个目标学期约一半 | < 1 MB |
| 合计 | 开发池规模下约 11 小时，exact 与 online 两步约占 9 小时；封存池三个学期更少 | 十条命令顺序执行不叠加；单步峰值约 18 GB 提交内存（exact 两个工作进程各约 8.5 GB） |

这些是开发池（17.6 M job／条）上的实测值，封存池规模未知，故这里只给冻结前的量级估计，不用封存数据校准。Guard 原网格与 aging 的选择都在冻结之前完成，不属于封存那一次。

临时文件默认落在系统临时目录（`spjf_main_*` / `spjf_visibility_*`），每格约 750 MB，跑完即删——但只在正常结束时删，崩一次就留一份。建议十条命令里支持 `--scratch` 的命令都指到一个自己清得动的目录；重跑前先核对并清理对应残留。`--workers` 固定用 2。

## 五 中途崩了怎么办

规矩是「看结果之前不能改方法」，不是「文件只能打开一次」。所以技术性重跑允许，条件有三条：

1. **锁没变。** 重跑前核对 `sha256sum protocol_lock.json` 与第二节记下的指纹一致。不一致就不是同一份方法，停下来。
2. **代码与配置没变。** 崩了不要「顺手修一下再跑」。真发现必须改的 bug，那就是新的一份方法：说明情况、重新冻结、在台账里写清楚前一次读过什么。
3. **每一次都记台账。** 崩掉的那一次也有一行：十条命令都在 `finally` 里写台账，输出栏写的是「运行中断于<哪一步>，未产出汇总表」加异常类型，重跑再添一行，旧行不改。只有一种情况要手写——进程被整个杀掉（内存不足、机器断电），那时 Python 没有机会写。那一行照上面的六列格式补上，输出栏写清楚跑到哪一步。

具体怎么重跑：

- **叠加或分数那一步崩了**：原样重跑整条命令，它们是确定性的，产物会被覆盖成同样的内容。
- **解析缓存那一步崩了**：原样重跑。它写的是 `ev_sealed.parquet`，不碰 `ev.parquet`，所以重跑
  不会把开发缓存搭进去。要是发现 `ev.parquet` 的大小或行数变了，立刻停下——那说明跑的是旧版本
  的 `build_cache.py`，它会就地覆盖开发缓存，后面每一个滚动起点都会没有训练行。
- **主运行中途崩了**：原样重跑整条命令。主运行不逐格落盘（选参才逐格落盘），所以会从头再跑一遍 15 格，约 16 分钟——比补格子省事。真要补某几格，用 `--reps` / `--levels` 指定，再把两次的 `main_cells.csv` 合起来，但那样出来的表得自己核对行数。
- **exact 那一步崩了**：锁与代码未变时带 `--resume` 原样重跑；完成的 policy/cell 在代码、配置、overlay、分数、控制缓存与 delta 哈希一致时复用，未完成的一项从头细化。不能看部分结果后改策略、lag、withholding 或 assessment。`deltas/` 以最终 `exact_delta_manifest.csv` 为准；不拼接不同输入的检查点。
- **机器内存不够被杀**（表现是进程直接消失、没有 traceback）：把 `--workers` 降到 2 再重跑。本轮开发期就遇到过一次：另一个重活同时在跑，选参跑到第 3 格时进程被杀，没有任何报错，原样重跑即过。

不允许的做法：看完一部分结果之后改承诺 G、改 (B0, η)、改策略集、改指标、改聚合方式，然后再跑一次。那不是重跑，那是重选。
