# 独立审查：DYNAMIC_RUL as-of freeze candidate v2

审查日期：2026-10-16
审查模型：gpt-6-luna/high
结论：**NO_FREEZE / NO_TRAINING_GO**。候选的整体审慎立场及 NO_GO 有证据支持；配置状态仍为 DRAFT_NOT_FROZEN，training_allowed=false、inference_authorized=false。发现一个需要明确补入协议的 source-backed as-of 风险，以及若干未冻结的估计对象/统计定义。此静态审查不是训练许可或科学 GO。

审查输入及 SHA-256：
- `docs/DYNAMIC_RUL_ASOF_FREEZE_CANDIDATE_v2_ZH.md`：`fc42a43dc6ca1e4a750f164e12df9f347c928c15958de9729d93b83a2828e939`
- `configs/protocols/dynamic_rul_v2_candidate.json`：`679811e9e168e756f983af453da283f4d21541b7e050113a409f4c57697ef283`
- 本审查只读以上文件及下列静态/既有审计证据；没有改协议或共享状态。

## 具体问题与修订建议

### 1. [BLOCKER] MATR 的 cycle-level as-of 有“下一 cycle 代入当前编号”例外

候选第7行把“完成整个循环后”设为输入边界，第19行提到 MATR 有特定尾段 cycle 修正；但它没有明确指出该修正在 pinned 源码中会令当前 cycle 索引携带下一 cycle 的测量。

证据：pinned `process_scripts/preprocess_MATR.py` SHA-256 `ada511cf294862f123def7ff52e060a84e935ab1d3cec8efe3633b46015349b9`，168-206行。具体为：
- `b1c0` 从 cycle>=11 起把 `cur_data` 改为 `cycles[cycle+1]`（175-180行）；
- `b1c18` 从 cycle>=39 起同样改用下一 cycle（189-192行）；
- 随后输出仍将 `cycle_number=cycle`（196-205行）。
这两个起点落在默认 early threshold=100 内（`run_main.py:74`，SHA-256 `a90a5e39bd3ed26b7dad20b42f2ffaa0d18b78a9cbb76788dfbc3a36357ea216`）。若已存 v11 processed 数据确由这条逻辑生成，则 cycle k 的曲线至少在这些 cell/周期上不是截至 k 可见的记录；“cycle 完成后”不能令其因果。当前 staged generator 对应关系仍未证，所以这是明确的**版本条件性风险**，不是已证明 v11 文件一定泄漏。

建议：在确认 v11 generator/输出周期映射前，不把 b1c0 的 k>=11、b1c18 的 k>=39 纳入 as-of-safe 人口；或按可追溯来源证明输出 cycle 坐标与实际可见次序的关系，再正式决定是否可保留。不要静默将 pinned 代码的移位解释成安全修正。b2c12/b2c44 的相似替代分别始于252/247，默认前100网格不受影响；若以后扩展网格，应再处理。

### 2. at-risk 与未来结局选择的分界正确，实际选择项应按 EOL 标签性质限定

候选第13行区分“k 时已观察仍在役”与按后来 EOL 选择早期样本，方向正确。loader 的控制流是：`data_loader.py:487-505` 先对 `eol <= threshold` 返回空；再只为 `eol > threshold` 的电芯遍历 `i=seq_len,...,threshold`。默认 threshold=100 时，保留 cell 的 `i <=100<eol`，故后续 `i>=eol` 分支不可达。此点候选准确写出“通常冗余”，但可更精确写成此标准控制流中不可达。

风险是前置资格过滤：`eol<=100` 会整颗排除，包括本来可能在 k<100 时具有可观察前缀的 cell。仅当该 `eol` 是已观测事件坐标时，所产生的人口条件才可按已知事件状态解释；若它是标签生成器由末20点/末端状态外推的 `estimated_T`，就是未来结局选择。标签源码 `Extract_life_labels.py:106-165`（SHA-256 `a905ef24c568e6f615ee638ebb6581c170aaf1e21ee50354a57ebaf11e9ad85b`）含尾20回归路径；既有审计中 MATR 81 个为估计、HUST 77 个 nominal threshold crossing 未观察到。候选第9、13行对此区分基本成立。

合法风险资格应是：在预先登记的 origin k，使用截至 k 的实测记录确认尚未按同一事件规则 crossing，且随访/记录确实到达 k；event 已于 k 之前或当时发生的 origin 不能进入 at-risk 预测。对右删失电芯只主张在可观察随访覆盖到的 k 上的资格。最终 EOL 估计是否大于 k，不能替代这些当时可得状态。JSON 的 `at_risk_rule` 建议改成明确的可观测条件，并把 `eol <= 100` 排除记为禁止的未来标签过滤，而非模糊的 “no future EOL>early-threshold selection”。

候选正确地没有宣称该门槛实际排除了多少 cell；在既有审计证据未给计数前应保持未知。

### 3. cycle-level 可见性条件总体正确，但不能概括所有预处理/所有实体

HUST 时间归一化按 cycle 顺序累计（已审查 `time_normalization_utils.py:29-83`），未见用未来 cycle 容量回写既往周期；单个 cycle 的时间修复需完整该 cycle 时间数组。故只可候选化“cycle 完成后”预测。loader 还在 cycle 内做 bfill 和以该周期最大电压缩放；若决策在完整 cycle 后，这些周期内完整观测可以成立。候选第7、20行对此边界总体稳妥。

需要将第1项 MATR 的偏移例外写入“预处理门槛”，并说明版本未知。HUST_7-5 的前两 cycle 删除后又被 loader 按列表序号重编号（HUST preprocessor 64,72-78；loader 456-465）；候选第7行提到 row/actual mapping pending 是适当的未冻结项。

### 4. 主指标方向受代码支持，CI 与删失评价仍未冻结成可执行方案

候选第28行和 JSON 的 `cell_macro_MAE_cycles` 与现有 evaluator 定义相符：`src/rul_benchmark/evaluation.py:57-85`（SHA-256 `3c26463b5fa072cb0733e9b4e376afc6c836fd8f1d146c6c81ee1237dc3195ee`）先算每个 physical_cell 的 prefix 平均 MAE，再对 cell 等权平均；同时另报 prefix-micro MAE。candidate 对“先电芯内、再电芯等权”的文字是清楚的。精确 MAE 只含 observed crossing 的规则也与 `queries.py:133-153`、`audited.py:79-108` 一致；将作者估计值与删失对象分开是正确边界。

尚需冻结：
- 目标 population/estimand：cell-macro MAE 若只基于 observed crossing cell，将是 event-observed 子群的条件结果。既有标签决定文件明确指出 MATR 88-cell 子集不能外推到全部169或群体可靠性，HUST目前没有 nominal observed crossing。候选应明确这一限制。
- 多 origin 聚合：现有 evaluator 是每 cell 对该 cell 实际给出的预测 origins 等权，再跨 cell 等权。grid、risk set、missingness/censoring 规则必须先冻结，否则“每 cell MAE”比较的 cell 内 origin 组成也会变。
- 不确定区间：`evaluation.py:87-106` 是配对 cell bootstrap，并明示假设独立 cell；若实验 batch 依赖显著则用 batch-level resampling。候选“按物理电芯/实验batch聚类”不是唯一可执行算法。须选定配对/单模型估计、抽样单位（cell或batch/分层方案）、置信水平、重采样次数与最低独立簇数。物理身份及 batch 依赖尚未完全审计。
- censoring：候选第9/28行说下界/生存评价分表，正确但尚未定义具体 estimand、评分函数、删失机制假设及可用 cohort；不得把 lower bound MAE 或 estimated_T 回归误称为 exact MAE。

### 5. 其他 failure metrics 方向可用，数值定义需等 protocol freeze

“危险高估”可采用正向误差，但应明确符号为 `predicted_RUL - true_RUL > 0`。现有 `audited.py:41-45` 正是该定义，候选要求开发期冻结阈值，方向一致。过估门槛数值、目标分位数/服务代价未定时，不能给危险告警结论。

“预测震荡”可由不同 origin 的 EOL 估计修订量诊断；现有 `evaluation.py:68-70` 用相邻 query 的预测 EOL 差值绝对值，且注明小不代表准确。候选称“EOL估计修订量并与准确性同时评价”合理；具体 origin pairing 和汇总方式应跟随冻结 grid/risk set 一并登记，不能单独最小化该项。

未来策略只解释为已记录策略分布、无新策略因果 claim；NO_GO 说明是协议/数据未就绪而非模型无效，这两点有证据支持。

## 必须保留的未冻结阻塞

1. release 到实际 generator/config 的可追溯链；MATR 下一 cycle 代入当前 cycle 的输出映射与可用性判断。
2. 绝对 query grid、cycle 坐标空间、缺测/记录终止处理、每个 origin 的 observed event / alive / follow-up 状态与风险集计数。
3. EOL 阈值分母、阈值规则、首次 crossing、标签源与 `observed_crossing / right_censored / estimated_T` 逐电芯状态。
4. 物理身份、split/预训练 overlap 和事件观测子群可推广范围。
5. cell-macro MAE 的固定 cohort/origin 聚合；删失专用估计量；CI 的抽样单位/假设；高估阈值。
6. 同一合法 population/input/split/budget 下的基线计划、独立确认 role 与未来策略解释。

## 审查判定

- 候选文字：方向大体正确；第13行对控制流可改为“在阈值和 EOL 编码均不变时必不可达”；第19行应把 MATR 的 11/39 cycle next-cycle substitution 明确写成周期级 as-of 风险。
- JSON：状态和禁训标记适当；`absolute_query_grid`、`eol_reference`、`processed_generator`、identity 等明确标未冻结是正确做法。建议新增/明确 `censoring_estimand`、`risk_set_counts`、`metric_aggregation`、`uncertainty_method` 和 `MATR_shifted_cycle_exclusion_or_resolution`，当前不可据此开 gate。
- 结论：保留 `NO_GO_FOR_DYNAMIC_TRAINING` 合适。它是数据与 protocol readiness 的 NO_GO，不是模型性能判负；本 review 的完成也不把状态提升为 PASS/GO。
