# 0004 封存数据的保护放在路径层，由配置锁加显式开关解除

要防的不是「文件被打开过」，而是「看了测试结果再改方法」。约定、注释和 code review 都挡不住一次随手的 `read_parquet`，而封存学期在磁盘上和开发学期挨着。

保护写在 `src/spjf_guard/data/sealed.py`：封存的学期、ACcoding 编号区块和 OULAD 学年只在这一处命名；任何会读到它们的调用必须先过 `guard_semesters` / `guard_id_block` / `guard_oulad_year`，而这三个函数在两件事同时成立之前一律抛 `SealedDataError`——根目录存在**冻结的** `protocol_lock.json`（草稿 `protocol_lock.draft.json` 不算），并且调用方显式传了 `--unseal`。同一处还有一张开发学期白名单：既不在白名单又不是封存学期的学期一律报错，免得多一个学期悄悄溜进训练集。每次获准的封存读取往 `docs/sealed_access_log.md` 追加一行，列就是那份台账已有的六列。

两件事一起要求，是因为它们防的东西不同。配置锁保证方法在读之前已经定死；`--unseal` 保证这次读取是有人主动决定的，不是某个默认参数的副作用。任何一个单独都不够：只有锁，一次例行重跑就会顺手读进去；只有开关，方法还能在看到结果之后改。

拒绝发生在打开文件之前，所以它可以在没有封存数据的机器上被测试——`tests/test_sealed_data.py` 的 20 条全部不碰任何数据文件。代价是解封那天要多做一步手工操作：把草稿改名为 `protocol_lock.json`。这一步故意不写成脚本。
