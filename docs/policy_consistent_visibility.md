# 策略一致的结果可见性

本说明修正第一次 M2 审计对“排队暴露”的解释。第一次审计的约 80% 不是同一份班次—学期拷贝
因排队而产生的暴露；95.39% 的池外历史也不等于不可用信息。旧表保留，不改数字。本次把拷贝语义、
历史删减、固定滞后和模型重拟分开，并用冻结的原始 M4 权重构造逐策略、逐负载、逐 overlay 的精确
可见性证书。全部实测只使用开发与验证池；没有读取、解析或哈希封存输入。

## 1. 估计对象与拷贝语义

设原始分数实际使用的历史结果集合为 `H_i`。一条结果同时进入 user、exercise 和 pair 聚合时只
计一次。干净的初始排队暴露集合是

```text
V_i(P) = {j in H_i: copy_entry(j) = copy_entry(i),
          replay_arrival(j) + wait_P(j) + service(j) > replay_arrival(i)}.
```

`copy_entry` 表示同一班次—学期、同一 outer round 和同一 shift；不把同 round 中另一独立移位
班次的结果算进来。历史还须通过原特征 sweep 的可见性与同时间事件顺序。非零结果在完成时先于
该时刻的读操作释放；零时长事件不能向同一时刻的读操作泄露。重放阈值在整数微秒时钟上比较。

历史分为三类：

1. **本拷贝的重放提交。** 完成时间由该策略的重放决定；这是 M2 所问的队列反馈。
2. **其他班次或学期的历史。** 每份班次拷贝视为独立部署实例，外部历史是原相对时钟下的外生
   信息。目标实例移位 `s_i` 时，外部记录按 `original_done_j + s_i` 解释，不使用另一实例的
   独立移位 `s_j`。已经发生的早期学期和 pool 外历史因此保留。我们不声称这等于把所有拷贝
   放进共享学生状态、相互改变结果时钟的部署系统。
3. **其他同学期班次的敏感性。** 对也在 pool 中的同学期其他班次，另做整条历史记录删除：既删
   outcome，也删其 arrival counts 和 time-since-arrival；再对本拷贝运行同样的精确细化。
   该敏感性覆盖全部 15 格的 Guard(600)，较早学期历史仍保留。

原审计把 pool 内历史映到同 outer round，却让各班次独立移位。这是可复现的**映射暴露统计**，
不是队列造成的信息泄露率。`outputs/dev_visibility/` 的约 80% 与 `unreplayed = 95.39%` 只
保留这种含义，不能证明必须丢弃跨学期历史或采用一小时滞后。

## 2. 冻结权重的精确细化

每个目标学期按原训练配方确定性重建 M4，断言其原分数与已存 `spjf_e` 逐值相等后冻结权重。
固定种子的 512 个目标行还逐位核对定向重算与原 sweep。静态代码、课务与到达时已知列不变；仅
重算受影响目标的 22 列 M4 历史块。withheld outcome 不撤销已经发生的到达，通常保留 arrival
counts 与 time-since-arrival；只有整条其他班次记录敏感性会改变这些列。

对每个 `(overlay, level, policy)`，从原 `done_j` 释放的分数开始，令 `S_i = empty`：

1. 完整模拟该策略，独立计数所有本拷贝且晚于目标到达才完成的原可见记录。
2. 减去 `S_i` 已 withheld 的记录，得到本轮新增违规。仅重算新增违规目标，用同一冻结模型
   重评分；令 `S_i` 与新增记录取并集。
3. 重新模拟，直到一轮没有新增违规。最终轮断言仍被分数使用的违规数严格为零。

记录一旦对某个目标被 withheld 就永不恢复。每个非终止轮至少增加一条有限的 `(i,j)` 边，故必然
终止，不用人为迭代上限。计数与枚举采用两条独立路径核对；后续轮用向量化已 withheld 边计数加速，
terminal audit 仍对全体 job 重新计数。`exact_passes.csv` 写每轮新增目标、记录、累计集合大小及
simulation/detection/rescore 时间，包括零违规的末轮。

exact 指**最终重放中每条仍使用的本拷贝 outcome 确实已完成**，不是最大可用历史、唯一不动点或
完成事件驱动的在线预测器。单调删减可能保留早先轮次不再必要的 withholding；我们不称它为最小
删减解，也不声称离线构造过程可直接在线部署。Guard 对任意静态排序的逐 job 保证另行核验；
SPJF-E 与 Aging 不附加该保证。

每格只落盘受影响 job 的索引、delta、精确 corrected score 和 withheld count，不写完整 17.6M
行分数副本。corrected score 避免浮点减法再加法的舍入误差。NPZ 的相对路径、大小及 SHA-256
由 `exact_delta_manifest.csv` 钉住。完成的 policy/cell 可按输入、实现和控制缓存哈希恢复，过期
检查点不能静默复用。

## 3. 干净的初始暴露与分数影响

逐格结果为 `outputs/dev_consistent_visibility/same_copy_exposure_cells.csv`，汇总为
`same_copy_exposure.csv`。各策略先在 original 分数下模拟，报告 `|V_i(P)| > 0` 的 job 比例及
deadline-window 比例。记录数与 `|delta score|` 分布只在受影响 job 中计算；分数差仅删除第一轮
违规记录，不叠加后续细化。

rank displacement 在**原模拟的实际 dispatch 前队列**上计算：全部第一轮受影响 job 同时换成
修正分数，对同一队列比较排序名次。同微秒较早 dispatch 的 job 已移除；分数相同按 arrival rank
打破平局；正值表示排得更后。这不是两次模拟的 dispatch 序号差，也不是 Guard eligibility 名次。
Aging 使用 `score + beta * relative_arrival` 的等价静态键。CSV 同时给有符号与绝对位移的
mean、p50、p90、p99、max。
FCFS 行的名次是其实际 dispatch 队列中预测分数的反事实排序；它不会改变 FCFS 本身的服务次序。

<!-- MEASURED_EXPOSURE -->

## 4. 一次只改变一项的归因

全部对照沿用原 Guard(600) 参数。`class_term_local` 只改 namespace；`drop_unreplayed` 只删除
未进入 pool 重放的记录；四条 `same_copy_lag*` 只把本拷贝提交 outcome 的释放时间平移
60、300、900、3600 秒，外生历史与 arrival-known 列不变。滞后不只过滤最近结果，还按新释放时间
重排 retained outcomes，避免 rolling last-120 特征的顺序错误。

这些单项对照均使用冻结原 M4，不重新训练。`combined_frozen` 另把第一次 conservative 的三种
特征限制合起来，仍用原权重；与 committed `conservative` 的差别隔离**模型重拟**这一项。单项
效应不能相加：删减、namespace、顺序与树模型存在交互。`static` 与 committed `conservative`
仍使用其原来训练好的模型，没有替换成冻结原权重的版本。

<!-- MEASURED_ATTRIBUTION -->

## 5. 全部开发单元的精确结果与 headline

测量前钉住全部 5 条 primary overlay × 3 档负载，不按性能挑子集。策略为 SPJF-E、Guard(300)、
Guard(600)、Guard(1200)、Aging(600)。四条主比较分数是 original、exact、committed conservative
及 static。三条 Guard 参数与 Aging beta 均不因开发结果改变。

`exact_cells.csv` 是逐格结果，`exact_comparison.csv` 是五条 overlay 汇总。p99dl 与 gap closed
沿用原聚合，区间仍是原 2,000 次 paired week-block bootstrap；max excess、harm 用原 worst-cell
聚合，firing rate 用原 queue-weighted 定义。分布汇总是五条 overlay 相应统计量的均值，max 取
最大；不是把全部受影响 job 混成一条池化分布。

<!-- MEASURED_EXACT -->

`exact_sensitivity_comparison.csv` 对照保留外生其他班次历史与整条删除该类历史后再精确细化的
Guard(600)。这检验拷贝语义，不是同拷贝排队延迟。

<!-- MEASURED_SENSITIVITY -->

headline 的决定与边界见 ADR 0007 的 2026-09-23 Amendment；旧决定与原表保留为历史。original
是 optimistic reference，conservative/static 是较少历史信息的参照锚，并非数学上的性能上下界。
原 pooled AUROC 0.9360、conservative 0.9116、static 0.8371 属于原预测器比较；exact 分数随策略
与 cell 改变，不能把旧 pooled AUROC 的下降归因于排队，也不能用它替代本次 policy-specific 实验。

## 6. 验证池重选的成本与限制

验证 pool、逐格 harm 约束、最大化 worst-cell gap 的规则在本次工作前已固定。若按 exact 分数
重新选择，每个候选策略需要自己的细化，不能共用最后选中策略的 exact 分数再扫全部参数。

查看新结果前，计时方案按 fixed、capped、hybrid、aging 网格分成 12 层，每层均匀抽取一个候选
与独立均匀抽取一个验证 cell，种子 20260922。fixed 的 42 个点分三层；capped 与 hybrid 按三个
G 分层；11 个 aging 点分三层。`outputs/consistent_selection_final/timing_plan.json` 先写方案；
`timing_cells.csv`、`timing_passes.csv`、`cost_projection.json` 写完整测量与外推。

按层大小加权到全部 15 格，另给 258 个 Guard 展开点降到 243 条不同调度的节省，再按理想两
worker 加速除以二；不计拟合、读盘及 FCFS/SJF reference。因此是乐观时间估计，不是统计置信下界。
计时样本的调度指标不参与选参。

12 个计时点全部完成，终止轮均为零违规。细化本身合计 3,329.65 秒，含读盘与 reference 的计时
循环为 3,427.29 秒；整条命令含冻结模型复现约 58.1 分钟。具体样本如下，cell 写作 overlay/level：

| 层 | 网格权重 | 抽中策略 | cell | 轮数（含零轮） | 细化秒数 |
|---|---:|---|---|---:|---:|
| fixed low | 14 | FIX-B60 | 4/2 | 14 | 300.84 |
| fixed middle | 14 | FIX-B568.726 | 4/1 | 17 | 333.68 |
| fixed high | 14 | FIX-B2919.9 | 3/2 | 15 | 331.96 |
| capped 300 | 54 | B240, eta=.75 | 3/2 | 15 | 353.37 |
| capped 600 | 54 | B30, eta=.9 | 3/2 | 15 | 349.59 |
| capped 1200 | 54 | B120, eta=.25 | 4/1 | 13 | 279.34 |
| hybrid 300 | 18 | B0, gamma=4, eta=.9 | 1/2 | 14 | 321.38 |
| hybrid 600 | 18 | B120, gamma=4, eta=0 | 2/0 | 12 | 207.71 |
| hybrid 1200 | 18 | B30, gamma=4, eta=0 | 4/1 | 15 | 300.57 |
| aging low | 4 | beta=.00003 | 0/1 | 14 | 192.77 |
| aging middle | 4 | beta=.001 | 2/2 | 15 | 227.84 |
| aging high | 3 | beta=.1 | 2/2 | 8 | 130.60 |

乐观的去重双 worker 全网格外推是 **164.26 小时**，超过约 8 小时预算约 20.5 倍；未去重的
串行外推是 348.26 小时。因此没有运行 exact 全网格重选，也没有第二套选中参数。我们实际完成
的是上述预声明成本评估和固定原参数的全部开发比较。读者可以据此比较同一决策规则在不同信息
协议下的结果，不能据此断言 exact 下的最优参数、验证池可行性或更换参数后的开发性能。

计时清单记录四个核心实现文件的 SHA。计时后补充了首轮绝对分数的内存保存（供队列 rank 的精确平局
处理）和“其他班次没有重放 job 则保留”的敏感性边界；这些不改变计时用的违规检测、调度或主
细化语义，后者也未在计时样本中启用。成本外推不包含这两项的独立重测，不视为精确墙钟承诺。

保留的参数如下；frozen-score sensitivity 改变的是信息协议，不是参数选择规则。

| policy | family | B0 base (s) | eta | gamma base (s) | beta |
|---|---|---:|---:|---:|---:|
| Guard(300) | capped | 60 | .5 | 0 | — |
| Guard(600) | capped | 120 | .75 | 0 | — |
| Guard(1200) | hybrid | 0 | 0 | 16 | — |
| Aging(600) | linear aging | — | — | — | .03 |

Guard 点原来按 original 选择，Aging 的 .03 按 conservative 选择。固定参数比较可隔离信息协议
影响，但不等于 exact 下的最优调参结果，不证明 exact 仍满足原验证池选参可行性条件，也不能把
未运行的全网格称为重选。开发结果不回流选择任何候选。
`Aging(600)` 保留原比较标签，600 是原验证协议的目标，不是更换分数后仍成立的逐 job 上界；
它在 exact 下的 max excess 与 harm 必须照实报告。

## 7. 复现、保存旧表与运行成本

测量使用不可变的 `configs/visibility_development_20260922.yaml`；最终决定写回 `configs/main.yaml`，
不回写测量配置。旧产物清单指向字节完全相同的 `configs/main_original_84932d9.yaml`，保留原配置
与产物哈希，不声称旧表在新配置下重跑。

```sh
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python \
  scripts/assess_consistent_selection.py \
  --config configs/visibility_development_20260922.yaml \
  --out-dir outputs/consistent_selection_final --workers 2

env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync python \
  scripts/run_consistent_visibility.py \
  --config configs/visibility_development_20260922.yaml \
  --pool primary --out-dir outputs/dev_consistent_visibility --workers 2 --resume
```

exact runner 最多同时执行两个 cell，每个 worker 内按 policy 顺序细化并复用自己的冻结模型与
缓存。主进程构造控制分数后释放全量上下文；两个持久 worker 各自重建并逐值验证同一模型配方，
不共享可变历史状态。汇总按预先固定的 cell 次序，不按完成先后，以保持浮点聚合顺序。每次只有
一条重计算命令，`--workers 2`、Numba 和 OpenMP 各 4 线程。

<!-- MEASURED_COST_AND_CHECKS -->

`scripts/check_preserved_outputs.py` 对原 75 张 CSV 的 18,627 行与所有原列逐字节核验；
另有 10 张从未重跑或改写的既有校验/smoke CSV、308 行纳入辅助快照检查。
`scripts/check_consistent_visibility.py` 检完整覆盖、单调证书和 sparse delta，并把重放的
original/conservative/static 锚点与旧逐格表核对。新论文衍生表写入独立
`outputs/consistent_paper_tables/`，不覆盖 `outputs/paper_tables/`。命令、封存顺序与磁盘预算见
`GENERATED.md` 和 `docs/sealed_run_procedure.md`；这里只更新 draft，不创建正式 lock。

## 8. 论文可使用的陈述

<!-- PAPER_SENTENCES -->
