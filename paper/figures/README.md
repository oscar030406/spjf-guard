# figures

论文插图，每图一个 `.tex`，全部用 TikZ/pgfplots 在 LaTeX 里直接画，不放任何外部图片文件。
文件名 `fig_<label>.tex`，`\label{fig:<label>}` 与文件名一致；`main.tex` 不直接引用，由用到它的那一节 `\input{figures/fig_xxx}`。
图里的每个数字都必须来自正文已有的表格或 `../../prechecks/` 的输出文件，文件开头的注释写明出处（哪张表、哪一列），caption 里也要写。不在图里做新计算。
新图放进这里，并在对应小节 `\input` 一行、正文里 `\ref` 一次。

- `fig_threejob.tex` — §1 三作业时间线；出处：§1 正文里的算术
- `fig_guard.tex` — §5 guard wrapper 示意与计费；出处：Algorithm 1 与 §5.2 的定义
- `fig_gapvsg.tex` — §8 gap closed vs 承诺 G；出处：`tab:guard` 的 Gap closed 列
- `fig_excess.tex` — §8 最坏单作业超额，有无 guard；出处：`tab:guard` 表头与 `tab:adv`
