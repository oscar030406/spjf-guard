# 共享评测机池上的调度与逐任务保证

这个仓库把 `prechecks/` 的探索脚本重写成一个配置驱动、可复现的包：论文主线开发期结果由它逐任务重放，方法冻结后在封存学期上跑一次。术语表只收本项目特有的概念，论文、代码、配置和表格用同一套词。

## Language

**job**（任务）：
一次提交进入评测系统后要执行的工作单元。论文里对应 submission / invocation / run。
_Avoid_: submission, task, request, 作业（作业指 assessment）

**server**（评测机）：
执行 job 的一台机器。部署里叫 executor、judge host、worker。
_Avoid_: executor, judge host, worker, machine, 节点

**rank**（次序）：
由 (arrival, input index) 诱导的全序。`j < i` 表示 j 的次序更小。FCFS 永远派工次序最小的等待 job。
_Avoid_: index, order, 优先级, 到达顺序

**work-conserving**（不空转）：
有 job 在等时没有任何 server 空闲。两条定理去不掉的唯一假设。
_Avoid_: non-idling, 忙碌, 满负荷

**dispatch epoch**（派工时刻）：
某台 server 空闲且队列非空的瞬间；策略在此选出一个等待 job。同一时刻的事件按完成、到达、派工处理。
_Avoid_: decision point, scheduling instant

**C_cap**（执行工作量）：
`min(C, L)`，一次评测实际执行的墙钟秒数；到时限被停的 job 恰好贡献 L。仿真、记账、护栏充值用的都是它。
_Avoid_: exec_time, service time（英文正文可用 service time）, cost（cost 指预测量）

**L**（时限）：
单个 job 的执行上限，CodeBench 上观测到 60 秒。保证的量纲以 L 为单位。
_Avoid_: timeout, cap, 超时

**excess**（多等）：
`W_P[i] - W_FCFS[i]`，同一输入、同一 k 下相对先来先服务多等的秒数。
_Avoid_: delay, slowdown, 延迟

**harm**（伤害）：
在 FCFS 下 1 秒内就能开跑的那些 job 里最大的 excess。保证 G 不约束它的分布，运营者感觉到的就是它。
_Avoid_: unfairness, 最大伤害, victim delay

**heavy job**（重任务）：
真实 C_cap 超过训练期固定阈值（训练学期 95 分位）的 job。被预测成轻任务的重任务照样算。
_Avoid_: long job, outlier, 长尾任务

**gap closed**（缺口收回比例）：
`(W_FCFS - W_P) / (W_FCFS - W_SJF)`，以主指标计。不是等待缩短的百分比，两个绝对值必须并列印出。
_Avoid_: improvement, gain, 提升幅度

**deadline window**（截止窗口）：
每个 assessment 截止前 24 小时。job 属于窗口当且仅当它的到达落在窗口内；窗口内到达、窗口后完成的照样计入。
_Avoid_: peak, rush window, 高峰期

**over[q]**（已充值的插队工作量）：
次序在 q 之后、且已经完成的 job 的真实 C_cap 之和。只在完成事件上充值，这是护栏可部署的原因。
_Avoid_: overtaken work, 插队量（正文可用）

**budget**（预算）：
`min(B0 + eta k (t - a_q), Bmax)`，q 能容忍的 over 上限。`Bmax = k(G - (3 - 2/k)L)` 由承诺 G 反解，不用数据。
_Avoid_: threshold, quota, 额度

**guard**（护栏）：
包在任意底层调度器外的包装器：触发集合非空时派工其中次序最小的 job，否则听底层的。
_Avoid_: wrapper（英文正文可用）, limiter, 保护机制

**SPJF-E**：
按 Tweedie(p=1.5) 拟合的期望开销 `E[C_cap | x]` 排序的底层策略，不带护栏。
_Avoid_: SPJF, predicted-SJF, 按预测排序

**SPJF-log**：
同一套特征、同一协议，拟合在 `log1p(C_cap)` 上再反变换的对照。
_Avoid_: M4, 对数点预测

**Guard(G) / Fixed(G) / Skip(G)**：
同一承诺 G 下的三种护栏：带上限的相对预算、固定预算（eta=0, B0=Bmax）、按派工计数的位置计数护栏（`N = floor(Gk/L - (2k-2))`）。
_Avoid_: CAP / FIX / SKIP（`prechecks/` 的旧标签，新代码不用）

**overlay**（叠加轨迹）：
把多个班次—学期按各自真实的星期几与钟点对齐、整周平移后叠加成的一条轨迹。五次叠加是同一批数据的不同构造，不是五个独立平台。
_Avoid_: replica, trace（trace 指仿真器的输入对象）, 副本

**online / exact / original**（分数可见性协议）：
一个 job 的分数允许用哪些历史结果。online：调度器只跑一次，job 到达那一刻，用这次重放里已经完成的
同班次—学期拷贝结果重算历史、冻结模型打分（主结果，ADR 0008）。exact：离线单调扣留，反复重放直到
没有分数用到未完成的结果，是一个保守解（ADR 0007）。original：原平台的记录时钟，乐观参照。
conservative 与 static 是另外两条更严的参照。
_Avoid_: 用「exact」指 online；把 original 叫「无泄露」

**sealed**（封存）：
冻结前不可读的部分：CodeBench 2023-1 / 2023-2 / 2024-1、ACcoding 编号 80%–100%、OULAD 2014。路径级拒绝，见 `src/spjf_guard/data/sealed.py`。
_Avoid_: holdout, test set, 留出集

**`\devnum{}` / `\sealednum{}`**（数字标注宏）：
论文里每个数字外面的那一层。`\devnum` 说这个数来自开发数据，`\sealednum` 说它来自封存运行，
两者互斥。出表脚本按这个分，逐值核对脚本也按这个找数，所以一个封存数字包进 `\devnum` 不只是
标注错，还会让它被当成开发数字去核对。
_Avoid_: 把封存数字写成 `\devnum`；给同一个数字两层标注

**`rho_target` / `rho_realised`**（目标利用率 / 实际利用率）：
`rho_target` 是这一格按哪一档负载建的，也是论文印的那个数；`rho_realised` 是这条叠加在这个 k 上
忙时真正跑到的利用率（忙时工作量 ÷ 3600k）。两者的差来自 k 取整。封存学期上实际达到多少如实报告，
不回头调 k 去凑目标值，所以两列都要在表里。
_Avoid_: 把 `rho_realised` 当成目标值去比较；用「利用率」一个词同时指这两件事

**protocol lock**（配置锁）：
`protocol_lock.json`。冻结方法的那一份哈希：代码、配置、输入产物，加上学期划分、可见性协议、预测器与种子、排序分数、护栏家族与选择规则、k 与加压方式、主指标、bootstrap 设置。`protocol_lock.draft.json` 是草稿，不解封任何东西。
_Avoid_: manifest, freeze file, 快照

**生成物清单**（manifest）：
`outputs/**/manifest.json`。某一次运行在它产出的表旁边写下的东西：产它的脚本、配置与输入的 sha256、每个产物的 sha256。`scripts/check_generated.py --only outputs` 用它判断有没有人手改过表、配置是不是在出表之后又动过。它不判断数字对不对。
_Avoid_: 元数据, metadata, 配置锁（配置锁是冻结方法，清单是记录一次运行）

**封存彩排**（dry run）：
`scripts/run_main.py --dry-run-sealed`。把封存那一次要读的文件、要跑的策略、锁的状态全部打印出来，一个文件都不打开。
_Avoid_: 模拟运行, 试运行, preview

**逐 cell 落盘**：
选参与主运行每测完一个（叠加，负载档）就把这一格的结果写成一个文件，崩了原样重跑会跳过已经有文件的格。
_Avoid_: 断点续传, checkpoint, 缓存
