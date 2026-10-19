# 标准因果直线阈值外推：完整4567前缀负结果
日期：2026-10-19。**NO_GO_STANDARD_FIXED20_LINEAR_THRESHOLD_AS_COMPETITIVE_BASELINE_NO_RESCUE**。

## 已完成与真实结果
使用既有10cal的当前SOH与固定past20 Theil–Sen速率，RUL=(SOH−0.8)/(−rate20_per_cycle)，速率单位SOH/实际cycle。名义1.1Ah、首次实际QDischarge<=0.88Ah事件、origin100..event−1与三臂参考相同。没有拟合、缩放、clip、horizon、整数取整或窗口搜索。
实际10份因果特征表、4,567前缀全部得到有限正预测；本次未出现非负、缺失或非有限速率，有限预测比例100%。因此下列是**完整同前缀宏平均**，不是有效子集结果：

|方法|TimeMAE/cycle|严重高估>100cycle|
|---|---:|---:|
|标准固定20速率直线外推|1488.7459|69.1636%|
|早期存活参考|55.2421|0.2791%|
|逐时动态|33.0272|3.1631%|
|固定等权CDF中位数|35.4520|0.6047%|

直线外推bias为+1488.6599cycle，最大有限RUL109335.8353cycle（b4c19）；没有以预测上限掩盖极端值。9/10cell的MAE比动态与等权参考差，b2c1例外：直线4.9885、动态10.6993、混合13.0478cycle。故不把该基线描述为每cell都失败。逐cell明细见per_cell_metrics.json。
数学上，当前负斜率的倒数会放大小退化速率，对非线性退化不能仅凭当前20cycle斜率推出准确首次越阈。这里观察到直线方法失配，不能据此声称所有物理模型或所有趋势外推无效；不通过clip速率、改window、加horizon或多seed救援。
本基线输出确定性点预测，未给概率分布，不编造区间覆盖、Brier或概率收益。

## 最小验证与运行证据
原始静态窄审发现“missing标记之前float解析空rate”的错误。真实执行之前作最小修复，旧runner与NEEDS_REVISION审查保留；一个missing空字段用例返回(null,missing_rate)。delta窄审PASS后主控签fresh exact0fit GO，随后只运行一次，invocation.claim/完成回执保留，没有真实运行失败重试。
4,567键/角色、已见截止时点、源特征SHA、EOL/真RUL一致检查通过。独立从保存预测重算4臂宏指标最大差1.14e−12；利用既有capacity20保存的速率与真实容量变化检查3组20cycle差分恒等式，最大差2.78e−17，无新增原始特征读取。该差分消去了阈值，不能代替绝对0.8阈值核查；绝对阈值由冻结公式、源manifest与预GO检查单独保障。
命令：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/experiments/causal_linear_threshold_fixed20_v1/runner.py（已完成，不重跑）。
ROOT_GO、protocol、feature_manifest、dedup_static_receipt、两版审查、missing_input_fix_validation、metrics/per_cell_metrics、independent_validation、completion、root_decision绑定真实来源/预算/结果SHA。
完整8列predictions.csv仅服务器保留；公开public_predictions_lossless.json精确保留cell_id/origin/linear_RUL/status四列原字节及decoder，并绑定完整服务器CSV SHA，不冒称完整8列公开包。没有上传原始容量、SOH或速率特征表。

## 边界与下一步
本轮新增fit=0、学习模型推理=0、checkpointload=0、dev/test读取=0；只读取获准10cal特征文件4567行。新科研CPU仍20=RUL18+辅助2，神经4fit2580steps、旧MATR41另记，所有旧GO及本次GO已消费。globalnewfitsfalse保留。
10cal反复暴露、event-only、物理serial/完整源身份未知、固定已知工况等限制不变。该标准简单基线既不是新方法，也不重开已NO_GO的学习式固定20递归容量EOL。
paper/EMPIRICAL_RESULTS_DRAFT_ZH.md已加入本结果并保留v1历史；下一项只用既有预测和逐cell指标制作论文经验图：来源b2c1与b4c7预先指定，展示逐cell精度/覆盖及真实RUL轨迹。保留大预测值（适当明确log尺度）、不选择有利窗口，不新增训练、推理、特征读取或test；图是描述性开发证据。
