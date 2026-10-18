# 条件分位数强基线：两次真实fit完成，NO_GAIN

同42fit22281/10cal4567、原age/SOH/robust20单位、原event_cycle-origin标签与等cell权重。固定HGB150iter/leaf7/depth3/lr.05/min50/L2=1/seed42/无earlystop，分别学习logRUL q.1与q.9。已有saved中位数未重训/未修改。一次独立窄审PASS后签发fresh精确GO，两次fit均完成并消费，180秒总预算内，0optimizer/标量校准/checkpoint加载/dev/test。

|电池等权指标|旧固定sigmaA|直接条件分位数|
|---|---:|---:|
|TimeMAE cycles|58.113698|58.113698|
|coverage80|62.0234%|53.9283%|
|区间宽度cycles|124.005661|137.380644|
|80%区间得分|264.570734|265.090803|
|lower-miss|24.5237%|31.1479%|
|upper-miss|13.4528%|14.9238%|

区间得分恶化.19657%，覆盖率降低8.09517个百分点，宽度增加10.7858%；虽然7/10cell覆盖误差改善，主要联合指标失败。pairedcell score改善95%区间[-80.296374,87.645428]跨零。

lower>已有median有82origin、upper<已有median128origin，合计210（无重叠）；lower>=upper为0。有序上下界的interval score仍有定义，但三分位一致性失败，gateFAIL。没有排序/clipping/换median/调seed救援。只有两个边界不足以唯一确定完整CDF，不计算新Brier或宣称分布完成；点MAE完全不变，不是主TimeMAE收益。

独立CSV重算主指标与crossing计数最大差5.68e-14；完整CSV SHA fde7a87d1dce3c8f3e9bff3059551c8de8a912234f8db09b6869021ab36c5e00。2checkpoint仅服务器保存，哈希见completion。公开prediction_delta+decoder从旧calCSV精确复原新CSV，已核byteSHA。runner/配置/cohort/review绑定见ROOT_GO；两次fit日志均保留，不能重跑。

cal已暴露、event-only实验、物理serial/fullsourceSHA未闭合，不能当独立确认/泛化。关闭当前直接条件分位数参数组合，不扩模型/seed或调分位数。

下一步0fit：固定两种相反区间失败case（b4c7下侧漏出、b2c6上侧漏出），只读42fit及这2cal的原特征，用fit-only median/IQR尺度做跨sourcecell局部输入/原RUL标签支持诊断。判断外推或相近状态下剩余寿命差异，不把事后邻居分析当新性能方法；不读18dev/test，不新增推理/训练。
