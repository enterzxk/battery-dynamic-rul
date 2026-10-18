# 已知工况下动态更新：精度增益成立，联合风险护栏FAIL

同policycontext模型已存10cal4567预测，先冻结protocol。固定早期基线=max(0,exp(context_mu100)-(t-100))；动态=exp(context_mu_t)，均有同一已知工况输入。无新训练/模型推理/尺度估计/原始特征/checkpoint/dev/test读取。

|电池等权|origin100固定EOL递减|逐时点动态|
|---|---:|---:|
|TimeMAE cycles|75.740130|36.400814|
|bias cycles|-34.982175|-3.523895|
|severeover100|0%|4.258247%|

动态MAE改善51.93986%，8/10cell改善；pairedcell2000seed42旧减新差95%区间[13.121580,73.205613]cycles。严重高估增加4.258247个百分点，超过冻结1个百分点增幅护栏；联合开发gateFAIL，不以平均误差收益抹去风险。该结论不撤销上一项“工况vs三状态”的PASS，比较对象不同。

固定早期基线很保守，平均低估34.98cycle，还有647个预测归零但真实尚未EOL的origin。零严重高估并不表示该固定点基线整体可靠；它没有显式使用已存活事实，不能称生存条件化基线。

相邻4557次更新：51.6915%帮助、48.3085%伤害，电池等权；每次平均绝对误差减少.180143cycle，平均绝对EOL修正3.198785cycles。不能据事后真值建选择更新门控。

按真实RUL分段仅作结果诊断：<=100时10cell948origin，MAE40.330154→4.609152且严重over100均0；(100,300]时9cell1800origin，MAE80.006587→27.210824，动态over100 .88889%；>300时9cell1819origin，MAE92.729125→66.231676，动态over10011.35768%。分段电池集合不同、真实RUL预测时未知，不能直接作在线阈值。

独立标准库从源CSV重算主指标/647expired/更新伤害比例通过，最大差1.42e-14。源预测SHA796844ff5c863a08ca7f1238c620afee39a3f22b84d68b615ec52135c48b7ea0；可重现diagnose.py/independent_recompute.py，已有create-only输出不覆盖。0fit/optimizer/新推理/新sigma，CPU14与神经4fit2580steps不变。

cal已暴露，6seen/4unseenpolicy，lab已知固定工况、event-only、物理serial/fullsourceSHA限制保留，非独立确认/新方法或安全保证。动态age和健康一起变，也不能纯归因新增健康观测。

下一步0fit：固定原fit-only sigmaA不变，将policy mu100作正规存活条件化、policy mu_t作动态lognormal，以旧三状态动态作为同尺度参考，比较MAE/严重over100及80%区间得分/覆盖/Brier100/300。它是明确分布假设下的新对照，不能改写本轮风险FAIL；不估新sigma，不训练/推理/读devtest，不用变阈值补救。
