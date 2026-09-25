# 决策记录（ADR）

一条一个文件，`0001-slug.md` 递增。正文可以只有一段：背景是什么、决定了什么、为什么。

只在三条同时成立时写：难以撤销；没有背景的人看代码会问「为什么这样做」；确实有过别的选项。
三条缺一就不写。

| 编号 | 决定 |
|---|---|
| [0001](0001-integer-microsecond-time.md) | 仿真器的时钟与记账用整数微秒 |
| [0002](0002-result-availability-clock-and-jitter.md) | 到达与可见性按结果可用时刻定义，同秒记录用确定性抖动打散 |
| [0003](0003-validation-only-selection-with-harm-constraint.md) | 护栏参数只在验证轨迹上选，且必须满足伤害约束 |
| [0004](0004-sealed-data-path-level-protection.md) | 封存数据的保护放在路径层，由配置锁加显式开关解除 |
| [0005](0005-one-guard-three-budget-shapes.md) | 护栏是一个机制，预算形状是设计自由度；三张同等密度的网格由同一条规则选出胜者 |
| [0006](0006-single-server-copies-reused-on-the-sealed-pool.md) | 单机轨迹的拷贝数在开发池上选定，封存池沿用并如实报告利用率 |
| [0007](0007-policy-consistent-score-visibility.md) | 用班次—学期内的 3600 秒保守可见性作为预测排序的主结果 |
| [0008](0008-online-replay-headline.md) | 预测排序的主结果改为在线重放：到达时只用本次重放已完成的同拷贝结果打分；exact 降为离线证书 |
| [0009](0009-zero-cost-blocks-leave-every-term.md) | 开销为零的块在封存学期同样离开仿真轨迹；第一次冻结作废，重新冻结 |
