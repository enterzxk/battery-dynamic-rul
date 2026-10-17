# 动态RUL标签与信息边界：由本轮审计得到的决定草案
状态：PROPOSED，动态训练尚未开放。本文件是主线程对已保存证据的推论，不是新方法或创新结论。

## 目标必须先固定
循环寿命 T 是某个明确SOH阈值规则下的首次事件坐标。在线时点 k 的精确RUL为 T-k，只在T已按同一坐标/分母/阈值/规则观测到时才能当精确监督值。row_position 和 actual_cycle_number 必须分开，HUST_7-5已存在2周期偏移。等效完整循环、日历时间和循环次数也不能混用。

早期总寿命预测只用前1至100循环估计T。反复增加早期输入并得到一串T预测，可以诊断更新修订，但并不自动构成全生命周期动态RUL实验。动态协议还要明确后续观测时点、输入历史、各预测时点的风险集和评价聚合。

若未来操作策略会改变退化，T的分布还依赖未来策略π。一个可讨论的预测对象是 P(T-k <= r | H_k,T>k,π)，H_k只包含k及以前可得信息。现有记录上的回顾性预测最多对应记录中的策略分布；没有支持时不能将它用于新的充电策略的因果效果或直接驱动服务调度。此处为问题定义建议，尚未由本项目实验验证。

## 实际数据给出的三类不同对象
MATR v11审计169电池/140001 cycles。88个有严格 nominal80% crossing，作者标签与首次crossing一致。81个未出现这一观测事件，作者标签却由末20点线性规则生成：69个估计值位于已观测row范围内，12个在尾端之外。只看label是否小于max(row)不能确认事件被观察到。169/169重建吻合是code-consistent证据，不能证明作者具体运行的生成器版本。

HUST v11同版本数据及labels的77电池，nominal1.1Ah*0.8在文件内都没有crossing。作者label属于待溯源估计值，不能更名为实测精确RUL。用首循环容量作分母会得到另一套事件；这是另一目标定义，不能为了得到事件数而偷偷替换分母。

|对象|可保存的标签|允许的评价|不得混同|
|---|---|---|---|
|真实观测到的同口径事件|T、RUL=T-k、event=1|精确RUL误差，按电池聚合|原始事件与拟合事件|
|到C仍无同口径事件|event=0、T>C、RUL>C-k|删失模型/下界一致性；需处理删失假设|把C当EOL、把回归估计当真值|
|作者用尾段拟合产生的估计|estimated_T、规则/来源/不确定性状态|单独的作者标签复现轨道|精确事件ground truth|

离线监督标签使用后来发生的结果本身不是未来特征泄漏；但标签是事件还是估计，决定了它可以支持什么结论。未来泄漏审计要检查输入预处理、标准化、训练划分、预训练暴露与任何按未来寿命决定的查询规则。

## 当前可以做与尚不能做
已完成CPMLP和CPTransformer的HUST作者totalEOL开发pilot，各1fit/300steps。训练47、验证15、测试推断0；单seed、短预算、验证集选epoch，结果不支持SOTA或完整官方论文复现。MATR/HUST的动态训练门仍关闭。

仅使用88个observed MATR电池做精确RUL比较可以作为明确条件范围的开发子集，但会改变评价群体，并排除81个不同标签状态的电池。不能将子集结果外推为全部电池或电池群体可靠性，也不能假定删失完全随机。BatteryLife原始整理还按尾部SOH与寿命等规则筛选，保留下来的169个本来就不是任意现场电池的随机样本。删失方法本身不能消除已有数据选择偏差。

预训练中出现HUST训练集47电池，可属于合法warm-start；不能叫未见该数据集的冷启动。也不能据此断言HUST测试集15电池已被训练使用。需要逐checkpoint的训练IDs/args/scalers/版本与物理来源对账。统一公平轨道要区分target-only与有额外来源数据、scratch/zero-shot/fine-tune，而非把预训练收益归给某个结构。

## 下一协议的具体冻结条件
1. 保存dataset/release/raw-source hash、阈值分母、threshold、crossing rule、坐标空间、未来策略/记录策略边界；每条query带label_status。
2. 事先固定绝对观测grid，例如10/25/50/100及以后的可用绝对周期。具体列表须在审计每个split风险集后正式冻结；不得用真实寿命百分比筛选在线查询或拿未来T决定输入。
3. 特征只用prefix。容量斜率/统计量、scaler和超参数只能从合法训练role估计。现有processed文件可能经过整条轨迹的清洗；还需检查清洗是否用了未来窗口或未来标签决定早期cycle保留，不能仅凭query代码prefix-safe就说原数据as-of合法。
4. canonical identity先纳入MATR已知5组continued-cell alias；用来源证据继续核对raw ID和跨来源/预训练重叠。未知实体关系保留审计状态。
5. 同一query population、同一legal input、同一split和预算下比较简单强基线，再讨论更复杂模型。所有模型保留每条预测和种子，不因开发结果追加预算救结果。
6. 电池内先聚合、再电池等权；精确误差与censored诊断分表。高估的阈值/分位数及risk校准要在训练/验证中冻结。相邻EOL预测修订衡量更新波动，单调RUL约束不能未经检验强制，因为新信息会使合理预测发生修订。
7. 测试只在方案和选参冻结后运行一次独立确认。跨工况、负迁移、未知条件和校准分别设实验，不用一个平均MAPE代替五类失败模式。

## 证据入口
- reports/matr_label_reconstruction_audit/summary.json 与 per_cell_with_diff.jsonl
- reports/independent_review/matr_label_semantics_protocol_v1.md
- reports/data_schema_audit/run_20261015T164049_918837Z/index_capacity_clarification_zh.md
- reports/independent_review/cpmlp_fit_20261016T034610_311103Z_audit_zh.md
- reports/independent_review/cptransformer_hust_pilot_audit_20261016.md
- src/rul_benchmark/queries.py、audited.py 与19项契约测试

这些要求及审计发现还不是研究创新。尾段估计标签是否放大动态高估/负迁移，是一个可检验候选问题；必须先完成相关文献冲突审查并取得适当独立数据。
