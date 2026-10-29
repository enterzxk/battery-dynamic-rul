# 2026-10-29 有限检测站基线已完成（当前）

目标ACTIVE，论文门未通过。真实回放62电芯、2960共同查询、2/4台检测站四种策略，共23680预测；21730实际模型行，0新拟合/0C4。全部可见前缀、来源事件、站点重叠与成本独立重算通过。

M4陈旧程度规则：占站13415.1→9303.3小时（−30.65%），失效前MAE2.8097→2.8400周（+0.0303），漏报同为2/61，但80%覆盖率降低2.38pp且误报增加；只有一个耦合车队，不称非劣/正式节费。M2同规则省23.48%占站、MAE+0.0196周，最坏电芯恶化2.609周。固定宽度门限漏报58/59个事件，停止该配置；固定风险门限近似全接纳，未见可靠选择效果。

[结果](experiments/rulaas_station_admission_20261029/run01/RESULTS_ZH.md)、[独立复核与逐电芯损害](experiments/rulaas_station_admission_20261029/run01/INDEPENDENT_RECOMPUTE.json)、[方法冲突核查](experiments/rulaas_station_admission_20261029/METHOD_CONFLICT_CHECK_ZH.md)。

下一条：[训练检测增益可辨识性](experiments/rulaas_station_admission_20261029/NEXT_GAIN_IDENTIFIABILITY_PLAN_ZH.md)，需新GO；不重跑失败配置、不在C3调门限。完整服务收益、迟到寿命标签反馈、独立确认仍未完成。

---

# 2026-10-29 RULaaS 首轮开发实验已完成

目标模式 ACTIVE。冻结强 HGB，0 新拟合、0 优化步、0 C4，完成 17760 条重建可见历史的预测；62 个查询电芯。六种策略共用固定查询、参考事件及廉价循环信息。

结论：SUPPORTED_IN_THIS_FIXED_MODEL_GATE。只检验已有检测机会的信息保留价值；没有共享队列/真实干预或SLO保证。

[真实结果](experiments/rulaas_value_gate_20261029/run02/RESULTS_ZH.md)、[计划](experiments/rulaas_value_gate_20261029/PLAN_ZH.md)、[独立指标重算](experiments/rulaas_value_gate_20261029/run02/INDEPENDENT_RECOMPUTE.json)。

下一步：Implement a bounded queue-aware observed-opportunity scheduler comparison; frozen model and delayed visibility, no controller using unavailable RUL labels.

P4 已完成 NO_GAIN；旧“历史已被完全表达”的表述应收缩为该表示与预算未检出增量。既有尾部探针/OOF切换 NO_GAIN 继续保留，不重跑。C3 仍是多轮开发，不能宣称独立确认。

---

# 2026-10-29 RULaaS goal activated

Human approved continued bounded experiments toward publication-quality evidence. First action: fixed-HGB RPT-information retention gate, 0 fits, 0 C4; plan and exact-hash GO in experiments/rulaas_value_gate_20261029. No new service gain established. P4 actually completed on 2026-10-27 with NO_GAIN (4 neural fits, 3 HGB fits, 720 optimizer steps); older pending wording below is historical.

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
