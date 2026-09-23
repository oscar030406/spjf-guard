# Held-out scope: what the paper promises about sealed data, and what can be delivered

**Question.** Before the protocol is frozen: which sentences of the manuscript promise a
sealed or held-out part, which workloads actually have one that can be run, and where do
the two disagree?

**Answer.** They disagree in two places, both recorded as findings with a remedy list.
The paper says in the introduction and in Section 7 that part of *every* trace was
sealed; only CodeBench has a sealed pipeline that can be run, and the Azure, Netbatch and
two CI workloads have no sealed part at all — `sealed.py` does not mention them. The
sealed list itself is accurate where it is defined. The audit also confirms that, at the
time it was written, no sealed run had happened: the repository held only
`protocol_lock.draft.json`, which is the gate in `sealed.py`.

**Paper items.** The sealed-scope sentence of `paper/sections/01_introduction.tex`
(findings G1 and G2-G3), the output-scope paragraph of `paper/sections/07_data.tex`
(G1-G6), and one location in `paper/supplementary.tex` (Q2).

**Inputs.** None, by construction. Nothing was opened, parsed or hashed: every conclusion
comes from the code, the configuration, the logs, the `out_*.txt` files and the paper
source. No sealed semester is touched.

**Status.** Current as a pre-freeze audit. The notes are in Chinese; the finding table is
readable from the file and section references alone.

**Not copied here.** Nothing; both files are present.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout), `<cache-dir>` (a scratch directory outside the repository) and `<python-root>` (the interpreter install); set them before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

# heldout_scope

冻结前的一次只读审计：论文对留出数据的承诺、各工作负载实际可跑的划分、两者的差距与补救清单，全部在 `heldout_scope.md`。不产数据，不碰封存数据。
