# CALB选模目标诊断：当前5电池无目标冲突

四种已存验证指标（prefix-MAPE、cell-equal MAE、prefix-MAE、cell-equal MAPE）的最优epoch均为2，与原completion选模一致。因此没有证据把当前结果归因于官方prefix-MAPE选模牺牲整体cell-MAE。

选中epoch2：cell-equal MAE=61.634743121831 cycles，prefix-MAPE=0.078796143611。cell-MAE次优epoch4=64.673062810416，差3.038319688585 cycles（4.929557%）。其余已存epoch都没有更低整体MAE；不据此推断所有未来训练必然无效。

本轮只读既有10epoch JSONL及完成/配置文本，并核原selected prediction SHA；按每epoch5cell/497prefix摘要独立重算四种聚合，与原日志吻合。此处原native标签口径有既有微小float/scaler往返误差，不替换精确作者标签MAE61.63474574634282。

各cell的事后最优epoch不同，但不得据验证结果为每cell挑epoch：这只作诊断，不产生新模型。原epoch2、预测/回执哈希和CALB扩展NO_GO均不变。相同5开发电池不能作为独立确认；本轮没有新fit/steps、模型加载、推理、test或数据binary读取。

机器记录selection_diagnosis.json及epoch_comparison.csv保留结果、旧证据SHA与范围。下一项回P0，只核已有HUST原始来源公开metadata和source manifest的物理身份凭证；不重复CALB选模/组先验诊断。
