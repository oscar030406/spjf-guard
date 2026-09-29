# ACcoding service side: the same protocol on a second platform

**Question.** Do the cost-prediction and scheduling results of
`evidence/codebench_service_v2/` reproduce on a second, independent online judge
(ACcoding, Beihang University)?

**Paper items.** The ACcoding sizes of Table 4 (Section 7.1) and the sealed-block count of
Section 7.3; the ACcoding difference M5 − M4 quoted in Section 4.3; the ACcoding guard
entry of Table 9 (Section 8.6, block `sim poisson_rho0.8_main`); the ACcoding column of
Table S2 (Supplementary Section S1.5), the lag sensitivity of Supplementary Section S1.3,
and the ACcoding rows, both per-job limits and the id-to-time check of Table S3 and
Supplementary Section S2.4. Supplementary Section S5.4 names this folder in its text.

**Inputs.** `data/accoding/`. The sealed submission-id block (80–100%) is never opened
beyond counting rows and reading the first id.

**Status.** Current. It supersedes the first ACcoding pre-check, which is not included
here.

Absolute paths that were baked into the scripts appear as `<repo-root>` (your checkout) and `<cache-dir>` (a scratch directory outside the repository); set both before rerunning. Raw data is not redistributed with this folder — see `data/README.md` for where each dataset comes from.

---

## Original study notes

ACcoding 服务侧预检 v2：按 `../codebench_service_v2/` 的协议在第二个平台（北航 ACcoding 在线评测）上复跑开销预测与调度，`accoding_v2.py` 是本目录唯一脚本，`out_accoding_v2.txt` 由 `--stage report` 汇总各阶段日志生成（提交编号 80–100% 的封存块全程只读过行数与首个 id）。
