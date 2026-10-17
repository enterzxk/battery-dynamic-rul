# CALB CPMLP官方配方单GPU验证适配：真实运行结果

已完成单次真实fit：seed2021、17train/5val、1689/497prefix、batch32（每epoch52个drop-last batch）、恒定LR5e-5；10个完整并验证epoch/520steps，官方patience5 afterleast5早停完成，冻结prefix-MAPE选epoch2。实际wall18.74s，预算上限1fit/5200steps/1200s；剩余步数不授权再fit或resume。

|指标|CPMLP|仅17训练标签中位数基线|
|---|---:|---:|
|cell-equal EOL-MAE（cycle）|61.634743|350.400000|
|cell-equal MAPE|0.078686577|1.236774262|

相对弱全局中位数MAE下降82.4102%，4/5电池改善；训练中位数为1233cycle。模型prefix-MAE 61.576999、prefix-MAPE 0.078796144，与cell-equal口径分开。cell-equal bias -14.124906；按精确作者标签复算MAE 61.634746，浮点标签scaler往返最大误差1.52587891e-05cycle，不改原标签。

|验证电池|prefix数|模型MAE|中位数MAE|
|---|---:|---:|---:|
|CALB_0_B187.pkl|100|27.021391|1044.000000|
|CALB_25_T25-2.pkl|99|89.835955|251.000000|
|CALB_35_B222.pkl|99|28.333775|27.000000|
|CALB_35_B247.pkl|99|95.433383|178.000000|
|CALB_45_B253.pkl|100|67.549212|252.000000|

最小验证：模型/优化器架构复用已真实运行的pinned CPMLP，数据/shape/scaler先前已核，不重复smoke。首个实际训练batch检查输出形状及有限loss/gradient。停止/deadline/partial语义AST与已审runner一致；独立CSV复算497唯一cell-prefix键/5cell原始预测、连续520step账本、10×52完整epoch匹配。没有test、旧checkpoint load/resume或额外seed。

此结果是DEVELOPMENT_BASELINE_COMPLETED_NO_INDEPENDENT_CONFIRMATION：官方CALB和seed已对齐，但仍为单GPU32、val-only自定义runner，相对2GPU accelerate/DeepSpeed及官方test调用存在偏离，不能称完整忠实复现或paper score。5验证电池同集选模，不是独立确认；相对全局中位数的提升不等于强对照/SOTA/创新或strict在线真实RUL。物理serial/实际generator/asof边界不隐去；HUST和MATR的NO_GAIN不被CALB结果覆盖。

新神经训练本轮1fit520steps；累计4fits2580steps，旧3fits2060steps保留。MATR41CPUfits另列。全局new_fits_allowed=false，PBT已消费门保持。

精确证据：config.json、runner.py、ROOT_GO.json、root_adaptation_review.json、completion_receipt.json、budget_ledger.jsonl、epoch_metrics.jsonl、validation_predictions_epoch_002.csv、independent_metrics.json、root_result_decision.json。原始数据/checkpoint/运行原始日志不公开。

下一步：Use only existing CALB selected validation predictions and training17 labels to compare with prespecified train-only file-group conditional median (global median fallback for unsupported group), decompose weak-global-median gain concentration; no refit/new seed/model/inference/test, no label/selection changes.
