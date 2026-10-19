# 已到达容量误差能否识别不可靠RUL更新：零训练诊断
日期：2026-10-19。结论：**NO_GO_DELAYED_CAPACITY_RESIDUAL_GATE_FROM_CURRENT_DIAGNOSTIC**。

仅复用已经保存的10cal预测，未训练、未加载checkpoint、未作新模型推理、未读18dev/test，也没有改变任何RUL预测。CPU累计仍20=RUL18+辅助2，神经4fit2580steps，旧MATR41另计。

## 问题与预先冻结的计算
在循环s，只读取从s−20发出、target_cycle正好为s的容量预测。信号x_s=|predicted_delta_mSOH−true_delta_mSOH|；true_delta只在s观测到后才可用。不能把s发出的s+20误差提前用于s。
事后评分y_s=|dynamic_RUL_s−true_RUL_s|−|halfCDF_RUL_s−true_RUL_s|。正值表示动态点预测比固定等权CDF更差；RUL真值只用于事后评分，从未作为在线信号。
主统计为每cell Spearman(x_s,y_s)。另冻结连续循环一阶差分Spearman(Δx_s,Δy_s)检查趋势敏感性。筛选约定：两种相关各至少7/10为正，且同cell同时为正至少7/10；即便通过也只支持进一步研究，不授权门控或新fit。没有阈值、权重、窗口或horizon搜索。

## 实际结果
4,367个唯一cell/origin匹配到已到达反馈，10cal均覆盖；原RUL表4,567行。每cell的100–119循环共200行无延迟反馈，按冻结规则排除、没有填补；没有因标签或误差大小删除样本。

|指标|实际值|
|---|---:|
|原始信号相关为正的cell|6/10|
|一阶差分相关为正的cell|6/10|
|同cell两者同时为正|4/10|
|cell等权平均原始相关|0.033578|
|原始相关中位数|0.062496|
|cell等权平均一阶差分相关|0.019400|
|一阶差分相关中位数|0.019625|

原始相关的方向不一致：b2c21 −0.321338、b4c14 −0.218211，而b4c19 +0.255414、b2c1 +0.242474。b4c7原始相关+0.167772，一阶差分−0.021035；这节电池既有严重高估问题，当前容量残差仍未提供方向一致的代理证据。
严重高估>100cycle的动态减混合指示差是次要描述；7/10 cell该差为常数，相关记null，不能把它们计作零相关或风险改进。其余3cell的相关也未呈统一正方向，详见per_cell_metrics.json。
冻结筛选未通过，因此不从这组cal训练或启用容量残差门控，不换horizon/尺度/阈值救援。这不是证明所有容量反馈均无用，也不是整个动态RUL任务NO_GO。

## 验证、证据与限制
诊断命令：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/reports/delayed_capacity_reliability_20261019_root/diagnose.py（已完成，不重复运行）。
protocol.json绑定4份输入SHA；ROOT_GO.json绑定runner/protocol且一次预算已消费。唯一键、cal角色、两RUL来源真值一致、20实际cycle跨度、发出时可见边界和排除范围断言通过。独立平均秩计算重算10cell两类相关，最大差8.33e−17；validation.json保留3条实际对齐样例。
完整4,367行派生表只保留服务器aligned_diagnostic_rows.csv，SHA9d6a260987ad40f9f5d818544c4b03574df946bb356a08d96079cf86f99a7710。公开protocol/runner/逐cell统计/决策/验证/完成回执；本目录不重复发布源预测，源路径与SHA见protocol。公共镜像没有该完整派生CSV，不冒称完整镜像复现包。

10cal已经反复用于开发；时间相关、年龄/存活选择和残差可用性选择仍存在，一阶差分不等于消除混杂。容量模型是既有3state固定20cycle预测，RUL为lossless schedule模型，相关不是因果关系。物理serial未知、event-only、固定工况、旧sigma概率参考的限制均保留。此次不重新启动已NO_GO的recursiveEOL路线，不把容量局部误差当首次EOL误差。

## 下一条实际交付
停止继续堆叠可靠性代理。基于已完成的固定早期存活、纯动态、等权CDF及失败诊断，写一份中文论文“实验结果与局限”草稿和证据表，明确开发结果、简单强基线、负结果与缺少独立确认。无新训练/test、无首次性或条件覆盖宣称；该草稿不是可投稿完成稿。
