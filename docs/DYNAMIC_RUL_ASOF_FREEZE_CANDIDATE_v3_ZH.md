# 动态 RUL 的 as-of 冻结候选 v3

状态：DRAFT_NOT_FROZEN。training_allowed=false，inference_authorized=false。本文件记录总控基于现有标签审计和本轮静态源码审查作出的协议细化；不报告新模型效果或创新。旧协议与失败证据均保留。本轮 new_fits=0、optimizer_steps=0；历史累计2fits/600steps，test inference=0。

## 预测对象与可见性

以完成整个循环后的决策时点 k 为首个候选口径，输入只能使用该循环及以前数据。循环内预警另设任务；不能用完整循环最大电压或循环内双向清洗支持循环内实时预测。RUL=T-k 的 T 必须固定阈值分母、首次/持续穿越、cycle坐标与物理电芯。HUST_7-5 row和actual cycle差2，未经映射不能混用。

MATR nominal80% 88 observed/81 estimated 与 HUST77 no observed crossing 的证据仍沿用既有审计，不重新扫描pickle。估计标签仅允许作者标签复现轨道；observed精确误差和censored下界/生存评价必须分表。用全寿命构建离线监督结果本身不等于特征泄漏。

## 风险集不宜一概禁止使用存活信息

在 k 时已知电芯仍在役、没有按同规则发生事件，可以用于当时风险集资格。这不要求把已发生事件之后继续构建虚假在线查询。相反，用后来才知道的真实/估计 EOL>100 来排除 k<100 的电芯，会用未来结果选择早期查询群体。pinned loader read_samples_from_one_cell先排除 eol<=early_cycle_threshold；在通过这一筛选的标准1..100路径上 i>=eol停止在该标准控制流中不可达。静态代码中的两个检查不能简单算作两个独立的泄漏效应。

候选查询按绝对循环grid事先注册；到达k、完整观测和在役资格只据k时可知记录判断。EOL百分比可作为离线分层描述，不能作为部署查询计划或输入。固定grid具体值、稀疏缺测规则及各role风险集计数仍待审查，尚未冻结。

## 预处理与实体的剩余门槛

1. 当前pinned MATR代码包含全轨迹硬编码清理、continued-cell拼接和特定尾段cycle修正；stage v11的实际generator commit/config尚未证。需建立release到生成器/原始实体的出处链，或另建明确不改变早期观测的因果处理版本。不得把不确定处理悄悄命名为原版复现。
2. HUST时间累计按循环顺序执行；当前源码未显示未来cycle容量回写过去，但循环内修复使用完整cycle数据。仅能作为cycle完成后口径的候选证据。仍需小型前缀不变性验证和v11来源一致性。
3. 官方collate会清零mask外cycle；Dataset中间样本保留early-threshold全部曲线。所有实际消费者必须执行等价mask，不能由collate存在推断任何自写loader均安全。
4. 文件名split、已知MATR五组alias和物理原始实体、跨源预训练暴露是不同证据层。未知项阻止独立迁移宣称。逐checkpoint实际训练IDs不由MIX_large目录名或通用split代码代替。

## 同输入强基线与五类失败模式

先比较合法prefix下的train-only median、可解释容量统计/线性或树模型与直接时间序列基线；候选具体实现须在合法人口与输入冻结后登记。CPMLP/CPTransformer现有HUST作者total-EOL短pilot只作为开发记录，不能沿用为动态基准结果。

共同主指标为cycles单位的cell-macro MAE，先电芯内再电芯等权，区间按物理电芯/实验batch聚类。早期信息不足按固定绝对grid分层；域外下降按预先隔离工况/来源比较；负迁移需要同目标输入/role/预算的scratch对照；预测震荡用EOL估计修订量并与准确性同时评价；危险高估用正误差与开发期冻结阈值评价。删失对象不塞进精确MAE，风险校准另外评估；无交换性不能自动宣称conformal保证。

未来策略只能解释为记录策略分布或有证据的明确参考策略，不能以固定寿命预测宣称新操作策略的因果效果。没有真实服务决策、资源约束和服务级实验时，TSC适配仍未成立。

## GO/STOP

当前判定 NO_GO_FOR_DYNAMIC_TRAINING，属于数据/协议证据不足，不是模型无效结论。下一可执行动作是对小型release/alias manifest对账，并冻结坐标、事件/删失状态、角色、绝对grid和未来策略说明；源码与数据一致性及独立审查通过前不运行新fit或test。PBT仍先完成validation-only安全依赖审计，任何zero-shot推理需单独冻结配置和预算。

证据入口：docs/DYNAMIC_RUL_LABEL_DECISIONS_v1.md；reports/asof_preprocessing_audit_v1/REPORT.md与manifest.json；reports/matr_label_reconstruction_audit/summary.json；reports/independent_review/matr_label_semantics_protocol_v1.md；repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9/data_provider/data_loader.py:480-528。此处源码控制流由root直接复核。

## 独立审查后的明确补充

来源 reports/asof_preprocessing_audit_v1/root_protocol_review_v2.md，root已核pinned preprocess_MATR.py:168-206。b1c0在cycle>=11、b1c18在cycle>=39改取cycles[cycle+1]，输出cycle_number仍为cycle；两个起点都在前100内。b2c12/b2c44相似规则在252/247起生效。若v11确由此代码生成且cycle坐标对应原始可见循环，当前编号下可能出现下一循环记录，完成当前循环并不能自动保证as-of。源码是否只是修复原始缺号、实际采集顺序/可用时间与编号如何对应，仍须有原始出处链佐证；不能在版本未知时直接宣称已存v11泄漏，也不能默认安全。该映射未解析前，这些受影响cell/query不进入声明as-of-safe的人口。

精确cell-macro MAE只基于observed事件子群时，是该条件子群的结果；MATR88/169不能代表全体电芯可靠性，HUST该口径目前没有observed事件。每电芯实际origin数及组成受grid、缺测和risk-set影响，跨模型必须完全一致。当前CI算法尚未选定：配对cell bootstrap依赖独立cell假设，batch依赖存在时需另冻抽样单位/分层、置信水平、重采样次数与最小独立簇数。删失专用estimand/评分/假设、风险集计数、危险高估阈值以及相邻origin配对仍未冻结。不得由审查完成把NO_GO改为GO。
