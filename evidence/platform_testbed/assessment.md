# 挑战杯 平台能否当调度论文的真实试验台

读时间 2026-09-23。只读检查，未改动 `<platform-repo>` 任何文件，未起服务，未部署任何东西。
未读 `.env*`。`apps/classroom/data/accounts/accounts.json` 含 `password` 列，只统计了行数与列名，未读取内容。
提交包解到两个仓库之外的一个临时目录，只取了三份 `.md`；
`挑战杯报名表.pdf` 与 `03-测试数据/学情数据组/*.json`（含画像）未读内容。
论文只读了 abstract、`paper/sections/03_problem_model.tex`、`paper/sections/07_data.tex`，
以及 `paper/sections/05_scheduling.tex` 的 Algorithm 1。

## 结论（三句）

1. **平台里没有判题沙箱。** README 的「提交后判代码」是一个**读代码的 LLM 判官，不执行代码**。
   论文 §7 里 CodeBench / ACcoding 那种"提交 → 判题机执行 → 记时长"的对象在这里不存在。
2. **平台里唯一真排过队的机制是知识库接入链的 k=1 闸**（有事故叙事、有排队事件类型，
   但 93 条归档里排队事件 0 条）；**造课任务是 k=∞、从不排队，但它是改成 k 工人池最便宜的位置**
   ——一个新文件 + 一行改动 + 五个新字段。
3. **在本机跑一套完整栈、用脚本客户端打真实负载，是五天内唯一可交付的实验**，
   它能拿到真实执行时长、真实有界工人池、可测量的 per-job 保证；
   **它拿不到重尾**——平台上每一类作业的实测 CV 都 < 1（造课 0.68，接入 0.62）。

---

## 0. 竞赛上下文：为什么线上站点不能动

`docs/02-spec/赛题原文-XH-202630.pdf`（发榜单位 上海云之脑智能科技）：

- 提交截止 **2026-09-05**（已过）；**9 月 20 日前初审**定晋级名单；**10 月**发榜单位指导完善；
  **11 月终审擂台赛**。也就是说 09-23 正处在初审结果与终审之间，线上实例**随时可能被评委打开**。
- 评分 100 分制：作品完整性 30（明写「**系统能正常部署运行**」得满分，「系统无法正常部署运行」扣 15–30）、
  技术创新性 25、用户体验 15（明写「智能体调度过程无可视化**或存在卡顿**」扣 5–10）、实用价值 30。
- 提交包 `02-软件模块/源代码与在线地址.md` 把作品钉在**公开仓库 `ca7384f`（2026-09-04）**，
  并声明「线上实例运行的是同日构建的不可变 release，代码与该提交一致」。

两条直接后果：

- **不要碰 `jizhi.chenmingkun.cn`。** 一个排队实验按定义就是让请求"卡顿"，正好命中用户体验那一项的扣分措辞；
  而且线上代码与提交版本一致这句话是写进材料的，改了它就不再成立。
- **实验代码走独立分支**，不进 `ca7384f` 那条线，也不进提交包（`scripts/build-submission.ps1` 的装配范围）。

同一份材料也解释了为什么自然流量小：这是为评委建的展示实例，
「首页『体验学习端 / 体验管理端』两个按钮进入演示账号，不用注册」——访客走的是演示账号，不造课。

---

## 1. 平台里像 job 的活

### 1.1 学员代码提交判题：**不存在会排队的执行**

- `apps/agent-engine/backend/services/practice_coach.py:11-12` —
  「判代码（grade_code）：对照任务的判分要点判 correct / partial / incorrect……**不跑代码——判官是读，不是执行**」
- `apps/agent-engine/backend/services/practice_coach.py:153-183` `grade_code()`：
  一次 `gateway.structured_chat(COACH_AGENT, ...)`，`max_tokens=900`，同步返回，无队列。
- `apps/agent-engine/backend/services/content_verification.py:34-40` `verify_python_block()`：
  「一般 Python 必须进入外部系统级沙箱；当前只报告未验证，**绝不执行**」，一律返回 `unverifiable`。
  同文件 1-15 行写明未接入隔离沙箱，也**不声称**具备沙箱。
- `apps/agent-engine/backend/schemas/curriculum.py:65` 有 LeetCode 形制的判题用例结构
  （`expression` 在提交代码的命名空间里求值），但没有找到执行它的运行时。

派发点是 `apps/classroom/app/api/practice-guide/[action]/route.ts` →
`apps/agent-engine/backend/api/practice_scout_routes.py:178`，一次同步 HTTP + LLM 调用。
无队列、无并发上限、无逐 job 落盘。唯一节流是外部 API 配额
（`docs/部署说明.md`：匿名 GitHub 配额一小时 4 次起草）。

**这一条必须在论文里说清楚**：如果写"在一个教学平台上部署"，读者会默认是判题机。这里不是。

### 1.2 造课流水线：**有完整 job 记录，无队列，k=∞**

| 位置 | 内容 |
|---|---|
| `apps/classroom/app/api/generate-classroom/route.ts:63` | `const jobId = nanoid(10)` |
| 同上 `:64-68` | `createClassroomGenerationJob(...)` 写盘，status=`queued` |
| 同上 `:71` | `after(() => runClassroomGenerationJob(jobId, input, baseUrl))` —— **发射即忘，零准入控制** |
| 同上 `:73-83` | 立刻返回 202 + pollUrl，`pollIntervalMs: 5000` |
| `apps/classroom/lib/server/classroom-job-runner.ts:14-68` | 执行体；`runningJobs` Map 只做同 jobId 去重（`:19-22`），**不是并发闸** |
| `apps/classroom/lib/server/classroom-job-store.ts:112-134` | 建 job，写 `apps/classroom/data/classroom-jobs/<id>.json` |

**并发上限：没有。** 全仓搜 `Semaphore / p-limit / maxConcurrency`，造课 job 这一层是空的。
唯一旋钮在 job **内部**：`apps/classroom/lib/server/classroom-generation.ts:712`
`const auditConcurrency = Math.max(1, getParallelSceneConcurrency())`，定义在
`apps/classroom/lib/server/provider-config.ts:699-704`（读 `PARALLEL_SCENE_CONCURRENCY`，钳 [0,10]，
**默认 0 = 串行**，`apps/classroom/.env.example:288` 注释掉）。这是"一门课里几屏并行审核"，不是"几门课并行"。
底层信号量：`apps/classroom/lib/utils/concurrency.ts:1-58`。

**非抢占：是。** 启动后跑到 `generateClassroom()` 返回或抛错为止（`classroom-job-runner.ts:29-52`）。

**per-job 时限 L：没有真的。** 只有看门狗：`classroom-job-store.ts:88-106`，
`STALE_JOB_TIMEOUT_MS = 30 * 60 * 1000`——看的是 `updatedAt` 而不是总时长，
持续上报进度的 job 可以跑任意久。`classroom-generation.ts:713-717` 记了 2026-08-18 栽的跟头：
审核相位并发化后整段不上报，20 屏那轮超过 30 分钟被看门狗判死。
单次调用有超时：`apps/classroom/lib/server/audit-panel.ts` `CALL_TIMEOUT = 300_000`（300 s/次，两次），
`lib/generation/content-verify.ts` 40 s，`lib/generation/learner-profile.ts` 25 s。
路由层 `route.ts:15` `maxDuration = 30` 只管那个 202 响应，不管 `after()` 里的执行体。

**实测时长**（我从 109 份落盘 job 记录算的，只读时间戳）
`apps/classroom/data/classroom-jobs/*.json`，`createdAt` 跨度 2026-08-04 → 2026-09-02，
succeeded 71 / failed 31 / running 7（残留）。103 份同时有 `startedAt` 与 `completedAt`：

```
service time (startedAt -> completedAt), n=103
min 0.2s   p50 2154s (35.9 min)   p90 4160s   p99 5874s   max 6411s (107 min)   mean 2141s
CV = 0.68        top-decile 占总 work 的 0.235
submit -> start: p50 0.01s  p90 0.02s  max 0.06s     <- 从不排队
到达: p10 间隔 0.0s（成串）, p50 1018s, p90 16750s; 单日最多 26 个（2026-09-02）
```

**两个含义**：到达确实突发；**时长不重尾**（CV<1，top decile 只占 23.5% work）。
它是"长而集中"（几十分钟量级），不是重尾。

**每 job 已记录什么**：`classroom-job-store.ts:17-53` 的 `ClassroomGenerationJob` 带
`createdAt`（= a_i）、`startedAt`（= s_i，写在 `:184`）、`completedAt`（`:219` 成功 / `:237` 失败）、
`ownerAccountId` / `ownerOrgId` / `corpus` / `status` / `step` / `progress` / `scenesGenerated` / `totalScenes` / `error`。
**论文需要的五元组已经全在盘上**，一行都不用加。

**token 账**：`apps/classroom/data/usage/2026-{07,08,09}.jsonl`，共 9288 行，列为
`id/createdAt/kind/source/providerId/modelId/inputTokens/outputTokens/cacheReadTokens/cacheCreationTokens/reasoningTokens`
（口径见 `scripts/usage-ledger.py:31-40`）。**只有一个时间戳，没有每次调用的墙钟**，所以它能做特征，不能做 C_i。
汇总：input 32.91M / output 32.49M tokens。按 source：

```
scene-audit              n=1738  in 6.27M  out 7.75M
generate-classroom-scene n=1559  in 6.87M  out 6.69M
scene-content            n=1462  in 5.43M  out 7.37M
scene-audit-revise       n=1156  in 3.17M  out 6.37M
scene-audit-2            n=1475  in 5.71M  out 0.69M
模型: Qwen3.5-397B-A17B 4542 次 / DeepSeek-V3.2 1737 / Qwen3.6-35B-A3B 1587 / MiniMax-M2.5 989
```

摊到 109 个 job ≈ **每门课 0.3M input + 0.3M output tokens**。这个数是第 3 节成本估算的唯一真源。
（账本没有单价字段——`usage-ledger.py` 自己说明「所以不出金额」——所以下面也不写金额，只写 token 数。）

### 1.3 知识库接入链（domain_intake）：**平台里唯一真排过队的服务**

`apps/agent-engine/backend/services/domain_intake.py`：

- `:3494` `_CHAIN_GATE = threading.Semaphore(1)` —— **k = 1**。注释（`:3486-3493`）：
  「每条 run 自己开 3 线程的池，跨 run 原本没有任何控制——两人同时投币就是 6 线程抢 2 核。
  **2026-08-22 那次整机饱和（连 sshd 都发不出协议 banner、失联十几分钟）就是这么来的**：
  一份验证包与一次真实投币撞在一起。」「串行而不是拒绝：管理者只是来早了，拒了他会以为系统坏了。」
- `:3497-3498` `MAX_ADMITTED_RUNS_GLOBAL`（env `INTAKE_MAX_ADMITTED_GLOBAL`，默认 4）、
  `MAX_ADMITTED_RUNS_PER_ORG`（env `INTAKE_MAX_ADMITTED_PER_ORG`，默认 2）——active+queued 硬上限，
  撞线明确拒绝（`:3576-3600` `start_run` 抛 `IntakeCapacityError`）。
- `:3546-3574` `_run_with_gate()`：拿不到闸就 `emit("run","run_queued","前面还有 {ahead} 个…")` 再阻塞。
- `:1133` `TRIAL_CONCURRENCY = 2`；`:1408 / :2257 / :2748` 各 3 线程池。

落盘 `apps/agent-engine/data/knowledge_base/intake_runs/<runId>/{run.json,events.jsonl,docs/}`，93 份，
`created_at` 跨度 2026-08-15 → 2026-08-24，failed 62 / done 30 / aborted 1。30 份有 `duration_ms`：

```
p25 516s  p50 835s (13.9 min)  p75 1029s  p90 1214s  max 1861s  mean 752s  CV 0.62
top-decile work share 0.207
到达: 2026-08-22 一天 62 条（事故那天）, p50 间隔 0 秒
```

**93 份里 `events.jsonl` 含 `run_queued` 的有 0 份**——闸装上以后生产环境从未真正排过队。
有队列机制、有事故叙事，**没有 recorded wait 轨迹**。

### 1.4 其它异步执行

- **视频渲染服务** `apps/classroom/render-service/`：教科书式 k 工人非抢占池。
  `src/config.ts:31` `maxConcurrency`（`RENDER_MAX_CONCURRENCY`，默认 2）；`:39` 每用户 1；
  `:41` 全局 queued+running 20；`:48` **`jobDeadlineMs`（`RENDER_JOB_DEADLINE_MS`，默认 45 分钟）——
  平台里唯一一个真正的 per-job 墙钟上限 L**；`src/render-manager.ts:39-140` 有 FIFO `queue`、
  `reserve/submit/release` 准入、`AbortController`、`RenderRejectedError -> HTTP 429`；
  `src/semaphore.ts:9-38` 另一把解压闸。入口 `apps/classroom/app/api/export-video/render/route.ts`。
  **但它是 vendored 的上游包（openmaic / hyperframes），不是主线功能，`data/` 下没有它的 job 归档。
  它的价值是"照着抄 L 的实现"，不是当 workload。**
- **LLM 网关** `apps/agent-engine/backend/services/llm_gateway.py:113` 有 timeout，
  `:148` `for attempt in range(MAX_STRUCTURED_ATTEMPTS)` 有重试，`:194` 放弃后告警。**没有并发闸。**
- **比对服务** `backend/services/compare_service.py:304` `ThreadPoolExecutor(max_workers=len(profiles))`，无上限。
- **PDF 转写** `backend/rag/pdf_transcribe.py:258` `ThreadPoolExecutor(max_workers=CONCURRENCY)`。

---

## 2. 真实流量

**有真实使用，量很小，几乎全是运营者自己在用。** 这与第 0 节一致：平台是为评委建的。

| 证据 | 位置 | 数字 |
|---|---|---|
| 造课 job | `apps/classroom/data/classroom-jobs/` | 109 份，2026-08-04 → 2026-09-02 |
| 造课 job 的不同 owner | 同上 `ownerAccountId` | **3 个**（含 null）；org 也是 3 |
| 账号 | `apps/classroom/data/accounts/accounts.json` | **28 个账号 / 2 个机构**（只数行数；列为 `id/username/displayName/role/password/profile/createdAt`） |
| 已发布课程 | `apps/classroom/data/classrooms/` | 81 门 |
| 接入 run | `apps/agent-engine/data/knowledge_base/intake_runs/` | 93 条，2026-08-15 → 2026-08-24 |
| 学习者画像 | `apps/agent-engine/data/learner_profiles/` | **1 个** |
| token 账本 | `apps/classroom/data/usage/*.jsonl` | 9288 行 |

**没有**学员提交流水表、没有 PostgreSQL 导出、没有访问日志。
`scripts/export-submission-data.py:1-13` 那个"提交数据"是**赛事提交包的装配器**
（知识库切片 + 差异化学情数据，取自 `apps/agent-engine/data/runs/*.json` 的 IO 快照），
**不是用户提交流水**，名字容易误会；提交包里对应 `03-测试数据/`。
`docs/05-evidence/` 下 40+ 份文档全是模型质量评测（接地率、判官一致性、学习增益），
**没有一份是延迟 / 吞吐 / 排队的测量**；`learning_gain_protocol.md` 是**模型扮演学习者**，不是真人实验。

**平台排过队吗**：唯一可证的容量事件是 2026-08-22 的整机饱和，写在
`domain_intake.py:3486-3493` 的注释里（代码注释，不是测量记录）。
造课 submit→start 最大 0.06 s；接入链 `run_queued` 事件 0 条。
**目前平台上不存在任何一条 recorded-wait 轨迹。**

---

## 3. 本机部署 + 脚本负载：可行性与设计

按用户的新口径：**本机起全栈（`scripts/start-demo.ps1` 那条路），测试账号自己种，
脚本客户端打负载，不碰线上，不涉及真人学员。** 下面全部按这个前提写。

### 3.1 哪种作业能给出**真实**服务时长分布

四个候选，按"真实性 / 成本"排：

| 作业 | 一次的真实耗时 | 真实性 | 成本（token） | 现成的 L |
|---|---|---|---|---|
| **A. practice-guide 里程碑拆解** | **实测 90–150 s** | 真 LLM 调用链，走真实 HTTP 路径 | 一次调用，约每门课的 1/100 | **有：170 s** |
| B. grade_code 判代码 | 数秒（`max_tokens=900`，fast 档） | 真 LLM 调用，但**不是代码执行** | 最低 | 无 |
| C. 造课全流水线 | **实测 p50 2154 s** | 最完整（多智能体 + 双判官 + 仲裁） | **约 0.6M tokens / job** | 无（需新加） |
| D. domain_intake 接入链 | 实测 p50 835 s | 真，且**已有 k=1 队列** | 中；吃满 2 核 | 无 |

**A 是本机实验的首选。** 依据：
`apps/classroom/app/api/practice-guide/route.ts:5` 的注释写着「引擎同档缓存，
**首次生成实测 90-150 秒，超时给 170 秒**」，同文件 `:40` `signal: AbortSignal.timeout(170_000)`。
这是平台上**唯一一条既有实测时长、又有现成 per-job 时限**的作业——论文模型要的 L 直接就是 170 s。
缓存键 `profile_key(profile, difficulty)`（`apps/agent-engine/backend/services/practice_guide.py:167, 297-307`），
`build_guide(..., refresh=False)` 命中缓存直接返回；路由 `:38` 透传 `refresh`，
所以**只要传 `refresh: true` 或变画像，每个 job 都是真跑**。
工作量来源：22 个已发布实操项目 × 画像档位（`programming_level / agent_level / engineering_level /
time_budget_hours / role`，见 `route.ts:70-76`）→ 几百个互不命中的键，够打一轮负载。

**B 最便宜但最弱**：它是 LLM 判官，不是沙箱。**平台上没有任何沙箱代码执行**（§1.1），
所以"真实 sandbox code runs"这个选项在这套代码上**不存在**，不能作为实验对象。
把 B 写成"代码执行"会是事实错误。

**C 最像论文的对象**（长、非抢占、真会把池堵死），但一轮 40 个 job ≈ **24M tokens**。
**这是必须由用户自己决定的一笔真实账单**（见 §4 决策项）。

**D 已有队列**，但需要语料包（本机 `apps/agent-engine/data/knowledge_base/corpora/` 只有
`iotdb`、`smart-manufacturing` 两个域），且 2026-08-22 的教训是它会打爆两核机器。
它的价值是**第二现场**：把 `_CHAIN_GATE` 的 `Semaphore(1)` 换成 k 工人 + Algorithm 1，
`:3553-3560` 已有的 `run_queued` 事件改成落真实 wait——改动比造课那条还小。

### 3.2 重尾吗？——**不。这一点不能含糊**

手上有实测的两类，CV 都 < 1：造课 **0.68**（top decile 占 23.5% work），接入 **0.62**（20.7%）。
A 类按 README 的 90–150 s，极差比 1.7，CV 只会更小。
**平台上没有任何一类作业是重尾的。** 唯一的尾部来源是重试与超时
（`llm_gateway.py:148` 的 `MAX_STRUCTURED_ATTEMPTS`、`audit-panel.ts` 的 300 s×2、路由的 170 s abort），
那是**机制性尾**，不是分布性重尾。

**能诚实构造的替代**：两类混合。90% 的 A（≈120 s）+ 10% 的 C（≈2150 s）这个混合的
CV > 1、top-decile work share > 0.8，**在论文里要如实写成"平台自身两类作业的混合"
（a disclosed two-class mixture of the platform's own job types），
绝不能写成"平台的作业时长是重尾的"。** 这样做的正当理由是：论文 §3 明说
「We place no stochastic assumption on a_i, on C_i, or on the dependence between them」，
定理对任何分布都成立——所以混合构造检验的是保证本身，不是分布假设。

### 3.3 需求怎么造

脚本客户端 → 真实 HTTP 路径 → 真实工人池。**载体已经现成**：
`scripts/seed-public-courses.mjs:53` 已经在 `POST ${BASE}/api/generate-classroom`，
`:69` 轮询 `/api/generate-classroom/${jobId}`，支持 `--base` 与 `--concurrency`
（同类还有 `scripts/generate-path-courses.mjs`、`scripts/skill-gap-courses.mjs`、
`scripts/production-dual-org-e2e.mjs`）。
**要改的只有一件事：把"并发 N 的池"换成"按时间戳表发请求"。**

到达序列：从论文 development trace 取一个 24 小时 deadline window 的到达形状
（`paper/sections/07_data.tex` 的 overlay 构造），按两步缩放到本机池：

1. 时间压缩因子 `α`：把 24 h 窗压到实验窗（例如 2 h，α=12）；
2. 计数缩放：令 offered load `ρ = λ·E[C] / k ≈ 0.85`。以 A 类（E[C]≈120 s）、k=2 为例，
   `λ ≈ 0.85·2/120 = 0.0142 job/s`，2 小时 ≈ **102 个 job**。
   这个量级 A 类完全承受得起；C 类则是 102×0.6M ≈ 60M tokens，不现实。
   **所以：A 类做主实验，C 类只按 10% 混进去做尾。**

账号：本机可以完全不配 PostgreSQL（README / `docs/部署说明.md` 都写明「未配置时以访客模式运行」）。
造课路由的准入在 `apps/classroom/app/api/generate-classroom/route.ts:49-53`
（`authorizeInternalCorpusService` 内部服务令牌 / `requireCorpusVisible` 登录态）——
**内部服务令牌那条路就是给服务端批量生成用的，seed 脚本走的正是它**，
所以"多测试账号"在本机可以直接用 `ownerAccountId` 字段区分，不必真去种 28 个登录账号；
需要多账号语义时，`apps/classroom/data/accounts/accounts.json` 是一个普通 JSON 文件，
**由用户自己种**（我不碰它，里面有 `password` 列）。

### 3.4 要改的代码（与线上方案相同，但只在本机跑）

1. **新增** `apps/classroom/lib/server/classroom-dispatch.ts`（约 150–200 行）：
   - 等待集 `Q`（进程内单例，与 `classroom-job-runner.ts:12` 的 `runningJobs` 同级）；k 个工人槽（`SCHED_K`，默认 0 = 关）；
   - Algorithm 1（`paper/sections/05_scheduling.tex:118-145`）：完成事件把 `C_c` 加到所有 rank 更小的等待者的 `over[q]`（`:126-130`）；
     派发时算 `E = {q : over[q] >= min(B0 + gamma*n_q + eta*k*(t - a_q), B_max)}`（`:135`），
     非空取最小 rank（guard 开火），否则交基策略 `A(Q,t)`（`:139`）；
   - 基策略 A = SPJF-E；`C_hat_i` 用现成特征（`inputSummary.pdfTextLength/pdfImageCount`、`totalScenes`、
     `corpus`、是否开图/视频/TTS；A 类则用 `project_id` + 画像档）。第一版可以只用 per-class 中位数——
     论文 §3 明说保证对任意 score 成立，**包括对抗性的 score**；
   - per-job 硬时限 L：照抄 `render-service/src/config.ts:48` + `render-manager.ts` 的 `AbortController`。
     A 类取 L = 170 s（已有），C 类取 L = 7200 s（实测 max 6411 s 之上）。
2. **改 1 行** `apps/classroom/app/api/generate-classroom/route.ts:71`：
   `after(() => runClassroomGenerationJob(...))` → `after(() => enqueueClassroomGenerationJob(...))`。
   `SCHED_K` 未设时 `enqueue` 直接调原函数，**逐字等价于现状**。
3. **改 ~10 行** `apps/classroom/lib/server/classroom-job-store.ts`：加
   `dispatchedAt`（= s_i；现有 `startedAt` 是 runner 开跑，有队列后两者会分离）、
   `predictedCost`、`guardFired`、`overAtDispatch`、`rank`。
   `createdAt / startedAt / completedAt` 已有（`:17-53`），不重建。
4. **A 类要新建一层**：practice-guide 现在是同步 HTTP（`route.ts:32-40`），没有 job 记录。
   最省的做法是在课堂侧包一个与造课同构的 job 壳（复用 `classroom-job-store` 的写盘模式，
   约 80 行），让 A 和 C 共用同一个 `classroom-dispatch`。
5. **分支纪律**：独立分支，不进 `ca7384f` 那条线，不进 `scripts/build-submission.ps1` 的装配范围。

### 3.5 这样的实验**能**宣称什么

- **机制在一套生产级栈里跑过**：真实 Next.js 路由 + 真实引擎 + 真实模型调用与其真实延迟 +
  真实有界工人池，不是一个玩具 harness；
- **per-job 保证在实测等待上被验证**：同一条 `(a_i, C_i, k)` 离线重放 FCFS，
  逐 job 算 `excess = W_guard − W_FCFS`，检验 `<= G`。这是论文目前**完全没有**的东西——
  `paper/sections/07_data.tex` 现在必须写「The pooled side is simulated, so neither supports a claim
  that the platform ever queued」；
- **模拟器对实测等待的校验**：论文现在只用 CI pool A/B（别人的日志）做这件事，
  这是一个**独立的第三个系统**；
- **派发器开销**：Algorithm 1 每个 dispatch epoch 要遍历 Q 更新 `over[]`，
  在真实服务里量出 per-epoch 的墙钟（微秒级 vs 秒级的 C_i）——这是一个**只有真部署才拿得到**的数；
- **数据是用户自己的**，无授权问题（对比 CodeBench / ACcoding / Azure / Netbatch 都是第三方）。

### 3.6 **不能**宣称什么

- **需求是脚本造的，不是人**。必须逐字写进 §7 / §9：arrivals are scripted replays driven by
  synthetic accounts on a local deployment; no human learner was in the loop.
- **不是重尾**（§3.2）。混合构造要标明是构造。
- **主指标 `p99_dl`**（deadline window 内 99 分位等待）：10² 量级的 job 出不了可信的 p99，
  而且本机没有"assessment 截止时刻"这个对象——deadline 是从论文 trace 借的形状，不是本平台的日历。
- **判题平台的任何结论**：平台没有判题机（§1.1）。
- **规模**：论文主 trace 1763 万 job，这里 10²。**这是存在性证明，不是 scale 结果。**
- **多机 / 分布式**：`render-manager.ts:8-13` 自己说计数器是单事件循环上的同步字段，
  分布式要换 Redis。本机单进程实验不支持任何关于分布式派发的结论。

### 3.7 工期与成本

| 阶段 | 内容 | 估时 |
|---|---|---|
| S0 | 本机起栈（`scripts\start-demo.ps1`）、访客模式、跑通 `docs/部署说明.md` 的三条 curl 验证 | 0.5 天 |
| S1 | 写 `classroom-dispatch.ts`（Algorithm 1 + k 槽 + L）；改 route 一行 + job store 五字段 | 1 天 |
| S2 | A 类 job 壳（practice-guide 包成异步 job）+ 负载脚本（改 `seed-public-courses.mjs` 为时间戳驱动） | 0.5 天 |
| S3 | 离线单测：合成到达序列断言 `max_i (W_guard − W_FCFS) <= G`；跑 `pnpm test`（4818 例） | 0.5 天 |
| S4 | 正式跑：2 h 窗 × 2 轮（k=2 与 k=4），A 类为主 + 10% C 类做尾 | 0.5 天（墙钟 4–5 h） |
| S5 | 重放分析（FCFS / SJF-true / guard 的 mean / max excess / harm / firing rate）+ 模拟器比对 | 0.5 天 |
| | **合计** | **约 3.5 个工作日**，留 1.5 天余量 |

**模型 API 成本（用户付费，必须由用户决定）**：账本没有单价字段，所以只给 token 量。

- A 类（practice-guide）：一次 guide 起草是**一次** `structured_chat`。按造课侧同档调用的量级
  （`scene-content` 均值 5043 output tokens）保守估 **≈ 10K in + 6K out / job**。
  两轮各约 100 个 job → **≈ 2M in + 1.2M out tokens**。这个量级相对造课是零头。
- C 类（造课）：**≈ 0.3M in + 0.3M out / job**（实测：32.9M in / 32.5M out ÷ 109 job）。
  若按 10% 混入，两轮共 ≈ 20 个 job → **≈ 6M in + 6M out tokens**。
- **两轮总计约 8M input + 7M output tokens。** 换算成钱要用用户自己的 SiliconFlow 账单单价
  （主力模型是 `Qwen/Qwen3.5-397B-A17B`，4542 次调用里的第一名）。**这是决策项，不是我能替他算的数。**
- 省钱的档：C 类比例从 10% 降到 0（放弃混合尾），总量掉到 ≈ 2M + 1.2M tokens，
  代价是只剩一个窄分布，`gap_closed` 类指标会很平——**但 per-job 保证的验证不受影响**，
  因为那条定理不依赖分布。

---

## 4. 建议：2026-09-28 前做哪一个实验

**本机全栈 + 脚本客户端 + Algorithm 1 的 k 工人池，A 类（practice-guide，L=170 s）为主工作量，
可选 10% C 类（造课）混入做尾，全程离线重放 FCFS 做对照。**

目标不是抢主结果，是把论文最大的一处软肋补上一块真砖：
`07_data.tex` 现在必须写「The pooled side is simulated, so neither supports a claim that
the platform ever queued」——这个实验让它可以改成"机制在一套真实服务栈里跑过，
per-job 承诺在实测等待上成立"。

### 步骤

1. **D0（半天）**：本机起栈并跑通 `docs/部署说明.md` 的三条 curl 验证。
   同时离线从 109 份 `classroom-jobs/*.json` 拟 `C_hat` 的粗模型（per-corpus × 屏数中位数），报 hold-out Spearman。
2. **D1（1 天）**：`classroom-dispatch.ts`（Algorithm 1，cap `B_max = k(G − (3−2/k)L)`，
   见 `05_scheduling.tex:150-157`；shape `B0, gamma, eta` 取论文用过的档；基策略 SPJF-E；硬 L）。
   改 `route.ts:71` 一行 + `classroom-job-store.ts` 五字段。独立分支。
3. **D2（半天）**：A 类 job 壳 + 把 `seed-public-courses.mjs` 的并发池改成时间戳驱动的到达回放
   （`--schedule arrivals.csv`），到达形状取论文 dev trace 的一个 24 h deadline window，α=12 压到 2 h，
   计数缩到 `ρ≈0.85`。
4. **D3（半天）**：**先证伪**。合成序列单测断言 `max_i (W_guard[i] − W_FCFS[i]) <= G`；
   再跑 `pnpm test`（README：4818 例）确认没碰坏既有行为；`SCHED_K` 未设时逐字等价于现状。
5. **D4（半天跑，墙钟 4–5 h）**：两轮，k=2 与 k=4，各 2 h 窗。全程 `run_in_background` + 日志。
6. **D5（半天）**：重放分析。同一条 `(a_i, C_i, k)` 跑 FCFS 与 SJF-true，出
   mean wait / max excess / harm / firing rate（`03_problem_model.tex` 的五个量），
   再把 `(a_i, C_i, k)` 喂论文模拟器比对模拟 wait 与实测 wait。

### 要记什么

每 job 一行：`jobId, class(A|C), a_i(createdAt), s_i(dispatchedAt), e_i(completedAt), C_i = e_i − s_i,
C_hat_i, rank, over[i]@dispatch, guardFired, k, B_max, L, timedOut, accountTag, corpus, status`，
外加每个 dispatch epoch 的派发器耗时（微秒）。
落到 `apps/classroom/data/classroom-jobs/` 现有 JSON（已有一半字段），
再导一份 CSV 归档到 `<repo-root>\prechecks\platform_testbed\`。

### 期望的证据

- 一张表：实测 vs. 重放-FCFS 的 mean / max wait，`max_i excess <= G` 成立或不成立（不成立同样是结果）；
- 一张图：实测 wait vs. 模拟器 wait（论文目前只对 CI pool 做过）；
- 一个数：派发器 per-epoch 开销相对 C_i 的量级；
- 一段可写进 §7 / §8 的话，**附带 §3.6 那份"不能宣称"清单逐条写进 §9 limitations**。

### 必须是用户自己的决定

1. **模型 API 花费**。两轮约 8M input + 7M output tokens（含 10% 造课）；只做 A 类降到约 2M + 1.2M。
   **钱是用户的，这条我不替他决定。**
2. **C 类是否混入**。混入才有跨两个量级的服务时长（才有尾），不混只剩窄分布。见 §3.2 的诚实措辞要求。
3. **种测试账号**。`apps/classroom/data/accounts/accounts.json` 含 `password` 列，**我不碰**。
   本机走访客 / 内部服务令牌那条路可以完全不种账号（§3.3）。
4. **线上站点一律不动**（§0：9/20 初审已过、11 月终审擂台赛、"系统能正常部署运行"与"卡顿"都是扣分项，
   材料里写死了线上与 `ca7384f` 一致）。我的建议是**明确放弃线上部署这一选项**，
   哪怕带 feature flag——收益（"生产环境"四个字）换不回风险。
   本机全栈已经能拿到 §3.5 的全部四条，唯一丢掉的是"真人用户"，
   而真人用户本来就不存在（§2：109 个 job 来自 3 个账号）。
