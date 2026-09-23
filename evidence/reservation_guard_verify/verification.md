# `reservation_guard/report.md` 的独立对抗性复核

日期：2026-09-23。复核对象是 `../reservation_guard/report.md` 的 C1、C2、C3、C4a、C6（k=1）与 C5 的文献句子，以及这些结论所依赖的 `06_theory.tex` 定义。规则 R 按 report.md 的文字在 `rguard_indep.py` 中重写，没有读取 `rguard.py` 的实现、也没有 import `../reservation_guard/` 或 `../guard_theory/` 的任何模块；`checks.py`、`check_c1b.py` 只调用 `rguard_indep.py`。全程没有使用任何数据集。

## 1. 裁决表

| 编号 | 主张（report.md 的原话或其内容） | 裁决 | 证据与计数 |
|---|---|---|---|
| C1-a | `In_i <= Z_i`（Lemma R1） | **PROVED** | `out_c1_indep.txt` 1,983,467 条穷举 run / 10,230,898 次逐作业检查，`max(In-Z)=0`，0 次违反；`out_c1rand_indep.txt` 20,000 条随机 run / 160,755 次检查，含逐作业 `Z_q` 向量；`out_edge_indep.txt` 四个边界块共 398,670 条 run |
| C1-b | k=1 时 `excess <= B`，且可取等 | **PROVED** | 同上，`max(exc-B | k=1)=0`；`out_c6b_indep.txt` 给出对每个 `B in 0..40` 取等的显式实例 |
| C1-c | k>=2 时 `excess <= B/k+(2-2/k)L` | **PROVED，且为严格不等式** | 同上，`max(k*exc-B-(2k-2)L)=0` 仅在 k=1 达到；分 k 统计的最大余量为 k=2 时 −3、k=3 时 −6（L=3） |
| C1-d | eq. (guardin) 的 `kL` 溢出消失 | **PROVED** | 规则 R 的 `In` 在全部 10.2M 次检查中不超过 `Z`；`out_c1b_indep.txt` 中 17 个见证实例的 `In_R` 恰等于 `B` |
| C1-e | `(2-2/k)L` 仍被逼近 | **PROVED（渐近，不可达）** | `out_c1b_indep.txt` 把 S8.2 上行见证推到 m=8：k=2 的比值恰为 `2-2^(1-m)`（1, 3/2, 7/4, …, 255/128）→ 2 = 2k−2；k=3 到 907/243=3.73→4；k=4 到 323/64=5.05→6。闭式见证仍 OPEN |
| C1-f | 实例形式 `k*excess <= B+Λ_{k-1}(a_i)+Λ^{<i}_{k-1}` | **PROVED** | `out_t32_indep.txt` 1,488,984 次检查，最大余量 0，0 次违反 |
| C2-a | Prop. R4 闭合式 `min(1,max(0,floor((G-ell)/sigma)+1)/n)` | **PROVED** | `out_c2a_indep.txt` 848 行（8 个族 × G × 4 档 cap，含 `sigma<ell<L`），0 次不符，两个角点 `ell=C`、`ell=L` 也 0 次不符，0 次超承诺 |
| C2-b | Theorem R3：k=1 点态最大性 | **PROVED（须带三处修正，见 §3）** | `out_c2b_indep.txt` k=1 共 573,252 次重标记测试，0 次失败，`min(excess-G)=1` |
| C2-c | “k>=2 OPEN” | **REFUTED：k>=2 不是 open，而是假** | `out_c2b_indep.txt` k=2：452,810 次测试中 416,368 次被拒的动作其实安全；k=3：491,340 次中 481,964 次。反例见 §2 |
| C2-d | “needs no integer lattice … removes the real-valued defect flagged in verification.md §5” | **PROVED 但表述过头** | 测试 `over+ell<=G` 确实是实数安全的；但此前复核 §5 已给出实数下的点态最大规则“`over>G-L` 时触发”，`ell≡L` 的规则 R 与它逐动作相同。新内容是逐作业 cap，不是“消除实数缺陷”本身 |
| C3-a | `In = ell*floor(B/ell) <= B` | **PROVED** | `out_c3_indep.txt`，L=12、B=10、k=1/2/4、6 档 `ell`，18 个格子全部与 `ell*floor(B/ell)` 相等 |
| C3-b | k=1 入场门槛 `G >= L`，与 Prop. floor 取等 | **PROVED** | admission 要求 `ell_j <= Z_q`；k=1 时 `Z=B=G`，`ell=L` 给出 `G>=L`。Prop. floor 排除 `G<L` |
| C3-c | 一般 k 的门槛 `(2-1/k)L`，对比 Algorithm 1 的 `(3-2/k)L` | **PROVED** | `B=kG-(2k-2)L >= L` 等价于 `G >= (2-1/k)L`；`out_c3_indep.txt` 列出 k=1..16 |
| C3-d | “**the threshold drops by exactly L**” | **REFUTED** | `(3-2/k)L-(2-1/k)L = (1-1/k)L`：k=1 为 0，k=2 为 L/2，只有 k→∞ 才趋于 L。掉落恰为 L 的是**承诺中的加性常数**（`(3-2/k)L → (2-2/k)L`），不是入场门槛；报告把两件事写成了一句 |
| C4a-a | Prop. R5：`In_i=Out_i=0` 而 `excess=f` | **PROVED** | `out_c4_indep.txt`、`out_c4b_indep.txt`：k=2,3 各 m=1..6，取 `L=k^m`，每行 `In=Out=0`，`excess` 恰为 `L(1-((k-1)/k)^m)`，`excess/L` 为 1/2,3/4,…,63/64（k=2）与 1/3,5/9,…,665/729（k=3） |
| C4a-b | “no charging rule can see it”，`Omega(L)` 下界 | **PROVED** | 同上，上确界为 `L`，不可达 |
| C4a-c | “the honest defence of the residual `(2-2/k)L`” | **REFUTED（k>=3）** | 该构造的上确界是 `L`；`(2-2/k)L` 在 k=2 等于 `L`，在 k>=3 严格大于 `L`（k=3 为 4L/3，k=4 为 3L/2）。它辩护的是 `Omega(L)`，不是 `(2-2/k)L` |
| C4b | `max_t(U_P-U_FCFS) <= (k-1)min(L,B)` | **NOT EXAMINED** | 不在本次任务范围（报告自己标 OPEN），未独立重跑 |
| C6-a | k=1 规则 C 的 `E(B)=B+L-1` | **PROVED，但只到 B=10** | `out_c6_indep.txt` 完全复现报告表：B=1..10 与 `B+L-1` 相符，B=11,12 该族封顶在 12（应为 13,14），所以是族的覆盖不够而非等式失败 |
| C6-b | k=1 规则 R 的 `E(B)=B`，故 `B*=G` | **PROVED（并被加强为一般结论）** | `out_c6_indep.txt` 复现全部数字与 run 计数；`out_c6b_indep.txt` 给出对任意整数 `B` 的通用见证（受害者 + B 个单位 overtaker，cap=真值），`E(B)=B` 对 B=0..40 全部取等，`B+1` 立刻超承诺。配合 C1-b 的上界，`B*=G` 对任意整数 `G>=0` 成立，不依赖那个有限族 |
| C6-c | “`E(B)=B` for rule R”（无限定） | **须加限定** | `ell=C` 时 `E(B)=B`；`ell=L` 时 `E(B)=0`（B<L）而后为 `B`。一般只能写 `E(B)<=B`，取等发生在 cap 紧且 B 可由可用尺寸表出时 |
| C6-d | “rule R 的 k=1 预算 G 超过 `k(G-L)`，该界不可用于 reserving rule” | **PROVED** | `out_c6_indep.txt` 的 `B*` 表：G=3..11 时规则 R 为 G，`k(G-L)=G-L` |
| C5-a | Mu'alem–Feitelson TPDS 2001：conservative backfilling “only if they do not delay any job in the queue” | **CONFIRMED（原文核对）** | 论文摘要原句：“a more conservative approach, in which small jobs move ahead only if they do not delay any job in the queue”；正文另有 “a reservation is made for each job when it is submitted” |
| C5-b | “with one server-slot per job … it collapses to FCFS here” | **CONFIRMED，但不完整** | 推理正确（队首的 reservation 就是当下空闲的那台服务器），但同样的推理让 EASY（aggressive）也退化为 FCFS，因为 EASY 保护的正是队首。只说 conservative 会被审稿人抓 |
| C5-c | arXiv:1905.03439 “v1 Def. 1”：按 `r=floor(log_c x)` 对每台服务器累计**派发**工作、约束 `|G^r_s-G^r_s'|<=g c^(r+1)`、尺寸在派发时已知、无参照策略 | **CONFIRMED（内容），指针与“no refund”须改** | 该定义在 arXiv HTML（默认版与 v1 URL）中编号为 **Definition 2.1**，不是 Def. 1；且计数器并非只增：服务器清空时会 reset，“we decrease `G^r_s` to match the minimum among all rank r work counters”。“no refund”只在“不按单个作业完成退费”的意义上成立 |
| C5-d | Lindsay, Galloway-Carson, Johnson, Bunde, Leung（CCPE 25(4), 2013, DOI 10.1002/cpe.2860） | **READ**（Euro-Par 2011 同名版本，作者主页 PDF）— 并且它**推翻了报告的 novelty 框架** | 见 §4 |

## 2. 反例（显式实例）

### 反例 1：规则 R 在 k>=2 不是点态最大的（对 C2-c 的“OPEN”）

```
k = 2,  L = 1,  承诺 G = 0
作业（按 rank）:  (a,C) = (0,1), (0,1), (0,1), (0,1)
cap:              ell   = 1, 1, 1, 1
```
t=0 两台服务器都空闲，等待队列 (0,1,2,3)，队首 h=0，`overR[0]=0`。
规则 R 拒绝候选 j=1，因为 `overR[0]+ell_1 = 0+1 = 1 > 0 = Z_0`。
但先派发 1 是安全的：同一瞬间第二台服务器取走 0，于是 `W[0]=0=W_FCFS[0]`，作业 2、3 在 t=1 开始，与 FCFS 相同，每个作业的 excess 都是 0，且在规则 R 的任何后续下都保持 0。因此一个承诺 G=0 的 wrapper 可以放行这一步，而规则 R 禁止它。

同一族在 k=3 上给出同样的反例（`out_c2b_indep.txt` 列出前 4 个）。规模：k=2 时 452,810 次被拒动作里有 416,368 次经重标记后受害者 excess 仍 `<= G`；k=3 时 491,340 次里有 481,964 次。所以 k>=2 的点态最大性不是 open，而是**假**：这是多服务器上 `In` 与 excess 不再一一对应（`excess=(In-Out+Delta)/k`）的直接后果。

### 反例 2：C3 的“the threshold drops by exactly L”

纯算术：规则 R 的入场门槛 `G >= (2k-1)L/k`，Algorithm 1 的 `G > (3k-2)L/k`，差为 `(1-1/k)L`。k=1 时两者分别是 `G>=L` 与 `G>L`，差为 0；报告自己在同一句里写了 k=1 的 `G>=L` 与 `(3-2/k)L`（k=1 时也是 L），已经与“drops by exactly L”自相矛盾。

### 反例 3：C4a 的辩护范围

`out_c4b_indep.txt` 中该构造的 excess/L 上确界为 1。k=3 时 `(2-2/k)L = 4L/3 > L`，k=4 时 `3L/2 > L`。所以它不能解释 `(2-2/k)L` 中超过 `L` 的那一部分。

## 3. 逐条证明核对

**Lemma R1 — HOLDS。** 需要而且只需要四件事：(i) rank 由 `(a_j, index)` 决定，所以 `j>i` 蕴含 `a_j>=a_i`，凡计入 `In_i` 的作业都在 `i` 到达后、`i` 派发前被派发，那时 `i` 在等待；(ii) `i` 在等待且 rank 低于 `j`，故 `j` 不是队首，head 豁免不适用，测试必定对 `q=i` 执行；(iii) 已派发作业的记账值（完成则 `C_j`，未完成则 `ell_j`）恒 `>= C_j`，因此 `overR[i](t_s) >= sum_{u<s} C_{j_u}`；(iv) 被拒时派发的队首 rank 不高于 `i`，永远不进 `In_i`。同相位的情形不破坏它：先于本次派发、同一瞬间出手的 overtaker 完成时刻为 `t+C>t`，被按 `ell` 计费，正是最后一个 overtaker 论证所需的。`C_j=0` 也不破坏（`out_edge_indep.txt` (b) 块）。**前提是 cap 被强制执行**：只要作业可以超过 `ell_j`，(iii) 立刻失效。

**Theorem R2 — HOLDS，但是两行推论。** 由 Lemma R1 与 `Out_i>=0` 得 `In_i-Out_i<=B`，再套论文 Corollary `cor:sufficient`。k>=2 时应写严格不等号（`thm:identity` 在 k>=2 是严格的），报告写成 `<=`。k=1 时 `excess=In-Out<=In<=B`，与恒等式无关。

**Prop. R4 — HOLDS。** 独立重推：k=1 的派发时刻必有空闲服务器，故没有 rank 高于队首的作业在服务中，队首在第 s 个短作业前的 `overR` 恰为 `(s-1)sigma`，测试即 `(s-1)sigma+ell<=G`，放行数 `r=floor((G-ell)/sigma)+1`；第一个长作业跑完后队首换成第二个长作业，其 `overR` 仍是 `(s-1)sigma`（已完成的长作业 rank 更低，不计入），所以不会再放行。848 行 0 次不符。

由此得到一条报告没有写、但决定怎样描述这条规则的事实：**k=1 时 `overR` 恒等于完成工作量记账 `overC`**（`out_overR_eq_overC_k1.txt`：255,861 次读数 0 次不等；k>=2 时 110,503 次读数中 8,277 次不等）。单服务器上的全部收益来自测试里前瞻的 `ell_j` 一项，预留与退费在 k=1 上是空转的。

**Theorem R3 — HOLDS（k=1），三处必须改。**
- “relabel every dispatched-unfinished job (incl. j)”：k=1 的派发时刻没有任何在服务中的作业，要重标的只有 `j` 自己。写成“全部未完成的已派发作业”在一般 k 下会把 rank 低于 `h` 的在服务作业也重标，那时 `W_FCFS[h]` 就不再不变。正确的范围是 `j` 以及 rank 高于 `h` 的未完成作业。
- “`W_FCFS[h]` is untouched since all relabelled jobs rank above h”：结论对，但理由要补一句——`h` 是队首，所有 rank 低于 `h` 的作业都已派发，而 FCFS 按 rank 派发，`h` 的开始时刻只由 rank 低于 `h` 的到达与服务量决定（`out_wfcfs_indep.txt`：20,000 个实例重标 rank 高于 `h` 的全部作业，`W_FCFS[h]` 0 次改变）。
- 不透明 base 的量词不能省：若 base 是读取真实尺寸的固定策略（例如 exact SJF），重标后它在**当前这一步**的提议就可能改变，不可区分性失效。只有把承诺全称量化到 base 的提议 transcript 上，这一步才闭合。这是此前复核 §5 已提出的同一要求，必须一并搬过来。至于**后续**步骤，不需要 transcript 相同：`h` 是队首所以 `Out_h` 永远为 0，`In_h` 单调不减，`excess[h]>=overR[h]+ell_j` 与后续无关。

另加一条可用的结构事实：**常数 allowance 下只需测试队首**，因为 `overR[q]` 关于 rank 不增（`out_c1b_indep.txt` part 0：19,381 次决策 0 次分歧）。论文里 O(log n) 的实现因此可以照搬。

**Prop. R5 — HOLDS。** 构造按其文字重建（m 轮 cascade，每轮 `k-1` 个大小 `L` 与 `L/s` 个大小 `s`，终局注入一个 rank 低于受害者的填充作业与受害者），在 `L=k^m` 下对 m=1..6 精确成立。数值与 `Omega(L)` 结论成立；对 `(2-2/k)L` 的辩护只在 k=2 成立。

## 4. C5 文献

**Mu'alem & Feitelson, IEEE TPDS 12(6), 2001（已读原文 PDF）。** 摘要原句确认：conservative 的规则是 “small jobs move ahead only if they do not delay any job in the queue”。正文确认 “there is no danger of starvation, as a reservation is made for each job when it is submitted”，并确认用户估计是**被强制的**：“a low estimation may lead to killing the job before it terminates”，以及 “running jobs will either terminate or be killed when they exceed their declared runtime”。也就是说，规则 R 所要求的“到达时已知、系统强制的 cap `ell_j >= C_j`”在这条文献里就是用户运行时估计，自 2001 年起即是标准做法，不能作为新设定介绍。

**arXiv:1905.03439（Grosof, Scully, Harchol-Balter, *Load Balancing Guardrails*）。** 内容与报告描述一致：按 `r=floor(log_c x)` 的尺寸档、按服务器累计**派发**工作 `G^r_s`，约束 `|G^r_s-G^r_s'| <= g c^(r+1)`，尺寸在到达时已知，定义里不含参照策略。两处要改：该定义在 arXiv HTML 中编号 **Definition 2.1**（默认版与 v1 URL 都如此），报告写的 “Def. 1” 是错指针；计数器也不是只增，服务器清空时会 reset —— “we decrease `G^r_s` to match the minimum among all rank r work counters”。因此 “no refund” 必须限定为“不按单个作业的完成退费”。

**Lindsay, Galloway-Carson, Johnson, Bunde, Leung。** 取到的是同一工作的 Euro-Par 2011 版《Backfilling with guarantees granted upon job submission》（作者主页 PDF：`https://faculty.knox.edu/dbunde/pubs/backfillVars.pdf`；CCPE 25(4):513–523, 2013 是它的特刊版本，Wiley 全文仍打不开）。它提供的保证是：**每个作业在到达时得到一个绝对开始时刻**，由一张 profile 给出，profile 用各作业的（强制的）运行时估计排定，且任何作业的计划开始时刻只会提前、不会推后 —— “Since no job's planned start time is ever delayed, each job's initial reservation is an upper bound on its actual starting time”。作业提前结束时在 profile 上留下 hole，由 compression 重排收回。

对本工作的直接后果：**预留—退费不是新机制**。profile 就是按 cap 预留，compression 就是提前完成后的退还；它比规则 R 更早、更强的一点是保证的是绝对开始时刻，更弱的一点是这个保证不相对于任何参照策略、没有预算参数、也没有逐作业的工作量记账。所以 C5 现在可以定稿的差异是三条，且只有这三条：保证的是相对 FCFS 的逐作业 excess 而不是绝对开始时刻；保证是路径式定理而不是模拟结论；k=1 有点态最大性。报告里 “C5 — novel, with one gap” 与 “rule R is its budgeted generalisation” 这类整体新颖性措辞不能写。

## 5. 可以写进论文的句子

以下英文句子在本次复核下是安全的：

- “Let every job carry a cap $\ell_j$ with $C_j \le \ell_j \le L$ that the system enforces and that is known when the job arrives. Charge a waiting job $q$, for every dispatched job of rank above $q$, its cap while that job is in service and its true service time once it has completed, and accept a proposal $j$ only when $j$ is the queue head or when $\mathrm{over}_R[q]+\ell_j \le Z_q$ for every waiting $q$ of rank below $j$. Then $\mathrm{In}_i \le Z_i$ for every input, every base policy and every job.”
- “With $Z \equiv B$ this gives $\mathrm{excess} \le B$ at $k=1$ and $\mathrm{excess} < B/k+(2-2/k)L$ for $k \ge 2$. The additive constant of the promise falls from $(3-2/k)L$ to $(2-2/k)L$, a drop of exactly $L$ at every $k$.”
- “At one server the reservation never binds: a dispatch epoch has an idle server, so no job of rank above the head is in service and $\mathrm{over}_R$ coincides with the completed-work charge. The single-server gain comes entirely from the forward-looking term $\ell_j$ in the admission test.”
- “At $k=1$ the largest constant allowance with promise $G$ is exactly $B^*=G$, against $B^*=G-L+1$ for completed-work charging, and the statement needs no integer lattice.”
- “At any reachable history with queue head $h$, a wrapper that reads the caps and promises $G$ must reject a later-ranked proposal $j$ whenever $\mathrm{over}_R[h]+\ell_j>G$: relabelling $j$ to its cap leaves the arrivals, the ranks, the revealed sizes of completed jobs and the base's proposals up to that decision unchanged, leaves $W_{\mathrm{FCFS}}[h]$ unchanged because only ranks above $h$ move, and forces $\mathrm{excess}[h]=\mathrm{In}_h \ge \mathrm{over}_R[h]+\ell_j>G$.”
- “For a constant allowance only the queue head has to be tested, because $\mathrm{over}_R[q]$ is non-increasing in rank.”
- “On the integer two-size batch family at one server, around an exact-SJF proposal sequence, the rule closes $\min(1,\max(0,\lfloor(G-\ell)/\sigma\rfloor+1)/n)$ of the FCFS-to-SJF total-wait gap; this is $\lfloor G/\sigma\rfloor/n$ at $\ell=C$ and $(\lfloor(G-L)/\sigma\rfloor+1)/n$ at $\ell=L$, so at $\ell=L$ it matches, and does not beat, the sharp completed-work guard.”
- “At $k=1$ an overtaker of cap $L$ becomes admissible as soon as $G \ge L$, which meets the $L$-scale floor of Proposition~\ref{prop:floor} with equality; for general $k$ the condition is $G \ge (2-1/k)L$, against $G>(3-2/k)L$ for Algorithm~\ref{alg:guard}, a difference of $(1-1/k)L$.”
- “At $k \ge 2$ the rule is not pointwise maximal. With two servers, four unit jobs arriving together and $G=0$, it refuses every later-ranked proposal at the first epoch, although the second server starts the head in the same instant and every job has excess $0$ under any continuation.”
- “There are inputs on which a job has $\mathrm{In}_i=\mathrm{Out}_i=0$ and excess $L(1-((k-1)/k)^m)$, so no charging rule of any kind can remove an $\Omega(L)$ residual; at $k=2$ this reaches the full $(2-2/k)L$, and for $k \ge 3$ it accounts only for the part of it up to $L$.”
- “Conservative backfilling gives every queued job a reservation when it is submitted and lets a job move ahead only if it does not delay any job in the queue~\cite{mualem2001}. With one server per job, the head's reservation is the server that is free at that instant, so both conservative and EASY backfilling reduce to first-come first-served in our model.”
- “Enforced runtime caps are standard in that literature: a job that exceeds its declared runtime is killed~\cite{mualem2001}. Conservative backfilling already reserves a job's cap in a tentative profile and recovers the reservation by compression when the job ends early, and Lindsay et al.~\cite{lindsay2013} keep that profile while reordering it, guaranteeing each job an absolute start time fixed at its arrival. What is different here is the quantity guaranteed --- a per-job bound on the delay relative to first-come first-served, proved pathwise and with a maximal permission rule at one server --- and not the reservation mechanism.”
- “Guardrails~\cite{grosof2019guardrails} charge dispatched work per size rank and per server and balance the counters across servers; the size is known at dispatch, no reference policy appears, and the counters are decreased only when a server empties, never at an individual job's completion.”

## 6. 不得写进论文的句子

1. “the threshold drops by exactly L”（C3）。掉落恰为 `L` 的是加性常数，门槛的差是 `(1-1/k)L`，k=1 时为 0。
2. “k>=2 OPEN”（C2 的 Theorem R3）。k>=2 已被反例证伪，必须写成“假”并给出反例，不能写成未决。
3. “This is the sharpest form of the `Omega(L)` floor … the honest defence of the residual `(2-2/k)L`”（C4a），在 k>=3 不成立。
4. “`E(B)=B` for rule R”不带 cap 限定（C6）。`ell=L` 时 `B<L` 给出 `E(B)=0`。
5. “`E(B)=B+L-1` for rule C”不带族的限定（C6）。本族只验到 `B=10`。
6. “C5 — novel”以及 “rule R is its budgeted generalisation (of conservative backfilling)”这类整体新颖性措辞。预留—退费即 conservative backfilling 的 profile 与 compression；强制 cap 即被强制的用户运行时估计。只能写上一节最后两条被限定的差异句。
7. “arXiv:1905.03439v1 Def. 1”。该定义编号为 2.1。
8. guardrails “no refund” 不加限定。服务器清空时计数器会被下调。
9. “removes the real-valued defect flagged in verification.md §5”。此前复核 §5 已给出实数情形的点态最大规则（`over>G-L` 时触发），`ell≡L` 的规则 R 与之逐动作相同；可写的是“逐作业 cap 把那条规则参数化”。
10. “relabel every dispatched-unfinished job (incl. j)”。k=1 时没有这样的作业；一般 k 下只能重标 rank 高于 `h` 的。

## 7. 判断

规则 R 在 k=1 上是干净、可证、锐的：`In_i<=Z_i` 与 `excess<=B` 无条件成立（10.2M 次逐作业检查 0 次违反），`B*=G` 有通用见证而不只是有限族的上界，闭合式 `min(1,max(0,floor((G-ell)/sigma)+1)/n)` 精确，点态最大性在“读 cap 的 wrapper”类里成立且不需要整数格点。但它的份量不足以在正文占一个定理：k=1 上预留与退费是空转的（`overR` 恒等于 `overC`），真正起作用的只是测试里前瞻的一项 `ell_j`；机制本身——强制的运行时上界加上按上界预留、提前完成即收回——正是 2001 年以来 conservative backfilling 的 profile 与 compression，Lindsay 等人 2013 年还在同一框架里给出更强的绝对开始时刻保证；k>=2 则不仅没有最大性，而且被反例证否，能留下的只有 `In` 里 `kL` 溢出的消失，也就是加性常数从 `(3-2/k)L` 降到 `(2-2/k)L` 这一条。再加上它改变了论文的信息模型（正文明确假设服务量只在完成时可知，而规则 R 需要到达时已知且被强制的 cap），把它放进正文会并行出现两套信息模型。因此结论是：**放进补充材料的一节**——把 Lemma R1、`B*=G` 与闭合式写成该节的命题，把 k>=2 的反例如实写出，把 backfilling 文献放在该节开头交代清楚；正文至多保留一句话的 remark，说明当运行时上界被强制时加性常数恰好下降 `L`。
