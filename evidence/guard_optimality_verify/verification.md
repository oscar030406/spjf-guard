# `optimality.md` 的独立对抗性复核

日期：2026-09-21。复核对象为 `../guard_optimality/optimality.md`、其中引用的程序与日志，以及论文和 `../guard_theory/theory.md` 中的相应定义与证明。全程没有读取或使用任何数据集。

## 结论先行

| 主张 | 裁决 | 必须改正之处 |
|---|---|---|
| T1(a)：两尺寸批到达族上达到“保证的代价” | **CONFIRMED WITH CORRECTION** | 正确的是上下夹逼，不是 guard 的实现点“落在一条直线上”。有限样本带还必须显式加上分母误差 `epsilon_- + epsilon_+`；`theory.md` 第 1879 行给出的 `epsilon=E/D_0` 不是第 1917 行比值的精确误差。`k>=2` 的精确 `F*(G)` 仍未解决。 |
| T1(b)：实例最优性为假，且比值无界 | **CONFIRMED** | 可用 3 个作业给出总等待时间比值趋于无穷的更直接反例；不必只说“节省比例为无穷”。 |
| T1(b')：`k=1` 时 `B*=G-L+1` 点态最大 | **CONFIRMED WITH CORRECTION** | 只对整数服务量、整数预算、`G>=L`、确定性且对所有不透明基策略统一保证的 wrapper 成立。原定义漏掉了基策略提议这一可观察量；原证明中的 `Out_i=0` 不能对任意非队首作业删掉，但可把受害者固定为队首修复。实数服务量时 `+1` 消失，而且没有采用 `>=B` 的常数阈值能实现点态最大规则。 |
| T1(c)：`k=1` 的 size-oblivious frontier | **CONFIRMED WITH CORRECTION** | 精确式须写成 `min(1,max(0,floor((G-L)/sigma)+1)/n)`，并使用锐预算 `B*`；论文当前的 `Bmax=G-L` 通常差一个短作业。一般 `k` 下“guard 的点落在线上”是 **FALSE**，只能说位于带内。 |
| T2：精确恒等式 | **CONFIRMED** | 所有符号和同相位抵消都成立；这是标准工作量平衡与论文既有 busy-period 等式的逐作业重写，不宜作为新的守恒定律主贡献。 |
| T2：自适应预算保持承诺 | **CONFIRMED WITH CORRECTION** | 作为离线/已知服务量规则，承诺证明成立，同相位派发不破坏它；但在论文“服务完成时才知道真值”的信息模型中，`Gamma_FCFS(a_i)` **不可在线观测**，所以“模拟一个 FCFS shadow 即可在线计算”的实现性主张是 **FALSE**。 |
| T3：四个实例相关不等式 | **CONFIRMED WITH CORRECTION** | T3-3 应在最后一个 overtaker 的派发时刻取预算，或额外假设预算单调后改用 `s_i^P`。实际尺寸版 `Lambda` 在论文的信息模型中也不是在线可读；用类别上界得到的是另一个、可部署但更松的量。 |
| T3：tightness 与 Pareto 比例 | **NOT PROVED / CONFIRMED WITH CORRECTION** | 齐次情形只证明总的最坏常数不能统一降低，不证明三个统计量各自“函数意义下最小”。`0.24--0.74` 可按原程序的事后样本最大值口径复现，但不是固定截断上界口径下的比例。 |

## 1. 精确模型、量词和可观察信息

### 1.1 通用调度模型

输入是任意有限作业集 `J={1,...,N}`。作业 `j` 有到达时刻 `a_j>=0` 和服务量 `x_j in [0,L]`；除 T1(b')、T1(c) 明说整数格点外，服务量是实数，允许零。rank 是 `(a_j,input-index)` 诱导的全序，因此 `j<i` 蕴含 `a_j<=a_i`。

有 `k>=1` 台相同单位速度服务器。策略 `Q` 非抢占、work-conserving；只要有空闲服务器和等待作业就立即派发。策略可确定、随机、clairvoyant、预测驱动或完全不按 rank；路径式结论对随机策略应理解为固定每条随机样本路径。事件顺序固定为：同一时刻先处理全部完成，再处理全部到达，最后逐个派发；同相位内的逐个派发顺序属于策略的一部分。FCFS 每次取最小 rank，同相位按 rank 递增。

记 `j prec_Q i` 为 `j` 在派发序列中严格先于 `i`，并定义

```
W_Q[i]    = s_i^Q-a_i,
excess_Q[i] = W_Q[i]-W_FCFS[i],
In_i      = sum{x_j: j>i and j prec_Q i},
Out_i     = sum{x_j: j<i and i prec_Q j}.
```

`rho_i^Q>=0` 是 `s_i^Q` 时刻所有“在序列中严格先于 `i` 派发且仍在运行”的作业剩余工作量之和；`i` 自身和同相位中排在 `i` 之后的作业不计。同相位中排在 `i` 之前的 overtaker 以完整 `x_j` 同时进入 `In_i` 和 `rho_i^Q`，所以在 T2 中精确抵消。`rho_i^P` 的符号是负，`rho_i^FCFS` 的符号是正。

令 `t_0=min_j a_j`，

```
Gamma_Q(t)=integral_[t0,t] (k-b_Q(u))du
          =k(t-t0)-E_Q(t),
```

其中 `b_Q(u)` 是忙服务器数，`E_Q(t)` 是截至 `t` 已执行的总工作。它计入一台作业都没有时的全部空闲容量，也计入系统只有 `r<k` 个现存作业时的 `k-r` 台空闲容量；零时长的逐个派发相位不贡献面积。work conservation 只排除“有等待作业却故意空闲”，不排除作业数不足造成的部分空闲。

### 1.2 “size-oblivious wrapper”的可用定义

原文的定义不足：wrapper 明明要接收基策略的选择，却没有把这个提议列入可观察历史。可证明版本如下。

固定一个不透明的基策略接口。wrapper 在派发时可使用到达/rank、自己的派发与完成历史、已完成作业的真服务量、公开上界 `L`、固定的随机币，以及基策略至今给出的提议序列；它不能读取未完成作业的 `x_j`，也不能读取基策略内部状态或通过接口外的旁路获得 `x_j`。promise `G` 的量词是：对每个有限输入、每个可能的基策略提议 transcript、每条随机路径和每个作业，都有 `excess<=G`。

如果预测分数在服务量重标记时作为外生输入保持不变，则“按预测排序”的基策略可在这个接口下使用，wrapper 仍是 size-oblivious。若预测器或基策略直接读取真实 `x_j`，特别是 exact SJF，则组合后的调度器不是 size-oblivious；T1(b') 只能约束 wrapper 的许可动作，不能把 exact-SJF 组合体称为 size-oblivious。全称量化到不透明 transcript 是重标记证明能成立的必要条件。

## 2. 上次留下材料的复核与处理

- `sim.py` 的事件顺序、`In/Out/rho/Gamma` 和 guard 状态更新是可靠的，故保留并复用。它在每个派发点对每个等待作业分支，确实覆盖非 rank-based 选择；同一时刻的多次派发也逐次分支。相同服务器的标签不会改变任何状态，因此不枚举服务器标签不丢调度。
- `check_t2.py` 原有恒等式核心检查可靠；本次增加低 `G` clamp 搜索、在线不可观测的成对输入搜索和专门的同相位实例。
- `check_t1.py` 原有小实例枚举可靠，但旧的“锐性/重标记”构造用 LIFO 时先取了长作业，没有实现文字声称的 overtaking，旧 `out_t1.txt` 因此不能支持锐性。本次改成显式派发序列，并另加直接的 `B-1` 个单位 overtaker 加一个长度 `L` overtaker；新日志中所有 12 个构造都精确达到 `B+L-1`，而 `B*+1` 在 9 组参数上都恰好超承诺 1。
- 新增 `check_t3.py`，不调用原 T3 程序。先完成自己的随机、穷举和 Pareto 计算，再检查原程序与日志；原程序确实把每个样本的 `max(xs)` 当作 `L`。
- 穷举程序在每个 dispatch 都枚举当前 waiting set 的全部选择。标为“every schedule”的 T1、T2、T3 小实例分别至多 6、5、5 个作业；相应无 cap 或 cap 大于 `5!=120`/`6!=720`，没有截断。T1(b) 的另一个随机最优值 sweep 有 `cap=3000`，因此只作为找反例，不作为穷尽性证据。

## 3. T1(a)：两尺寸族的可达性

### 3.1 修正后的全量词陈述

取 `k>=1,m>=1,n>=1,0<sigma<L`，`m` 个 rank 较小的长作业大小为 `L`，随后 `n` 个短作业大小为 `sigma`，全部在 0 到达。SJF 在同尺寸内按 rank 打破平局。对任意非抢占 work-conserving 策略 `P`，若每个作业都满足 `excess_P<=G`，定义

```
F(P)=Delta(P)/Delta(SJF),
Delta(Q)=sum_i(W_FCFS[i]-W_Q[i]),
F*(G)=max_P F(P).
```

最大值允许 `P` clairvoyant，并在全部 work-conserving 派发选择上取；这不是只在 rank-based 策略中取。要求 `Delta(SJF)>0`。guard 用真实大小 SJF 为 base，取 `B=kG-(3k-2)L>=0`。

令

```
D0 = mn(L-sigma)/k,
E  = 2(1-1/k)L(m+n),
q  = min(1, B/(n sigma)),
A  = (kG+(3k-2)L)/(n sigma).
```

在 `D0>E` 时，正确的有限样本夹逼为

```
q-epsilon_- <= F(guard) <= F*(G) <= min(1,A+epsilon_+),
epsilon_- = E(1+q)/(D0-E),
epsilon_+ = E(1+A)/(D0-E).
```

因此 leading terms 的宽度至多 `2(3k-2)L/(n sigma)`，但完整有限样本宽度还包括 `epsilon_-+epsilon_+`。若只写渐近结论，两项都是 `O((m+n)/(mn))`，其中隐含常数依赖 `k,L,sigma,G/n`。

### 3.2 独立推导

1. 在第一个长作业派发前，所有完成的 overtaker 都是短作业。`B=0` 时 guard 从初始相位起就是 FCFS；`B>0` 时短作业以最多 `k` 个一波完成，故第一个长作业前派发的短作业数为
   `r_g=min(n,k ceil(B/(k sigma)))`，从而 `r_g/n>=q`。
2. 这 `r_g` 个短作业都先于每一个长作业派发，贡献至少 `m r_g(L-sigma)` 的正 inversion sum；同尺寸 inversion 贡献 0。
3. 论文既有 net-overtake 恒等式逐作业求和给出
   `|Delta(Q)-I(Q)/k|<=E`。因此 `Delta(guard)>=qD0-E`，且 `D0-E<=Delta(SJF)<=D0+E`。
4. 用 `Delta(guard)-q Delta(SJF)>=-E(1+q)` 再除以 `Delta(SJF)>=D0-E`，得到上述 `epsilon_-`。
5. 对任一满足 promise 的 `P`，既有必要条件给出每个长作业 `In_u<=kG+(3k-2)L`；故正的长短 inversion 总和不超过 `m(L-sigma)(kG+(3k-2)L)/sigma`。于是 `Delta(P)<=AD0+E`，除以 `Delta(SJF)>=D0-E` 得 `A+epsilon_+`。批到达同机的 SJF 是总等待最优，因此再截到 1。

这里没有逻辑循环，但也不是脱离论文 Theorem 1 的新证明：第 3 步依赖其逐作业恒等式，第 5 步依赖由同一恒等式导出的必要工作预算。只要 Theorem 1 独立成立，这种依赖是合法的；若把 T1(a) 宣称为对 Theorem 1 的独立验证，则不成立。

`theory.md` 第 1879 行写 `epsilon=2(k-1)L(m+n)/(mn(L-sigma))=E/D0`，但第 1905--1917 行实际比值的精确增量是 `E(1+A)/(D0-E)`；前者既漏了 numerator correction 与 denominator correction 的耦合，也与后文自己的式子不一致。`optimality.md` 使用 `O(...)` 避开了等号错误，但“显式带”必须采用上面的两项。

### 3.3 数值攻击

独立枚举覆盖 `k=1..3`、`m+n<=6`、四组 `(L,sigma)` 和每个 `G in [0,4L]`，共 2300 个 `(family,G)` 行：上界、guard 下界、promise 和 `guard<=F*` 均为 0 次违反。可是 guard 有 186 行严格高于所谓 `C_lo`，另有 145 个专门的 `k=1,2` 行不等于它；所以“实现点落在该直线上”被直接否证。

**最终裁决：CONFIRMED WITH CORRECTION。** 保留夹逼和“leading band”结论；删去 exact-line 措辞，写出正确有限样本误差，并继续把 `k>=2` 的精确 `F*(G)` 标为 open。

## 4. T1(b)：实例最优性

取 `k=1`，三个批到达作业依次为 `(L,1,1)`，`G=L>=2`。论文参数给 `Bmax=G-L=0`，guard 等于 FCFS，总等待为 `2L+1`。竞争策略按 `(1,1,L)` 派发，总等待为 3；长作业相对 FCFS 多等 2，两个短作业不受正伤害，所以它对每个作业都满足 `excess<=G`。比值

```
(2L+1)/3 -> infinity.
```

新日志在 `L=10,100,1000,10000` 得到 `7,67,667,6667`。这同时排除了任何输入无关的乘法近似；扩展作业数或 `L` 也使加性差无界。竞争者使用真大小，因此该结论针对 T1(b) 所写的“所有 `G`-feasible policies”；若另行限制竞争者也必须 completion-only，问题会改变。

**最终裁决：CONFIRMED。**

## 5. T1(b')：一台服务器上的最大许可 wrapper

### 5.1 修正定理

假设 `k=1`，`x_j` 是非负整数时间单位且 `x_j<=L`，`L` 为正整数；预算也取整数。wrapper 按 §1.2 的不透明接口确定性运行，并对所有输入和所有基策略 transcript 给出路径式 promise `G`。

若 `G>=L` 且为整数，则：

- 对 `B>=1`，常数预算 guard 的最坏 excess 恰为 `B+L-1`；`B=0` 时最坏 excess 为 0。
- 最大正整数预算是 `B*=G-L+1`。
- 在任意可达历史，只要队首 `h` 满足 `over[h]>G-L`，任何提供 promise `G` 的 size-oblivious wrapper 都必须立即派发 `h`；若 `over[h]<=G-L`，允许任意一个当前等待的后 rank 作业先走这一单步在最坏大小 `L` 下仍安全。因此以 `over>=B*` 触发的 guard 是这个动作集合意义下的 pointwise-maximal wrapper。

若 `G<L`，唯一通用安全的非负常数预算是 `B=0`，所以原文不加 `G>=L` 的 “iff `B<=G-L+1`” 是假的。若 `G` 为实数而服务量仍为整数，最大正整数预算为 `floor(G)-L+1`（仅在该值至少 1 时）；不能直接写实数 `G-L+1`。

### 5.2 重标记证明及原证明的缺口

令 `h` 是某派发时刻的最小 rank 等待作业。因为所有更低 rank 作业已经派发，最终必有 `Out_h=0`。设 wrapper 仍允许 `j>h` 先走，且此刻 `w=over[h]`。把尚未完成的 `j` 的服务量重标为 `L`，并让不透明基策略重放同一提议 transcript；wrapper 到本次决策为止看到的到达、派发、完成服务量和提议完全相同，故仍派发 `j`。一台服务器上恒有

```
excess[h]=In_h-Out_h=In_h>=w+L.
```

FCFS 参照没有“随反例一起移动”：`j>h`，所以改变 `x_j` 不会影响 FCFS 中 `h` 的等待；到达与 rank 也未改变。于是 promise 强制 `w+L<=G`。

原文若把同样推理用于任意非队首 `i` 就不成立，因为 `Out_i` 可抵消 `In_i`。新搜索找到了 `Out_i>0` 且 `over[i]>G-L`、但所有作业仍满足 promise 的实例，故该假设确实 load-bearing。修复方法不是删假设，而是始终选队首 `h`；常数预算下 `over[q]` 随 rank 不增，只要任何作业触发，队首也触发。

原定义的另一缺口是没有规定重标后基策略提议是否保持。exact SJF 会因 `x_j` 改变而改变提议，不能用于 indistinguishability；把基策略定义成不透明 transcript，并利用 promise 对所有 transcript 的全称量化，才能闭合这一步。若 wrapper 可读取基策略代码、内部状态或由基策略泄露的真大小，当前定理 **NOT PROVED**。

整数锐性很直接：未触发时 `over[h]<B`，故最后一个 overtaker 派发前至多累计 `B-1`，再加一个尚不可见的 `L`，得上界 `B+L-1`。反例由受害者、`B-1` 个先完成的单位 overtaker、再一个大小 `L` 的 overtaker 组成，恰好达到上界。

实数服务量时，未触发只给 `over<B`，最坏 excess 的上确界是 `B+L`。任何 `B>G-L` 都可选 `G-L<w<B` 后再放行一个大小 `L` 的作业而违规；`B=G-L` 的 `>=` 测试又会在恰好等号时过早阻止一个仍安全的动作。因此实数情形的点态最大规则是“`over>G-L` 时触发”，没有任何采用 `over>=B` 的常数 `B` 与它完全相同；`+1` 完全来自整数格点。

随机 wrapper 只有在 promise 对每条随机路径都成立时可逐路径套用上述论证；若 promise 只在期望或高概率意义下成立，本证明不覆盖。

**最终裁决：CONFIRMED WITH CORRECTION。** 修正后的 theorem 有价值，但当前定义和量词必须先改。

## 6. T1(c)：一致性—稳健性前沿

在 T1 两尺寸批到达族、`k=1`、整数服务量、exact-SJF base、按 §1.2 定义的 wrapper 类中，令 robustness 为对所有输入/基 transcript 的最坏逐作业 `G`，consistency 为该族上 exact predictions 时闭合的 FCFS-to-SJF 总等待差比例。T1(b') 表明最多能让

```
r(G)=min(n,max(0,floor((G-L)/sigma)+1))
```

个短作业越过长作业，故

```
C_bo(G)=r(G)/n.
```

`B*=G-L+1` 的 guard-around-SJF 恰好实现它。803 个小实例行上，穷举许可动作得到的前沿与公式 0 次不符，锐 guard 0 次不符；论文使用的 `Bmax=G-L` 有 130 行低于前沿。

这不是“所有 size-oblivious policies”的前沿：exact SJF 自身读取真大小；它是“对任意外部基策略提议进行保护、但 wrapper 自身不读未完成大小”的前沿。一般 `k` 下，T1(a) 只把 guard 和 `F*` 放进一条带，不能推出实现曲线本身是直线；小实例中 186 行严格高于其 lower line。

**最终裁决：CONFIRMED WITH CORRECTION**（仅 `k=1` 的修正式）；一般 `k` 的 exact-line 版本为 **FALSE**。

## 7. T2：精确恒等式与预算规则

### 7.1 恒等式的逐行推导

对每个实数服务量输入、每个 `k>=1`、每个非抢占 work-conserving `P` 和每个作业 `i`，在 `a_i` 同时到达作业已加入之后读取状态。令 `R_i^Q` 为此时 rank `<i` 作业的剩余工作量。`i` 在 `[a_i,s_i^Q)` 一直等待，所以除零长度区间外所有 `k` 台服务器都忙；按 rank 分解期间执行的工作，精确得到

```
k W_Q[i]=R_i^Q+In_i-Out_i-rho_i^Q.                 (1)
```

FCFS 的 `In=Out=0`，故

```
k W_FCFS[i]=R_i^FCFS-rho_i^FCFS.                   (2)
```

另一方面，对相同到达工作过程 `A(t)`，

```
U_Q(t)=A(t)-E_Q(t),
U_P(t)-U_FCFS(t)=Gamma_P(t)-Gamma_FCFS(t).          (3)
```

在 `a_i` 之后读取时，rank `>=i` 的同时到达作业在两边都尚未执行且贡献完全相同，因此

```
R_i^P-R_i^FCFS=U_P(a_i)-U_FCFS(a_i)
              =Gamma_P(a_i)-Gamma_FCFS(a_i).       (4)
```

用 (1) 减 (2)，再代入 (4)，即

```
k(W_P[i]-W_FCFS[i])
 =In_i-Out_i+(Gamma_P(a_i)-Gamma_FCFS(a_i))-rho_i^P+rho_i^FCFS.
```

没有一步使用 `k=1`。`k=1` 时任意 work-conserving 策略有相同累计执行量，两个 Gamma 相同，且派发 `i` 时没有别的服务器，两个 rho 都为 0，才退化为 `excess=In-Out`。同相位 overtaker 的 `+x_j` 与 `-rho` 精确抵消；专门的 `k=2,3,4` 同相位检查为 15 个作业、0 失败。

### 7.2 数值攻击

自己的实现先用 FCFS 的 `In=Out=0`、已知 floor 构造、旧的绝对界和两尺寸命题做校准。随后在 `k=1..4`、零/相同服务量、密集 ties、非批到达下，使用 FCFS、SJF、逆 rank、最长优先、固定的非 rank score、随机选择和 guard 多类策略：随机部分 169,736 个作业检查；每个派发分支穷举 2,073 个调度、9,435 个作业；`k=1` 再查 35,564 个作业。总计 214,735 个逐作业恒等式检查，恒等式、Gamma/R、Gamma/U 均 0 失败。

### 7.3 自适应预算：数学保证与在线实现是两件事

写 `D_i=Gamma_P(a_i)-Gamma_FCFS(a_i)`，并在 `i` 到达时冻结

```
b_i=max(0,k(G-L)-(k-1)L-D_i).
```

在论文的标准范围 `G>=(3-2/k)L`，有 `D_i<(k-1)L`（`k>=2,L>0`），所以 raw budget 非负，clamp 不起作用。guard 给 `In_i<b_i+kL`，而 T2 给

```
k excess_i <= In_i+D_i+rho_i^FCFS
             < b_i+kL+D_i+(k-1)L = kG.
```

同相位项已经在恒等式中抵消，不会破坏证明。16,000 次标准范围运行中 0 promise violation。

clamp 对所有 `G>=0` 其实也可证明安全，但原文没有给出所需分情况。令 `G0=(2-1/k)L`：若 `G<=G0`，在首次偏离 FCFS 之前 `D=0`，所有新预算都 clamp 为 0，零预算又强制 FCFS，故首次偏离不可能存在；若 `G>G0`，raw 为正的作业用上式，raw 非正的作业预算为 0、不会被 higher-rank 作业 overtaken，故 `In_i=0`，并有 `k excess_i<=D_i+rho_i^FCFS<2(k-1)L<kG`。低阈值随机搜索 18,000 次运行、108,177 个作业，其中 39,090 个 raw budget 为负，0 次违反；这只是证明的压力测试，不替代证明。

然而 `D_i` 在论文的信息模型下不可在线计算。反例有 `k=2`、到达

```
a =[0,0,1,1,2,7]
I : x=[4,1,1,4,5,2]
I': x=[4,1,1,5,5,2].
```

固定策略 `P` 在两输入的开始时刻都是 `[0,0,1,4,2,7]`；唯一变化的 job 3 在 `t=7` 仍未在 `P` 下完成，所以到 victim 到达时两条可观察历史相同。FCFS 开始时刻均为 `[0,0,1,2,4,7]`，但 job 3 在两个 shadow 中分别于 6 和 7 完成，导致 `D_i=-1` 与 `0`。要推进 shadow，调度器必须在 `P` 尚未揭示 `x_3` 时知道它是 4 还是 5；单纯“并行模拟 FCFS”不能产生未知完成时刻。

若模型改为服务量在到达时已知，FCFS shadow 当然可在线维护，且一份事件队列即可做到每事件对数开销。若仍坚持 completion-only 模型，该预算只能作为事后证书、clairvoyant 比较规则或用上下界替代后的另一个保守算法，不能作为当前 Algorithm 1 的在线 corollary。

**最终裁决：恒等式 CONFIRMED；promise 的离线数学命题 CONFIRMED WITH CORRECTION；当前信息模型下的在线可计算性 FALSE。**

## 8. T3：实例相关常数

### 8.1 量词与定义

对任意实数服务量输入、任意 `k>=1`、任意两个非抢占 work-conserving 策略，定义 `Lambda_r(S)` 为集合 `S` 中最大的至多 `r` 个原始服务量之和（空位补 0）：

```
Lambda_{k-1}(t)     : {j:a_j<=t},
Lambda^{<i}_{k-1}   : {j:j<i},
Lambda^{>i}_k(t)    : {j:j>i,a_j<=t}.
```

这些定义使用真实 `x_j`，包括尚未完成作业；因此它们是实例证书，不自动是 size-oblivious 在线量。若用每类公开上界 `L_c` 代替 `x_j`，同样的计数证明给出可部署上界，但那不是文中所写的 actual-size `Lambda`。

### 8.2 四步推导

1. **T3-1。** 令 `D(t)=U_{Q1}(t)-U_{Q2}(t)`。到达给两边相同跳跃，故 `D` 连续，而 `Lambda` 只向上跳。若 `U_{Q1}(t)>Lambda_{k-1}(t)`，`Q1` 中不可能只有至多 `k-1` 个现存作业，否则其剩余工作不超过这 `k-1` 个原始大小之和；所以 `Q1` 的 `k` 台服务器全忙，此时 `D'=b_{Q2}-k<=0`。因此 `D` 不能从下方穿过非降障碍 `Lambda`；交换两策略即得绝对值界。这里不需要 rank-based 选择。
2. **T3-2。** 在 T2 中取 `D_i<=Lambda_{k-1}(a_i)`，丢掉 `-rho_i^P<=0`，并注意 FCFS 在 `s_i` 前仍运行的至多 `k-1` 个作业都满足 rank `<i`，故 `rho_i^FCFS<=Lambda^{<i}_{k-1}`。直接得到所写上界。
3. **T3-3。** 若 `i` 有 overtaker，令 `tau` 是最后一个 overtaker 的派发时刻。此前已完成 overtaker 的总工作严格小于 `budget(i,tau)`，而 `tau` 时至多有 `k` 个已派发但未完成的 overtaker（刚派发者加其他服务器上的至多 `k-1` 个）；它们之和至多 `Lambda^{>i}_k(s_i^P)`。故严格正确的式子是
   `In_i<budget(i,tau)+Lambda^{>i}_k(s_i^P)`。
   若预算随时间不减，可再以 `budget(i,s_i^P)` 代替；若只知道统一 cap，则以 `Bmax` 代替。原文把 `budget(i,t)` 留成自由的 `t`，量词不完整。
4. **T3-4。** 把 T3-2、T3-3 和 `budget<=Bmax` 相加；有 overtaker 时严格号来自 T3-3。没有 overtaker 时只能保留弱式。

随机检查含 `k=1..4`、非批到达、ties、相同大小、FCFS/SJF/逆 rank/最长优先/非 rank 与 guard：T3-1 共 132,424 个时刻、T3-2 共 145,180 个作业，T3-3/T3-4 均 0 违反。另在所有枚举调度对上查 23,478 对、170,326 个时刻，T3-1 为 0 违反。

当所有大小都等于 `L`，三个 `Lambda` 确实退化为 `kL,(k-1)L,(k-1)L`，所以 T3-4 回到既有 worst-case 总常数。结合既有齐次锐性族，这支持“总的统一 worst-case 不能降低”；它不证明每个 `Lambda` 项分别是给定其余统计量后的最小函数，也不排除利用三个统计量之间相关性的更小联合函数。故原句“none of the constants can be lowered as functions of these statistics”超出了证明。

### 8.3 自己的 truncated-Pareto 计算

选择 `alpha=1.5,xmin=1,hard cap=1000,N=200`，独立生成 5,000 个样本，seed 73621。结果为：

| `k` | `E[Lambda/((k-1) sample_max)]` | `E[Lambda/((k-1) hard_cap)]` |
|---:|---:|---:|
| 4 | 0.6825 | 0.0444 |
| 8 | 0.4648 | 0.0263 |
| 16 | 0.3139 | 0.0161 |

完成自己的计算后再看原程序：它设置 `Lm=max(xs)`，故第一列复现其 `0.681,0.466,0.312`。原文 `0.24--0.74` 是把 `alpha=1.1,1.5,2.0`、`k=4,8,16` 的多个设置合并成范围，并使用每个有限样本的事后最大值；这在“实例上令 `L=max_j x_j`”的数学口径下成立。若“truncated”意指部署前已知固定截断/timeout `L=1000`，则相应比例是第二列量级，不能把第一列称为相对 published timeout constant 的比例。数值主张必须同时写 `alpha,N,cap` 和 `L` 的口径。

**最终裁决：四个不等式 CONFIRMED WITH CORRECTION；逐项函数最优性 NOT PROVED；`0.24--0.74` 在事后样本最大值口径下 CONFIRMED WITH CORRECTION。**

## 9. 查新与贡献边界

### 9.1 T2 与经典守恒/样本路径恒等式

- Kleinrock 1965 的守恒律是在 Poisson、多优先类单服务器模型中，`sum_p rho_p W_p` 对一类 discipline 的**期望汇总量不变**。它不是这里的多服务器、有限输入、逐作业 `In/Out/rho/Gamma` 等式；阅读深度为出版方摘要。
- Wolff 1970 的 *Work-conserving priorities* 统一了 GI/G/1 的 work-conserving priority 分析；阅读深度为出版方摘要。
- Green--Stidham 2000 明确研究“每条样本路径、每个时刻”的强守恒律及 scheduling/fluid 应用，但摘要展示的对象仍是类别加权系统工作量/作业数等汇总量；阅读深度为摘要与书目信息，未据此引用定理号。
- El-Taha--Stidham 的 *Sample-Path Analysis of Queueing Systems* 是更广的样本路径方法背景；这里只读到出版方书目与简介，未检查具体定理。Wolff 也未读全文。

因此 T2 不是 Kleinrock 公式的逐字重述，但其核心 `U=A-E`、两个 work-conserving 运行相减得到 idle-capacity 差，是标准样本路径工作量记账；另一半 busy-period 分解已经在论文自己的 Theorem 1 中。最稳妥定位是“有用的逐作业精确分解 lemma”，而不是新的 conservation law；真正可能产生方法价值的在线预算恰好又被不可观测性反例阻断。

### 9.2 `k=1` 最大许可性与相邻文献

- Nudge（全文，arXiv:2106.01492）限制每个大作业最多参与一次 swap；这会附带产生单服务器有界额外延迟，但论文目标是响应时间分布的随机占优，并未给出可调 work budget 或上述 pointwise-maximal theorem。Nudge-K（摘要/预印本说明）把可交换数量推广到 `K`，仍是按次数和类型。
- Conservative backfilling 给每个作业一个不再被后续 backfill 推迟的预留开始时刻；“Backfilling with Guarantees Granted upon Job Submission”全文说明这种 reservation guarantee。它是基于运行时间上界和资源配置的绝对开始时刻承诺，不是相同输入 FCFS 等待的加性差。
- Sabin--Sadayappan 的 fair-start-time 文献（论文摘要及可检索全文描述）把作业 `i` 的参照定义为截断到 `i` 的作业流在同一 scheduler 下的开始时刻，并用 actual-start 减 FST 作事后不公平度；它不是在线强制的最宽松 wrapper。
- PV-EASY（全文）研究在并行刚性作业与预测误差下不违反 reservation 的 strict fairness，可视为 `G=0` 精神相近端点，但模型、参照和抢占机制均不同。
- 没有在所查全文/摘要中找到“completion-only、任意基策略、对 FCFS 的逐作业加性 promise、且点态最大”的同一定理。这只能支持谨慎的新颖性陈述，不能证明文献中绝无先例；相关工作应明确承认最大许可监督规则这一更一般思想并非调度领域独有。

### 9.3 Schwiegelshohn--Yahyapour 2000

出版方页面确认文章为 *Fairness in Parallel Job Scheduling*, Journal of Scheduling 3(5):297--320 (2000)，并确认模型是运行时间在释放时未知的在线并行作业、使用抢占、按资源消耗取权重且证明 makespan 与 weighted completion time 的常数竞争比。出版方只提供摘要；没有取得该期刊版本全文，因此下面不引用期刊文章的定理编号。

作者 Yahyapour 的学位论文 §3.3 提供了完整对应章节。其精确定义可形式化为：对每个输入 `I` 和每个作业 `i`，若 `I_{<=i}` 删除所有在 `i` 之后提交的作业，则策略 `S` 为 `lambda`-fair 当且仅当

```
flow_i(S,I) <= lambda * flow_i(S,I_{<=i}).
```

所以它是逐作业、对每个输入的 worst-case、乘性 flow-time 条件；参照是删掉后到作业的反事实输入，不是同一输入上的 FCFS 调度。模型中作业 `i` 同时需要 `m_i` 个节点，处理时间 `p_i` 在释放时未知，采用 gang scheduling，抢占有相对代价 `sbar`，并取 `w_i=m_i p_i`。该完整章节的 Theorem 2 给 PFCFS 的界为 `(2+2 sbar)`-fair、weighted completion cost `<(3.562+3.386 sbar)OPT`、makespan `<(4+3 sbar)OPT`；这些编号和数字只归于已打开的学位论文章节，不声称是期刊版编号。阅读深度：期刊出版方摘要；学位论文对应章节全文。

`lambda`-fairness 把实际 flow time 与“删去所有后到作业”的同策略反事实 flow time 相比，以作业自身基线作乘法界，并允许抢占。这里的保证把实际等待与**同一完整输入**上的 FCFS 等待相比，以固定的 `G` 作加法界，且模型非抢占、单节点作业上 `k` 台服务器。

## 10. 30 页论文中的取舍建议

### 主文保留

1. **T1(a) 修正版定理**：这是既有“任何保证都要付代价”的匹配 achievability，直接回答贡献只是已知性质拼接的批评。主文写完整量词、leading band 和两个有限样本误差；明确只在两尺寸批到达族上近似匹配，`k>=2` 的 exact `F*` 开放。
2. **T1(b') 修正版 theorem + T1(c) 的 `k=1` corollary**：它给出 wrapper 限制类中的精确最大许可性与精确前沿，比单纯再加一个界更能说明结构性贡献。主文必须先把 opaque-base transcript、整数单位、`G>=L`、确定性/pathwise promise 写清，并用一段说明 exact SJF 组合体本身不属于 size-oblivious 类。
3. 相关工作中正面加入 Schwiegelshohn--Yahyapour、conservative backfilling/FST、Nudge/PV-EASY 的区别，尤其不能再暗示逐作业 worst-case fairness 这一目标本身无人研究。

### 补充材料保留

1. T1(a) 的全部代数、枚举表和 `k>=2` 两个失败 closed-form candidate。
2. T1(b) 的无界三作业反例；它是重要边界，但不值得占主文 theorem 位。
3. T1(b') 的完整重标记、整数锐性、实数严格阈值和随机保证范围。
4. T2 恒等式作为 lemma/记账恒等式，以及离线自适应预算的条件性 corollary；清楚标成 completion-only 模型下不可部署。
5. T3-1--T3-4 作为技术 proposition，并把真实大小证书与类别上界部署版分开；Pareto 结果只作说明性实验，参数与 `L` 口径齐全。

### 当前版本不要进入论文

- 一般 `k` 下“guard 实现点落在直线”的说法。
- `theory.md` 第 1879 行的错误 exact `epsilon`，以及省略 `epsilon_-+epsilon_+` 的“显式带”。
- 没有 opaque-base 定义、没有整数/`G>=L` 条件的 T1(b')。
- completion-only 模型下“FCFS shadow 使 `D_i` 在线可观测”和据此把自适应预算作为已实现方法的说法。
- T3 三个 `Lambda` 各自函数最优的断言，以及不说明 sample maximum 的 `0.24--0.74` 标题数字。
- 把 T2 称作全新的 conservation law 或把 `k=1` 有界 overtaking 的思想本身称作首次提出。

## 11. 可复现记录

所有程序均为单进程、小实例，无并行和等待循环。日志对应：

- `check_t1.py` / `out_t1.txt`：T1(a)--T1(c)、无界比值、整数锐性、实数边界。
- `check_t2.py` / `out_t2.txt`：214,735 个恒等式作业检查、预算 promise、在线不可观测 witness、同相位检查。
- `check_t3.py` / `out_t3.txt`：T3 随机与全调度对检查、两种 Pareto 分母口径。

## 参考链接与阅读深度

- Kleinrock, 1965，出版方摘要：[A conservation law for a wide class of queueing disciplines](https://doi.org/10.1002/nav.3800120206)。
- Wolff, 1970，出版方摘要：[Work-conserving priorities](https://doi.org/10.2307/3211968)。
- Green and Stidham, 2000，摘要/书目信息：[Sample-path conservation laws, with applications to scheduling queues and fluid systems](https://doi.org/10.1023/A:1019183220080)。
- El-Taha and Stidham，出版方书目/简介：[Sample-Path Analysis of Queueing Systems](https://doi.org/10.1007/978-1-4615-5721-0)。
- Schwiegelshohn and Yahyapour，出版方摘要：[Fairness in Parallel Job Scheduling](https://onlinelibrary.wiley.com/doi/abs/10.1002/1099-1425%28200009/10%293%3A5%3C297%3A%3AAID-JOS50%3E3.0.CO%3B2-D)；对应完整章节：[Yahyapour dissertation](https://eldorado.tu-dortmund.de/server/api/core/bitstreams/6974f397-737b-4646-9ce8-75cd1226ca5c/content)。
- Grosof et al.，全文：[Nudge: Stochastically Improving upon FCFS](https://arxiv.org/abs/2106.01492)。
- Sabin and Sadayappan，摘要及可检索章节：[Unfairness Metrics for Space-Sharing Parallel Job Schedulers](https://doi.org/10.1007/11605300_12)。
- Lindsay et al.，全文：[Backfilling with Guarantees Granted upon Job Submission](https://faculty.knox.edu/dbunde/pubs/backfillVars.pdf)。
- Yuan et al.，全文：[PV-EASY](https://madsys.cs.tsinghua.edu.cn/publication/pv-easy-a-strict-fairness-guaranteed-and-prediction-enabled-scheduler-in-parallel-job-scheduling/HPDC2010-yuan.pdf)。
