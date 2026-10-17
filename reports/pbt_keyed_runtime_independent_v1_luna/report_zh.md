# Keyed runtime contract 独立静态复核

复核结果：PASS_STATIC_SOURCE_ONLY_WITH_LIMITATIONS。主控 GO/STOP 决策未改变，执行门仍关闭。本复核只读固定源码和小型 JSON/CSV，不读取二进制或 embedding 值，没有新解码或模型操作。

15/15 只有 aggregate coverage 支持。join receipt 记录 covered=15、target=15、missing=0，同时声明 receipt 不含 key names；CSV 中有按固定 loader 规则派生的 DKP key，但每行 exact-per-cell-receipt 字段为空。因此逐电芯 key-to-array binding 仍未证。固定 loader 在 data_loader.py:902-907 使用去掉 .pkl 后的 cell_name 查询映射；:918-920 在查询缺失时换成零向量。该查找规则不能替代实际逐键映射证据。源码哈希与行号见 review.json。

valid_cycle_number 的源码表达式核对无误：data_loader.py:1052-1053 取 len(cycle_data)。合同引用的小型 metadata 没有每 cell cycle_data 长度；本次未读 cell pickle，因此每个有效长度未证。

循环及筛选的静态描述与源一致：data_loader.py:1114-1116 丢弃 df 缺失或 EOL 不大于 threshold 的记录；:1126 从 seq_len 遍历到 threshold（含端点）；:1127-1134 在达到 EOL 或 i 超过 valid_cycle_number 时 break；:1136-1137 将 mask[:i] 置1。seq_len=1、threshold=100 时，只有每个条件均满足才可有每 cell 最多100个候选 prefix。CSV 的1500是条件投影，不是观察到的运行行数或 mask。

finetune_PBT.sh:9-10 设置 seq_len=1、early_cycle_threshold=100，没有设置 eval_cycle_min/max。evaluate_model.py:485-486 默认值为10和10，:490-497 读取运行参数并处理负值，:668-674 将值传给 provider。CSV 的每 cell 第10 prefix 只是使用默认值且该 row 存在时的 projection；active CLI/config 未冻。

collate 静态路径可具体到 data_factory.py:241-249：非 lookup PBT 选择 my_collate_fn_withId 并交给 DataLoader；data_loader.py:163-194 说明静态 stack 与 mask 清零行为。没有运行样本，因此实际输出 shape、row ID、DKP 对齐和 mask 数值仍未证。

inactive proposal 保持 INACTIVE_SOURCE_PROPOSAL_ONLY_NOT_EXECUTED。执行授权均为 false；计划限 pinned HUSTval15，且 key-only/cycle-count/最小 val-only 证据都要求另行授权，没有扩大到其他 split、payload、模型构造、strict load、forward、metrics、fit 或 test。没有从局部源码缺项推断整个项目不存在相关行为。

被审计 JSON/报告、contract、CSV、proposal 与固定 source 的路径、SHA-256、行号均列在 review.json。结论保持纯静态来源层级，不证明 runtime pairing、等价性或 scientific readiness。