# 封存学期读取台账

封存学期：CodeBench 2023-1、2023-2、2024-1；ACcoding 编号 80%–100%；OULAD 2014 学年。每次有脚本读到封存数据，在下面加一行：日期、脚本、读了什么、输出了什么、有没有人看过输出、输出是否影响了设计。要防的是“看了测试结果再改方法”。

| 日期 | 脚本 | 读取内容 | 输出 | 谁看过 | 是否影响设计 |
|---|---|---|---|---|---|
| 2026-09-18 | `prechecks/codebench/parse_codebench.py` | 全部 18 个学期的归档（解析成 parquet） | `out_parse.txt` 逐学期行：事件、提交、测试、登录计数，时间范围，作业窗口内与截止后比例，完全重复行比例，执行时间填充率 | 主线程看过行数（699,668 条事件、477 个作业、751 个用户目录）和跨学期汇总区间 | 否 |
| 2026-09-19 | `prechecks/codebench_audit/counts_reconcile.py` | 三个封存学期的归档（流式） | 逐学期计数：文件数、班级数、学生数候选口径、练习数之和、代码文件数、各去重规则下的块数、重复块计数、作业窗口内计数；封存学期 672 个学生标识中 131 个也在开发学期出现 | 主线程看过计数表 | 否；只用于和官方表对账 |
| 2026-09-19 | `prechecks/codebench_audit/tail_and_counts.py` | parquet 全部学期 | 全体计数（含封存学期的行数合计）；执行时间分布只算开发学期 | 主线程 | 否 |
| 2026-09-19 | `prechecks/accoding_v2/accoding_v2.py` | ACcoding 全表的行数与封存块（编号 80%–100%）的首个编号，用来确定划分边界；封存块在任何统计之前被切掉，每个阶段有断言 | 封存块行数 809,330 与起始编号 3246174 | 主线程读了代理报告 | 否 |
| 2026-09-25 | `prechecks/codebench_service/code_features.py`（经 `local_tools/code_features_to.py` 调用） | 封存学期 2023-1 的归档（流式），每次执行日志的 CODE 段 | `data/codebench/parquet/code_features/2023-1.parquet`：每个提交/测试块的静态代码计数（字符数、行数、关键字与导入计数等 45 列），244,481 行；终端只打印行数与耗时 | 主线程看过行数与耗时，没有看任何特征值或统计 | 否。冻结前补齐 `build_cache` 需要而 09-18 未生成的输入，没有计算开销、预测或调度结果；同一解析器在开发学期 2022-1 上重跑与盘上文件逐列相同 |
| 2026-09-25 | `prechecks/codebench_service/code_features.py`（经 `local_tools/code_features_to.py` 调用） | 封存学期 2023-2 的归档（流式），每次执行日志的 CODE 段 | `data/codebench/parquet/code_features/2023-2.parquet`：每个提交/测试块的静态代码计数（字符数、行数、关键字与导入计数等 45 列），212,559 行；终端只打印行数与耗时 | 主线程看过行数与耗时，没有看任何特征值或统计 | 否。冻结前补齐 `build_cache` 需要而 09-18 未生成的输入，没有计算开销、预测或调度结果；同一解析器在开发学期 2022-1 上重跑与盘上文件逐列相同 |
| 2026-09-25 | `prechecks/codebench_service/code_features.py`（经 `local_tools/code_features_to.py` 调用） | 封存学期 2024-1 的归档（流式），每次执行日志的 CODE 段 | `data/codebench/parquet/code_features/2024-1.parquet`：每个提交/测试块的静态代码计数（字符数、行数、关键字与导入计数等 45 列），242,628 行；终端只打印行数与耗时 | 主线程看过行数与耗时，没有看任何特征值或统计 | 否。冻结前补齐 `build_cache` 需要而 09-18 未生成的输入，没有计算开销、预测或调度结果；同一解析器在开发学期 2022-1 上重跑与盘上文件逐列相同 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/archives/cb_dataset_2023_1_v1.81.tar.gz（271,701,503 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/archives/cb_dataset_2023_2_v1.81.tar.gz（237,054,274 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/archives/cb_dataset_2024_1_v1.81.tar.gz（293,907,257 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/events/2023-1.parquet（3,077,064 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/code_features/2023-1.parquet（1,790,613 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/assessments/2023-1.parquet（11,769 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/events/2023-2.parquet（2,709,769 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/code_features/2023-2.parquet（1,556,504 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/assessments/2023-2.parquet（11,728 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/events/2024-1.parquet（3,087,324 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/code_features/2024-1.parquet（1,824,620 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/assessments/2024-1.parquet（11,941 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/build_cache.py` | 封存学期 2023-1, 2023-2, 2024-1 | 699,668 行事件表写到 data/derived/codebench_cache_r4/ev_sealed.parquet | 运行者 | 否 |
| 2026-09-25 | `scripts/build_overlays.py` | 封存学期 2023-1, 2023-2, 2024-1 | 5 条叠加轨迹写到 data/derived/overlay_traces，每条 31 份拷贝、29 个整周 | 运行者 | 否 |
| 2026-09-25 | `scripts/fit_scores.py` | 封存学期 2023-1, 2023-2, 2024-1 | 1,058,593 行排序分数写到 data/derived/package_ranking_scores/sealed_scores.parquet | 运行者 | 否 |
| 2026-09-25 | `scripts/run_main.py` | 封存学期 2023-1, 2023-2, 2024-1 | 运行中断于逐格仿真，未产出汇总表（ValueError: service times must be positive） | 运行者 | 否 |
| 2026-09-25 | `scripts/run_consistent_visibility.py` | 封存学期 2023-1, 2023-2, 2024-1 | 手动终止于拟合与核对冻结原 M4 模型（第 4 步报错后停下整个封存运行），未开始仿真，未产出任何表；进程被强制结束，Python 没有写行，此行手写 | 运行者 | 否 |
| 2026-09-25 | （方法修订，无脚本） | — | 第一次冻结（1289aa2，锁存档 `docs/archive/protocol_lock_1289aa2.json`）下第 4 步载入叠加轨迹时报 `service times must be positive`：配置的零开销剔除名单只列了开发学期。按补充材料写明的规则（开销恰为 0 的块离开仿真轨迹）把三个封存学期加入名单（ADR 0009），重新冻结后从第 1 步重跑。第一次冻结下产出的只有第 1–3 步的缓存、叠加与分数（重跑覆盖），第 4 步无表，第 6 步未开始仿真 | 主线程只看过报错信息与各步日志的末几行（行数、拷贝数、k） | 否：修订由论文已写明的规则决定，不依赖任何封存结果 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/archives/cb_dataset_2023_1_v1.81.tar.gz（271,701,503 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/archives/cb_dataset_2023_2_v1.81.tar.gz（237,054,274 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/archives/cb_dataset_2024_1_v1.81.tar.gz（293,907,257 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/events/2023-1.parquet（3,077,064 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/code_features/2023-1.parquet（1,790,613 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/assessments/2023-1.parquet（11,769 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/events/2023-2.parquet（2,709,769 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/code_features/2023-2.parquet（1,556,504 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/assessments/2023-2.parquet（11,728 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/events/2024-1.parquet（3,087,324 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/code_features/2024-1.parquet（1,824,620 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/freeze_protocol.py` | 封存学期 2023-1, 2023-2, 2024-1 | 只读取字节求 sha256：data/codebench/parquet/assessments/2024-1.parquet（11,941 字节），未解析内容 | 冻结脚本 | 否 |
| 2026-09-25 | `scripts/build_cache.py` | 封存学期 2023-1, 2023-2, 2024-1 | 699,668 行事件表写到 data/derived/codebench_cache_r4/ev_sealed.parquet | 运行者 | 否 |
| 2026-09-25 | `scripts/build_overlays.py` | 封存学期 2023-1, 2023-2, 2024-1 | 5 条叠加轨迹写到 data/derived/overlay_traces，每条 31 份拷贝、29 个整周 | 运行者 | 否 |
| 2026-09-25 | `scripts/fit_scores.py` | 封存学期 2023-1, 2023-2, 2024-1 | 1,058,593 行排序分数写到 data/derived/package_ranking_scores/sealed_scores.parquet | 运行者 | 否 |
| 2026-09-25 | `scripts/build_overlays.py` | 封存学期 2023-1, 2023-2, 2024-1 | k = 1 叠加轨迹 sealed_k1_rep0.npz 写到 data/derived/overlay_traces，321 份拷贝（321 copies reused from pool primary），实际忙时利用率 2.2614 | 运行者 | 否 |
| 2026-09-25 | `scripts/run_main.py` | 封存学期 2023-1, 2023-2, 2024-1 | 29 个策略—格的汇总写到 outputs/sealed_tables/k1（29 条策略 × 1 档负载 × 1 条叠加） | 运行者 | 否 |
| 2026-09-25 | `scripts/eval_scores.py` | 封存学期 2023-1, 2023-2, 2024-1 | 24 行预测器指标写到 outputs/sealed_predictor/predictor_metrics.csv | 运行者 | 否 |
| 2026-09-25 | `scripts/run_main.py` | 封存学期 2023-1, 2023-2, 2024-1 | 435 个策略—格的汇总写到 outputs/sealed_tables（29 条策略 × 3 档负载 × 5 条叠加） | 运行者 | 否 |
| 2026-09-25 | `scripts/run_visibility.py` | 封存学期 2023-1, 2023-2, 2024-1 | 策略一致可见性比较写到 outputs/sealed_visibility，耗时 1039 秒 | 运行者 | 否 |

上表是全部记录，冻结前后都一样：冻结之前，行里只有计数、字节数与划分边界，没有对任何封存学期或 ACcoding 封存块算过开销分布、预测或调度结果；冻结之后，封存运行每开一次也各占一行，中断的那一次同样有行，输出栏写明停在哪一步。
