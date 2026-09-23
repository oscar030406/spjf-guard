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

逐格结果在 `same_copy_exposure_cells.csv`，下表是 `same_copy_exposure.csv` 的五条 overlay 汇总。
表头即 CSV 列名，只有 `affected_share` 与 `deadline_affected_share` 写成百分数；
数值按论文使用的位数四舍五入，没有重新计算，完整精度在 CSV 里。

| level | policy | affected_share % | deadline_affected_share % | records_mean | records_p99 | abs_delta_score_p99 | abs_rank_displacement_p99 | abs_rank_displacement_max |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | FCFS | 1.08 | 2.04 | 7.03 | 75.2 | 9.782 | 350.8 | 1435 |
| 0 | SPJF-E | 0.89 | 1.81 | 7.34 | 72.6 | 9.561 | 225.2 | 1248 |
| 0 | Guard(300) | 0.91 | 1.84 | 7.29 | 71.2 | 9.677 | 241.2 | 1247 |
| 0 | Guard(600) | 0.90 | 1.82 | 7.30 | 72.2 | 9.578 | 235.0 | 1354 |
| 0 | Guard(1200) | 0.90 | 1.82 | 7.32 | 72.2 | 9.642 | 226.9 | 1247 |
| 0 | Aging(600) | 0.92 | 1.85 | 7.45 | 74.2 | 9.595 | 215.8 | 1459 |
| 1 | FCFS | 2.85 | 4.74 | 7.22 | 109.4 | 10.033 | 709.9 | 5467 |
| 1 | SPJF-E | 1.92 | 3.53 | 8.39 | 99.8 | 10.154 | 299.8 | 1707 |
| 1 | Guard(300) | 2.09 | 3.74 | 8.32 | 106.0 | 10.296 | 594.4 | 3653 |
| 1 | Guard(600) | 1.99 | 3.61 | 8.21 | 98.0 | 10.153 | 391.8 | 2086 |
| 1 | Guard(1200) | 1.96 | 3.60 | 8.25 | 98.0 | 10.285 | 334.2 | 1904 |
| 1 | Aging(600) | 2.24 | 3.90 | 8.16 | 111.6 | 10.001 | 377.0 | 3455 |
| 2 | FCFS | 4.74 | 7.50 | 6.81 | 107.2 | 10.210 | 1051.4 | 8946 |
| 2 | SPJF-E | 2.69 | 4.80 | 8.35 | 110.0 | 10.807 | 324.0 | 2066 |
| 2 | Guard(300) | 3.18 | 5.41 | 8.20 | 114.6 | 10.871 | 1044.8 | 5955 |
| 2 | Guard(600) | 2.92 | 5.04 | 8.07 | 106.4 | 10.814 | 754.6 | 4377 |
| 2 | Guard(1200) | 2.85 | 5.00 | 8.12 | 107.4 | 11.008 | 535.6 | 2364 |
| 2 | Aging(600) | 3.59 | 5.82 | 7.78 | 118.4 | 10.414 | 600.6 | 4021 |

最忙负载下 Guard(600) 有 2.92 % 的 job 至少读到一条本拷贝尚未完成的结果（`affected_share`），deadline 窗口内是 5.04 %（`deadline_affected_share`）；受影响 job 平均读 8.07 条（`records_mean`）。
同一格 FCFS 的 `affected_share` 是 4.74 %，高于任何预测排序，因为它把短 job 压在队里更久；它那一行的名次位移是反事实的，不改变 FCFS 自己的服务次序。
分数影响有限：`abs_delta_score_p99` = 10.814 秒，`abs_delta_score_max` = 40.641 秒；队列名次位移 `abs_rank_displacement_p99` = 754.6，`abs_rank_displacement_max` = 4377。
每行的 `jobs` 列都是 17634760，即一条 overlay 的 job 数。

## 4. 一次只改变一项的归因

全部对照沿用原 Guard(600) 参数。`class_term_local` 只改 namespace；`drop_unreplayed` 只删除
未进入 pool 重放的记录；四条 `same_copy_lag*` 只把本拷贝提交 outcome 的释放时间平移
60、300、900、3600 秒，外生历史与 arrival-known 列不变。滞后不只过滤最近结果，还按新释放时间
重排 retained outcomes，避免 rolling last-120 特征的顺序错误。

这些单项对照均使用冻结原 M4，不重新训练。`combined_frozen` 另把第一次 conservative 的三种
特征限制合起来，仍用原权重；与 committed `conservative` 的差别隔离**模型重拟**这一项。单项
效应不能相加：删减、namespace、顺序与树模型存在交互。`static` 与 committed `conservative`
仍使用其原来训练好的模型，没有替换成冻结原权重的版本。

下表来自 `attribution_comparison.csv`，全部是 Guard(600)、原参数、五条 overlay 汇总；
每格写 `gap_closed` 与它的 `gap_closed_lo`/`gap_closed_hi`。
最后一行的 `exact` 取自 `exact_comparison.csv` 的同一格，放在这里作参照。

| variant | rho=0.5, k=7.8 | rho=0.8, k=5 | rho=1.0, k=4 |
|---|---|---|---|
| original | 0.740 [0.713, 0.760] | 0.837 [0.815, 0.851] | 0.801 [0.764, 0.842] |
| class_term_local | 0.739 [0.714, 0.759] | 0.839 [0.819, 0.852] | 0.807 [0.771, 0.845] |
| other_class_withheld | 0.739 [0.715, 0.758] | 0.837 [0.818, 0.850] | 0.806 [0.770, 0.844] |
| drop_unreplayed | 0.711 [0.680, 0.732] | 0.814 [0.785, 0.829] | 0.770 [0.724, 0.814] |
| same_copy_lag_60 | 0.639 [0.594, 0.674] | 0.679 [0.585, 0.723] | 0.573 [0.473, 0.649] |
| same_copy_lag_300 | 0.643 [0.606, 0.681] | 0.653 [0.587, 0.695] | 0.519 [0.443, 0.603] |
| same_copy_lag_900 | 0.681 [0.642, 0.722] | 0.663 [0.606, 0.706] | 0.502 [0.434, 0.595] |
| same_copy_lag_3600 | 0.680 [0.641, 0.721] | 0.675 [0.629, 0.714] | 0.518 [0.454, 0.611] |
| combined_frozen | 0.677 [0.653, 0.706] | 0.705 [0.660, 0.735] | 0.536 [0.462, 0.631] |
| conservative | 0.640 [0.604, 0.671] | 0.634 [0.560, 0.688] | 0.429 [0.357, 0.533] |
| static | 0.560 [0.519, 0.594] | 0.571 [0.504, 0.638] | 0.349 [0.281, 0.457] |
| exact | 0.724 [0.697, 0.747] | 0.785 [0.748, 0.807] | 0.672 [0.602, 0.743] |

最忙负载这一列从上往下读：只换 namespace 是 0.807，再整条删掉同学期其他班次的记录是 0.806，两者都没有把 original 的 0.801 拉下来。
删掉没有重放 job 的历史降到 0.770。真正移动结果的是固定滞后：60 秒 0.573、300 秒 0.519、900 秒 0.502、3600 秒 0.518。
三项限制合起来、仍用冻结权重是 0.536；committed conservative 重新拟合之后是 0.429，这一步单独隔离出模型重拟的贡献。
精确证书是 0.672，高于任何一档固定滞后：一小时滞后删掉的历史远多于重放真正要求删的。
滞后档之间不单调（900 秒低于 3600 秒），所以这四个点不能读成一条剂量—反应曲线；单项效应也不能相加。

## 5. 全部开发单元的精确结果与 headline

测量前钉住全部 5 条 primary overlay × 3 档负载，不按性能挑子集。策略为 SPJF-E、Guard(300)、
Guard(600)、Guard(1200)、Aging(600)。四条主比较分数是 original、exact、committed conservative
及 static。三条 Guard 参数与 Aging beta 均不因开发结果改变。

`exact_cells.csv` 是逐格结果，`exact_comparison.csv` 是五条 overlay 汇总。p99dl 与 gap closed
沿用原聚合，区间仍是原 2,000 次 paired week-block bootstrap；max excess、harm 用原 worst-cell
聚合，firing rate 用原 queue-weighted 定义。分布汇总是五条 overlay 相应统计量的均值，max 取
最大；不是把全部受影响 job 混成一条池化分布。

下表来自 `exact_comparison.csv`：五条 primary overlay、三档负载、五条策略、四种分数，没有一格缺失。
先看 `gap_closed` 与它的 `gap_closed_lo`/`gap_closed_hi`。

| policy | variant | rho=0.5, k=7.8 | rho=0.8, k=5 | rho=1.0, k=4 |
|---|---|---|---|---|
| SPJF-E | exact | 0.740 [0.711, 0.765] | 0.849 [0.817, 0.867] | 0.848 [0.802, 0.878] |
| SPJF-E | original | 0.754 [0.725, 0.776] | 0.885 [0.862, 0.899] | 0.916 [0.892, 0.930] |
| SPJF-E | conservative | 0.662 [0.629, 0.691] | 0.735 [0.682, 0.766] | 0.670 [0.599, 0.733] |
| SPJF-E | static | 0.565 [0.524, 0.599] | 0.627 [0.578, 0.680] | 0.525 [0.461, 0.604] |
| Guard(300) | exact | 0.677 [0.644, 0.703] | 0.645 [0.574, 0.694] | 0.356 [0.268, 0.474] |
| Guard(300) | original | 0.705 [0.678, 0.724] | 0.738 [0.697, 0.761] | 0.478 [0.387, 0.602] |
| Guard(300) | conservative | 0.576 [0.527, 0.616] | 0.473 [0.391, 0.556] | 0.217 [0.143, 0.326] |
| Guard(300) | static | 0.514 [0.464, 0.555] | 0.387 [0.317, 0.478] | 0.202 [0.136, 0.288] |
| Guard(600) | exact | 0.724 [0.697, 0.747] | 0.785 [0.748, 0.807] | 0.672 [0.602, 0.743] |
| Guard(600) | original | 0.740 [0.713, 0.760] | 0.837 [0.815, 0.851] | 0.801 [0.764, 0.842] |
| Guard(600) | conservative | 0.640 [0.604, 0.671] | 0.634 [0.560, 0.688] | 0.429 [0.357, 0.533] |
| Guard(600) | static | 0.560 [0.519, 0.594] | 0.571 [0.504, 0.638] | 0.349 [0.281, 0.457] |
| Guard(1200) | exact | 0.733 [0.707, 0.755] | 0.789 [0.757, 0.810] | 0.708 [0.656, 0.759] |
| Guard(1200) | original | 0.746 [0.719, 0.768] | 0.844 [0.823, 0.857] | 0.830 [0.801, 0.857] |
| Guard(1200) | conservative | 0.642 [0.610, 0.672] | 0.649 [0.591, 0.690] | 0.516 [0.448, 0.593] |
| Guard(1200) | static | 0.559 [0.518, 0.592] | 0.588 [0.537, 0.647] | 0.443 [0.378, 0.531] |
| Aging(600) | exact | 0.615 [0.542, 0.654] | 0.529 [0.425, 0.622] | 0.256 [0.218, 0.329] |
| Aging(600) | original | 0.613 [0.548, 0.653] | 0.608 [0.505, 0.677] | 0.313 [0.276, 0.404] |
| Aging(600) | conservative | 0.228 [0.180, 0.271] | 0.111 [0.082, 0.161] | 0.051 [0.035, 0.074] |
| Aging(600) | static | 0.128 [0.095, 0.168] | 0.052 [0.035, 0.088] | 0.029 [0.018, 0.038] |

exact 变体的其余列，同一个文件，表头即列名：

| policy | level | p99_dl_s | max_excess_s | harm_s | fired_pct | reduction_pct |
|---|---|---:|---:|---:|---:|---:|
| SPJF-E | 0 | 14.94 | 1237.454 | 248.057 | 0.00 | 45.87 |
| SPJF-E | 1 | 46.42 | 3025.763 | 705.892 | 0.00 | 60.96 |
| SPJF-E | 2 | 78.46 | 5830.092 | 1324.288 | 0.00 | 71.24 |
| Guard(300) | 0 | 16.14 | 200.095 | 116.024 | 2.09 | 41.98 |
| Guard(300) | 1 | 63.84 | 206.011 | 127.906 | 12.96 | 46.35 |
| Guard(300) | 2 | 191.52 | 223.629 | 146.319 | 28.94 | 29.90 |
| Guard(600) | 0 | 15.25 | 498.598 | 248.057 | 0.45 | 44.88 |
| Guard(600) | 1 | 51.90 | 508.984 | 215.642 | 2.64 | 56.35 |
| Guard(600) | 2 | 118.94 | 519.871 | 332.841 | 7.82 | 56.43 |
| Guard(1200) | 0 | 15.07 | 833.467 | 94.537 | 21.78 | 45.43 |
| Guard(1200) | 1 | 51.60 | 1101.439 | 127.828 | 9.44 | 56.64 |
| Guard(1200) | 2 | 110.49 | 1118.731 | 212.556 | 6.37 | 59.51 |
| Aging(600) | 0 | 17.16 | 888.508 | 244.561 | 0.00 | 38.11 |
| Aging(600) | 1 | 74.05 | 1453.994 | 358.088 | 0.00 | 37.97 |
| Aging(600) | 2 | 214.89 | 1837.105 | 454.676 | 0.00 | 21.47 |

headline 读数在最忙负载：Guard(600) exact 的 `gap_closed` = 0.6715344319171953，区间 [0.6024522980795439, 0.742715180786423]，`p99_dl_s` = 118.93693605000044 秒。同一格 original 是 0.8013141740724661，conservative 是 0.42907950876102036，static 是 0.34876069519470415。
无护栏的 SPJF-E 在同一格：exact 0.8478892898214522，conservative 0.670404820033541，original 0.916436739323007。
Guard 的逐 job 边界在 exact 下仍然成立：三条 Guard 在这一格的 `max_excess_s` 是 223.629、519.871、1118.731 秒，各自低于 300、600、1200 秒的承诺。Aging(600) 没有这个保证，exact 下 `max_excess_s` = 1837.105 秒，照实报告。
harm 在 exact 下没有普遍下降：Guard(600) 三档负载的 `harm_s` 是 248.057、215.642、332.841。

`exact_sensitivity_comparison.csv` 对照保留外生其他班次历史与整条删除该类历史后再精确细化的
Guard(600)。这检验拷贝语义，不是同拷贝排队延迟。

下表来自 `exact_sensitivity_comparison.csv`，Guard(600)，全部 15 格。

| level | variant | p99_dl_s | gap_closed [lo, hi] | max_excess_s | harm_s | fired_pct |
|---|---|---:|---|---:|---:|---:|
| 0 | exact | 15.25 | 0.724 [0.697, 0.747] | 498.598 | 248.057 | 0.45 |
| 0 | exact_other_class_withheld | 15.32 | 0.722 [0.694, 0.743] | 500.418 | 153.893 | 0.38 |
| 1 | exact | 51.90 | 0.785 [0.748, 0.807] | 508.984 | 215.642 | 2.64 |
| 1 | exact_other_class_withheld | 52.65 | 0.777 [0.736, 0.798] | 507.739 | 344.166 | 2.60 |
| 2 | exact | 118.94 | 0.672 [0.602, 0.743] | 519.871 | 332.841 | 7.82 |
| 2 | exact_other_class_withheld | 122.69 | 0.655 [0.583, 0.732] | 519.811 | 320.159 | 7.75 |

最忙负载上 `gap_closed` 从 0.6715344319171953 落到 0.6552768465857393，区间从 [0.602, 0.743] 变成 [0.583, 0.732]；`p99_dl_s` 从 118.94 秒到 122.69 秒。
三档负载方向一致，幅度都小于 original 与 exact 之间的差，说明拷贝语义不是主导项。
这条敏感性只删同学期其他已复制班次；更早学期的历史在两种读法里都保留。

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

`exact_costs.csv` 的 `stage` 与 `seconds` 两列，按 stage 求和，行数在第二列：

| stage | 行数 | 合计秒 |
|---|---:|---:|
| frozen_models | 1 | 63.89 |
| score_controls | 1 | 1033.36 |
| worker_frozen_models | 2 | 131.81 |
| cell_baselines | 15 | 253.29 |
| fcfs_decomposition | 15 | 655.47 |
| attribution | 165 | 2375.15 |
| exact_policy | 75 | 20615.30 |
| exact_sensitivity | 15 | 5538.27 |
| parallel_cells_wall | 1 | 15592.54 |
| total_compute | 1 | 16690.42 |

`total_compute` 是单独一行 16690.42 秒，detail 写 `before table writes`；`parallel_cells_wall` 也是单行 15592.54 秒，detail 写 `max_workers=2; worker_model_fits=2; parent model fit built controls and was released before worker launch`。逐 policy 的 `exact_policy` 最短 123.15 秒、最长 405.79 秒。

`exact_passes.csv` 按 `overlay`/`level`/`policy`/`variant` 分组：`variant=exact` 有 75 个单元（5 条策略 × 15 格），轮数 10–18 轮（含末轮零违规那一轮），合计 1033 轮。每个单元末轮的 `terminal_zero` 都是 `True`、`offending_records` 都是 `0`：全部成立。
终态 `cumulative_jobs` 在 145,463 到 681,325 之间，`cumulative_records` 在 1,171,095 到 6,526,252 之间；每格的 job 数是 17,634,760。
`variant=exact_other_class_withheld` 有 15 个单元（Guard(600) × 15 格），轮数 11–17 轮，合计 214 轮，末轮同样全部零违规。
看一格的收敛：Guard(600) 在最忙负载的五条 overlay 分别用 15、15、16、14、14 轮，终态 withheld job 数 570,586、576,095、580,679、566,237、568,459。

`manifest.json` 的 `notes` 记下这次运行的语义：`model_weights` = frozen original M4 rolling-origin LightGBM，`other_class_terms` = exogenous on their original relative clock，`other_class_sensitivity` = same-semester other-class history withheld，`terminal_assertion` = every exact policy/cell ends with zero new violation；`dense_policy_scores_written` = false，稀疏 delta 的完整性由 `exact_delta_manifest.csv` 钉住。
`scripts/check_generated.py` 的 consistent visibility 一项读这份 manifest 与全部 CSV，报 `1 run(s) have complete monotone, terminal-zero certificates`。

`scripts/check_preserved_outputs.py` 对原 75 张 CSV 的 18,627 行与所有原列逐字节核验；
另有 10 张从未重跑或改写的既有校验/smoke CSV、308 行纳入辅助快照检查。
`scripts/check_consistent_visibility.py` 检完整覆盖、单调证书和 sparse delta，并把重放的
original/conservative/static 锚点与旧逐格表核对。新论文衍生表写入独立
`outputs/consistent_paper_tables/`，不覆盖 `outputs/paper_tables/`。命令、封存顺序与磁盘预算见
`GENERATED.md` 和 `docs/sealed_run_procedure.md`；这里只更新 draft，不创建正式 lock。

## 8. 论文可使用的陈述

<!-- PAPER_SENTENCES -->
