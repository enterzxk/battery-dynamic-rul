# 端点目标覆盖修复：单fit匹配比较完成，首过路线仍失败
## 2026-10-18：端点标签修复匹配fit已完成，递归首过路线仍NO_GO
- **已完成**：新DataV2下执行且仅执行1辅助CPUfit，相同42fit/10cal、模型/seed/生成规则；容量MAE1.031446→0.974923mSOH改善5.4800%，但4567首过预测仍163noncross（旧191），全部b2c6；4/10cell改善，冻结gateFAIL。关闭本固定20cycle递归首过路线，不加horizon/强制下降/seed。
- **证据**：experiments/capacity_endpoint_firstpassage_seed42_v2/RESULTS_ZH.md、protocol/cohort/ROOT_GO/fit_ledger/completion、capacity_comparison/calibration_predictions/independent_metrics/root_decision；checkpoint SHA0980e4c7898a18de7562c20679ebbd60000a03bd9c7ebb1a976dad46c75dd127只在服务器；审查reports/capacity_endpoint_v2_review_20261018_luna/review.json SHA42bb9de27515bbb658f1af7af9d7d4ed149ee067745e8e67c5b2aea64d2a6d53。
- **最小验证**：CSV独立重算首过指标最大差2.84e-14，容量指标差4.44e-16；保留全4567origins及163noncross，原EOL不变。RUL预测无损压缩，容量v2用旧CSV+精确delta复原SHA通过。签发脚本曾因review字段名不一致而在GO前拒绝，0claim/fit，失败日志与preGO_control_failure/resolution保留；核哈希签发后真实fit账本仅1次。
- **阻塞/风险**：129.644624是把未到端点赋2000cycle下界cap的全样本诊断分数，不是有效完整点预测MAE；直接RUL在同10cal有效MAE58.113698。修复数据覆盖不足以修复长程预测；capacity能力不能当RUL/分布/新方法证据。新增1fit0optimizer、0checkpointload、100rolloutcalls73060rows+1capacitycall4367rows、0dev/test；旧预算不变。
- **下一步**：做一个缺失的强简单基线：同42fit/10cal、相同age/SOH/robust20与固定HGB参数，仅将log-RUL平方损失改为native-cycle RUL absolute_error；1CPUfit，独立窄审+fresh exactGO后直接执行。同4567cal预测与旧directRUL比较，先解决训练目标和主MAE口径的差异，不开发新模块。0dev/test、不重训旧checkpoint，cal暴露不得当独立确认。

| 校准容量变化MAE(mSOH) | 数值 |
| --- | ---: |
| 容量不变 |9.5882540153|
| robust20斜率外推 |1.9728936895|
| 原preEOL target模型 |1.0314458076|
| 新endpoint target模型 |0.9749230470|

旧模型21441训练pairs，新模型22281，增加42at-event+798post-event，其他模型/seed/原始标签/生成规则未改变。短期target域修复有效改善容量指标，但不足以保证长程首过行为。
首过比较：原directRUL58.113698；新rollout capped diagnostic129.644624（旧139.206680），noncross163（旧191），全部b2c6，163prefix未来age超过训练source范围。4/10改善；有noncross时不将这些数字当完整pointMAE或正式相对收益，不能删除noncross再选优。
fit_ledger.jsonl记录唯一合法fit_started/completed；前一次控制脚本字段差异没有签发GO，runner在GO读取处拒绝，尚未claim/数据/模型/fit。错误证据保留，后以reviewed_hashes正确绑定再运行，未消费旧训练票据或重跑已消费实验。
原始capacity_calibration_predictions.csv由capacity_prediction_delta.json依赖上一capacity20原始公开预测恢复，decode_capacity_delta.py核byte数/SHA；calibration_predictions.csv由published_predictions.json恢复。服务器原始科学CSV均未覆盖。完整checkpoint不公开。
下一实验将比较log-MSE与native-cycle绝对损失，这是强基线目标函数对照，不是预设创新。其是否改进MAE需要真实实验，不以数学目标一致性代替性能。
