# 原生循环数绝对误差 HGB：真实单次对照 NO_GAIN

同42fit/22281origin、10cal/4567origin，复用旧age/SOH/past20 Theil-Sen原单位、原EOL与电池等权。固定seed42及HGB150iter/leaf7/depth3/lr.05/min50/L2=1/无earlystop，仅改nativeRUL目标与absolute_error。一次fit已消费；没有dev/test读取。

|指标（电池等权）|旧logRUL squared_error|新nativeRUL absolute_error|
|---|---:|---:|
|Time-MAE cycles|58.11369800278736|64.52446672083731|
|bias cycles|11.676224212761717|17.809011030925152|
|severe over100|0.1416005147437414|0.1402663646286486|

MAE恶化11.0314245%，4/10cell改善，配对电池2000次seed42 bootstrap的旧减新MAE差95%区间[-21.5464520513,3.5066260455]cycles；严重高估率降低0.133415个百分点；raw负预测0。预先冻结的四项联合门槛FAIL，保留NO_GAIN，不扩seed/调参。b2c1对总体MAE增加贡献6.634659cycles；剩余9cell平均旧减新0.248767cycles只是事后说明，不能删除电池挽救结论。

独立CSV重算最大差7.11e-15；完整CSV SHA a7ecaf89ea350ff05a19e16f9df52c23a6a58b23f48e93aee04fede2c9e6d261。checkpoint SHA 7696b53075addfe6a06b1a449e87f11b0cfac532f72fd0b2410236b813295954（仅服务器）。实际耗时0.514s，1CPUfit，0optimizer，0dev/test。runner/protocol/cohort及审查哈希见ROOT_GO.json。审查请求gpt-6-luna/high，实际运行身份不可独立内省；同次窄审解决剩余时间预算和首账本独占创建后PASS。先前因账号额度停止，排队heartbeat未宣称执行；恢复后续审，无重复fit。

权威路径：/home/yndx/zxk/rul/experiments/native_rul_mae_seed42_v1。复算：指定a40_env Python运行independent_metric_recompute.py；已存在输出勿覆盖，按createonly规则用新审计目录。公开prediction_delta.json + decode_prediction_delta.py可从已有baseCSV无损复原完整新CSV，已verify-only核byteSHA。不得重跑已消费runner。

本结论仅为已暴露cal开发比较，非独立确认、论文创新、条件分布完成或完整物理电芯泛化证明。原始event-only及物理serial/fullsourceSHA限制不变。

下一步：只用既有同10cal预测，冻结origin100早期EOL递减对照与每时点更新比较，0fit/0新模型推理；量化新增观测更新在何处帮助或伤害，不以换损失代替失败机制研究。
