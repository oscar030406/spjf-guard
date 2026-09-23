# 留出评估范围审计（冻结前，2026-09-21）

只读审计。没有打开、解析、哈希任何封存数据：CodeBench 2023-1 / 2023-2 / 2024-1、ACcoding 编号 80%–100%（id ≥ 3246174）、OULAD 2014 学年。结论全部来自代码、配置、日志、`out_*.txt` 与论文源文件。

封存清单的权威定义在 `src/spjf_guard/data/sealed.py:21`（学期）、`:24`（ACcoding 编号区块）、`:27`（OULAD 学年）。除这三处外，项目没有封存别的东西：`evidence/cross_domain`（Azure、Netbatch）与 `evidence/firefox_ci`（两个 CI 池）在 `sealed.py` 里一个字都没有。

根目录当前只有 `protocol_lock.draft.json`，没有 `protocol_lock.json`，所以按 `sealed.py:81-94` 的门禁，封存运行一次都还没发生。这与 `docs/sealed_access_log.md:12` 的台账结论一致。

---

## 一 论文承诺了什么（Q1）

### 1.1 逐句清单

| # | 位置 | 原句（节选） | 覆盖范围 | 今天是否为真 |
|---|---|---|---|---|
| S1 | `paper/main.tex:109` 摘要 | 无任何 sealed / held-out / frozen 字样 | — | 真（无承诺） |
| S2 | `paper/sections/01_introduction.tex:31` | "The sealed part of **each trace** is opened once, after the method, the parameters and the main metric have been frozen" | 全部六个工作负载 | **假**：只有 CodeBench 有可跑的封存流水线 |
| S3 | `paper/sections/03_problem_model.tex:113` | "We fix this choice before any sealed part of a trace is opened." | 主指标定义 | 真 |
| S4 | `paper/sections/04_prediction.tex:45` | "each target period is predicted by a model fitted only on periods before it, frozen before the target's first arrival" | 可见性协议，非封存承诺 | 真 |
| S5 | `paper/sections/05_scheduling.tex:148` | "a validation trace that excludes the test period; that pool is **held out of the selection and not of the development process**" | 选参 | 真（自限定） |
| S6 | `paper/sections/07_data.tex:163-165` | "Fitting both on the window and then reporting agreement on that same window would be circular, so we refit both on one chronological part of each window and test on the other" | CI 池 | 真，但与 S8 的 "sealed" 不是一回事（见 G6） |
| S7 | `paper/sections/07_data.tex:172` `:179` `:186` | "the **held-out** part comes back at 0.90 to 1.14 times the recorded mean wait"；"The 90th percentile does not survive the **held-out** test" | CI 池 | 真（窗口内时序划分，已开已报） |
| S8 | `paper/sections/07_data.tex:278` §Sealed Data 首句 | "Part of **every trace** was sealed before the method was designed, and is opened once after the method, its parameters and the primary metric are frozen." | 全部六个 | **假**：Azure、Netbatch、两个 CI 池没有封存部分 |
| S9 | `paper/sections/07_data.tex:280-283` | 三个封存部分的定义：CodeBench 三学期；ACcoding 末 20% 编号 809,330 行；OULAD 2014 学年 | 三条轨迹 | 真（定义本身准确） |
| S10 | `paper/sections/07_data.tex:283-285` | "No cost distribution, prediction or scheduling result has been computed on any sealed part, and every access to one is entered in a ledger" | 全部 | 真（台账 `docs/sealed_access_log.md` 佐证） |
| S11 | `paper/sections/08_experiments.tex:66-71` | "**nothing here is held out**… We do not describe any figure in this section as out-of-sample" | §8 全节 | 真（明确自认） |
| S12 | `paper/sections/08_experiments.tex:84-86` | "The sealed terms will be opened once after the protocol freeze and reported in **the same tables** as an additional column, with the parameters unchanged." | CodeBench | **部分假**：单机表 tab:s_k1 与预测器表拿不到封存列（见 G4、G5） |
| S13 | `paper/sections/08_experiments.tex:94` | `% SEALED-RESULTS-PLACEHOLDER` | CodeBench | 真，全文唯一一个占位符（`:96-97` 自述"exactly one of it"） |
| S14 | `paper/sections/09_limitations.tex:95` | "Every CodeBench number in this paper is development data." | CodeBench | 真 |
| S15 | `paper/sections/09_limitations.tex:105-107` | "The **sealed semesters** are opened once, after the method, the parameters and the primary metric have been frozen, and their numbers are reported separately." | CodeBench（措辞已限定为 semesters） | 真 |
| S16 | `paper/supplementary.tex:74-76` | "nothing in this file comes from a sealed part of any trace, and nothing here was recomputed for it" | 补充材料全篇 | 真 |
| S17 | `paper/supplementary.tex:197-211` | S2 节，CI 的 "held-out refit" 的锐度与循环性检查 | CI 池 | 真（同 S6/S7） |
| S18 | `paper/sections/09_limitations.tex:167` 起 Conclusions | 无封存承诺 | — | 真 |

图注：`paper/main.tex:56-57` 定义 `\devnum{}` 为"来自开发数据而非封存学期"的标记，全文 1,605 个数字都包在里面。没有任何图注单独承诺封存版本。

### 1.2 逐工作负载

| 工作负载 | 封存部分有定义吗 | 定义在哪 | 论文承诺在它上面报什么 | 占位符 | 实际可跑 |
|---|---|---|---|---|---|
| CodeBench（主判题轨迹） | 有：2023-1 / 2023-2 / 2024-1 | `07_data.tex:280`；`sealed.py:21`；`configs/main.yaml:43` | 主表加一列（S12），参数不变 | **有**（`08_experiments.tex:94`） | **能**：`docs/sealed_run_procedure.md` 四条命令，约 20 分钟 |
| ACcoding（第二判题平台） | 有：末 20% 编号，809,330 行 | `07_data.tex:281-282`；`sealed.py:24` | 只被 S2 / S8 的全局句覆盖，没有专门承诺 | 无 | **不能**：代码不在包里（`README.md:132`） |
| Serverless（Azure Functions） | **无** | — | 被 S2 / S8 的全局句错误覆盖 | 无 | 不适用 |
| Compute farm（Intel Netbatch） | **无** | — | 同上 | 无 | 不适用 |
| CI pool A（gecko-t-osx-1500-m4） | **无** | — | 同上。§7.3 的 "held-out" 是窗口内划分，已开已报 | 无 | 不适用 |
| CI pool B（gecko-t-linux-talos-2404） | **无** | — | 同上 | 无 | 不适用 |
| OULAD（佐证轨迹） | 有：2014 学年 | `07_data.tex:283`；`sealed.py:27` | 只被全局句覆盖 | 无 | **不能**：代码不在包里（`README.md:132`） |

---

## 二 证据脚本实际用的划分（Q2）

| 目录 | 拟合在 | 报告的数字算在 | 是否排除了封存部分（代码位置） | 盘上有未评估的封存部分吗 | README 的纪律声明 |
|---|---|---|---|---|---|
| `evidence/accoding_v2` | 编号分位 0.00–0.48（id 1–1,951,042），`accoding_v2.py:61` `:131-134`；heavy 阈值 = 训练块 p95 `:695-698`；LightGBM 拟合 `blk==0` `:1008,1046,1051` | devtest 块，分位 0.64–0.80，id [2,598,676, 3,246,173]，647,465 行（`:1010,:1047,:1060-1062`；调度 `:1352-1356`）。验证块 0.48–0.64 只用来选 `num_leaves` `:1018-1037` | **是**，且在任何统计之前切掉：`df.iloc[:sealed_lo]` `:128`、`assert int(df["id"].max()) < sealed_id_min` `:129`、划分不相交断言 `:136-139`、逐阶段 `assert_no_sealed` `:152-153`（调用于 `:171,:704,:900,:1356`） | **有**：`submissions.parquet` 4,046,652 行里最后 809,330 行从未评分（`out_accoding_v2.txt:59-61`） | `README.md:14`「封存块除了行数与首个编号之外从未打开」 |
| `evidence/cross_domain`（Azure + Netbatch） | Azure 到达日 < 8（1,121,378 行）；Netbatch 日 < 18（5,424,503 行）。`cd_build.py:27-28` `:256`；heavy 阈值与 L 只取训练段 `:257,:262` | Azure 日 [10,14) = 456,399 行；Netbatch 日 [22,30) = 2,021,586 行。`cd_predict.py:111-116,:178`；调度 `cd_sim.py:92,:101` | **没有封存部分**。纯粹是轨迹内向前时序划分，而且测试窗就是整条轨迹的尾段（Azure 共 14.000 天 `out_audit_azure.txt:5`，Netbatch 共 30.00 天 `out_audit_netbatch.txt:11`），没有留下未打开的部分 | 无 | `README.md:25` 只说不写目录外、不读教育数据，无封存声明 |
| `evidence/firefox_ci` | 预测器：到达日 < 13（osx）／< 4（talos），`fci_common.py:43-50,:57-60`。`k_eff` 与 `s0` **拟合在整窗的实测等待上**（`fci_simval.py`、`keff_*.csv`） | 测试窗 osx 日 [16,21) = 46,722 次运行；talos 日 [5,7) = 3,892。`out_leaktest_*.txt:5`，`out_sim_*.txt:1-3`。排序分数冻结在验证窗 [13,16) | **没有封存部分**，只有窗口内时序划分。真正的问题是反向的：`k_eff`/`s0` 是在整窗上样本内拟合的，这正是 `firefox_ci_holdout` 要修的循环性 | 无 | `README.md:34`「池、窗口与划分冻结在 `fci_common.py`」，无封存措辞 |
| `evidence/firefox_ci_holdout` | `k_eff`（粗网格 + 步长 1）与 `s0` **只在拟合段重估**：`fch_holdout.py:40,:83,:90`；五个划分 `fch_common.py:73-83`（osx 前半 [0,10.5)、后半 [10.5,21)、fit7-test14 [0,7)；talos 前半 [0,3.5)、后半 [3.5,7)） | 互补的那一段，从整窗仿真里掩出：`fch_holdout.py:103`，`part` ∈ {test, test-burnin（丢前 12 小时，`fch_common.py:84`）, fit}。`holdout.csv` 76 行 | **这是真的留出时序划分，而且已经打开并报告完毕**。它不是封存，也从来不是：它是对手上已有 parquet 的重新分析（`README.md:13`「什么都不重新下载」） | 无。CI 窗口没有任何部分未评估 | `README.md:1-6,:30-39` 目的就是样本外重估；结论已报（均值 14% 以内、p90 落在 0.81–1.21、`k_eff` 155/155/157 of 173 与 96/92 of 105） |
| `evidence/oulad` | 只用 2013 两次开课：`load_forecast_test.py:34` `PRES=("2013B","2013J")`，过滤于 `:58,:73,:100,:106,:113`；`procrastination_test.py:48` 同；单开课脚本 `precheck.py:15`、`precheck_lgbm.py:21`、`relation_feature_test.py:35`、`share_convex_test.py:31` 均为 `2013J`。训练日 14–140，早停 141–160（`:42-43`） | 同一批 2013 开课内的第 161–240 天（`load_forecast_test.py:44`，`out_load.txt:2-5,9,30,51`）；`precheck.py:19` 为 161–200 天 | 2014B/2014J 靠**包含式过滤**排除（`.isin(PRES)` / `== PRES`），不是断言；文档串 `load_forecast_test.py:5-6`、`procrastination_test.py:8-9` 写明它们"在读取时就被丢掉，从不进入任何数组"。2013 内部是按天向前划分，**不是封存留出** | **有**：2014 行与 2013 行在同一批 csv 里，没有任何脚本选中它们 | `README.md:12`「封存的 2014 开课从未打开」；`:14-16` 该方向已被推翻，保留是因为 §7 引用 `out_load.txt` |
| `evidence/codebench_service_v2` | `TRAIN_CORE` 2018-1..2019-2 `service_precheck_v2.py:176`，`+REMOTE` 2020-ERE..2021-2 `:177`；滚动起点：目标 s 的训练集 = 首次到达早于 s 且结果在 s 首次到达前可用的学期，`:1297-1302`，起点 `FORWARD_FROM="2019-1"` `:182` | P1 测试 = `TEST=["2022-2"]` `:179`（用于 `:935,:1096,:1172,:701`）；验证 2022-1 `:178`；前向预测逐目标学期评估 `:1302`；调度在叠加池 `POOL60` `:203` | **是**：`HOLDOUT=["2023-1","2023-2","2024-1"]` `:181`；加载循环里 `assert s not in HOLDOUT` `:287`；参数解析处 `assert not set(DEV) & set(HOLDOUT)` `:3002`。但划分本身是**开发数据内部的滚动向前**，2022-2 是开发测试学期，不是封存学期 | **有**：三个封存学期的 parquet 与归档都在盘上，从未为任何开销／预测／调度数字读过 | 文档串 `:94`；`README.md:71`「封存学期 2023-1、2023-2、2024-1 全程没有打开」 |
| `evidence/predictor_neural` | 固定划分：`train_neural.py:62-65,:199-200`，训练 = `TRAIN_CORE` 或 `TRAIN_CORE+REMOTE`，验证 2022-1；滚动起点变体 `forward.py:72-73,:108-110` | **2022-2**，40,844 行、536 个重任务（`out_evaluate_core.txt:1,:7`；`metrics_2022-2_*.csv`；按用户分块的成对 bootstrap `boot_*.csv`）。前向目标 = 六个池学期（`fwdtab_neural.csv`） | 间接：消费 v2 缓存，`build_base.py:58,:103-104` 断言三个封存学期都不在 `ev.parquet` 里。划分仍是开发内部（固定 2022-2 测试 + 滚动向前） | 有（同样三个 CodeBench 学期） | `README.md:9`「测试学期 2022-2」，无自己的封存声明 |
| `evidence/ranking_score` | 逐目标学期滚动起点：`rs_fit.py:86-87`，顺序取自 `SP.DEV`（`rs_common.py:66-68`），`assert m_tr[core].all()` `:92`。实际拟合链（`fit_targets.csv`）：2020-ERE←2018-1..2019-2；2020-2←..2020-1；2021-1←..2020-2；2021-2←..2021-1；2022-1←..2021-2；2022-2←..2022-1 | 每个目标学期本身（`m_te = sem == s`，`rs_fit.py:88`）；调度在 `primary` 叠加轨迹（含 2022-2，`rs_sim.py:9`）与丢掉开发测试学期的 `validpre` 轨迹（`rs_sim.py:11-12`，过滤 `:65`） | **是**，写在常量注释里：`rs_common.py:40-41` `VALID_SEM = "2022-1"  # every threshold/choice is fixed here and earlier`、`TEST_SEM = "2022-2"  # dev test; 2023-1/2023-2/2024-1 are never read`。封存学期从不进 `SP.DEV`。**代码自己把它标成 dev test**，是开发数据内部的滚动向前 | 有（同样三个 CodeBench 学期） | README 说输入是只读导入的 v2 缓存；封存声明在代码注释里 |

### 2.1 归纳

- **有封存部分、仍然关闭、可以跑**：只有 CodeBench 三学期。
- **有封存部分、仍然关闭、没有流水线**：ACcoding 编号 80%–100%、OULAD 2014。`README.md:132` 已经明确决定这两个不进包，9-24 那次运行不覆盖它们。
- **压根没有封存部分**：Azure、Netbatch、CI pool A、CI pool B。这四条轨迹的每个数字按构造都是开发数字，论文必须这么说，而不是承诺一次留出运行。
- **容易被误读成封存的**：`evidence/firefox_ci_holdout`。它是已经打开、已经报告的窗口内样本外重估，用来修 `firefox_ci` 把 `k_eff` 拟合在自己要验证的等待上的循环性。

---

## 三 差距清单（Q3）

每条给两条路：(a) 改句子，(b) 让那次运行成为可能。推荐一条，判断依据是顶刊审稿人会追问什么，以及三天内能不能安全做完。

### G1　「每条轨迹都封存了一部分」对四条轨迹不成立

- 位置：`01_introduction.tex:31`（"each trace"）、`07_data.tex:278`（"every trace"）。
- 事实：Azure、Netbatch、CI pool A、CI pool B 在 `sealed.py` 里没有任何条目；`cd_build.py:27-28` 与 `fci_common.py:43-50` 显示它们用的是轨迹内向前时序划分，而且测试窗就是整条轨迹的尾段，没有剩下未打开的部分。

**(a) 改句。** `01_introduction.tex:31` 整句替换为：

> All figures quoted above come from development data. On the main judging trace, three terms were sealed before the method was designed and are opened once, after the method, the parameters and the main metric have been frozen; their numbers are reported separately from these. The other workloads have no sealed part, and every figure we give for them is development data.

`07_data.tex:278-285` 整段替换为：

> Three of the traces carry a part that was sealed before the method was designed. On the main trace it is three terms, \devnum{2023-1}, \devnum{2023-2} and \devnum{2024-1}; on the second judging platform it is the last \devnum{20\%} of the submission-id range, \devnum{809{,}330} rows, of which only the row count and the first id have been read; on the corroborating trace it is the \devnum{2014} academic year. Only the main trace's sealed terms are opened in this paper, once, after the method, its parameters and the primary metric were frozen; the frozen pipeline covers those three terms and nothing else, and the sealed parts of the other two traces stay shut and are reported on by neither. The serverless trace, the compute farm and the two continuous-integration pools have no sealed part, so every figure we give for them is development data. No cost distribution, prediction or scheduling result has been computed on any sealed part, and every access to one is entered in a ledger in the repository.

**(b) 让运行成为可能。** 要给这四条轨迹造封存部分，只能重新切划分再重跑 `cross_domain` 与 `firefox_ci` 的全流程。做不到也不该做：这些轨迹的现有数字已经用整条轨迹训练并报告过，事后切一块出来叫"封存"是自欺；而且这两个目录不在包里、不受锁保护，重跑不具备封存纪律。

**推荐 (a)。** 这是三天内唯一诚实的选项，而且改后的句子比原句更强——它明说哪一条是留出、哪几条不是，审稿人不必自己去猜。

### G2　ACcoding 封存块有数据、有护栏，没有流水线

- 位置：承诺来自 G1 的两个全局句；`07_data.tex:281-282` 定义了这个块。
- 事实：块在盘上（`out_accoding_v2.txt:59-61`，809,330 行，起始 id 3246174），`sealed.py:116` 的 `guard_id_block` 与 `sealed.py:141` 的 `record_access` 都写好了并有测试，但 `README.md:132` 写明 ACcoding「暂时留在 prechecks 里，没有进正式包」，9-24 那次不覆盖它。

**(a) 改句。** 由 G1 的 `07_data.tex` 替换段一并解决（"stay shut and are reported on by neither"）。另在 `09_limitations.tex` 的 "Development data, and what is still sealed." 段末加一句：

> The second judging platform's sealed id block and the corroborating trace's sealed year are not opened here: the frozen pipeline covers the main trace alone, and opening them would need a second pipeline under the same lock, which we did not build.

**(b) 让运行成为可能。** 规格如下（不推荐三天内做）：
- 基础脚本：`evidence/accoding_v2/accoding_v2.py`，1,300+ 行单体，要拆成包内模块并接上 `guard_id_block`。
- 留出输入：`submissions.parquet` 的 id ≥ 3246174，809,330 行。
- 拟合在什么上：不重拟。沿用开发块（分位 0.00–0.48）训出的 LightGBM 与 heavy 阈值（`accoding_v2.py:695-698`），只在封存块上前向打分。
- 填哪些数字：`tab:cross` 的 ACcoding 行（`08_experiments.tex:601`）与 `tab:tails` 的两行（`:252-253`）。
- 事先要钉死的：num_leaves（已由验证块选定 `:1018-1037`）、heavy 阈值、假设的固定服务项 0.5 s、到达生成的 λ 与种子、B = 10L 的预算档、报告口径。
- 纪律：`guard_id_block` + `--unseal` + `record_access` 写台账，与 CodeBench 同一套。
- 预计运行时间：预测约 10 分钟，调度仿真按 `out_accoding_v2.txt` 的规模约 30 分钟。
- 彩排：在开发块的 0.64–0.80 段上冒充封存块跑一遍全流程，验证产物集合与断言。
- 工作量：16–24 小时，且要新增受锁保护的代码。

**推荐 (a)。** 三天内做 (b) 会把冻结往后推，而且收益有限：ACcoding 的到达时间是合成的（`08_experiments.tex:612-614` 的脚注 a 已声明），它的调度数字本来就只说明排序机制、不说明那个平台上的等待，在封存块上再跑一次不会加强论文的任何主张。预测侧的 AUROC 倒是真数字，但 §4 的结论（按期望开销排序、误差不对称）靠的是 CodeBench，ACcoding 只是佐证。

### G3　OULAD 2014 同样有数据、有护栏、没有流水线

- 事实：`sealed.py:27` 与 `guard_oulad_year`（`:131`）就位；2014 行与 2013 行在同一批 csv 里，靠 `.isin(("2013B","2013J"))` 这样的包含式过滤排除（`evidence/oulad/load_forecast_test.py:34`）。
- 另一层：这个方向已被推翻（`evidence/oulad/README.md:14-16`，`README.md:136`，原方案存档在 `docs/archive/`）。论文只在 `07_data.tex:231-235` 引用它的负载形状作佐证。

**(a) 改句。** 同 G2，由 G1 的替换段与 `09_limitations.tex` 的补句覆盖。

**(b)** 8 小时左右，把 2014 两次开课接进 `load_forecast_test.py` 的按天划分。

**推荐 (a)。** 在一个已被推翻的方向上开封存数据，换来的是一个论文不依赖的佐证数字。不值得，也会多一条台账记录要解释。

### G4　「在同样的表里加一列」对单机表不成立

- 位置：`08_experiments.tex:84-86`。
- 事实：封存池建不出 k = 1 轨迹。`configs/main.yaml:185` 把 `overlay.single_server.pool` 写死成 `primary`，而 `scripts/build_overlays.py:186` 在 `--single-server` 时用它**覆盖** `--pool`，所以 `--pool sealed --single-server` 建出来的仍然是 primary。此外 `build_overlays.py:100-114` 的 `load_scores` 读的是 `cfg["data"]["score_predictions_file"]` 并要求 `len(frame) == n_rows`，封存池行数不同，分数会被静默丢成空字典。受影响的是补充材料的 `tab:s_k1`（`supplementary.tex:382`）。
- `tab:rank`（`08_experiments.tex:120`）另有两行包外产不出：refit 对照与 GRU 序列状态，`08_experiments.tex:111-112` 已自述。

**(a) 改句。** `08_experiments.tex:84-86` 末句替换为：

> The sealed terms will be opened once after the protocol freeze and reported in the same multi-server tables as an additional column, with the parameters unchanged. The single-server trace is not part of that run, and neither are the two rows of Table~\ref{tab:rank} this package does not produce.

**(b) 让运行成为可能。** 冻结前改两处受锁路径：`configs/main.yaml:184-185` 让 `single_server` 接受池名参数；`scripts/build_overlays.py:186` 改成只在未显式给 `--pool` 时才回落到配置值，并让 `load_scores` 接受 `--score-parquet`。之后封存 k = 1 = 一条 `build_overlays --pool sealed --single-server --unseal` 加一条 `run_main --pool sealed --prefix k1 --reps 0 --levels 0`，约 3 分钟。但 `run.sealed_tables`（`configs/main.yaml:212-220`）与 `check_sealed_tables`（`run_main.py:447-462`）要求封存运行写出的文件名集合**恰好**等于锁里那一份，多写 k1 子目录会直接报错，所以还要给 k1 单独的产物清单。

**推荐 (a)，把 (b) 放 P1。** 理由：k = 1 是恒等式精确成立的那条轨迹，审稿人确实会想看封存版本；但 `09_limitations.tex:109-113` 已经把"形状选在一组多机验证格上、k = 1 上不转移"写成公开的局限，所以缺一个封存 k = 1 不会让任何句子变成假的——只要 S12 改成上面的措辞。(b) 动的是 `configs/main.yaml` 与 `scripts/`，冻结前动这两处要把 0–8 全部闸门重跑一遍（约 1.5 小时），三天内可行但要排在 P0 之后。

### G5　封存运行不产任何预测器指标

- 详见第四节。这是 S2 / S8 的全局句之外最可能被审稿人抓住的一条：论文第三项贡献是预测器比较（`01_introduction.tex:25`），§4 的每个 AUROC 都是开发数字，而全局句让读者以为封存运行会给出留出版本。

**(a) 改句。** 在 `04_prediction.tex` 的预测器families小节前加一句：

> Every predictor figure in this section is a development figure: the frozen pipeline opens the sealed terms for the scheduling tables alone, and no predictor metric is computed on them.

**(b) 让运行成为可能。** 冻结前新增 `scripts/eval_scores.py`，规格见 §4.3。约 6 小时含测试。

**推荐 (b)，回退到 (a)。** 这是四条差距里唯一一条我认为值得动受锁代码的：一个留出 AUROC 直接支撑论文的第三项贡献，成本有界（分数 parquet 已经由封存运行写出，标签与真实 C_cap 都在同一份缓存里，指标本身是三十行 numpy），而且不改变任何已有产物。**这一条要用户拍板**：它把 `scripts/`、`configs/main.yaml`、`tests/` 各动一次，冻结前必须重跑全部闸门。

### G6　"held-out"（CI，窗口内，已开）与 "sealed"（封存，未开）同篇混用

- 位置：`07_data.tex:172,:179,:186`、`supplementary.tex:197,:206-207` 用 "held-out"；`07_data.tex:276` 起的小节用 "sealed"。
- 两者是不同的东西：前者是同一窗口的时序二分，整窗都已读过；后者是冻结前不可读的部分。`CONTEXT.md:83-85` 的术语表也把 `holdout` / `留出集` 列在 `sealed` 的 _Avoid_ 里，正文却在 CI 那一节用了它。

**(a) 改句。** 给 `07_data.tex:276` 的小节加 `\label{sec:sealed}`，并在 `07_data.tex:165` 那句后补一句：

> This split is internal to the recorded window and is held out of the fit only; it is not sealed in the sense of Section~\ref{sec:sealed}, and the whole window has been read.

**(b)** 不适用。

**推荐 (a)。** 一句话，零风险。

### G7　出表与核对脚本不认 `outputs/sealed_tables`

见第五节 Q5-1、Q5-2。属于"论文可审性"问题：封存数字进正文之后，现有的逐值核对闸门覆盖不到它。

---

## 四 CodeBench 的预测器侧（Q4）

### 4.1 封存运行产什么

只产调度表。`configs/main.yaml:212-220` 钉死的八个产物是 `main_cells.csv`、`main_table.csv`、`main_table.tex`、`paired_differences.csv`、`bound_checks.csv`、`identity_residuals.csv`、`policy_parameters.csv`、`manifest.json`，里面没有任何预测器指标。而且 `run_main.py:447-462` 的 `check_sealed_tables` 会把多写或少写一个文件直接判错退出，所以封存运行连"顺手多导一份"都做不到。

全仓搜索 `auroc|roc_auc|calibrat|brier` 在 `src/` 与 `scripts/` 下**零命中**，只在 `evidence/` 下命中（`predictor_neural/evaluate.py`、`codebench_service_v2/service_precheck_v2.py`、`cross_domain/cd_predict.py`、`firefox_ci/fci_predict.py`、`accoding_v2/accoding_v2.py`）。冻结的包里没有任何预测器评估代码。

### 4.2 能不能从封存运行自己的产物里算出留出 AUROC

**不能，需要新代码。**

`fit_scores.py --pool sealed` 写出的 `sealed_scores.parquet` 是 `to_frame(run)`，而 `src/spjf_guard/predict/forward.py:160-161` 是 `return pd.DataFrame(run.scores)`——只有 `spjf_e` 与 `spjf_log` 两列，没有标签、没有真实 `C_cap`、没有连接键，行序靠与 `prepared` 的位置对齐。旁边的 `.log.csv`（`fit_scores.py:119`）逐目标学期记了 `heavy_threshold_s`，但没有逐行标签。

要算 AUROC，缺的是 heavy 标签（= `C_cap` 是否超过训练期 p95，`04_prediction.tex:20` 的唯一定义）与真实 `C_cap`。两者都在封存学期的 `ev.parquet` 里，那是 `build_cache.py --pool sealed --unseal` 建的。再读一次就是一次新的封存读取，必须过 `sealed.guard_semesters` 并记台账，所以不存在"不写新代码就能算出来"的路径。

### 4.3 要加什么代码（冻结前）

新增 `scripts/eval_scores.py`，约 120 行：

- 命令行：`--pool sealed --scores data/derived/package_ranking_scores/sealed_scores.parquet --out-dir outputs/sealed_predictor --unseal`。
- 取数：复用 `fit_scores.run_once` 的前半段（`load_events` + `prepare` + `static_submission_columns`，`fit_scores.py:44-59`）拿 `c_cap`、`semester` 两个数组；heavy 阈值用已有的 `heavy_threshold_and_cuts`（`forward.py:88` 已在调用），参考学期取 `configs/main.yaml:71` 的 `heavy_reference_semesters`，与 §4 的定义同源。
- 算什么：逐目标学期、逐分数（`spjf_e` / `spjf_log`）给 AUROC、AUPRC、`log1p` 尺度 RMSE、Spearman，外加按用户分块的成对 bootstrap 区间（复用 `src/spjf_guard/experiment/bootstrap.py`）。
- 纪律：入口 `sealed.guard_semesters(targets, ROOT, unseal=args.unseal)`，收尾 `sealed.record_run(...)`，与其它四条命令同一套（对照 `fit_scores.py:112` 与 `:121-127`）。
- 产物清单：`configs/main.yaml` 新增 `run.sealed_predictor_tables`（`predictor_metrics.csv`、`manifest.json`），并在脚本里做与 `check_sealed_tables` 同样的集合比对。**不要**并进 `run.sealed_tables`，否则 `run_main.py:457` 的比对会失败。
- 测试：`tests/test_eval_scores.py`，在合成数组上比对指标值，并验证没有冻结锁时被拒；按 `tests/test_sealed_data.py` 的做法，不打开任何数据文件。
- 运行时间：三个封存学期，估计 2 分钟以内（读缓存为主）。
- 彩排：在开发学期上跑同一条命令（`--pool primary`，不带 `--unseal`），与 `evidence/predictor_neural/metrics_2022-2_core.csv` 的 2022-2 行对数，能对上就说明指标实现没错。这一步能在不碰封存数据的前提下证明 runner 可用。

### 4.4 k = 1 轨迹

**不产。** `configs/main.yaml:185` 的 `single_server.pool: primary` 写死，`build_overlays.py:186` 用它覆盖 `--pool`；即使绕过，`load_scores`（`build_overlays.py:100-114`）因 `len(frame) == n_rows` 不成立会把分数丢掉。要做封存 k = 1，这两处都得在冻结前改。见 G4。

### 4.5 恒等残差表

**产。** `run_main.py:574` 是 `residuals=(overlay == first_overlay)`，与池无关；`identity_residuals.csv` 在 `configs/main.yaml:218` 的封存清单里。所以 `tab:resid`（`08_experiments.tex:502`）与 `tab:s_resid`（`supplementary.tex:329`）能拿到封存列，口径是封存池的第 0 条叠加，与开发期的 `08_experiments.tex:495` 「on overlay~0」一致。

### 4.6 排序分数对照

**产。** `run_main.py:379-380` 无条件把 `("SPJF-E", "SPJF-log")` 加进成对差，`fit_scores.py` 两列都写，`run_main.py:561` 在轨迹里见到 log 分数就启用。所以 `tab:rank` 里包内产的那几行能拿到封存列；包外的两行（refit 对照、GRU 序列状态）仍然产不出，`08_experiments.tex:111-112` 已声明。

### 4.7 校准

**不产。** `04_prediction.tex:57` 的 average precision 与 `evidence/ranking_score/calib_*.csv` 那一套可靠性曲线都没有包内实现。若做 4.3 的新脚本，AUPRC 顺带就有了；完整的校准曲线不建议现在加。

---

## 五 冻结前还要决定或建的（Q5）

| # | 事项 | 证据 | 结论 |
|---|---|---|---|
| Q5-1 | `emit_paper_tables.py` 没有封存池入口 | `scripts/emit_paper_tables.py:3` 只有 `--dev-dir` 与 `--k1-dir`；`:41` 的 `NOT_PRODUCED` 把含 `sealed` / `2023-1` / `held out` 的行标成"本包不产" | **要改**。封存数字进正文后，这些行会变成本包产的，分类规则与输入目录都要加封存分支 |
| Q5-2 | `check_paper_numbers.py` 只认开发目录 | `:696-697` 默认 `outputs/dev_tables`；`:419` 与 `:425` 硬读 `dev / "k1"` 子目录 | **要改**。直接对 `outputs/sealed_tables` 跑会因缺 `k1/` 崩掉；不改则封存列进了论文却没有逐值闸门 |
| Q5-3 | `check_generated.py` 要不要认识 `outputs/sealed_tables` | `:58` 用 `outputs/**/manifest.json` 通配，已经自动覆盖 | **产物清单一项不用改**。但 `check_paper_prints`（`:108-111`）只比 `outputs/dev_tables`，要跟着 Q5-2 一起改 |
| Q5-4 | 冻结后 `test_no_frozen_lock_exists_yet` 必然失败 | `docs/sealed_run_procedure.md:80` 已写明"改测试之前先想清楚" | **要先决定改成什么**。建议改成：草稿存在且锁的指纹与台账里记下的一致，而不是直接删 |
| Q5-5 | 学期白名单里少四个学期 | `sealed.py:30-42` 白名单 11 个 + 封存 3 个 = 14；`data/codebench/parquet/events/` 有 18 个学期，2016-1 / 2016-2 / 2017-1 / 2017-2 两边都不在，按 `:69-78` 会抛错 | **确认即可**。这是设计意图（防止多一个学期溜进训练集），但冻结前要确认这四个学期确实不打算用 |
| Q5-6 | 锁尚未生成 | 根目录只有 `protocol_lock.draft.json` | 符合预期，冻结那天由 `scripts/freeze_protocol.py --yes` 生成 |

---

## 六 优先级工作清单

判据：P0 = 不做则论文有不真的句子，或封存数字进了正文却没有闸门覆盖；P1 = 审稿人会追问但不至于让句子变假；P2 = 可以留到下一篇。

| 编号 | 事项 | 工时 | 碰受锁路径？ | 说明 |
|---|---|---|---|---|
| **P0-1** | 改 `01_introduction.tex:31` 与 `07_data.tex:278-285` 的全局封存句（G1 给了整段替换文本） | 2 h | 否（`paper/` 不在锁内） | 这两句今天是假的。改完之后论文对四条无封存轨迹的表述比原来更清楚 |
| **P0-2** | 改 `08_experiments.tex:84-86`，把"同样的表"限定为多机表，并点名单机轨迹与 `tab:rank` 的两行不在封存运行里（G4 给了替换文本） | 0.5 h | 否 | |
| **P0-3** | 新增 `scripts/eval_scores.py` + `configs/main.yaml` 的 `run.sealed_predictor_tables` + `tests/test_eval_scores.py`（规格见 §4.3） | 6 h | **是**：`scripts/`、`configs/main.yaml`、`tests/` | **FLAG-HUMAN**。做了就有留出 AUROC 支撑第三项贡献；不做就要落到 P0-3′。做完必须把冻结前检查 0–8 从头跑一遍（约 1.5 h） |
| **P0-3′** | P0-3 的回退：在 `04_prediction.tex` 加一句"本节每个预测器数字都是开发数字，封存运行只开调度表"（G5 给了文本） | 0.5 h | 否 | 只在用户决定不做 P0-3 时执行。两者必须二选一，否则 G5 的差距留着 |
| **P0-4** | 给 `emit_paper_tables.py` 加封存输入与分类分支；给 `check_paper_numbers.py` 加封存目录参数并让 `k1/` 可缺席；`check_generated.py` 的 `check_paper_prints` 跟着改 | 4 h | **是**：`scripts/` | 不做则封存列进了论文却没有逐值闸门，等于把全文唯一的留出结果放在核对范围之外 |
| **P1-1** | 封存 k = 1：`configs/main.yaml:184-185` 接受池名、`build_overlays.py:186` 不再无条件覆盖 `--pool`、`load_scores` 接受 `--score-parquet`、给 k1 单独的封存产物清单 | 3 h | **是**：`configs/main.yaml`、`scripts/` | 做了则 `tab:s_k1` 也能加封存列，P0-2 的措辞可以放宽。排在 P0 之后 |
| **P1-2** | 给 `07_data.tex:276` 小节加 `\label{sec:sealed}`，并在 `:165` 后补一句区分 CI 的 "held-out" 与封存（G6 给了文本） | 1 h | 否 | |
| **P1-3** | 决定 `tests/test_sealed_data.py::test_no_frozen_lock_exists_yet` 冻结后改成什么，并把改法写进 `docs/sealed_run_procedure.md` | 0.5 h | **是**：`tests/` | 冻结当天必然撞上，提前定好比现场决定好 |
| **P2-1** | ACcoding 封存块流水线（G2 的 (b) 规格） | 16–24 h | **是**：新增包内模块 | 不建议三天内做。到达时间是合成的，封存块上再跑一次不加强任何主张 |
| **P2-2** | OULAD 2014 流水线（G3 的 (b)） | 8 h | **是** | 不建议。方向已被推翻，论文只引用它的负载形状 |
| **P2-3** | 确认 2016-1 / 2016-2 / 2017-1 / 2017-2 四个学期不进白名单 | 0.5 h | 否（只是确认） | |

P0 合计：做 P0-3 的路线 12.5 h + 闸门重跑 1.5 h；走 P0-3′ 回退的路线 7 h + 闸门重跑 1.5 h。两条都在三天之内。
