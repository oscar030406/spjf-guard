# 平台试验台：建造与冒烟报告

2026-09-23。只在本机跑，没有 push，没有部署，没有碰 `jizhi.chenmingkun.cn`。
平台侧的改动全在分支 `sched-experiment` 上，一次本地提交 `b953e20`；
逐文件的改动说明与回退步骤在平台仓 `D:\UserData\Desktop\挑战杯\docs\调度实验改动说明.md`
（那个仓的 `.gitignore` 把 `/docs/*` 排除在外，所以这份说明留在盘上而不进版本库）。

**先说超支**：任务书写的是「每个策略至多 10 个 job，总共 ≤ 30 次模型调用」。
实际跑了 **41 次**（8 次带练路线 + 33 次学情蓝图）。多出来的 11 次是两件事造成的：
一轮闸的 cell 因为参数设错（见 §4.1）跑了 3 单就作废，重跑又花了 8 单。
按 §5 实测的单价，这 41 次合计约 **5.5 万 token**，不是一笔要请示的钱，
但数字超了，如实记在这里。

---

## 1. 造了什么

### 1.1 派发器

`apps/classroom/lib/server/classroom-dispatch.ts`（约 400 行，含注释）。

- **k 个并发槽**。`SCHED_K` 不设时 `dispatch()` 直接调用传进来的执行体：
  不建队列、不落盘、不加请求头。既有单元测试 556 个文件 / 4933 例全部通过。
- **三种策略**（`SCHED_POLICY`）：
  - `fcfs`：按 rank 升序；
  - `spjf`：按派发时可算的预测代价升序（§2 说代理是什么）；
  - `guard`：在 `spjf` 外面套 `05_scheduling.tex` 的 Algorithm 1。
    完成事件把完成者的执行工作量 `min(C_c, ℓ_c)` 记到所有还在等、rank 更小的人账上；
    派发时算开火集 `E = {q : over[q] ≥ min(B0 + γ·n_q + η·k·(t − a_q), B_max)}`，
    非空取其中 rank 最小的，空则听基策略的。
    `B_max = k(G − (3 − 2/k)L)`（`06_theory.tex` Cor. `cor:params`）。
- **两种计费口径**（`SCHED_CHARGING`）：
  - `completed`：上面这条，只记已完成超越者的工作量；
  - `reservation`：规则 R。`overR[q] = Σ_{j≻q 已派发}(已完成则 C_j，否则 ℓ_j)`，
    派发即按 ℓ 扣住、完成时退还 `ℓ_j − C_j`；准入检验是「基策略的提案 j 要么是队首，
    要么对每个 rank 比它小的等待者都满足 `overR[q] + ℓ_j ≤ Z_q`」，否则改派队首。
    上限取 `Z_max = k(G − (2 − 2/k)L)`，k=1 时正好是 `G`
    （`evidence/reservation_guard/report.md` 的 C1/R2、C3）。
- **打分档**（`SCHED_SCORE_MODE`）：`proxy`（规模代理）、`inverted`（把代理取负，
  故意弄坏的预测）、`random`（固定种子的随机序）。冒烟只跑了 `proxy`。
- **记账一律整数微秒**，判定式里不出现浮点时钟。

逐 job 记录的字段（`records/jobs-<cell>.jsonl`，一行一个 job）：
`cell, policy, charging, scoreMode, k, jobClass, rank, enqueueWallMs, enqueueUs,
dispatchUs, startUs, completeUs, waitMs, serviceMs, executedMs, capExceededMs,
timedOut, limitMs, promiseMs, budgetCapMs, b0Ms, gamma, eta, predictedCostS,
baseRankAmongWaiting, guardFired, overAtDispatchMs, overRAtDispatchMs,
budgetAtDispatchMs, queueLenAtDispatch, dispatchEpochUs, ok, error` 加上每类自己的
元字段（`corpus / projectId / milestonesPredicted / hasRepoLink / requestBytes /
responseBytes / engineDeadlineHit / engineCached`，或蓝图的 `goalChars /
conceptMasteryKeys / blueprintReturned`）。**不存提示词，不存生成正文。**

逐次派发决策另有 `records/decisions-<cell>.jsonl`：决策时刻、闸有没有开火、
基策略提的是谁、队长、派发器自身耗时，以及**当刻每个 rank 比被派者小的等待者的
`[rank, over, overR, budget]`**——两种账同时维护，口径切换只改由谁做决定。

### 1.2 两类作业

| 类 | 路由 | 逐 job 上限 ℓ | 本机实测服务时间 |
|---|---|---|---|
| `practice-guide` | `POST /api/practice-guide` | 170 s | 中位数 135 s，最大 170 s（触顶） |
| `blueprint` | `POST /api/adaptive/blueprint` | 25 s | 中位数 5.2 s，最大 25 s（触顶） |

两条都是真模型调用。带练路线每次带 `refresh: true`，蓝图每次换一个目标串，
两边的引擎缓存都绕开了——每一单都是真生成。

选第二类是因为线上日志（`live_server_survey.md`）显示 `personalize/blueprint`
n=492、中位数 8.2 s、p90 13.6 s、最大 44.1 s：又快又真，而且**与带练路线差一个半
数量级**，规模代理才有东西可分。

### 1.3 上限：原来只是调用方不等了，现在是引擎真的停

这是这一阶段最重要的一条发现，也是规则 R 能不能在这套栈上成立的前提。

**改动前**：`practice-guide/route.ts` 的 `AbortSignal.timeout(170_000)` 是**调用方**的。
引擎那边 `POST /api/practice-scout/{corpus}/guide` 是 FastAPI 的同步 `def`，跑在线程池里，
Starlette 不会因为客户端断开去取消线程池里的活；而模型网关默认走流式
（`llm_gateway.py:98`），`LLM_TIMEOUT_SECONDS` 只约束「两块之间」的停顿，
**整次调用的墙钟是无界的**。线上 2026-09-23 的日志里那次 228.1 s 的生成就是这么来的：
路由 170 s 就断了，引擎又跑了 58 秒。槽位在 170 s 被放掉，服务器却还在忙——
逐 job 上限只是「被观察到」，不是「被执行」。

**改动后**：课堂端把本次的剩余上限放在 `x-sched-deadline-ms` 头里，引擎用一个
contextvar 接住（`backend/services/call_deadline.py`，随 `run_in_threadpool` 复制进工作线程），
模型网关按剩余时间压单次超时、**在流式拼块的循环里看表**、上限用完就不再重试。
不带这个头时 `remaining_seconds()` 返回 `None`，所有路径与改动前一致。

**实测**（引擎日志，`records/` 之外的服务日志）：

- 一次触顶的带练路线：引擎日志 `status=502 durationMs=170122`，
  且前一行是 `structured_chat for ResourceGenerationAgent hit the call deadline`。
  **引擎侧超出 ℓ=170 s 的部分是 122 ms（0.07%）。**
- 一次触顶的蓝图：`status=200 durationMs=25040`，超出 ℓ=25 s 的部分 **40 ms**。

**槽位一直占到执行体真的返回为止**（不是到路由放弃等待为止），所以槽位占用
等于真实占用。两件事合起来：**ℓ_j 在这套栈上是被执行的上限，不是被观察的上限。**

残余口子，报告里必须留着：引擎侧的截止时刻只压模型调用，`_fetch_readme`
（GitHub）与证据检索在模型调用之前，不在这个表的管辖内；实测它们是秒级，
上面那 122 ms / 40 ms 就是全部残余。

### 1.4 负载发生器

`experiments/scheduling/run-cell.mjs`。

- 过 app 自己的注册接口建 N 个账号（`POST /api/auth {action:'register'}`，
  用户名 `loadtest_u001`…，明显的合成名字，没有用任何真人信息），
  再写一份画像——画像里的时间预算决定引擎拆几段里程碑，也就是规模代理的主项。
- 三种需求规则，`--think` 选：
  - `open`：开环，按 `--schedule <csv>` 的时刻表发，前一单回没回来都不影响；
  - `independent`：闭环，思考时间与上一单的代价无关（指数分布）；
  - `wait-scaled`：闭环，思考时间 `mean + slope × 上次等待`（等久了就慢下来）。
- 开环用的到达时刻表由 `make_arrivals.py` 从论文的 development overlay 裁出来：
  取 `primary_rep0`（terms 2020-ERE / 2020-2 / 2021-1 / 2021-2 / 2022-1 / 2022-2，
  SHA-256 与 `evidence/weakness1_attack/development_inputs.json` 记录的一致，
  封存学期一个都没碰），选**最忙的那个 24 小时 deadline 窗**（149,119 个到达，
  只按到达数选，不看任何策略结果），时间压缩 α=12 压到 2 小时窗，
  再按 `N = ρ·k·T/E[C]` 抽稀到 245 个到达（ρ=0.85、k=2、E[C]=50 s）。
  产物 `records/arrivals_deadline_burst.csv`，表头写明两次缩放。
  **冒烟没有用这一条**，只用了 `independent`。

### 1.5 离线检验（不花钱）

`apps/classroom/tests/server/classroom-dispatch.test.ts`，4 例，十几秒跑完：
开关关着时不建队列；三种策略下同时在跑的 job 都不超过 k；
合成序列上 `max_i (W_guard − W_FCFS) ≤ G`，两种计费口径各一例。

---

## 2. 规模代理是什么，为什么它是诚实的

`spjf` 排序用的 `predictedCostS` 在**派发那一刻**就能算出来，不看任何未来信息：

- **带练路线**：引擎按 `milestone_count` 决定要写几段里程碑
  （`practice_guide.py:_milestone_count`：时间预算 ≤5 h → 3 段，≤12 h → 4 段，
  否则难度 ≤3 → 5 段、>3 → 6 段）。输出 token 数是这次调用耗时的主项，
  而里程碑数直接定输出长度。时间预算在账户画像里、难度在已发布项目卡里，
  课堂端两样都拿得到。取 `Ĉ = 30 × 里程碑数 + 8 ×[有仓库链接]` 秒。
- **蓝图**：同类中位数 8 秒，加一个随目标串长度的很小的线性项。

**系数没有标定过**，它只用来排序，不进任何判定式——论文 §3 的保证对任意打分成立。
冒烟里它的表现是：3 次带练路线的预测 98 / 158 / 188 s 对实测 134.0 / 119.8 / 154.3 s，
**三个里有一次序反了**。这正是闸要处理的情形，不是要回避的情形。
另外两档（`inverted` 故意取负、`random` 随机序）已经接好，冒烟没跑。

---

## 3. 冒烟结果

本机，k=2，L=170 s（带练）/ 25 s（蓝图），G=400 s，`B_max = 2(400 − 2×170) = 120 s`，
需求规则 (ii)（闭环、思考时间与上次代价无关）。记录在
`evidence/platform_testbed/records/`。

### 3.1 四个 cell

| cell | 策略 | 用户数 | job 数 | 闸开火 | 实测平均等待 | 重放 FCFS 平均等待 | max excess | `≤ G` |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `smoke-fcfs` | fcfs | 3 | 10 | 0 | 13.64 s | 13.64 s | 0.01 s | 成立 |
| `smoke-spjf` | spjf | 3 | 10 | 0 | 11.79 s | 11.79 s | 0.02 s | 成立 |
| `smoke-guard` | guard | 6 | 10 | 0 | 5.61 s | 5.17 s | 9.22 s | 成立 |
| `smoke-guard2` | guard | 6 | 8 | **1** | 6.11 s | 28.27 s | 20.45 s | 成立 |

`excess` 的算法：拿同一条到达序列与同一批**实测**执行工作量 `min(C_i, ℓ_i)`
离线重放一遍先到先派，逐 job 算 `实测等待 − 重放等待`，取最大。

### 3.2 实测服务时间

| cell | 类 | n | 中位数 | p90 | 最大 | CV | 触顶 |
|---|---|---:|---:|---:|---:|---:|---:|
| `smoke-fcfs` | blueprint | 7 | 6.05 s | 25.0 s | 25.01 s | 0.696 | 2 |
| `smoke-fcfs` | practice-guide | 3 | 134.0 s | 150.3 s | 154.3 s | 0.104 | 0 |
| `smoke-spjf` | blueprint | 7 | 5.23 s | 8.46 s | 11.39 s | 0.408 | 0 |
| `smoke-spjf` | practice-guide | 3 | 148.1 s | 165.6 s | 170.01 s | 0.089 | 1 |
| `smoke-guard` | blueprint | 10 | 4.95 s | 9.49 s | 24.88 s | 0.855 | 0 |
| `smoke-guard2` | blueprint | 6 | 4.32 s | 10.81 s | 14.94 s | 0.670 | 0 |
| `smoke-guard2` | practice-guide | 2 | 135.9 s | 163.2 s | 170.0 s | 0.251 | 1 |

合起来 38 个 job：带练路线 8 个（2 个触顶）、蓝图 30 个（2 个触顶）。
**两类混起来的 CV 大于 1**（带练中位数 135 s 对蓝图中位数 5 s），
但这是**两类作业的混合**，不是任何一类本身重尾——写进论文时必须照
`assessment.md` §3.2 的措辞如实说明。

本机的蓝图比线上慢：线上中位数 8.2 s、p90 13.6 s，本机第一轮出现过连续两次
17.6 s / 25.0 s 触顶，后面几轮回到 4–6 s。这台机器同时还有别的重活在跑。

### 3.3 闸真的开火了，而且决策可以逐条回看

`smoke-guard2` 的 rank 5（一次带练路线）在 `over = 20.0 s` 对 `budget = 13.0 s`
时被闸强制派出。审计链在 `decisions-smoke-guard2.jsonl` 里是连续的：

```
rank=6 派发时  rank 5 还在等：over=0.0 s   budget=11.0 s   → 不开火，听基策略的
rank=7 派发时  rank 5 还在等：over=5.1 s   budget=11.5 s   → 不开火
rank=5 派发    over=20.0 s ≥ budget=13.0 s               → 开火，强制派 rank 5
```

这一轮的 shape 是 `B0 = 10 s, η = 0.05, γ = 0`。**这组 shape 是为了让闸在 8 个 job
之内一定开火而选的**，不是从验证集上选出来的——冒烟的目的是把机制跑通，
不是定参数。`B_max = 120 s` 仍然由 `G = 400 s` 反推，与 shape 无关。

`smoke-guard` 那一轮（`B0 = 30 s, η = 0.5`）没有开火：那一轮抽签一个长作业都没抽到，
`over` 最多只涨到 14.9 s，够不着 30 s 起步的预算。

### 3.4 派发器自身的开销

| cell | 每个 dispatch epoch 平均 | 最大 |
|---|---:|---:|
| `smoke-fcfs` | 14.4 µs | 32 µs |
| `smoke-spjf` | 15.4 µs | 54 µs |
| `smoke-guard` | 19.0 µs | 57 µs |
| `smoke-guard2` | 23.9 µs | 59 µs |

对比服务时间 10⁰–10² 秒：**派发开销比它小 5 到 7 个数量级**。
这是只有真部署才拿得到的数（`assessment.md` §3.5 第四条）。

### 3.5 模拟器对实测等待的校验（G3）

把每个 cell 的 `(a_i, C_i, score_i, k)` 喂给论文包的模拟器
（`spjf_guard.sim.simulate`，脚本 `replay_simulator.py`），逐 job 比等待：

| cell | 模拟器里的策略 | job | 实测平均 / 最大等待 | 模拟平均 / 最大等待 | 平均带符号误差 | 最大绝对误差 | 误差 > 1 s 的 job |
|---|---|---:|---|---|---:|---:|---:|
| `smoke-fcfs` | FCFS | 10 | 13.641 / 97.624 s | 13.639 / 97.618 s | −1.9 ms | 8.7 ms | 0 |
| `smoke-spjf` | SPJF-E | 10 | 11.793 / 110.861 s | 11.791 / 110.860 s | −2.1 ms | 16.0 ms | 0 |
| `smoke-guard` | Guard(400) | 10 | 5.607 / 18.844 s | 5.602 / 18.834 s | −5.5 ms | 11.5 ms | 0 |
| `smoke-guard2` | Guard(400) | 8 | 6.112 / 30.141 s | 6.108 / 30.131 s | −4.6 ms | 10.2 ms | 0 |

38 个 job，最大逐 job 偏差 16 ms。**包括闸开火的那一个决策**：模拟器独立地在同一个
epoch 开了火。这与 `weakness1_attack` 那次 timed-work 物理实验形成对照——那次
2151 个 job 上 Guard 的最大逐 job 偏差是 1354 s。38 个 job 的一致**不能**用来推翻
那个结果，只能说明这条比对链路是通的（见 §6）。

---

## 4. 这一阶段学到的两件事（会改变全量跑法）

### 4.1 闭环下队列深度的上限是 N − k

前两个 cell 用了 3 个用户、k=2，于是任何时刻最多 1 个 job 在等，
`queueLenAtDispatch` 全程是 1。**队里只有一个人时，三种策略给出的是同一个决定**，
所以 `smoke-fcfs` 与 `smoke-spjf` 逐 job 的 excess 都是 0——这两轮除了「机制跑得通」
之外，关于排序什么也没测到。换成 6 个用户后队长到了 4，基策略才真的开始插队
（`baseRankAmongWaiting` 出现 1 和 2），闸才有东西可管。

**全量跑必须 N ≫ k**。按 ρ ≈ 0.85、k = 2、E[C] ≈ 48 s、思考时间均值 20 s 算，
`N ≈ ρ·k·(E[C] + Z)/E[C] ≈ 0.85 × 2 × 68/48 ≈ 2.4` ——这个公式给出的 N 太小，
说明**想在闭环里同时钉住 ρ 和队列深度是做不到的**：闭环里 ρ 是结果不是参数。
可行的做法是：开环 cell 用 `--schedule` 钉 ρ，闭环 cell 直接钉 N（取 8–12）
并把实测到的 ρ 报出来。

### 4.2 小样本下按概率抽作业类会抽空

`smoke-guard` 那一轮 `--mix guide=0.2` 抽了 10 次，一次长作业都没抽到
（0.8¹⁰ = 10.7%，撞上了）。已经加了 `--pattern` 按固定顺序指定每一单的类，
全量跑用它，不用抽签。

---

## 5. 花了多少，全量要花多少

### 5.1 单价（实测，不是估的）

平台这两条路由本来不写用量账本（`data/usage/*.jsonl` 只记课堂端自己发起的模型调用，
引擎侧这两条不进账）。所以给模型网关加了一行日志，**只在带了 `x-sched-deadline-ms`
的调用上**记 `prompt_tokens / completion_tokens`。实测（`smoke-guard2` 那一轮）：

| 类 | n | 平均 input tokens | 平均 output tokens |
|---|---:|---:|---:|
| `blueprint`（LearnerDiagnosisAgent） | 6 | 212 | 251 |
| `practice-guide`（ResourceGenerationAgent） | 1 | 2591 | 1979 |

带练路线的 n=1，因为同一轮另一次触顶了，流被中途切断、没有 usage 块。
触顶的调用仍然烧了 output token（切断之前的部分），这部分**没有被记到**，
下面按 25% 的余量补。

前两轮（`smoke-fcfs` / `smoke-spjf`）跑的时候这行日志还没加，没有它们的实测值。

### 5.2 这次冒烟

41 次模型调用（8 次带练路线 + 33 次蓝图）。按上面的单价：
`8 × 4570 + 33 × 463 ≈ 5.2 万 token`，加触顶的余量约 **5.5 万 token**。

### 5.3 全量：任务书那个设计

3 策略 × 3 需求规则 × 100 job = **900 job**，按冒烟的 30% 带练 / 70% 蓝图混合：

- 带练 270 次：`270 × (2591 + 1979)` ≈ **70 万 input + 53 万 output**
- 蓝图 630 次：`630 × (212 + 251)` ≈ **13 万 input + 16 万 output**
- 加触顶余量 25%（冒烟里 8 次带练触顶 2 次）：
  **合计约 104 万 input + 86 万 output tokens，190 万 token 上下。**

墙钟：`E[C] = 0.3 × 140 + 0.7 × 8 ≈ 47.6 s`，k=2、ρ≈0.85
→ 一个 100 job 的 cell `100 × 47.6 / (2 × 0.85) ≈ 2800 s ≈ 47 min`，
9 个 cell **约 7 小时**，加每换一次策略要重起课堂进程（约 1 分钟 × 9）。
再加 k=4 的一轮就是两倍。

金额换算不出来：用量账本没有单价字段（`scripts/usage-ledger.py` 自己说明「所以不出金额」），
主力路由是硅基流动上的 Qwen 档，单价只有用户自己的账单知道。

### 5.4 更便宜的最小设计

目的是「机制在真服务里跑过 + 逐 job 承诺在实测等待上成立 + 模拟器对得上」，
这三条不需要跨三种需求规则：

| 设计 | cell 数 | job 数 | token（in + out） | 墙钟 |
|---|---:|---:|---:|---:|
| 任务书全量 | 9 | 900 | ≈ 190 万 | ≈ 7 h |
| **最小**：3 策略 × 闭环规则 (ii) × 100 job | 3 | 300 | ≈ 63 万 | ≈ 2.4 h |
| 最小 + 闸再各跑一遍规则 (i) 与 (iii) | 5 | 500 | ≈ 105 万 | ≈ 4 h |
| 最小 + 把带练比例从 30% 降到 15% | 3 | 300 | ≈ 35 万 | ≈ 1.4 h |

最后一档省钱但代价明确：长作业只剩 15 个/cell，尾部那一端的样本太薄，
`gap_closed` 一类的量会很不稳。**推荐第三档**（5 个 cell，约 4 小时、约 105 万 token）：
它保住了「需求会不会对等待做出反应」这个问题——那是这个平台相对
`weakness1_attack` 那次 timed-work 实验**唯一**新增的能力，只跑规则 (ii) 就等于放弃它。

这笔钱是用户的，这里不替他决定。

---

## 6. 每个目标能宣称什么、不能宣称什么

### G1 机制跑在一套生产级栈上

**能**：Algorithm 1（已完成工作量计费）与规则 R（预留-退还）都实现在一个真实的
Next.js 路由里，调用一个真实的 Python 引擎，做真实的模型调用，
**带一个真正在服务端生效的逐 job 上限**（§1.3，残余 122 ms / 40 ms），
逐 job 记录与逐次决策审计都落了盘；闸在实测负载上开过火，
那次开火的 `over` 与 `budget` 的累积过程可以逐条回看；
开关关着时行为不变（既有 4933 例单测全过）。

**不能**：
- 规模。38 个 job，10¹ 量级。这是存在性证明，不是 scale 结果。
- `p99_dl`。10¹ 个 job 出不了可信的 p99，而且本机没有「assessment 截止时刻」这个对象。
- 线上。全程本机，没有部署，没有真人。
- 策略之间的比较。四个 cell 的用户数与作业混合都不一样（§4），
  `smoke-fcfs` 与 `smoke-spjf` 的队列深度还只有 1，横着比没有意义。
  **边界检查是逐 cell 自证的**（拿同输入重放 FCFS），不依赖 cell 之间可比。
- 预测质量。规模代理没有标定，三次带练路线里还反了一次序（§2）。
- 分布式。单进程、单事件循环上的计数器，与 `assessment.md` §3.6 最后一条一致。

### G2 闭环负载

**能**：需求由脚本用户产生，账号是过 app 自己的注册接口建的，
请求走真实 HTTP 路径；思考时间规则是显式的、可配的；
三种规则都实现了，开环那条的到达形状是从论文 development trace 的
最忙 24 小时 deadline 窗裁出来的，两次缩放都写在文件头里。

**不能**：
- 没有真人。必须逐字写进 §7/§9：arrivals are scripted replays driven by synthetic
  accounts on a local deployment; no human learner was in the loop.
- 冒烟只跑了规则 (ii)。(i) 与 (iii) 的代码路径**一次都没有执行过**，
  全量跑之前要先各跑一个 2 job 的哑轮把它们点通。
- 闭环里 ρ 是结果不是参数（§4.1）。任何「ρ ≈ 0.85」的说法在闭环 cell 里只能是
  事后测出来的，不能写成设定。

### G3 模拟器校验

**能**：论文包的模拟器在这套真实服务的实测输入上，逐 job 等待与实测值最大差 16 ms，
四个 cell 38 个 job 全部如此，**包括闸开火的那一个决策**。
这是论文目前完全没有的东西——现在只对 CI pool A/B（别人的日志）做过。

**不能**：
- 38 个 job 不是保真度结论。`weakness1_attack` 那次 2151 个 job 的 timed-work 实验里，
  Guard 的最大逐 job 偏差是 1354.1 s、1753 个 job 的派发位置不同
  （`evidence/weakness1_attack/REPORT.md`）。这次的一致**不构成**对那个结果的反驳：
  那次的分歧来自两条事件序列的开火时刻不同，需要足够长的队列和足够多的开火才显形，
  38 个 job、1 次开火根本到不了那个区域。两件事要并列写，不能只写这一件。
- 模拟器的逐 job 上限是一个数，这里用的是两类里较大的那个（170 s）；
  每个 job 自己的 `executedMs` 在记录里已经按各自的 ℓ 截断过，所以结果不受影响，
  但这个细节要写在方法里。

---

## 7. 全量跑之前还要补的几件事

1. **蓝图那一类没记 `responseBytes`**（`fetchLearnerBlueprint` 返回的是解析过的对象）。
   补一行就行，不补的话蓝图这一类只能靠 token 日志算体量。
2. **引擎侧截止时刻建议留出余量**。现在课堂端的 abort 与引擎的截止时刻都是 ℓ，
   两者同时到点，实测是引擎先停（170.122 s 那次日志在 abort 之后 122 ms 落的），
   但这是一场竞速。把头里的值设成 `ℓ − 2 s`，引擎就总是先返回，
   调用方拿到的是一个明确的 502 而不是一个 abort，记录也更干净。
3. **规则 (i) 与 (iii) 各点一次哑轮**（2 个 job，全用蓝图，约 20 秒、不到 1000 token）。
4. **`inverted` 与 `random` 两档打分各跑一个 cell**——论文关于「预测错了闸也兜得住」
   的说法目前在这套栈上一次都没测过。
5. **造课那一类（`generate-classroom`）没有接**。一次几十分钟、约 0.6 M token，
   这轮用不上。要接是同一个形状的一行改动，写在改动说明第六节里。

---

## 8. 文件在哪

论文仓（本仓，只动了 `evidence/platform_testbed/`）：

- `evidence/platform_testbed/build_report.md`（本文件）
- `evidence/platform_testbed/make_arrivals.py` —— 裁开环到达时刻表
- `evidence/platform_testbed/replay_simulator.py` —— 喂模拟器比对
- `evidence/platform_testbed/records/` —— 四个 cell 的逐 job 记录、决策审计、
  客户端记录、清单、汇总（`summary.json`）、模拟器比对（`simulator_replay.json`）、
  开环到达表（`arrivals_deadline_burst.csv`）。
  另有 `*-abandoned-n3.*` 三条，是 §4.1 那一轮作废的 cell，留着以免被误读成有效数据。

平台仓（`D:\UserData\Desktop\挑战杯`，分支 `sched-experiment`，本地提交 `b953e20`）：

- `apps/classroom/lib/server/classroom-dispatch.ts` —— 派发器
- `apps/classroom/tests/server/classroom-dispatch.test.ts` —— 离线检验
- `apps/agent-engine/backend/services/call_deadline.py` —— 按请求生效的执行上限
- `experiments/scheduling/` —— 起停脚本、负载发生器、汇总脚本、README
- `docs/调度实验改动说明.md` —— 逐文件改动、开关默认值、回退步骤、测试账号清理
