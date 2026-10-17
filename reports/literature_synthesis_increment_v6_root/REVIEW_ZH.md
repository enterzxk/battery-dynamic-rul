# Batch07五篇增量科学综述与当前裁决

范围仅本轮新接纳P33/P35/P38/P39/P41，主文唯一接纳由30增至35；不冒充全35篇系统综述。source→fullread→独审→root聚焦原文/视觉附注→accepted记录链见manifest。所有表值均作者报告，未模型复测。

P33将ENR和聚类组合，BIBO论证只约束有界输入下的误差有界，不证明跨化学泛化或剩余循环误差改善。数据容量先上升的背景要求后续方法容纳恢复/温度变化，不可直接施加未经验证的全程单调先验。权重上限0.5和alpha选择需按合法训练人口冻结。[原文](https://arxiv.org/abs/2401.04734v2)，实际2/7页。

P35以最初100循环生成退化曲线、十样本择优并推阈值寿命，与全origin动态RUL不同。PDF表3的104下标6/168下标9是104±6/168±9，旧抽取1046/1689不是原表均值。SOH误差必要时reference补零；未来复现必须固定此口径并另报与动态RUL一致的误差，不能静默换算。[原文](https://arxiv.org/abs/2410.23893v3)，5-7/9页。

P38提供LOBO比随机CV更严的内部对照，但仅4只NASA电芯。组合指标RMSE/R2更好、CC-only的MAE2.72%仍优于组合2.87%。1.86Ah由观测最大容量定义，统计人口与asof未知，正文/表格SOH范围及636/637与623/630计数差异需保留。它支持前处理审计与逐指标报告，不证明跨数据集动态RUL或新模型必要性。[原文](https://arxiv.org/abs/2607.23482v1)，4-5/8/10-11页；关联DOI不等于出版社版本已核。

P39含目标电芯SP前训练，必须归入有目标适配的设置。VMD的kmax/alpha由PSO选，分解/选参窗口的asof边界仍未闭合，不能先断言泄漏或合法。表II的容量误差不是Time-MAE，表III才是cycles RUL；图4(b)CALCE SP100的RUL标签较EOL-SP及表III预测值多50。不同SP和reference基线不能当统一预算复现；95%CI未核独立覆盖。[原文](https://arxiv.org/abs/2510.02839v1)，3/6/8-10页。

P41把完整放电曲线Kneedle弯折点容量用于监督、局部段特征用于输入；完整监督构造不自动推出输入泄漏，真正asof还需代码审计。Verhulst中u先称capacity loss又称输出SOH，代码残差符号未核。gamma34在同10个留出电芯选择、结论又称test，故只能视开发验证。通常80% EoL是可选作者阈值，KPPE分母为全寿命；本文未报告独立逐origin绝对RUL误差。[原文](https://arxiv.org/abs/2608.14764v1)，6-8/11/13/16-17页。

主控科学裁决保持：strict动态RUL NO_GO；target/input/adaptation/budget匹配的负迁移NOT_ESTABLISHED；创新与TSC GO未建立。本轮没有以理论、文献接纳、元数据回执或单项PASS升级性能结论。历史两个author-total-EOL开发pilot共600steps保留，不能当严格动态RUL确认结果。

下一可执行科研顺序：先依当前PBT入口继续冻结候选前瞻val配置与逐键/valid-cycle证据获取stage，独审后才逐阶段裁定；并继续batch08正文阅读独审。公平强基线协议需先闭合物理ID、标签/观测EoL、前缀asof、相同输入/适配/算力预算和独立确认，再比较以cycles为单位、case等权的剩余时间MAE及辅助指标。当前不启动fit或forward。

本轮new_fits=0、optimizer_steps=0、PBTforward=0、metrics=0、test=0。实际额外执行仅一次7个固定文本metadata收集，共40644B；它不闭合G2/G3，回执在reports/pbt_stage0_metadata_freeze_v2_root/metadata_receipt.json。
