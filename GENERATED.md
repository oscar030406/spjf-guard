# 生成物地图

每一个由脚本或模型从别的文件产生的文件，在这里有一行：来源 → 产物 → 重生成命令 → 检查命令。手改产物会让检查失败。`scripts/check_generated.py` 跑全部检查行；pre-commit 会调它。

所有命令都假定在仓库根目录，并且前缀是

```text
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
    NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync
```

下表把这个前缀写成 `UV`。路径不再用环境变量：数据的位置写在 `configs/main.yaml` 的 `data` 段里，相对仓库根目录，由 `Config.data_path` 解析（`cache_dir` = `data/derived/codebench_cache_r4/`，`overlay_dir` = `data/derived/overlay_traces/`，`score_dir` = `data/derived/package_ranking_scores/`，见 README 与 `data/derived/README.md`）。

| 产物 | 来源 | 重生成 | 检查 |
|---|---|---|---|
| `protocol_lock.draft.json` | `configs/main.yaml`、`src/spjf_guard/**/*.py`、`scripts/*.py`、`tests/*.py`、配置里指名的输入产物 | `UV python scripts/make_protocol_lock.py` | `UV python scripts/check_generated.py --only protocol_lock`（重算并与磁盘上的逐字节比较，`written_at` 除外） |
| `outputs/reproduction.csv`、`outputs/reproduction_cells.csv` | 叠加轨迹 + `prechecks/main_v3/v31/table_main_primary.csv` | `UV python scripts/check_reproduction.py --overlay-dir data/derived/overlay_traces` | 该脚本自身即检查：任何一条逐任务等待不等或任何一个汇总数字挪动，退出码非零 |
| `data/codebench/parquet/{assessments,events,logins,codemirror,users}/<学期>.parquet` | `data/codebench/archives/cb_dataset_<学期>_v1.81.tar.gz`（数据发布方的归档） | `UV python scripts/parse_archive.py --semesters 2022-1`（一个学期约 11 秒，流式读，不落临时文件） | `UV python scripts/parse_archive.py --semesters 2022-1 --compare`：重解析一遍与盘上的逐列比对，40 列全等才算过（`tests/test_archive_parse.py`，标 `slow`） |
| `data/derived/overlay_traces/primary_rep{0..4}.npz`、`validation_rep{0..4}.npz` | `data/derived/codebench_cache_r4/ev.parquet` + `configs/main.yaml` 的 `overlay.pools` | `UV python scripts/build_overlays.py --pool primary` | `UV python scripts/check_overlays.py`（与 v3.1 的 `primary_rep*.npz` 逐数组比对到达、服务、周编号、截止窗口标记、job id） |
| `data/derived/overlay_traces/k1_rep0.npz` | 同上 + `configs/main.yaml` 的 `overlay.single_server` | `UV python scripts/build_overlays.py --single-server` | 选出的拷贝数与忙时利用率落在配置的窗口内（脚本自己打印并断言），且份数等于配置钉的 `copies: 321`，不等会打印一行不一致提示；汇总数字与 `prechecks/main_v3/v31/table_main_k1.csv` 的对照见 `outputs/dev_tables/k1/diff_vs_v31.csv` |
| `data/derived/overlay_traces/sealed_k1_rep0.npz`（冻结之后才存在） | 同上，池换成 `sealed` | `UV python scripts/build_overlays.py --pool sealed --single-server --no-scores --unseal` | 印出的份数必须是 321（沿用开发池的选择，ADR 0006），忙时利用率如实报告、不要求落在窗口内。文件名与开发期那条不同，互不覆盖 |
| `data/derived/package_ranking_scores/forward_scores.parquet` | `data/derived/codebench_cache_r4/ev.parquet` + `configs/main.yaml` 的 `predictor` 段 | `UV python scripts/fit_scores.py --repeat` | 同一命令重跑两遍，两列预测逐位相同（LightGBM 已钉 `deterministic`、`force_row_wise`、固定线程数与种子）；脚本自身就跑这个第二遍 |
| `data/derived/codebench_cache_r4/ev.parquet` | `data/codebench/parquet/{events,code_features,assessments}/<学期>.parquet` | `UV python scripts/build_cache.py --pool development` | `UV python scripts/build_cache.py --pool development --compare data/derived/codebench_cache_r4/ev.parquet --report outputs/cache_columns.csv`（逐列比对；58 列全等才算过） |
| `data/derived/codebench_cache_r4/ev_sealed.parquet`（冻结之后才存在） | 三个封存学期的同三张 parquet | `UV python scripts/build_cache.py --pool sealed --unseal` | 与开发缓存一起读时行数等于两份之和、开发那一半逐行不动（`tests/test_data_cache.py::test_the_sealed_cache_is_read_beside_the_development_one_and_moves_no_row`）。**它不是 `ev.parquet` 的新版本**：开发缓存是每个滚动起点的训练那一半，两份始终并存 |
| `outputs/selection_v3/cells/grid_o*_l*.csv`、`selection_grid.csv`、`selection_worst.csv`、`selection_frontier.csv`、`selected_parameters.csv` | 验证叠加轨迹 + `configs/main.yaml` 的 `scheduling.selection.grids` 三张预先写定的网格 | `UV python scripts/select_parameters.py --workers 3`（逐 cell 落盘，可断点续跑；`--from-grid` 只重跑规则不重跑仿真；`--part i --nparts n` 把一个 cell 拆开跑） | `UV python scripts/check_generated.py --only outputs`（比对 `outputs/**/manifest.json` 记的 sha256） |
| `outputs/dev_tables/main_cells.csv`、`main_table.csv`、`main_table.tex`、`paired_differences.csv`、`bound_checks.csv`、`identity_residuals.csv`、`policy_parameters.csv`（以及 `k1/` 下同名的一套） | 五次 primary 叠加 + `configs/main.yaml` + `outputs/selection_v3/selected_parameters.csv` | `UV python scripts/run_main.py --selection outputs/selection_v3/selected_parameters.csv --out-dir outputs/dev_tables --workers 3`；k = 1 那条加 `--prefix k1 --reps 0 --levels 0 --out-dir outputs/dev_tables/k1` | 同上；给了 `--selection` 时运行还会核对规则选出的九个点与配置钉的九个点一致，对不上在开头打印。逐格表里 `rho_target` 是这一格按哪一档负载建的，`rho_realised` 是忙时真正跑到的利用率（忙时工作量 ÷ 3600k），聚合表里后者是五条叠加的均值 |
| `outputs/dev_predictor/predictor_metrics.csv`（封存那一次是 `outputs/sealed_predictor/`） | `data/derived/package_ranking_scores/forward_scores.parquet`（封存那一次是 `sealed_scores.parquet`）+ 解析缓存 + `configs/main.yaml` 的 `features.heavy_reference_semesters` 与 `bootstrap` 段 | `UV python scripts/eval_scores.py --pool primary`；封存那一次是 `--pool sealed --scores …/sealed_scores.parquet --out-dir outputs/sealed_predictor --unseal` | `UV python scripts/check_generated.py --only outputs`（清单里的 sha256）。数值上的对照：2022-2 行的行数、重任务数与 heavy 阈值必须与 `evidence/predictor_neural/out_evaluate_core.txt` 相同（40,844 / 536 / 1.559043 s），spjf_log 的 RMSE 与 Spearman 与该目录 `metrics_2022-2_remote.csv` 的 M4 行相差 < 0.002 |
| `outputs/paper_tables/tab_*_sealed.tex`（冻结之后才存在） | `outputs/sealed_tables/` 的 CSV（加上 `k1/` 与 `outputs/sealed_predictor/`，两者都可缺席） | `UV python scripts/emit_paper_tables.py --sealed-dir outputs/sealed_tables --sealed-predictor-dir outputs/sealed_predictor` | `UV python scripts/check_paper_numbers.py --sealed-dir …`（论文里同标签的表逐值相同；论文还没贴就报「not in the paper yet」并跳过）。表里每个数包在 `\sealednum{}` 里，标签带 `_sealed` 后缀；贴进论文之前 `paper/main.tex`、`paper/main_article.tex`、`paper/supplementary.tex` 三个前言都要加 `\newcommand{\sealednum}[1]{#1}` |
| `outputs/paper_tables/tab_*.tex`、`numbers.csv` | `outputs/dev_tables/` 的 CSV + `paper/` 里所有 `\devnum{}`（只读，包含 `paper/supplementary.tex`） | `UV python scripts/emit_paper_tables.py` | 两道：`UV python scripts/check_generated.py --only paper_numbers`（每个数要么指得出产它的表，要么写明本包为什么不产它）与 `UV python scripts/check_paper_numbers.py`（论文表体与本包表体逐值相同——一张本包的表可以拆在正文与补充材料两张表里，见脚本的 `PAPER_TABLES`；正文与图注里的数字从 `outputs/dev_tables/*.csv` 重算得出；有来源的行仍然印着）。`numbers.csv` 的 key 是「文件:表格或小节:第几个」，不带行号，论文重新排版不会让它失效。四道检查都不认文件位置：表按 label 在所有论文源里找，正文拼法 `tab:x` 与补充材料拼法 `tab:s_x` 都认；正文里重算出来的数字先在它原来那份文件里找，找不到就找补充材料和其余各节，并报告它落在哪。把表、段落、证明整块搬进 `paper/supplementary.tex` 不会让闸门失效，一个数字哪儿都没印才算失败 |
| `outputs/dev_tables/diff_vs_v31.csv` | `outputs/dev_tables/main_table.csv` + `prechecks/main_v3/v31/table_main_primary.csv` | `UV python scripts/diff_dev_tables.py` | 同一命令重跑后逐字节相同；这是报告不是闸门，退出码恒为 0 |
| `outputs/**/manifest.json` | 产出它那一批文件的那次运行 | 由 `run_main.py` / `select_parameters.py` 自己写 | `UV python scripts/check_generated.py --only outputs`：产物被手改、被删，或配置在产表之后改过，都在这里失败。记的路径一律相对仓库根目录 |
| `protocol_lock.json` | `protocol_lock.draft.json` + 当前 commit + 十二个封存输入文件的字节哈希 | `UV python scripts/freeze_protocol.py --yes`（先 `--dry-run`）。工作区脏、没有 commit、任何一个闸门不过，都会被拒 | 冻结本身就是一次性动作；之后 `sha256sum protocol_lock.json` 与记下的指纹比对。脚本在临时克隆 + 假封存目录上测过 |

仓库里任何文件都不许出现只在某台机器上存在的路径：某个用户的主目录、系统临时目录、草稿目录。`UV python scripts/check_generated.py --only paths` 是那道闸门（要找的几个片段写在脚本的 `MACHINE_PATHS` 里），`tests/test_repo_hygiene.py` 连同「闸门自己能不能失败」一起测。

## 不由本仓库生成的输入

以下几样本仓库只读，并在配置锁里记哈希。表里写 `prechecks/` 的那几行，可发布副本在 `evidence/` 下同名位置，路径对照见 `evidence/PATHS.md`。

| 输入 | 内容 | 谁产生的 |
|---|---|---|
| `data/codebench/archives/*.tar.gz` | 数据发布方的每学期归档，整条链路的源头 | CodeBench 数据集发布方，`data/codebench/download_codebench.sh` 下载 |
| `data/derived/codebench_cache_r4/feat_ires0.parquet` | I-res 时钟下的因果特征 | `prechecks/codebench_service_v2/`。本仓库只用它做逐列对照，不再依赖它跑实验 |
| `data/derived/ranking_score_predictions/rs_pred_ires0.parquet` | v3.1 的排序分数前向预测 | `prechecks/ranking_score/rs_fit.py`。同上，现在只作对照 |
| v3.1 的五次叠加轨迹 `primary_rep*.npz` | 不在仓库里，也不在 `evidence/` 里：由 `evidence/main_v3/v31/v31_build.py` 写到仓库外的缓存目录 | 先用该脚本重建，再用 `scripts/check_overlays.py --theirs <缓存目录>` 逐数组比对。这是一次性的交叉核对（结果在 `outputs/overlay_check.csv`），不属于每次提交都跑的检查 |
| `prechecks/main_v3/v31/table_main_primary.csv` | v3.1 报出的汇总表 | 同上，`scripts/check_reproduction.py` 与 `scripts/diff_dev_tables.py` 拿它作对照 |

## 规矩

- 产物不进版本库（`.gitignore` 已排除 `outputs/`、`*.npz`、`*.npy`）。进版本库的只有 `protocol_lock.draft.json` 和冻结后的 `protocol_lock.json`。
- 论文表格的数字只有一个来源：`outputs/` 下的 CSV。`paper/` 里任何数字改动都要能指回某一行。
- 一个结论变了就改原处，不开第二版；被推翻的文件在开头写明被什么推翻。
