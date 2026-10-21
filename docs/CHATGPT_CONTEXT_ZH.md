# 网页版GPT阅读入口：DART-RUL V18
当前更新2026-10-21。请先读[实际结果](../experiments/dart_rul_v18/RESULTS_ZH.md)和[冻结协议](../experiments/dart_rul_v18/protocol.json)，再解释结论。服务器`/home/yndx/zxk/rul`是权威证据；公开仓库仅白名单镜像。

## 当前答案
**当前DART原型NO_GAIN。** 合法任务已跑通，但简单HGB事件头+未来寿命头最强；不能将“分布一致”或DART名称当创新成立，也不打开C4确认。

|模型|未确认sparse+delay pooled cell-equal Brier↓|delay7d全窗口MAE周↓|
|---|---:|---:|
|已有HGB|0.069174|2.6894|
|完整窗口HGB|0.062931|2.5891|
|HGB两头|0.031653|2.3587|
|标准查询离散风险|0.062844|2.8410|
|共享无平移|0.055389|3.1581|
|DART共享|0.059571|3.0284|
|DART分开状态|0.060504|2.9443|

完整记录窗口共62个开发sourcecell、每臂1255共同query、三臂3765例。三seed42/13/77、全部21CPU+12神经fit/3600steps先于开发推断；保存79065行（已有reference复用，不是三次独立训练）。原run1所有fit已完成后评估失败，scalar CDF最小修复后用27个保存资产0fit恢复。独立复算主指标一致。

DART相对HGB两头主Brier高88.2%；配对cell bootstrap95%差值区间跨0，不能称总体劣势独立显著。当前预设5%改善门失败，MAE/严重高估保护门也失败。DART delay coverage80=0.5773、IS80=17.6474，HGB为0.8621/11.4415。共享优于分开状态未获支持；无平移网络反而主Brier更低。

## 信息权限
T=原始有效RPT首次Q<=0.20Ah stop，是源实测事件，不是潜在物理EOL。s采样完成、a报告到达、q查询分开。未到报告不等于T>q。raw/sparse2/delay7d保持共同源标签及查询；隐藏信息不改变物理试验日程。C1/C2 train125、C3 dev63、C4 locked63预先冻结，当前共同查询train124/dev62。train隐匿事件sparse57/delay122，dev33/61，均各1query/cell。

无T可用训练2/开发1cell，只在源窗口评当前源状态0，未来RUL未知，不作独立删失。已知越阈报告到达后全部模型p1/RUL0，容量回弹不撤销首次事件。物理serial仍未知，calendar week不是cycle/EFC。

473无新报告对DART精确平移误差<=2.8e-16；61cell/1193到达panel全覆盖，57首次确认均闭合、233已确认后保持、903普通更新。闭合是共同逻辑权限。CDF最大1+4.44e-16、近p1导出S+最小约-1.41e-9，216行严格范围边界瑕疵保留；p1时S+空值不适用。84条无限bin logscore不删除、不截断。

## 贡献和下一步
文献审查：联合纵向事件、动态生存、发生/报告分离和Wiener在线RUL均有前作。DART当前是判别式分布向量，不是完整纵向生成联合模型；固定7天迟到不意味着已学到现实报告机制。2026部分竞争全文不可得，细节unverified，不从摘要补全。

本轮完成问题定义、强基线、候选原型和负结果；尚不支持优于强简单方法的新算法论文。[C4方案](DART_V18_CONFIRMATION_PLAN_ZH.md)未放行。下一步先解释神经分布过窄/逐cell失败及新信息价值；仅当不同机制及合法train-only目标成立才另签新预算。旧双状态STOP/标量小增益/GRU NO_GAIN均保留。

## 文件与预算
[主决定](../experiments/dart_rul_v18/analysis_v2/root_decision.json)、[三seed逐臂表](../experiments/dart_rul_v18/analysis_v2/three_seed_arm_summary.csv)、[到达摘要](../experiments/dart_rul_v18/analysis_v2/arrival_summary.csv)、[隐匿/负例](../experiments/dart_rul_v18/analysis_v2/hidden_and_negative_probability.csv)。静态源码、GO、回执、独立审查和竞争矩阵以白名单无损package提供，原始数据/权重/新54MB逐query预测不在公开镜像。不要把摘要可读等同全部实验原材料公开。

累计CPU57（MATR41另记）、神经18fits/6281steps，无新训练/确认GO。唯一battery-dynamic-rul15分钟任务沿用，当前聊天第一次实际compaction只checkpoint，第二次才fresh接续，不重复前驱触发。

旧全文历史[验证与解码](../reports/progress_history_public_lossless_v18_binary_20261021_root/validation.json)逐字节保存；本入口为当前精简上下文。公开状态应以实际public_snapshot和提交回读为准。
