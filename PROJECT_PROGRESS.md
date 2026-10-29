# 2026-10-29 在途接纳与训练校准年龄参考（当前）

目标 ACTIVE，论文门未通过。14 天为假设报告延迟，24 个保留电芯、每种站点容量 897 个共同查询，0 新拟合/0 C3/0 C4。两台站：训练校准年龄规则/在途规则的失效前逐电芯平均点 MAE 为 3.010/2.831 周、占站 3044.9/2968.1 小时，14 电芯改善、4 不变、6 恶化；最后失效后查询仍未确认 7/21 与 6/21。四台站：MAE 2.900/2.807 周、占站 3149.5/3117.4 小时，13 改善、3 不变、8 恶化；仍未确认均为 5/21。每个场景实际占站相差 2.59% 或 1.03%，容量相同但并非严格等成本。

原 1.325 周年龄阈值在此 14 天延迟下等同于有空即接纳，不能称为强节费参考。后补参考的 2.75/3.25 周阈值只在训练车队以固定网格匹配占站小时，不用保留车队选择；但提出补充比较之前已看到保留结果，且本批电芯此前参与开发。独立复核通过全部 24 个训练校准世界、802 个保留决策和 1794 对查询。两规则的查询陈旧度均有约 36%–41% 超原训练最大范围。当前点代理没有完整事件分布、失效前报警、真实延迟、删失反馈或独立确认，不能认定论文级收益；此前增益模型 NO_GAIN 保留。

[结果](experiments/rulaas_pending_station_20261029/RESULTS_ZH.md)、[补充对照独立复核](experiments/rulaas_pending_station_20261029/age_comparator01/INDEPENDENT_RECOMPUTE.json)、[逐电芯](experiments/rulaas_pending_station_20261029/age_comparator01/paired_per_cell.csv)、[决策](experiments/rulaas_pending_station_20261029/ROOT_DECISION.json)。下一步冻结策略和训练阈值，在互不重叠的 C3 开发车队用完整事件分布比较；C3 已参与以往开发，不作为最终独立确认，C4 仍锁定。

---

# 2026-10-29 在途报告信息重叠诊断（已完成）

目标 ACTIVE，论文门未通过。训练电芯和保留电芯共 184 案例、1,472 时点，0 新拟合/0 C3/0 C4；报告延迟 14 天为假设。24 个保留电芯的 80 个在途案例中，正常到达时新增检测代理增益 0.129 周、假设在途报告永不到达时 0.422 周，差 0.294 周、按 24 个来源组的区间 [0.121,0.481]；训练人口差 0.268 周、区间 [−0.194,0.580]。保留案例 42 正/21 零/17 负、5 个电芯平均方向相反，不能只报均值。

独立复核时序与标签通过。保留在途请求 33/80 超出原训练最大陈旧度；全部 3165 个去重模型输入中 1766 个超出。没有完整事件分布、真实延迟、可执行的同资源策略或独立确认；反事实屏蔽既有在途报告不能包装为节费。五模型 NO_GAIN 与折外标签修正结论继续保留。

[结果](experiments/rulaas_pending_value_20261029/run01/RESULTS_ZH.md)、[独立复核](experiments/rulaas_pending_value_20261029/run01/INDEPENDENT_RECOMPUTE.json)、[支持范围](experiments/rulaas_pending_value_20261029/run01/support_stratification.json)。下一步：固定在途感知策略，与年龄基线在同站点容量和共同查询上比较，并如实报告实际资源、误差和逐电芯损害。

---

# 2026-10-29 检测增益学习与折外标签修正（已完成）

目标 ACTIVE，论文门未通过；用户已明确选择当前 GPT-6.1 Terra。增益学习五个预注册估计器全部完成，24 个 C1/C2 保留电芯、85 个案例上的逐电芯增益预测 MAE：F0 0.7387、F2 0.7398、F3 0.7498 周，F3/F2 均未胜过预设全部强参考，NO_GAIN，停止原配置。事后零增益参考 0.6503 周，仅是预测参考、不是跳过检测建议。0 C3/C4。

训练案例原标签来自见过该电芯的回归头；严格电芯折外修正完成 3 个头、101 个训练案例，原 85 保留案例及输入不变。旧/新训练案例平均增益 0.8671/0.4615 周、平均绝对标签变化 0.7544 周、负增益 4/19；独立重算 808 时点与到达前条件通过。新头训练 40 电芯、原保留头训练 60，差异不能完全归因过拟合；没有在途案例、真实延迟或排队服务验证，不能宣称论文竞争力。

[增益结果](experiments/rulaas_gain_learning_20261029/run01/RESULTS_ZH.md)、[独立复核](experiments/rulaas_gain_learning_20261029/run01/INDEPENDENT_RECOMPUTE.json)、[折外修正结果](experiments/rulaas_gain_oof_repair_20261029/run01/RESULTS_ZH.md)、[独立复核](experiments/rulaas_gain_oof_repair_20261029/run01/INDEPENDENT_RECOMPUTE.json)。下一步：检查有在途变化的因果调度决策及同资源强参考；不重复停止的模型配置。

---

# 2026-10-29 训练检测增益代理与模型选择（历史：已执行）

历史状态：当时曾等待模型选择；用户后来已选择 Terra，五个模型现已完成，详见本文件最上方的当前结果。

已有0拟合标签实验186候选/48C1C2电芯；未被回归头拟合过的人口为85候选/24电芯，测试结束立即交付的平均增益0.526周，延迟7天0.391周；24候选为负增益，14为零，47为正。电芯bootstrap即时−延迟0.135周[0.061,0.207]，仅固定代理与选定案例的探索区间，同组依赖未建模。拟合人口与保留人口差异不能直接归因过拟合。

独立核查全部1488标签槽、来源事件、测试窗口、输入及未到达记录扰动；原186样本在途报告数全为0。元数据审计邻近机会在7天假设下仅3/76保留案例有在途，14天假设80/85但33/85输入超原训练最大陈旧度；报告延迟并非实测。无价值模型拟合、无C3/C4数据读取。

[结果](reports/rulaas_gain_review_20261029_terra/REVIEW_ZH.md)、[核对](reports/rulaas_gain_review_20261029_terra/AUDIT.json)、[等待报告支持](reports/rulaas_pending_lag_support_20261029_terra/AUDIT.json)、[下一次拟合预注册草案](experiments/rulaas_gain_learning_20261029/PROTOCOL_ZH.md)。代理不是完整hurdle服务效益，未来报告丢失/未采样的物理退化反事实尚未证实，论文门未通过。

---

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
