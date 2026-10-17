# 新增六篇的证据增量与当前科研判断

本增量只依据新接纳的P10、P25、P26、P29、P31、P32的实际读审记录、root源文抽查/附注和P26第8页视觉核对。旧综述保留，不重新阅读全文或重算模型。全项目现有30个unique主文接受ID；P05补充材料不双计。30篇接受不等于50篇任务完成或创新性证明。

## 与动态RUL总任务的对应

P25、P26、P31主要预测容量/SOH或其轨迹；P29预测形成阶段总循环寿命。它们能支持指标、单循环编码、极早期特征与单调先验的讨论，不能提供本项目严格多origin绝对剩余时间改善的实测证据。P10和P32使用RUL名称，但前者电芯隔离/评估表归属未明确，后者精确标签单位和origin操作未完整报告。不能将这些数值混排成公平动态RUL排行榜。

P25的简单线性模型与复杂模型没有全面赢家；P29设计特征的中位MAPE更好但最坏MAPE更差；P31外推R3由MLP在四项误差上胜出，且模型训练预算不同；P32的NASA平均MAE未胜AUKF。这些结果反对从复杂度或局部指标优势直接得出“复杂机制普遍有效”。它们仍是作者报告，不能当本项目baseline复现结果。

P26的PWM/恒流陈述、P25的W9周期数、P29的内层划分数量、P10的准确率汇总冲突均按来源并列保留。P26式24绝对值由PDF视觉确认，文本抽取漏竖线不构成作者公式错误。P32所称低估更安全仅是作者对示例曲线的定性描述，没有本项目signed error或现场安全验证。

## 当前GO/STOP

- 严格online dynamic-RUL仍NO_GO：v11标签/可得性/物理与预训练ID未闭环，protocol v3仍DRAFT_NOT_FROZEN。
- 匹配目标、输入、适配与计算预算的负迁移仍NOT_ESTABLISHED；source-only恶化不是自动负迁移，seed方差不是origin震荡，绝对残差不是高估方向。
- PBT静态导入与缺失G2证据已核；构造、strict-load、forward、metrics、test和新增训练门全部false。author estimated-total-EOL与strict online lane分开，checkpoint exposure未闭环阻止独立泛化宣称。
- 总目标仍为50篇精读独立审、真实公平强基线、动态RUL五模式、证据后的创新与独立TSC论证；本增量不作创新GO或TSC-ready判断。

下一实际动作是独立预检Batch07修复包并按live去重正式注册五篇；同时审完PBT最小同算术val-only的INACTIVE具体方案，缺证据项不可用静态PASS代替。
