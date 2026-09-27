[English](README.md) | **简体中文**

# 预测驱动的非抢占调度与有界插队

这里是一篇论文背后的代码、表格和运行日志。论文题目是 *Prediction-Driven Non-Preemptive
Scheduling with Bounded Overtaking for Shared Execution Services under Deadline-Driven
Bursty Load*。论文印出的每个数字，都能用这个仓库从论文所用的公开数据集重新算出来。

在浏览器里直接看论文：[paper/main.pdf](https://cdn.jsdelivr.net/gh/oscar030406/spjf-guard@main/paper/main.pdf)，
补充材料：[paper/supplementary.pdf](https://cdn.jsdelivr.net/gh/oscar030406/spjf-guard@main/paper/supplementary.pdf)。
这两个链接走的是 jsDelivr 对本仓库的镜像，推送后最多可能晚一天更新。GitHub 自己的文件页面
显示不了这两个 PDF；要从 GitHub 下载，用 [main.pdf](https://github.com/oscar030406/spjf-guard/raw/main/paper/main.pdf)
和 [supplementary.pdf](https://github.com/oscar030406/spjf-guard/raw/main/paper/supplementary.pdf)。

## 论文在讲什么

编程课的自动评测机收下许多学生的提交，放到几台机器上跑。每台机器一次跑一份提交。提交一旦
开始跑就不会被打断，只有跑到时间上限才会被杀掉，论文把这个上限记作 `L`。无服务器平台、
软件构建集群和计算集群也是这样替别人跑任务的。

作业截止前，几百个学生同时提交。一份死循环的提交会占住一台机器直到时间上限，排在它后面的
每一份提交都得等。自然的做法是预测每份提交要跑多久，先跑短的。这样大多数提交都能少等。
但预测一旦出错，某一份提交就会被一次次挤到队尾。在我们研究的这份日志里，有一个任务比按到达
顺序多等了将近 6,000 秒。没有哪个运营者敢把会这样对待用户的调度器放上线。

论文给每个任务一条承诺。它先证明：在任何这样的 `k` 台机器的服务上，一个任务比按到达顺序多等
的时间，等于插到它前面的工作量减去它自己插到别人前面的工作量，再除以 `k`，误差不超过
`(2 - 2/k) L`。然后给任意一种排序规则套
一个守卫：一条小规则，记录已经插到每个等待任务前面的工作量，一旦有任务的这个量达到它的预算，就让
这些任务里最早到达的那个下一个跑。结果是无论预测错得多离谱，没有任务会比按到达顺序多等超过 `G` 秒。`G` 由运营者
定，定理把它变成保证。

守卫之外，论文还有三项结果。第一，已部署的调度器用“最长等待时间”防止任务饿死，论文证明这条
规则也能给出同一类承诺；但在接近满载时，它保住的收益少得多，因为它把任务前面积压的全部工作都
记在账上，而不只是插队的那部分。第二，只凭到达日志就能给出绝对等待时间的上界，运营者可以直接
承诺一个秒数。第三，机器迟报任务完成时，论文给出守卫还能守住的承诺。

这个结论靠回放真实日志来检验：两个编程课评测平台、一个无服务器平台、两个给 Firefox 做构建和
测试的机器池，还有一个计算集群。

这个仓库是复现包，不是能装到服务器上的调度器。

## 仓库里有什么

| 路径 | 放什么 |
| --- | --- |
| `src/spjf_guard/` | 跑主实验的 Python 包。`sim/` 在 `k` 台机器前面模拟一条队列，并对每个模拟出的任务核对论文的界；`data/` 读数据集、处理时间戳、拒绝读封存数据；`features/` 用任务到达时已知的信息算它的特征；`predict/` 拟合预测任务运行时长的模型；`experiment/` 构造回放轨迹、选守卫的参数、算指标、写表 |
| `tests/` | 正确性测试，先于实现写好 |
| `configs/main.yaml` | 主实验的每一项设置，每项都有一句注释说它管什么 |
| `scripts/` | 下面列出的那些命令 |
| `evidence/` | 包本身不产出的那些数字背后的研究，一个研究一个文件夹；见「每个数字从哪来」 |
| `docs/adr/` | 难以回头的决定，一个一页，写明被否掉的备选；`docs/adr/zh-CN/` 是中文原稿 |
| `docs/sealed_access_log.md` | 封存数据读取台账，一次一行，用的是代码写入的中文字符串：包的每次封存运行，以及冻结前当时记下的读取。冻结前所有记账性读取按脚本和日志行列在 `evidence/README.md`；`docs/sealed_access_log.en.md` 是英文版 |
| `paper/` | 论文源文件。表里的数字从 `outputs/` 抄进来，没有脚本往 `paper/` 里写 |
| `CONTEXT.md` | 术语表。一个概念一个词，论文、代码、配置、表格用同一个词。`CONTEXT.zh-CN.md` 是中文原稿 |
| `GENERATED.md` | 每个由脚本产出的文件：来源、重新生成的命令、核对的命令。`GENERATED.zh-CN.md` 是中文原稿 |

`README.md` 是这个文件的英文版，逐节对应，命令相同。

下面提到的两个目录不在仓库里。`data/` 放原始数据集，我们无权再分发。`outputs/` 放流水线写出
的表，下面的命令能把每一张重新生成。

## 环境

Python 3.12。依赖由 [uv](https://docs.astral.sh/uv/) 锁定。这条命令把依赖装进仓库内的
`.venv`：

```bash
uv sync --extra dev
```

下面每条命令都通过一个 shell 变量 `$UV` 来调用解释器。这个变量做两件事：清掉 `PYTHONHOME`
和 `PYTHONPATH`，以防你的 shell 导出了它们（我们有一台机器就是这样，子进程会加载错误的标准
库）；限制线程数，因为仿真器受内存带宽限制，线程多了反而慢：

```bash
export UV="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
  NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-sync"
```

不需要设置任何路径变量。每个输入的位置都写在 `configs/main.yaml` 的 `data` 节里，相对仓库
根目录：

| 配置键 | 指向 | 由谁写入 |
|---|---|---|
| `archive_dir` | `data/codebench/archives/` | 你，下载发布方的逐学期归档时 |
| `raw_parquet_dir` | `data/codebench/parquet/` | `scripts/parse_archive.py` |
| `cache_dir` | `data/derived/codebench_cache_r4/` | `scripts/build_cache.py` |
| `overlay_dir` | `data/derived/overlay_traces/` | `scripts/build_overlays.py` |
| `score_dir` | `data/derived/package_ranking_scores/` | `scripts/fit_scores.py` |

如果某个输入在你的机器上必须放在别处，这些字符串里的 `${NAME}` 会从环境变量展开。仓库里
不允许出现只在某一台机器上存在的路径，`scripts/check_generated.py --only paths` 发现一个就
报错。

## 数据

这里不再分发任何原始数据。运行之前，先从各数据集的发布方下载到 `data/<名称>/`。使用条款
按发布方的原话给出。

| 数据集 | 是什么 | 来源 | 条款 |
|---|---|---|---|
| CodeBench v1.81 | 巴西亚马逊联邦大学一门编程入门课的日志：2016 到 2024 年 18 个学期，学生在线编辑器里的每个动作都有毫秒级时间戳，每次作业都有开始时间和截止时间。主实验跑在它上面 | <https://codebench.icomp.ufam.edu.br/dataset/> | 页面未声明许可证。用于学术研究并引用；原始归档不再分发 |
| ACcoding v1.0.0 | 一个在线评测系统的提交日志，第二个评测平台 | <https://zenodo.org/record/6522395>，doi:10.5281/zenodo.6522395 | 数据集论文写 CC BY 4.0，Zenodo 记录写 "other (open)"。引用，不再分发 |
| OULAD | 英国开放大学的学习分析数据集。这个项目最初是研究它的，那个方向没走通，论文里没有任何结论依赖它 | <https://analyse.kmi.open.ac.uk/open_dataset>，doi:10.1038/sdata.2017.171 | CC BY 4.0 |
| Azure Functions 2021 | 微软无服务器平台两周的函数调用，1,980,951 次 | <https://github.com/Azure/AzurePublicDataset>（Zhang 等，SOSP 2021） | CC BY 4.0 |
| Intel Netbatch 2012 | Intel 内部计算集群的一个池，9,054,066 个任务，Parallel Workloads Archive 的标准格式 | <https://www.cs.huji.ac.il/labs/parallel/workload/l_intel_netbatch/>（Shai、Shmueli、Feitelson，JSSPP 2013） | 归档未给许可证，声明日志对研究者免费，要求致谢和引用。致谢 Ohad Shai、Edi Shmueli、Nir Antebi（Intel）；文件不再分发 |
| LPC-EGEE 2004 | 法国的一个网格计算集群，任务按时限分成六类；用于 `evidence/lpc_egee_queues/` | <https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/> | 归档条款同上。致谢 Emmanuel Medernach 提供日志，Dan Tsafrir 做 SWF 转换，以及 Parallel Workloads Archive |
| Mozilla Firefox CI | 给 Firefox 做构建和测试的两个机器池，2026-08-24 到 09-14 和 2026-09-07 到 09-14。这里唯一记录了每个任务实际等了多久的日志，所以仿真器拿它来校验 | <https://firefox-ci-tc.services.mozilla.com/api/queue/v1> 和 <https://treeherder.mozilla.org/api>，公开、无需认证 | 未声明许可证。取自公开 API，署名 Mozilla；只保留这里采集的这一段，不再分发 |
| UPC Campus Nord Wi-Fi | 一所大学校园的 Wi-Fi 接入点占用数据；早期的一个方向，论文里没有任何结论依赖它 | <https://data.mendeley.com/datasets/55vx86j8wf/1>，doi:10.17632/55vx86j8wf.1 | CC BY 4.0 |

下载文件的 SHA-256 校验和记在作者工作区的 `data/README.md` 里，那个文件不入库。Firefox CI
这一段没有校验和，因为 API 会让旧页面过期，重新下载的字节不完全一样。

数据集里的任何一行都不会进这个仓库。入库的是代码、配置、汇总表和运行日志。已提交的表里那些
像标识符的列，指的是配置（策略、负载档、叠加轨迹、池、学期、模型、目标），不是人。没有任何
学生标识、用户名、邮箱、IP 地址或学生源代码行被提交。

## 复现表格

下面这些步骤从原始数据集重建论文里的每一张开发期表格。在仓库根目录、设好 `$UV` 后运行，一次
一个进程。整个流程在作者的机器上大约要一天，慢的那一步是选守卫的参数。

第 1 步检查代码本身：风格、类型、快速测试：

```bash
$UV ruff check src tests scripts
$UV mypy
$UV python -m pytest -q -m "not slow and not crosscheck"
```

第 2 步把这个包和最早做这项研究时用的两个程序逐任务比对。那两个程序放在 `evidence/main_v3/`
下，只读导入：

```bash
$UV python -m pytest -q -m crosscheck
```

第 3 步把原始数据变成实验的输入。一门课的一个学期很少能把评测机忙到看得出排队，所以实验
把同一批班级复制 44 份叠在一起。每份提交保留自己的星期几和钟点，每个班级的每一份副本各自
随机整周平移，叠起来就是一条带真实截止高峰的轨迹。论文把这样的轨迹叫 *overlay*（叠加轨迹），
用了五条，是五组不同的平移量得到的。*pool*（池）指进入一条叠加轨迹的学期集合：`primary` 是
2020 到 2022 年的六个学期，`validation` 是同一组去掉最后一个学期。守卫的参数只在 validation
的叠加轨迹上选，这样测试它的那个学期从不影响参数。单机叠加轨迹是另外一条轨迹，论文的恒等式
在它上面精确成立。

命令按这个顺序跑：解析十一个开发学期，算它们的静态代码特征，建逐提交缓存，拟合运行时长分数，
再建存有这些分数的叠加轨迹，并在上面选参数。这些命令都不读封存学期。

```bash
DEV=2018-1,2018-2,2019-1,2019-2,2020-ERE,2020-1,2020-2,2021-1,2021-2,2022-1,2022-2
SCORES=data/derived/package_ranking_scores/forward_scores.parquet
$UV python scripts/parse_archive.py --semesters $DEV
$UV python evidence/codebench_service/code_features.py --only $DEV
$UV python scripts/build_cache.py --pool development
$UV python scripts/fit_scores.py --repeat
$UV python scripts/build_overlays.py --pool primary --score-parquet $SCORES
$UV python scripts/build_overlays.py --pool validation --score-parquet $SCORES
$UV python scripts/build_overlays.py --single-server
$UV python scripts/select_parameters.py --workers 2 --out-dir outputs/selection_v4
$UV python scripts/select_aging.py --workers 2
```

`scripts/parse_archive.py --semesters 2022-1 --compare` 把一个学期再解析一遍，与盘上的文件
逐列比对。

第 4 步是实验本身。每个策略在五条叠加轨迹、三档负载上跑，负载档指最忙的那一小时机器有多忙：
50%、80% 或 100%。然后是单机那一行、运行时长预测器的准确度，以及让预测器少看一些历史的
那几组运行：

```bash
$UV python scripts/run_main.py --selection outputs/selection_v4/selected_parameters.csv \
    --out-dir outputs/dev_tables --workers 2
$UV python scripts/run_main.py --prefix k1 --reps 0 --levels 0 \
    --selection outputs/selection_v4/selected_parameters.csv --out-dir outputs/dev_tables/k1
$UV python scripts/eval_scores.py --pool primary
$UV python scripts/run_visibility.py --pool primary --workers 2
```

论文的主结果回放里，每个任务的分数只用它到达时它所在班级在模拟队列里已经拿到的结果来算
（`docs/adr/0007`、`0008`）。它们在第 4 步之后按下面的顺序跑，最后一条命令写出论文抄进去的
表体：

```bash
$UV python scripts/run_consistent_visibility.py --config configs/visibility_development_20260924.yaml \
    --pool primary --workers 2 --resume \
    --controls data/derived/package_ranking_scores/consistent_controls_20260924.npz
$UV python scripts/run_online_visibility.py --pool primary --workers 2 --resume --policies all
$UV python scripts/online_paired_differences.py
$UV python scripts/run_cluster_bootstrap.py --resamples 100 --workers 3
$UV python scripts/sealed_dev_contrast.py
$UV python scripts/emit_paper_tables.py --dev-exact-dir outputs/dev_consistent_visibility \
    --dev-online-dir outputs/dev_online_visibility --dev-cluster-dir outputs/cluster_bootstrap \
    --out-dir outputs/consistent_paper_tables
```

`sealed_dev_contrast.py` 也读封存运行的输出，所以要等下面说的封存运行做完才能跑。第一条命令
用到的控制缓存由同一个脚本加 `--build-controls-only` 建出；`GENERATED.md` 里有这条命令、补充
材料 S3.15 节的两组敏感性重跑，以及在 online 回放下重选参数的命令。

第 5 步核对结果：逐任务等待对照早期程序，叠加轨迹对照它的规格，表对照已提交的副本，论文里
印的数字对照表：

```bash
$UV python scripts/check_reproduction.py --overlay-dir data/derived/overlay_traces
$UV python scripts/check_overlays.py
$UV python scripts/diff_dev_tables.py
$UV python scripts/emit_paper_tables.py
$UV python scripts/check_paper_numbers.py
$UV python scripts/check_generated.py
```

开始之前有四件事值得知道。

已提交的表是在 Windows x86-64 上用锁定的依赖跑出来的，重拟合冻结预测器的回放在那里能逐位
复现它们。在 Linux 上用同样锁定的版本，第一个目标学期的 147,380 个任务里有 714 个的分数在
最后一位上不同（2026-09-25 核对），这些运行会停在「重拟合结果等于已发布分数」的断言上。
叠加轨迹本身在 Linux 上能逐字节重建，前提是把 zip 头里的宿主系统字节改成 Windows 的值。

选守卫的参数很慢。`select_parameters.py` 在每个 validation 单元上试 258 组事先定好的候选
参数（`docs/adr/0005`）。作者的机器上，两个工作进程跑一个单元约 29 分钟，十五个单元约 7.3
小时。结果按单元写盘，崩掉的运行会从停下的地方继续。`--part i --nparts n` 把一个单元拆到
多台机器上，`--from-grid` 从已存的结果重新推导选择而不再仿真。只跑了部分单元的运行写出的
`selected_parameters.csv` 不是最终选择；用 `--from-grid` 把各部分合到一个输出目录里。

界是在运行过程中核对的。第 4 步在每个模拟任务被派工时就断言论文的逐任务界，不是事后在平均
值上查。

`check_reproduction.py` 退出码是 1，这是预期的。它只要遇到一个不相等的逐任务等待就报失败。
早期程序用浮点秒记时，这个包用整数微秒（`docs/adr/0001`）。两者在 15.9 亿次比较里有 0.0043%
不一致，汇总后只有一个印出的数字变了：最重负载下不带守卫的按预测排序策略的 p99 等待，从
62.91 秒变成 62.92 秒。缺口收回比例一个都没变。

`outputs/main_table.tex` 里每个数字外面都包着一个 LaTeX 宏 `\devnum{}`，标明它来自开发期
学期。封存运行的数字会包在 `\sealednum{}` 里，这样印出来的页面上两类数字能分开。

## 封存学期

CodeBench 的三个学期（2023-1、2023-2、2024-1）、ACcoding 按编号排的最后五分之一提交，以及
OULAD 2014 年的几期课程，是*封存*的。没有 `--unseal` 参数和配置锁时，任何会读到它们的代码
路径都在打开文件之前就报错（`src/spjf_guard/data/sealed.py`，理由在 `docs/adr/0004`）。目的
是让「看到测试结果之后再改方法」这件事做不到。

方法在 2026-09-25 冻结（提交 `f32c393`，`protocol_lock.json`），之后三个封存的 CodeBench
学期跑了一次；论文在第 8.2 节和补充材料 S10 节报告它们。那次运行之后对报告脚本的改动，逐个
文件声明在 `docs/post_run_changes.json` 里（`docs/adr/0010`）。

冻结分四步。先用 `--dry-run-sealed` 演练一遍，它只打印会读哪些文件，不打开任何一个。然后写
*配置锁*：一个哈希文件，覆盖代码、配置和每一个输入产物。然后提交。然后跑
`scripts/freeze_protocol.py`，工作区不干净、有东西没提交、或任何一项检查失败，它都拒绝运行。
这之后封存池才带 `--unseal` 跑，且只跑一次。每次这样的运行都往 `docs/sealed_access_log.md`
追加一行：日期、脚本、读了哪些封存学期、产出了什么、谁看了、是否改了设计。
`docs/sealed_run_procedure.md` 有完整命令列表、每步的前提、耗时和磁盘占用，以及崩溃后怎么办。

封存学期上机器实际达到的负载如实报告。事后不回头调机器数去凑目标值，单机副本数也保持开发期
学期上选出的那个（`docs/adr/0006`）。

## 每个数字从哪来

论文印两类数字。

第一类来自 `src/` 里的包。上面的命令从原始数据集重建这些表，`scripts/check_paper_numbers.py`
核对论文印的是不是表里的原样。

第二类来自单独的研究，每个研究跑一次、回答一个问题。`evidence/` 一个研究一个文件夹，共 38
个。每个文件夹放当时跑的脚本、脚本打印的日志（`out_*.txt`）、写出的表，以及一份 `README.md`，
写明问题是什么、论文哪一处用了答案、需要什么输入、是否完成。用大白话说，这些研究覆盖：

- 主评测日志是怎么解析的，怎么和发布方自己的统计数对上的；
- 同一套方法用到第二个评测平台、无服务器平台、计算集群和网格上的结果；
- 仿真器能不能复现 Firefox 两个构建池实际记录下的排队等待；
- 运行时长预测器的比较，包括这个项目一开始用的图神经网络模型；
- 对定理的独立核查，写成审稿报告的形式；
- 稳健性：让用户等到上一份结果才提交下一份来回放日志、改变机器数、在一个真实的双工作机服务
  上跑守卫，以及一个试过又否掉的设计。

`evidence/README.md` 把每个文件夹和它回答的问题各列一行。论文源文件里的注释仍然写着这些研究
当时所在的文件夹名 `prechecks/`，`evidence/PATHS.md` 把每一个这样的名字对应到 `evidence/`。

副本保留了脚本之间互相导入所用的文件名和目录名。作者机器上的绝对路径换成了 `<repo-root>`
和 `<cache-dir>`；没有改任何测量值。`out_*.txt` 日志没有重写。这里不再分发任何原始数据集。
冻结之前，有几个研究为记账读过封存数据：解析并计数 CodeBench 归档、把这些计数和发布方的
统计表对账、算缓存需要的静态代码特征、确定 ACcoding 封存段从哪里开始、审计早先一份项目计划
里 OULAD 的请求计数。`evidence/README.md` 列出了每个脚本和日志行，其中没有一个在封存数据上
算过开销、预测或调度结果。

## 约定

`CONTEXT.md` 是术语表。讨论中定下的词进术语表，之后论文、代码、配置、表格都只用那一个词。
难以回头、事后会让人意外、又是真实取舍的决定，在 `docs/adr/` 里占一页。每个生成的文件在
`GENERATED.md` 里有一行：来源、重新生成的命令、核对的命令；手改生成文件会让
`scripts/check_generated.py` 失败，pre-commit 钩子会跑它。

## 许可证与引用

代码采用 MIT 许可证，见 `LICENSE`。数据集不在其内，各自保留上面数据表里的条款。`CITATION.cff`
给出论文标题和作者。
