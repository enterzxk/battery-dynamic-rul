# CALB固定17/5 cohort：剩余20一次审计与全量有效前缀清单

结论：CALB_FIXED22_FIELD_AND_PINNED_PREPROCESSING_AUDIT_PASS_SCOPED。新增20个成员各静态预检/受限读取/字段/官方基础曲线与mask检查一次，复用已有2个样本不重载。没有扩大两个符号/float64映射，未普通unpickle、导入torch或模型、训练/test。

|角色|电池数|实际前缀数|99前缀电池|100前缀电池|存储cycle范围|作者EOL范围|
|---|---:|---:|---:|---:|---|---|
|train|17|1689|11|6|99–208|104–1352|
|validation|5|497|3|2|99–100|189–1411|

完整22成员五个必需字段长度对齐，raw非有限值0、负容量点0；实际曲线[100,3,300]、值有限、电压真实cycle max1、mask前i可见/未来槽零、缺cycle零填充均通过，cell_id与文件名一致。存在存储208cycle的电池，官方取前100cycle形成输入；不据此声称前缀raw-asof合法或标签生成器正确。

官方按每个训练电池的unique EOL拟合StandardScaler，而非按前缀重复加权。仅17训练标签的预期均值 852.294117647059、总体方差 283488.795847750851、scale 532.436659000628；验证/test未参与参数估计。这里仅数值准备核查，没有调用scaler.fit，scaler_fits=0。

前缀加权会给100prefix电池比99prefix电池更大权重；后续同时保留官方prefix聚合和cell-equal native-cycle指标。不得把1689/497默写成1700/500，不能补造缺失前缀。

完整Dataset_original初始化、真实增强路径、shared train-only label scaler尚未执行。物理身份/源码生成器/严格在线标签和raw-asof、官方训练test调用冲突、2GPUruntime和模型/训练授权均未因本次数据subgate通过而解除。new_fits=0、optimizer_steps=0、model_loads=0、new_inference=0、testPKL0、test标签值0解码。

证据：cohort_audit.json、cohort_inventory.csv、static_scan_remaining20.json、audit_remaining.py及逐成员进度回执；其余2样本证据路径和源/stage/decoder SHA均绑定。

下一步：Construct pinned Dataset_original train/val only once against exact22 stage using fixed2-symbol restricted pickle facade; verify actual1689/497 examples, per-cell99/100 counts, train-only fitted label scaler shared with val and one real batch shape/mask. No test loader/model/fit; keep original official test-entry deviations explicit.
