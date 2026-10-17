# 两固定CALB样本：官方重采样、归一化与前缀mask检查

结论：PINNED_TWO_SAMPLE_CURVE_AND_MASK_CHECK_PASS。复用pinned data_loader.py的read_cell_df/read_samples_from_one_cell/get_charge_discharge_curves/resample_charge_discharge_curves原函数AST，不执行Dataset_original初始化或模型。仅未使用的增强返回分支作identity stub，基础曲线和mask调用原函数。不是完整loader/增广/训练复现。

|样本|实际曲线张量|前缀数|mask矩阵|缺循环补零槽|首循环独立归一化最大差|
|---|---|---:|---|---:|---:|
|CALB_35_B229.pkl|[100, 3, 300]|99|[99, 100]|1|0|
|CALB_0_B187.pkl|[100, 3, 300]|100|[100, 100]|0|0|

两个样本全部曲线值有限，真实cycle电压通道max=1（误差0）；首循环独立切分/插值及V/maxV、I/nominalAh、Q/nominalAh重算最大差均0。训练样本normalized Q最大约1.024、I最大约1.201C，按官方值保留，不裁剪或改标签。

99cycle样本第100槽全零且没有第100个样本；100cycle样本第100槽非零。每个prefix的mask恰好前i个1/后部0，应用mask后未来槽全零。这里验证数值mask作用，不声称模型已经正确使用mask或严格raw-asof合法。

源码行：read_cell_df433–477（按存储顺序重编号）；read_samples480–528（有效cycle与mask）；get_curves530–627（分支、归一化、缺cycle零填充）；resample629–644。源SHA、两个样本和stage/decoder/运行脚本绑定见preprocessing_check.json；另由既有完整运行回执核loader SHA吻合，source_identity_verification.json留存，未重跑。

new_fits=0、optimizer_steps=0、model_loads=0、new_inference=0、scaler_fits=0、torch_imported=false、testPKL0、test标签值0解码。未拟合train label scaler，不把数值预处理通过称为模型性能、全cohort数据许可或忠实复现成功。物理身份/生成器/在线标签及官方训练test入口/双进程限制不变。

下一步：Audit remaining20 CALB trainval members once with exact typed decoder and static symbolic gate; combine prior2 evidence for full17/5 field/preprocessing and per-cell effective-prefix inventory. Reuse prior2 without reruns; no test/model/fit, do not broaden dtype/global mapping on failure. Determine train-only scaler readiness from fixed17 train labels.
