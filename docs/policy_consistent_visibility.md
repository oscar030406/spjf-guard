# 策略一致的结果可见性

这份说明处理独立审阅的 M2，并顺带记录 M8、M9 的冻结前改动。所有数字只来自 CodeBench 开发池；
没有打开、解析或哈希任何封存数据。逐 overlay、逐负载、逐策略的原始结果在
`outputs/dev_visibility/`，下面只把五条 primary overlay 聚合成易读的表。

## 原管线实际暴露了什么

原分数先在原日历上按 `done_j <= a_i` 做一次特征，再由叠加文件的 `job_row` 把同一个分数挂到每一
份拷贝。拷贝**没有自己的历史**：它读的是原 job 的全局原日历历史，既不是“只读自己的拷贝”，也
不是按拷贝移位后的完成顺序重算。用户和题目 id 还跨班次—学期共享，所以历史里可以有另一个独立
移位的班次—学期，或 primary 池以外的学期。后者在这次 replay 中根本没有 job。

为了不替旧构造发明一种不存在的语义，审计作了唯一明确的匹配约定：若历史记录也在 primary 池且
会成为非零服务 job，就把它映到目标 job 所在的同一个 outer overlay round；池外学期、被丢弃的
零服务提交和非提交事件另列为 `unreplayed`。同一个 outer round 内各班次—学期仍有自己的独立
shift，这个映射只是可复现的暴露审计，不把旧分数变成策略一致分数。M4 的 `prev_ev_err` 还可能读
非提交事件结果；它没有调度 job，故未混入“提前提交记录数”，而是属于不可重放通道。

下表给出旧 `delta = 0` 分数的 mapped history 暴露。`影响`是至少有一条映射记录到 `a_i` 仍未
完成的 job 比例；`窗口`只看 deadline window；记录均值和 p99 只在受影响 job 内计算。每一个
overlay×负载×策略的计数、分位数和最大值均保存在 `visibility_exposure.csv`。

| 负载档 | replay policy | 影响 | 窗口 | 提前记录均值 | 提前记录 p99 | 有不可重放历史 | mapped∪不可重放 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | FCFS | 80.02% | 77.74% | 701.7 | 3954.6 | 95.39% | 98.29% |
| 0 | SPJF-E | 79.97% | 77.69% | 702.1 | 3954.8 | 95.39% | 98.29% |
| 0 | Guard(300) | 79.97% | 77.70% | 702.0 | 3954.8 | 95.39% | 98.29% |
| 0 | Guard(600) | 79.97% | 77.69% | 702.1 | 3954.8 | 95.39% | 98.29% |
| 0 | Guard(1200) | 79.97% | 77.69% | 702.1 | 3954.8 | 95.39% | 98.29% |
| 1 | FCFS | 80.45% | 78.41% | 698.1 | 3949.8 | 95.39% | 98.34% |
| 1 | SPJF-E | 80.21% | 78.13% | 700.1 | 3952.6 | 95.39% | 98.30% |
| 1 | Guard(300) | 80.26% | 78.18% | 699.7 | 3952.2 | 95.39% | 98.32% |
| 1 | Guard(600) | 80.23% | 78.15% | 699.9 | 3952.2 | 95.39% | 98.31% |
| 1 | Guard(1200) | 80.22% | 78.15% | 700.0 | 3952.2 | 95.39% | 98.31% |
| 2 | FCFS | 80.90% | 79.08% | 694.3 | 3944.0 | 95.39% | 98.39% |
| 2 | SPJF-E | 80.40% | 78.45% | 698.6 | 3950.0 | 95.39% | 98.32% |
| 2 | Guard(300) | 80.51% | 78.59% | 697.6 | 3948.8 | 95.39% | 98.35% |
| 2 | Guard(600) | 80.45% | 78.51% | 698.1 | 3949.8 | 95.39% | 98.33% |
| 2 | Guard(1200) | 80.43% | 78.50% | 698.2 | 3949.8 | 95.39% | 98.33% |

等待分布本身如下。除 `max` 是五条 overlay 中的最大值外，其余是五条 overlay 相应统计量的算术
平均；完整逐格数据在 `visibility_waits_and_lag.csv`。

| 档 | policy | mean | p50 | p90 | p99 | p99.9 | max（秒） |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | FCFS | 0.719 | 0 | 0.032 | 15.187 | 137.918 | 491.725 |
| 0 | SPJF-E | 0.292 | 0 | 0.027 | 6.598 | 40.782 | 1374.795 |
| 0 | Guard(300) | 0.344 | 0 | 0.027 | 6.982 | 51.082 | 630.672 |
| 0 | Guard(600) | 0.309 | 0 | 0.027 | 6.705 | 44.294 | 935.115 |
| 0 | Guard(1200) | 0.305 | 0 | 0.027 | 6.569 | 43.436 | 1182.836 |
| 1 | FCFS | 4.160 | 0 | 0.622 | 84.518 | 561.972 | 1023.820 |
| 1 | SPJF-E | 1.232 | 0 | 0.399 | 29.583 | 99.682 | 3312.793 |
| 1 | Guard(300) | 2.061 | 0 | 0.401 | 35.713 | 403.039 | 1167.359 |
| 1 | Guard(600) | 1.532 | 0 | 0.399 | 31.805 | 190.195 | 1467.375 |
| 1 | Guard(1200) | 1.410 | 0 | 0.399 | 31.081 | 144.511 | 2074.550 |
| 2 | FCFS | 10.270 | 0 | 8.928 | 230.803 | 984.309 | 1544.603 |
| 2 | SPJF-E | 2.294 | 0 | 1.112 | 41.710 | 192.443 | 6286.248 |
| 2 | Guard(300) | 5.552 | 0 | 1.250 | 73.735 | 981.738 | 1694.463 |
| 2 | Guard(600) | 3.830 | 0 | 1.151 | 50.195 | 717.570 | 1994.473 |
| 2 | Guard(1200) | 3.134 | 0 | 1.108 | 48.038 | 398.741 | 2603.170 |

## 冻结的修正

采用 ADR 0007 的保守充分条件，而不把不完整的在线近似称作 exact：

1. `conservative` 用班次—学期独立的 user/exercise namespace，只吸收实际进入 replay 的提交结果，
   并在 `done_j + 3600 <= a_i` 后才释放结果。开发期 `max W_FCFS = 1544.602708` 秒；由
   `W^P <= W^FCFS + G` 和 `G <= 1200` 得 2744.602708 秒，余量 855.397292 秒（31.2%）。
2. 每次运行都逐 policy×cell 输出 `wait` 分布、`W > 3600` 数量和比例。开发期 FCFS 与所有三条
   Guard 均为 0；没有保证的 conservative SPJF-E 在最忙五格共有 336 条（该档约 0.000381%，
   十五格总体约 0.000127%），如实留在表里。旧 SPJF-E 对同一检查有 285 条。
3. `static` 只用代码静态列和提交到达时已知的 assessment、deadline、时钟列；它不读窗口内任何
   outcome history，是下锚而不是主结果。

精确 policy-specific release 没有进入冻结：它要求把静态排序核改成完成事件驱动的特征状态机，并
在每个完成事件后执行冻结的 LightGBM；同时旧跨班次历史没有唯一拷贝语义。仅在一个 overlay 做它也
不能验证旧全局特征，因为未进入该 pool 的 95.39% 历史仍无完成事件。固定滞后并不声称等于在线
重算；它证明的是在 `W <= D` 的 cell 内，保守特征读到的每一个同班次提交结果都已经完成。

## 不重选参数的开发比较

下面沿用 `configs/main.yaml` 已选的三组 Guard 参数。区间是五条 overlay 的 paired week-block
bootstrap；`max exc.`、`harm` 和 `fired` 也是主流水线的原定义。

| 档 | 分数 | policy | p99dl（秒） | gap closed [区间] | max exc. | harm | fired |
|---:|---|---|---:|---|---:|---:|---:|
| 0 | original | Guard(300) | 15.58 | .705 [.678,.724] | 192.5 | 132.1 | 1.35% |
| 0 | conservative | Guard(300) | 17.80 | .576 [.527,.616] | 194.9 | 136.2 | 3.05% |
| 0 | static | Guard(300) | 18.82 | .514 [.464,.555] | 195.5 | 134.6 | 2.82% |
| 0 | original | Guard(600) | 14.97 | .740 [.713,.760] | 492.2 | 237.0 | .17% |
| 0 | conservative | Guard(600) | 16.68 | .640 [.604,.671] | 499.9 | 235.2 | .94% |
| 0 | static | Guard(600) | 17.95 | .560 [.519,.594] | 498.0 | 225.1 | .38% |
| 0 | original | Guard(1200) | 14.84 | .746 [.719,.768] | 907.8 | 94.3 | 22.01% |
| 0 | conservative | Guard(1200) | 16.65 | .642 [.610,.672] | 831.4 | 147.0 | 21.08% |
| 0 | static | Guard(1200) | 17.97 | .559 [.518,.592] | 1067.0 | 95.6 | 19.76% |
| 1 | original | Guard(300) | 55.94 | .738 [.697,.761] | 209.7 | 114.1 | 11.57% |
| 1 | conservative | Guard(300) | 78.46 | .473 [.391,.556] | 221.7 | 151.2 | 12.67% |
| 1 | static | Guard(300) | 85.90 | .387 [.317,.478] | 214.7 | 168.0 | 15.35% |
| 1 | original | Guard(600) | 47.47 | .837 [.815,.851] | 507.8 | 319.6 | 1.31% |
| 1 | conservative | Guard(600) | 64.77 | .634 [.560,.688] | 509.4 | 327.7 | 3.26% |
| 1 | static | Guard(600) | 70.18 | .571 [.504,.638] | 512.9 | 341.6 | 3.89% |
| 1 | original | Guard(1200) | 46.85 | .844 [.823,.857] | 1104.9 | 117.6 | 9.93% |
| 1 | conservative | Guard(1200) | 63.52 | .649 [.591,.690] | 1094.0 | 142.9 | 8.78% |
| 1 | static | Guard(1200) | 68.75 | .588 [.537,.647] | 1095.0 | 153.0 | 8.13% |
| 2 | original | Guard(300) | 163.40 | .478 [.387,.602] | 229.1 | 134.8 | 28.64% |
| 2 | conservative | Guard(300) | 223.31 | .217 [.143,.326] | 230.6 | 142.4 | 28.36% |
| 2 | static | Guard(300) | 226.80 | .202 [.136,.288] | 224.1 | 146.9 | 30.38% |
| 2 | original | Guard(600) | 89.24 | .801 [.764,.842] | 523.7 | 339.9 | 7.15% |
| 2 | conservative | Guard(600) | 174.71 | .429 [.357,.533] | 527.8 | 303.5 | 7.71% |
| 2 | static | Guard(600) | 193.11 | .349 [.281,.457] | 528.1 | 316.1 | 11.18% |
| 2 | original | Guard(1200) | 82.67 | .830 [.801,.857] | 1110.4 | 144.8 | 6.21% |
| 2 | conservative | Guard(1200) | 154.70 | .516 [.448,.593] | 1119.1 | 111.9 | 6.26% |
| 2 | static | Guard(1200) | 171.39 | .443 [.378,.531] | 1124.3 | 342.4 | 6.42% |

保守版和原版不接近，尤其是最忙档。因此 conservative 是 headline，不是稳健性附录；original 只能
叫 optimistic reference。以预先选定的 Guard(600) 为例，保守版在三档仍分别关闭 0.640、0.634、
0.429 的 SJF–FCFS gap，且都高于 static 的 0.560、0.571、0.349，但不能继承原版 0.740、0.837、
0.801 的效应大小。

预测器的 pooled 指标也显示同一梯度：

| score | AUROC [区间] | AP | RMSE log1p | Spearman |
|---|---|---:|---:|---:|
| original | .9360 [.9289,.9424] | .309 | .2486 | .405 |
| conservative | .9116 [.9054,.9173] | .087 | .2785 | .347 |
| static | .8371 [.8249,.8492] | .052 | .3210 | .295 |

按要求，主比较没有重选参数。额外的 conservative 重选探针只跑了验证 overlay 0、最轻负载这一格；
它已经说明排序变化足以移动局部最优：G=300 从 capped `(60,.5)` 到 `(120,.5)`，G=600 从
`(120,.75)` 到 `(600,.5)`，G=1200 从 hybrid `(0,0,16)` 到 `(0,.9,4)`。这不是 15 格
worst-cell 规则的最终重选，不能替换冻结参数；在本机按该格 1748 秒外推，全量约需 7.3 小时。

## 协议与两个小项

- `fit_scores.py` 一次产生 original、conservative、static 的两种目标分数，共六列；`--repeat` 已
  逐位复现。`eval_scores.py` 为三种变体各写逐学期与 pooled 指标。
- `run_visibility.py` 用不变参数写五份钉死的 CSV 和 manifest；封存 dry-run 现在列八阶段，封存
  可见性是独立的第 5 阶段。`protocol_lock.draft.json` 钉住变体、D、headline、aging 网格和四份
  sealed output lists。
- M8 加入外部简单基线 `Aging(600)`，priority 是 `predicted_cost - beta * age`，没有证明保证。
  beta 网格有 11 点，用与 Guard(600) 相同的 validation-only、逐格 harm≤300 秒、worst-cell gap
  规则选择，得到 `beta=.03`。原有开发表的既有行和列逐位不变。
- M9 的 `selection_protocol.json` 写出三张网格的定义、258 个展开点、每个 server count 的 243 条
  去重调度、以及每个 G×family 的候选数和可行数；aging 输出也写完整网格与计数。

`emit_paper_tables.py` 另写 `tab_visibility.tex` 和 `tab_visibility_audit.tex`；封存时带
`--sealed-visibility-dir outputs/sealed_visibility` 写 `_sealed` 版本。数字索引与 location-agnostic
checker 同时把 `visibility_comparison.csv`、`visibility_exposure.csv` 当作合法来源。

## 论文现在可以原样写的句子

> We make the policy-consistent, 3600-s-lag predictor the headline and retain the
> original-clock predictor only as an optimistic reference. The lag was fixed from the
> development cells: the largest FCFS wait was 1544.603 s, so the guard theorem implies a
> worst guarded wait of at most 2744.603 s for G at most 1200 s, leaving an 855.397-s
> margin. No FCFS or guarded development job violated the lag certificate.

> Under the original-clock construction, 79.97--80.90% of jobs, depending on load and
> replay policy, used at least one mapped history record that had not completed when the
> job arrived; 95.39% used at least one history record with no job in the same replay
> pool. These defects affect the deployability and measured benefit of the predictor, not
> the guard guarantee, which holds for arbitrary static rankings.

> With the previously selected Guard(600) parameters unchanged, the conservative score
> closed 0.640 [0.604, 0.671], 0.634 [0.560, 0.688], and 0.429 [0.357, 0.533] of the
> SJF--FCFS deadline-window p99 gap across the three load levels. The corresponding
> original-clock values were 0.740, 0.837, and 0.801, and the no-outcome-history static
> controls were 0.560, 0.571, and 0.349.

> The reduction at the busiest load is material: the original clock overstated the
> deployable benefit. The conservative result nevertheless remains above the static
> control, supporting a narrower claim that within-term completed-outcome history adds
> useful ranking information under the frozen lag certificate.
