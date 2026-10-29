# 2026-10-29 RULaaS 首轮开发实验已完成

目标模式 ACTIVE。冻结强 HGB，0 新拟合、0 优化步、0 C4，完成 17760 条重建可见历史的预测；62 个查询电芯。六种策略共用固定查询、参考事件及廉价循环信息。

结论：SUPPORTED_IN_THIS_FIXED_MODEL_GATE。只检验已有检测机会的信息保留价值；没有共享队列/真实干预或SLO保证。

[真实结果](experiments/rulaas_value_gate_20261029/run02/RESULTS_ZH.md)、[计划](experiments/rulaas_value_gate_20261029/PLAN_ZH.md)、[独立指标重算](experiments/rulaas_value_gate_20261029/run02/INDEPENDENT_RECOMPUTE.json)。

下一步：Implement a bounded queue-aware observed-opportunity scheduler comparison; frozen model and delayed visibility, no controller using unavailable RUL labels.

P4 已完成 NO_GAIN；旧“历史已被完全表达”的表述应收缩为该表示与预算未检出增量。既有尾部探针/OOF切换 NO_GAIN 继续保留，不重跑。C3 仍是多轮开发，不能宣称独立确认。

---

# 2026-10-27 M2 更新（当前）

完成 M2「训练 OOF 选择的尾部切换」（0 拟合）：**NO_GAIN，且训练数据否定了外推方向**。
OOF 上 cell-macro MAE 随阈值单调下降（τ=8 时 3.208 → τ=40 时 2.480），选择落在网格边缘 τ*=40（切换几乎不激活）；
C3 冻结评分：全体 2.444 vs tree 2.460，Δ **−0.015 [−0.046, 0.000]**，无收益。
上一轮在 C3 上看到的 32+ 桶改善（τ=12：11.92→9.17）在 OOF 上不复现（τ=12 OOF 2.888 反而更差）→ **C3 特定伪效应**。
结论：长寿命尾部低估（32+ 桶偏差 ≈ −11 周，四类方法一致）不是"外推/校准"能解决的，是**信息源限制**；
停止尾部外推方向，保留负结果。

[ M2 结果](experiments/rul_time_recovery_20261026/M2_RESULTS_ZH.md)、[决策](experiments/rul_time_recovery_20261026/M2_DECISION.json)、
[P2 诊断](experiments/rul_time_recovery_20261026/P2_DIAGNOSIS_ZH.md)。
下一步（需新 GO）：在训练数据中寻找对长寿命可辨识的信息（早期库仑效率/温度/工况组），
或把 32+ 尾部作为显式失败边界（下界 + 不确定区间）写进论文，不假装解决。本轮 0 fit、0 C4。

---

# 2026-10-27 P2 诊断更新（当前）

完成 P2 误差结构诊断（0 拟合）：**强基线的误差由长寿命电芯系统性低估主导**——|误差| 与目标 RUL 相关 0.853；
32+ 周桶（261 查询、仅 7 电芯）占全部绝对误差 **41.5%**、偏差 −11.5 周；12–32 周占 37.4%。F3/P1/P3 校准三者尾部都同样失败
（32+ MAE 11.46/10.88/12.24），校准反而放大尾部偏差。臂间差异很小（raw/sparse2/delay7d 2.29/2.46/2.57）→ 延迟/稀疏不是主因。

预注册尾部探针（斜率穿越时间，0 拟合）：32+ 桶 11.46→**9.08** 周，但 12–32 桶 3.71→4.89 周，总体 +0.317 周
（CI [−0.107,+0.754]）→ **NO_GAIN**，停止该规则，不在 C3 上调阈值。

下一机制（需新 GO）：**训练 OOF 选择的尾部切换**——阈值/混合方式只在训练电芯 OOF 上选并冻结，C3 只评分；
对照 TREE / EXTRAP-only / 固定阈值 / OOF 切换，关键消融去斜率；成功需 32+ 改善且 12–32 不恶化、配对 CI 不含 0。

[诊断与探针](experiments/rul_time_recovery_20261026/P2_DIAGNOSIS_ZH.md)、[决策](experiments/rul_time_recovery_20261026/P2_DECISION.json)。
本轮 0 fit、0 C4；C3 仅开发集；CALCE RUL 标签门保持。

---

# 2026-10-27 P4 更新（当前）

完成 P4 直接 RUL 监督的历史信息检验（4 神经 fits + 3 固定 HGB fits，720 优化步，27.9 秒，0 C4）：**NO_GAIN**。
HGB 当前+固定历史摘要 2.414 周中位 MAE，比原 F3 中位数 2.290 更差（Δ+0.124，CI[-0.006,+0.266]），显著差于 P3 线性校准
（+0.226[+0.053,+0.438]）；GRU_current/history 7.14/7.73 周，且 history 比 current 更差（+0.6 周），cov80 仅 0.21–0.30。
结论：完整历史信息已被静态 710 维 F3 摘要充分表达（该预算下），停止该配置；不扩网络、不加种子、不换端点。
恢复主线累计 25 次 CPU 估计器拟合 + 4 神经 fits，0 C4。

[P4 结果](experiments/rul_time_recovery_20261026/P4_RESULTS_ZH.md)、[决策回执](experiments/rul_time_recovery_20261026/P4_DECISION.json)、
[代码与自检](experiments/rul_time_recovery_20261026/p4_history.py)、[预验证](experiments/rul_time_recovery_20261026/p4_verify_20261027T1500Z/verify.json)。
下一条：按计划进入证据驱动的 P2 机制选择（不得再只做历史对照），或按人类指示切换；任何新机制需新 GO，
门槛为 raw/unconfirmed 上超过 P3 线性校准/F3 均值且配对 CI 不含 0。C4 本轮 0 读取；CALCE RUL 标签门保持。

---

# 2026-10-27 P3 更新（当前）

完成3次训练OOF条件校准+1次同工况参考库装配。线性校准raw/unconfirmed中位数MAE2.188周，但相对更强F3均值/P1直接回归的配对CI含0，竞争门槛未过；同组寿命/容量参考失败。累计18次CPU估计器拟合，0C4。

[P3实测与风险](experiments/rul_time_recovery_20261026/P3_RESULTS_ZH.md)。下一条：[直接RUL历史检验](experiments/rul_time_recovery_20261026/P4_HISTORY_PLAN_ZH.md)，待实现/审核/新GO，不是已执行结果。目标ACTIVE，不把已知校准作为创新。

---

# 2026-10-26 P2 实测更新（当前）

已完成0次新预测器训练的线性PR对照（30120条修正）和9次CPU拟合的退化时间尺度机制（15060条预测），均NO_GAIN；失败配置停止。恢复主线累计15次CPU拟合、0C4。

[P2结果与下一步](experiments/rul_time_recovery_20261026/P2_RESULTS_ZH.md)。候选raw/unconfirmed MAE2.650周，比旧F3中位数2.290周更差；派生时间尺度特征对照也未赢。下一步检验训练OOF条件残差校准，另签GO，不以容量预测替代RUL，不把校准直接当创新。目标ACTIVE，论文竞争力仍未达标。

---

# 2026-10-26 RUL 时间主线纠偏（当前）

目标模式已在新主控启动，owner=`01a17810-6ae6-7cf2-9729-5bfcaa8df5f4`。当前任务是 RUL 剩余周数，不将容量任务替代主指标。

- 完成：P1严格电芯隔离6次CPU拟合，0 C4；主指标NO_GAIN。旧0.506/0.522周来自C3原集拟合评分，已标INVALID_FOR_GENERALIZATION，其“A3无增量”结论亦无效。
- 证据：[研究计划](docs/RUL_TIME_RECOVERY_PLAN_20261026_ZH.md)、[P1真实结果](experiments/rul_time_recovery_20261026/P1_RESULTS_ZH.md)、[决策回执](experiments/rul_time_recovery_20261026/P1_DECISION.json)。
- 下一步：P2保存预测/训练OOF误差结构诊断，冻结一个新机制后另签有界GO；无P1重跑。旧预算和NO_GAIN保留。
- 边界：C4已在10月25日做过容量推断，不能再笼统称从未查看；本轮禁止C4读取。CALCE旧RUL标签门保留；C3只属开发。GitHub本次更新尚待同步。

---

以下是原入口历史原文，其中“当前”或“C4未读”等陈述仅代表原日期状态：

# Battery Dynamic RUL 当前进度
2026-10-21：真实原始信号信息研究已完成第一阶段与无报告/工况隔离实验，独立机制在正式评价中。权威科研根 `/home/yndx/zxk/rul`；C4封存未读。

- 已完成：188电芯4108条RPT及1,248,949条Cycling来源记录的流式缓存资产；正式F0/F1/F2/F3 2×2与6项冗余控制，80次同权限HGB/CatBoost重训、75,300条C3预测；逐电芯配对/概率/尾部风险分析。
- 证据：[科学结论与主表](reports/multisource_20261021_root/FORMAL_INFORMATION_RESULTS_ZH.md)、[正式回执](experiments/multisource_factorial_20261021/MULTISOURCE_FORMAL_2X2_80FITS_CLOCK_VALIDITY_REPAIR_20261021_receipt.json)、[逐电芯证据](reports/multisource_20261021_root/formal_primary_per_cell.csv)、[六面板图](reports/multisource_20261021_root/formal_information_figure/formal_information.svg)。HGB F0→F3三臂MAE2.029/2.230/2.344→1.606/1.730/1.826周。
- 最小验证：原成员CRC/SHA、原始索引/时间可见性、125/63来源角色不变，实际query124/62；全部拟合先于C3；配对按物理电芯重抽样。3条无效时钟整记录保留为未知，不推断只有3个真实循环缺失。C4读取0。
- 风险：CatBoost F3虽平均改善但严重高估/校准误差增加；Q2现有证据主要稀疏RPT时刻对照，off-RPT网格在执行；A四分支已完成，F3首步前格式错误保留，剩余分支新GO继续，F2未重训；B轨迹模型落后同输入强容量基线，失败保留。没有独立确认或未见工况/跨体系结果。
- 下一步：完成A动力学/观测更新消融、同多源next-capacity强基线和off-RPT网格，依据机制与误差决定方法；不回到V18局部结构调参。

V18及旧STOP/NO_GAIN/NO_GO全部保留。旧57CPU+18神经/6281steps；本轮已完成156CPU（20pilot+6capacity+80formal+18多源容量+32工况隔离）及B1两神经1000steps、A四分支2000steps；A完整评价进行，实际尝试/步数以回执为准，失败前的尝试不抹除。MATR41另记。新授权不复用旧GO。C4/Final/test未解封。现有heartbeat不重复创建。
公开仅白名单代码、协议、资产清单、必要结果和文献证据；原始信号/权重/论文全文/认证/会话不公开，12MiB上限维持。旧公开预测无损归档并保留旧提交。

最新[科学综合](reports/multisource_20261021_root/RESEARCH_SYNTHESIS_ZH.md)：off-RPT网格70032预测证实绝对信息增益、即时更新增益有限；held-G内部32拟合未支持Cycling增益；18次多源容量拟合显示F2短期最佳/F3寿命更佳。新B2为联合检查时间与容量路径方法准备中，尚未拟合。第二体系获取受访问/传输限制，未完成实证。

优先读取科学综合，区分信息价值、机制与独立确认。
