# 2026-10-30 KIT 阻抗数值增量开发对照（当前）

目标 ACTIVE，论文门未通过。KIT 16 个外部工况仍封存；C3/C4 读取均为 0。519 个共同查询中 105 个随后观察到记录事件、414 个右删失。当前阻抗配置 `NO_GAIN_FIXED_KIT_EIS_INFORMATION`：相同阻抗检测时间信息下，HGB 中位预测 MAE 为 7.75 周，加入阻抗数值后为 8.17 周；配对差 +0.42 周，三项比较校正后的 98.333% 工况组重抽样区间 [+0.17,+0.58] 周，2/16 电芯改善、14/16 恶化。纯容量斜率参考 2.79 周。

阻抗候选四周 Brier 从 0.1583 升至 0.2212，事件前四周漏报由 1/16 降至 0/16，名义 80% 区间在事件查询中覆盖约 34%；保留这一权衡。查询时序复核 1045 条通过；独立重算 2076 行及 519 条保存模型预测通过。仅有 6 个可观察事件工况；开发结局先前已使用，截止时点回顾性选取。报告送达时间未知；不能认定所有阻抗信息无用，更不能视为独立确认。

[阻抗对照报告](experiments/rulaas_external_kit_20261030/EIS_VALUE_RESULTS_ZH.md)、[逐电芯](experiments/rulaas_external_kit_20261030/eis_value01/paired_per_cell.csv)、[独立复核](experiments/rulaas_external_kit_20261030/eis_value01/INDEPENDENT_RECOMPUTE.json)、[阻抗时序审计](experiments/rulaas_external_kit_20261030/eis_asof_audit01/INDEPENDENT_RECOMPUTE.json)、[源码及历史文件无损归档](reports/rulaas_public_eis_code_lossless_20261030_v1/README.md)。

---

# 2026-10-30 KIT 开发对照：斜率锚定候选未通过（已完成）

目标 ACTIVE，论文门未通过。KIT 来源与官方归档及清单校验一致；16 个外部工况仍封存。第 400 天方案在 162 个截止后查询上全为删失，`INSUFFICIENT_KIT_DEVELOPMENT_SUPPORT`；再按训练工况预列支持规则回顾性选择第 100 天，原结论保留。

第 100 天开发对照保留 519 查询（105 后续事件、414 删失）；在 6 个事件工况、16 电芯上，纯斜率、HGB、删失 AFT、斜率锚定 AFT 的中位预测 MAE 分别 2.79、7.70、21.05、96.25 周。锚定相对纯斜率增量 +93.46 周，四项校正区间 [+13.09,+194.37]；15/16 电芯恶化，预警遗漏 15/16。状态 `NO_GAIN_FIXED_KIT_SLOPE_ANCHOR`；独立重算 2595 行并复核 519 次保存模型输出通过，停止该配置。0 C3/C4。

四周可判定标签仅 16 阳性、485 阴性，另 18 未知；低 Brier 不能掩盖漏报。保留组结局先前使用过，时点选择回顾性，且结果只覆盖有可观察事件的电芯；报告到达时间未知，不能称论文达标或独立确认。下一步审计其他检测信号在查询时是否已完成，比较其信息增量及纯斜率强基线。

[第100天结果](experiments/rulaas_external_kit_20261030/ANCHOR_DAY100_RESULTS_ZH.md)、[逐电芯](experiments/rulaas_external_kit_20261030/anchor_day100_01/paired_per_cell.csv)、[独立复核](experiments/rulaas_external_kit_20261030/anchor_day100_01/INDEPENDENT_RECOMPUTE.json)、[第400天结果](experiments/rulaas_external_kit_20261030/ANCHOR_DAY400_RESULTS_ZH.md)、[源码与旧文件无损归档](reports/rulaas_public_kit_code_lossless_20261030_v3/README.md)。

---

# 2026-10-30 右删失动态剩余寿命对照（已完成）

目标 ACTIVE，论文门未通过。同一 10 个既用保留工况组、18 电芯、536 查询，HGB、完整事件 AFT、加入右删失的 AFT 的中位数 MAE 分别为 1.952、1.788、4.640 周；加入删失相对 HGB 的增量为 +2.688 周，双比较校正区间 [+0.370,+5.088]，相对完整事件 AFT 为 +2.852 周，区间 [+0.602,+5.176]。预警遗漏从 0/51 增至 1/51，11/18 电芯比 HGB 更差。预设判定 `NO_GAIN_FIXED_CENSORED_RUL_SCREEN`，独立重算通过，停止此配置；0 C3/C4。

训练使用 900 条完整正事件与 450 条右删失（13 组）以及共用零事件模型；两种训练工况仅有 2 组重叠，无法归因于删失本身。反馈通道是未证实的检测后 14 天全量登记假设，保留组此前使用过，不是独立确认。下一步接入有独立工况预留的公开 KIT 数据，先核验来源、标签及时间语义，C4 继续封存。

[结果](experiments/rulaas_temporal_risk_20261029/SURVIVAL_PILOT_RESULTS_ZH.md)、[复核](experiments/rulaas_temporal_risk_20261029/survival_pilot01/INDEPENDENT_RECOMPUTE.json)、[逐电芯](experiments/rulaas_temporal_risk_20261029/survival_pilot01/paired_per_cell.csv)、[源码无损归档](reports/rulaas_public_survival_code_lossless_20261030_v1/README.md)。

---

# 2026-10-30 部分随访反馈与完整事件反馈比较（已完成）

目标 ACTIVE，论文门未通过。固定相同 F0 信息、10 个保留工况组、18 电芯和 536 条共同查询，完整事件成熟后的校准 Brier 0.10435；加入截止前已成熟的 279 条四周阴性后为 0.08981，相对下降 13.94%，但配对组重抽样区间 [−0.03159,+0.00028] 跨零，预设门槛未过，`NO_GAIN_FIXED_PARTIAL_FEEDBACK_F0`。原始未校准 Brier 0.10103→0.09898，区间也跨零；校准后阳性查询漏判 2.79%→4.47%，失效前电芯×臂窗口漏报均 0/51，14 电芯改善、4 恶化。0 C3/C4。

新增标签、训练组数和类别比例同时变化；其中 374 条查询仍未成熟或删失。参考登记端会在检测后 14 天收到所有已记录测试，属于未证实的模拟假设，可能包含实际策略会跳过的检测；之前保留组已经被查看，不能称独立确认或真实服务收益。独立复核 1219 条训练标签成熟时刻、工况组拆分、536 条共同查询和置信区间通过。先前 F3 风险 NO_GAIN 与固定在途策略 NO_GO 继续保留。

[结果](experiments/rulaas_temporal_risk_20261029/PARTIAL_FEEDBACK_RESULTS_ZH.md)、[独立复核](experiments/rulaas_temporal_risk_20261029/partial_feedback01/INDEPENDENT_RECOMPUTE.json)、[逐电芯](experiments/rulaas_temporal_risk_20261029/partial_feedback01/paired_per_cell.csv)、[方法冲突](experiments/rulaas_temporal_risk_20261029/METHOD_CONFLICT_CHECK_ZH.md)。下一步审计截止前可以构造的右删失寿命下界，在同一假设反馈通道和工况组隔离下探索不同的完整 RUL 生存基线；不得回跑停止配置。

---

# 2026-10-30 工况组时序风险筛查与部分随访标签（已完成）

目标 ACTIVE，论文门未通过。按整个工况组隔离并假设参考失效事件 14 天后才有标签：15 个成熟训练组、10 个保留组，940/536 条未知失效查询。校准 F3 HGB 的 Brier 0.0996，F0 HGB 0.1044，校正区间包含零且改善未达 5%，失效前窗口漏报 1/51 对 0/51，`NO_GAIN_FIXED_F3_RISK_SCREEN`，停止该配置。完整 F3 逻辑回归校准后 51/51 漏报，原始版为 6/51；不能只用退化参考宣称优势。

首轮审计时间格式失败、复核首次报告序列化失败，失败收据及修复后通过的独立复核均保留。训练折外诊断发现逻辑回归 940 条中 529 条概率近 0 或 1，校准压缩后报警明显减少；校准器在同一折外分数上评价，训练诊断不能称独立。风险实验 15 个预测/校准拟合、8 个预处理组件；相关阶段 C3/C4 均为 0。

固定截止下仅使用假设已到达参考记录，可额外成熟 279 条四周阴性随访标签，共 1219 条、19 训练组；另 374 条未成熟或删失保持未知，新增条目均非无精确 EOL 电芯。该参考登记端假设能收到所有记录，即使策略会跳过检测，真实反馈不可验证；这是支持诊断，不是模型收益。

[风险结果](experiments/rulaas_temporal_risk_20261029/RESULTS_ZH.md)、[独立复核](experiments/rulaas_temporal_risk_20261029/run01/INDEPENDENT_RECOMPUTE_V2.json)、[成熟度诊断](experiments/rulaas_temporal_risk_20261029/HORIZON_RESULTS_ZH.md)、[诊断复核](experiments/rulaas_temporal_risk_20261029/horizon_audit01/INDEPENDENT_RECOMPUTE.json)。下一步只将部分随访作为独立反馈机制，与固定 F0 参考在相同组/时序查询上比较；不重跑停止的 F3 配置。

---

# 2026-10-29 三个 C3 开发车队：固定在途规则风险门未过（已完成）

目标 ACTIVE，论文门未通过。冻结的在途规则相对训练车队校准的年龄参考，在 3 支 C3 车队、2/4 台站的六个场景中平均点 MAE 均下降，但 F1 两台站失效前四周漏警由 0/21 增至 2/21；F3 两台站名义 80% 覆盖由 67.7% 降至 66.7%，最差电芯 MAE 增 1.256 周。按事先风险停止条件，`NO_GO_FIXED_PENDING_RULE_RISK_GATE`，停止这个固定规则，不在 C3 调阈值。

61 个 C3 电芯有共同查询，60 个有失效前可评分查询；共 17022 条查询输出、10361 个模型输入、0 新拟合、0 C4。独立复核 7524 次接纳决定、3839 次站点分配、17022 条查询，概率、Brier、区间、删失和漏警重算通过。2 台站汇总 MAE 3.109→3.038 周，60 电芯中 25 恶化，漏警 3/60→4/60；4 台站 MAE 3.058→2.967 周，19 恶化，漏警 4/60→3/60。各车队 80% 名义区间覆盖仅约 61%–73%。

14 天延迟为假设；三支车队互不共享电芯，但同属此前使用过的 C3 数据，且 C3 的 63 个工况组全部在训练中有同组电芯。实际占站小时不同，无严格等预算或独立车队置信区间；不能声称论文级收益。下一步使用 C1/C2 的工况组隔离折外标签和相同信息强风险参考，先审计删失及标签可用时间，再研究不同的可靠性约束机制。

[结果](experiments/rulaas_c3_fleets_20261029/RESULTS_ZH.md)、[风险门决策](experiments/rulaas_c3_fleets_20261029/run01/ROOT_DECISION.json)、[独立复核](experiments/rulaas_c3_fleets_20261029/run01/INDEPENDENT_RECOMPUTE.json)、[逐电芯](experiments/rulaas_c3_fleets_20261029/run01/paired_per_cell.csv)、[漏警诊断](experiments/rulaas_c3_fleets_20261029/run01/RISK_DIAGNOSIS.json)。

---

# 2026-10-29 在途接纳与训练校准年龄参考（已完成）

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
