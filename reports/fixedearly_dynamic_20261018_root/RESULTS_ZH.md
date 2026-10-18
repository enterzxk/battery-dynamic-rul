# 固定早期EOL递减与逐时点更新：既有预测零训练诊断

同10cal4567origins，唯一输入为已存directRUL CSV（SHA c27dd53fce992318292397486aaff8ce02e3f8b802ee54932867517ce7c2af76）。先冻结protocol再运行，0fit/0新模型推理/0checkpointload/0rawfeature/0dev/test。固定点递减=max(0,exp(mu100)-(t-100))；动态点预测=exp(mu_t)。保留所有前缀，无标签/电池变更。

|电池等权指标|origin100固定EOL递减|逐时点更新|
|---|---:|---:|
|TimeMAE cycles|116.4334217342|58.1136980028|
|bias cycles|-10.2393973862|11.6762242128|
|severeover100|0.2000000000|0.1416005147|

相对MAE改善50.08847%，9/10cell改善；2000次seed42 pairedcell旧减新MAE差95%区间[26.385867,94.524897]cycles。预先冻结开发gate PASS。固定点递减有756个预测已经归零、真实电池仍未到EOL的origin；此风险完整保留。不能据此把固定点递减当生存条件分布对照，也不能声称独立确认或创新。

相邻时点更新对照：先将上一次动态RUL扣除真实已过cycle并floor0，再与本次预测在同当前真值下比较。共4557次transition；电池等权helpful50.1619%、harmful49.8381%、tie0%。平均每次更新绝对误差减少0.266183cycles，而绝对EOL修正3.634246cycles。次数接近一半有害并不抹去动态全轨迹收益，不能使用真值选择更新，也不足以直接开发门控。

按真实剩余寿命分段仅作结果诊断，不作为在线可用特征：RUL<=100时10cell948origins，MAE71.977453→7.156475，严重over100为20%→0%；RUL(100,300]时9cell1800origins，MAE120.338152→50.996698；RUL>300时9cell1819origins，MAE141.780752→108.482541，但严重over100由22.2222%升至32.3047%。各分段电池数不同，不能当同一加权总体或据此优化阈值。

独立标准库逐值重算主MAE/bias/over100、expired及有害更新比例通过（最大差见independent_metrics.json）。可重现脚本diagnose.py，计算源、公式和预算见protocol.json；已有输出create-only，不能原目录重跑覆盖。

cal已暴露，只能支持这组数据上的开发性动态信息价值；observed-event lab capacity、sourceID隔离而完整physicalserial/fullsourceSHA未证实，不能扩成删失/物理泛化结论。现有动态模型也将age与新SOH/rate一起改变，本对照不能单独归因给新健康观测。

下一步：不新增训练，固定origin100 lognormal分布与旧fit-only sigma A，显式用已存活至t的事实计算条件中位数，与点递减/既有动态作同10cal4567对照，分清简单存活信息与全动态状态更新。不得使用cal sigma B或新估计，不把参数分布假设当已校准事实。
