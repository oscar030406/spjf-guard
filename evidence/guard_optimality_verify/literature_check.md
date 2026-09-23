# 文献查新更正说明

本文件原有版本包含两处不能保留的判断：其一把 `Gamma_FCFS(a_i)` 说成 completion-only 模型下在线可观测；其二把作者学位论文的对应完整章节误记成已取得期刊全文。两点均已重新核对并更正。

完整文献判断、阅读深度和链接见 `verification.md` 第 9 节。简要结论是：

- T2 不是 Kleinrock 期望汇总公式的直接重述，但核心工作量平衡属于标准样本路径记账；逐作业 `In/Out/rho/Gamma` 分解适合作为 lemma，不适合作为新的守恒原理来宣传。
- `Gamma_P(a_i)` 可由实际运行观察；`Gamma_FCFS(a_i)` 一般不能，因为 FCFS shadow 可能要在真实运行揭示某个服务量之前决定该作业的完成时刻。`out_t2.txt` 给出两条可观察历史相同但 `D_i` 不同的成对输入。
- 没有在所查材料中找到与 T1(b') 完全相同的最大许可 theorem；Nudge、Nudge-K、conservative backfilling、fair-start-time 和 PV-EASY 是必须讨论的近邻。
- Schwiegelshohn--Yahyapour 期刊文章只读到出版方摘要；精确定义与数值界来自 Yahyapour 学位论文中已完整阅读的对应章节，不能把该章节的 Theorem 2 编号写成期刊版定理编号。
