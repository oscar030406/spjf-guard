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
