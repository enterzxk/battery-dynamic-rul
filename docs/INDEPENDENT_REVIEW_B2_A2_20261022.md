# B2 / A2 独立审稿备忘录（2026-10-22）

- 审稿角色：独立审稿 worker（只读；仅创建本文件，不改代码/数据/GO）。
- 审稿对象：B2 轨迹主线（reports/multisource_20261021_B2_trajectory/RESULTS_ZH.md 与 candidate_v2）、A1 对照、A2 状态机制（experiments/multirate_state_A2_20261022）、docs/DSH_PROGRESS_20261022_ZH.md。
- 方法：SSH 只读检查；对已保存 predictions 重新做 cell-equal 指标、paired cell bootstrap（5000 次，seed 42）与失败/已知事件/删失敏感性；未读 C4，未改任何代码、数据或 GO。
- 总体结论：**FAIL**（B2 主线）；**CONDITIONAL**（A2）；G（C4/raw/凭据）**PASS**。

## 0. 一句话结论

B2 报告的主比较用错了 B1 模型：eval_rul_compare.py 的 compm 字典按 (cell, arm, query) 建键，后写入的 B1 **independent 消融**覆盖了先写入的 B1 **full**；报告中的 13.66 周 MAE / 0.88 cov80 全部来自该消融。对设计文档明确称为 B-full 的完整机制模型，B2 的 MAE 是 6.38 vs 4.11（B2 更差），RMSE 16.82 vs 7.12，pinball50/90 也更差。因此“B2 显著优于 B1 比较器”的论文-facing 结论方向相反，必须重跑比较后才能继续。

## 1. 结论与状态

| 主线 | 结论 | 关键理由 |
|---|---|---|
| B2 主比较 | **FAIL** | 比较器被覆盖为 B1 independent 消融；对 B1 full，B2 在 MAE/RMSE/pinball 上均更差，校准也未更好 |
| B2 选择/泄漏 | CONDITIONAL | 4 fits 确为 cell-isolated，val 25 个 cell 参与 full refit；但“125 cell”表述不实（实际 124），且 C3 失败后的代码加固未披露 |
| B2 失败语义 | CONDITIONAL | 68 失败中 65 个在 fixed_gap，且集中在长 RUL；主表仅 3 个失败，结论稳健；fixed_gap 对照的幅度不稳健且未披露 |
| A2 机制实现 | CONDITIONAL | sigma 单位、Qref、HPHᵀ、无 readout 四项经代码核对成立；但“full-125 refit”不成立（实际 100 train cells），6-fit 只有 3 个选择期 val NLL，最终 refit 未验证 |
| A2 可复现链 | CONDITIONAL/FAIL | 无 receipt、GO 未消费、GO 的 out_dir 未生效、全量 fit 早于 GO 声明签发时间 |
| G 边界 | **PASS** | B2 各 receipt C4_reads=0、raw_payload_reads=0；A2 PREP 为 125 个 C1/C2 train cells；未发现 C4/raw/凭据/被拦截下载 |

> 整体判定：**FAIL**（不是因为 A2 的数学，而是因为 B2 的论文-facing 主结论目前不成立）。

## 2. 逐项证据

### A. 比较公平性

#### A1. B1 比较器选错（P0，决定性）

证据链：

1. experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2/eval_rul_compare.py:82-86 读取 comparator CSV 时只按 (cell_id, arm, round(query_epoch)) 建 compm，**没有按 model 过滤**；同一键后写入者覆盖先写入者。
2. experiments/multisource_mechanisms_20261021/evaluation_runs/run3_exact_schedule_clock/predictions_c3.csv 共 7530 行：第 0–3764 行 model=full，第 3765–7529 行 model=independent；因此 compm 最终全部是 independent。
3. 报告 RESULTS_ZH.md:15-19 的“B1 比较器”数值（MAE 13.6594、RMSE 33.1498、cov80 0.88158、pin50 6.8297、pin90 4.6977）与我用 independent 行重算的值逐位一致；用 full 行重算则为 MAE 4.1101、RMSE 7.123、cov80 0.6084、pin50 2.0550、pin90 1.6482。
4. experiments/multisource_mechanisms_20261021/DESIGN_AND_INTERFACES_ZH.md 明确写“B-full 为条件 GRU 路径密度”“B-independent 为预设机制消融”；evaluate_v1.py:268 也把两者列为 full / independent。B1 的 metrics_by_model_arm.csv 中 full 的 known_event_restricted_RUL_MAE_weeks 为 3.39/2.67/3.13 周（delay7d/raw/sparse2），independent 为 13.65/13.19/9.74 周。full 才是设计中的强比较器。

cell-equal 重算（同一批 4637 个 B2 model-row / 2320 个唯一 query 键，61 cells）：

| 模型 | N | MAE(周) | RMSE(周) | pin50 | pin90 | cov80 | severe>4w | width80(周) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B2 joint | 2319 | 6.384 | 16.824 | 3.192 | 2.815 | 0.550 | 0.321 | 9.91 |
| B2 independent | 2318 | 6.346 | 18.588 | 3.173 | 2.057 | 0.687 | 0.262 | 18.87 |
| **B1 full（应使用的比较器）** | 2319/2318 | **4.111** | **7.123** | **2.055** | **1.649** | **0.608** | **0.330** | **7.11** |
| B1 independent（报告实际使用） | 2320 | 13.659 | 33.150 | 6.830 | 4.698 | 0.882 | 0.443 | 47.50 |

paired cell bootstrap（B2 − B1 full；负值才表示 B2 更好）：

| 模型 | 指标 | Δ | 95% CI |
|---|---|---:|---:|
| joint | MAE | **+2.2732** | [+0.7476, +4.1721] |
| joint | pin50 | **+1.1366** | [+0.3816, +2.0833] |
| joint | pin90 | **+1.1660** | [+0.5760, +1.8370] |
| joint | cov_dist | −0.0052 | [−0.0573, +0.0469] |
| joint | severe4w | −0.0096 | [−0.0632, +0.0410] |
| independent | MAE | **+2.2371** | [+0.5287, +4.2805] |
| independent | pin50 | **+1.1186** | [+0.2754, +2.1481] |
| independent | pin90 | +0.4092 | [−0.2376, +1.0009] |
| independent | cov_dist | −0.0647 | [−0.1461, +0.0149] |
| independent | severe4w | −0.0684 | [−0.1232, −0.0142] |

结论：

- 对 B1 full，B2 joint/independent 的 MAE、RMSE、pin50、pin90 全部更差；MAE 差值 CI 不含 0，方向为 B2 更差。
- 校准差（cov_dist）在 B1 full 下不显著；B2 independent 的 severe>4w 反而略好。报告“B2 点精度更好、但区间更差、严重误差更多”的三句话，只有“joint 在长视界过度自信”这一条在分层里成立。
- 报告 RESULTS_ZH.md:133-134 与 docs/DSH_PROGRESS_20261022_ZH.md:80 的“B2 显著优于 B1（MAE 6.38 vs 13.66）”必须撤回或重写；这不是措辞问题，是估计量选错。

#### A2. 同键匹配与 delay7d

- eval_rul_compare.py:89 只按 (cell_id, arm, round(query_epoch)) 匹配，**没有校验 B2 与 comparator 的 target_rul_weeks 相等**。这是代码层面的公平性缺口：只要 comparator 的 delay7d 目标时间偏移，脚本会静默用 B2 的 target 去评 B1。
- 但本 comparator 的实测是干净的：4637/4637 个匹配键的 target_rul_weeks 完全相等（最大绝对差 0）；raw 1798/1798、sparse2 922/922、delay7d 1917/1917 全部精确。A1 报告第 28–30 行警告的“B1 delay7d horizon 约 +1.14 周”属于 B1 的 next-capacity 面板，不是这个 RUL comparator；本 comparator 的 target 已统一。
- 因此：delay7d **不是本轮 B2 结论错误的原因**；但代码没有 target 等式断言，下一轮若换 comparator 会重演 A1 的问题。建议在 eval 中加 abs(target_b2 − target_comp) <= 1e-6 的硬断言。
- 报告 RESULTS_ZH.md:99 的“仍需注意 B1 的检查策略定义”是过时且误导的：本 comparator 的 target 已逐键相等，应改成“已核验 4637/4637 同目标；代码将加断言”，或者删除。
- 计数口径：RESULTS_ZH.md:11 的“匹配 4637 条查询”实际是 4637 个 B2 model-row（joint 2319 + independent 2318），唯一 query 键只有 2320；同理 nextjump 的 1806 是 903 键 × 2 模型（RESULTS_ZH.md:111、表 118-120）。这不影响数值，但会让读者高估样本量，应改为“2320 个唯一 query 键 / 4637 个模型行”。

#### A3. known-event（RUL=0）如何进入/排除

- infer_runner.py:174 对已到达事件把 target 截到 0；:175-188 对 visible 中已有 capacity<=0.20 的 query 直接输出 256 个 0 样本，**完全绕过模型**，并标 event_known_by_query=True。main 条件共 1630 行（815 anchors × 2 模型），占 main 6327 行的 25.8%。
- eval_rul_compare.py:76 明确排除 event_known_by_query=='True' 与 censored；因此主表 4669 行 = 6327 − 1630 − 28。报告只在 RESULTS_ZH.md:10 写了“已知事件锚点数 815”，没有说这些样本被排除，也没有说它们是规则零而非模型输出。
- 这会不会高估 B2？**不会，反而是保守**：把 known 加回同键面板后，B2 joint MAE 从 6.384 降到 5.046，B1 full 从 4.111 降到 3.203；B2 independent 4.980 vs B1 full 3.202。B2 仍然更差；known 的排除只是把两边都变难，并没有制造 B2 的优势。
- 但必须披露：25.8% 的 main 行是规则零且被排除；B2 的 known 处理不是模型能力。comparator 的 known_event 集合与 B2 完全一致（815 重叠，B2 非 known 键中 0 个被 comparator 标 known），所以不存在“B1 已知道、B2 不知道”的错配。

#### A4. censored

- main 中 censored 28 行（14 个 query × 2 模型），target 为空，eval 排除。占比 0.4%，不足以改变结论，但报告未披露；建议在表注中写“28 行删失，未计入”。

### B. 校准结论

- 报告确实把“点精度”和“区间”分开写了（RESULTS_ZH.md:133-134），这一点是好的；但两边的数值都来自 B1 independent 消融，所以比较对象错了。
- 对 B1 full 的正确图景：
  - B2 joint：cov80 0.550、width80 9.91 周、pin90 2.815；
  - B1 full：cov80 0.608、width80 7.11 周、pin90 1.649；
  - B2 independent：cov80 0.687、width80 18.87 周、pin90 2.057。
  B2 joint 的区间**比 B1 full 更宽**却覆盖更差；B2 independent 覆盖更高但区间宽 2.65 倍、pin90 更差。因此“B2 区间过窄”只对 joint 相对其自身名义值成立，不是相对 B1 full 的事实；“B1 校准 0.88 更接近名义值”则是消融的过宽区间买来的。
- “严重误差更多”也不成立：B2 joint severe>4w 0.321 vs B1 full 0.330；B2 independent 0.262。报告该句应改为“joint 在 12–32w 与 32w+ 分层过度自信；independent 以更宽区间换取覆盖”。
- 分层校准才是关键：报告 RESULTS_ZH.md:90-94 已给出 joint 12–32w cov 0.318、32w+ cov 0.074；同一批键上 B1 full 的 32w+ cov 约 0.095（也不佳），12–32w 约 0.354。两者在长视界都不可用，但 B2 joint 更差。报告不应把“B2 校准不足”写成全模型结论，而应写成“joint 的长视界校准失败；independent 的覆盖是宽度换来的”。
- pinball 与 coverage 没有在文字上被直接混为一谈；但表里只报 pin50/pin90，代码里其实算了 pin10（eval_rul_compare.py:31），而 80% 中心区间的 proper score 需要两尾（pin10+pin90 或 interval score/Winkler）。只报 pin90 会奖励“上尾宽、下尾窄”的区间。建议补 pin10、pin10+pin90 与 interval score，不要把 pin90 叫作“80% pinball”。

### C. 选择/泄漏

#### C1. B2 的 4 fits

- fit_runner.py:59-60 用唯一贡献 cell 的 20% 做内部验证；fit4-20261022T0600Z.json 记录 n_cells=124、internal_validation_cells=25、internal_validation_cell_ids 25 个；fit_ledger.json 四个记录：joint internal（ran 1550，selected 1250，best val −0.6186）、joint full125_refit（1250）、independent internal（1550/1250，−0.6070）、independent full125_refit（1250）。确为 4 fits、cell-isolated。
- fit_runner.py:115 的 full refit 用 np.ones(len(x),bool)，即 prepared 的全部行；因此 25 个内部验证 cell **确实参与**了 full refit。这一点没有问题。
- “125 cell”不实：prep-v2_1-20261022T0545Z 的 cell_ids 只有 124 个（G61C1 缺失，prepared_cell_count=124），fit4 的 n_cells=124，fit_ledger 的 normalization_source 却写 all125_cells。应改为“124 个贡献 cell / 125 个 train cell 中 1 个无合法路径”。
- 没有用 C3 选择 checkpoint：fit4 在 06:00Z 完成，C3 推断 06:45Z 之后；fit GO 的 data_scope 是 prepared_train_only_no_C3_C4；target_builder.py:36-37 拒绝 C3/C4 cell id。C3 只用于评估，不用于选模型。这一点是干净的。
- 但 C3 推断代码在 0725/0950 失败后做了加固（数值拒绝、arm-major、90s 预算、失败率门禁）；这是 C3 失败信息驱动的工程改动，不是标签泄漏，但属于研究者自由度，报告应披露“1005 是第三次尝试，前两次 void/failed”。

#### C2. A2 的“full refit”

- a2_train_v2.py:203 注释写得很清楚：“Full refit (same 100 train cells, same seed init, fresh RNG)”；:208-214 的 refit_sampler 用 data.train_index，refit 仍只在 100 个 train cell 上训练。25 个内部验证 cell **从未进入最终模型**。
- 但 GO_A2_FITV2_full.json 的 scope 写“internal cell-isolated selection + full-125 refit, exactly 2 fits for arm full”；README_A2_ZH.md:290 写“3 臂 × 内部选择 + 全量重拟合 = 6 fits”；DSH_PROGRESS_20261022_ZH.md:64 也写“6-fit”。这与代码不符。
- 这不是泄漏（val 仍是 held-out，反而更干净），但它是**协议/声明不一致**：最终模型不是全量 125，不能叫 full-125；如果改成全量 125，25 个 cell 的 val NLL 就不再是 held-out，必须另设选择集。
- A2 没有 C3 推断，因此不存在“用 C3 选择”的问题；也正因如此，A2 目前只有 val NLL，没有 RUL/容量精度结论。

### D. 失败语义

- 1005 run 的 68 个失败（receipts/c3infer-20261022T1005Z.json：failures=68、failure_rate=0.0035808）分布不是随机的：
  - 按条件：main 3 个、fixed_gap 65 个；
  - 按臂：delay7d 50、raw 14、sparse2 4；
  - 按 cell：20 个 cell，G26C3 一个 cell 占 23 个。
- 失败率：fixed_gap 65/4607 = 1.41%，main 3/4669 = 0.064%。fixed_gap 的失败是 main 的 22 倍。
- 68 个失败都能在 comparator 中找到 target；fixed_gap 失败 target 的中位数 24.54 周、均值 29.56 周，而 fixed_gap 存活 query 的 target 中位数 10.25 周、均值 14.01 周。也就是说，fixed_gap 的失败集中在**长 RUL/难 query**。
- 因此：
  - 主表（main）只掉 3 个失败，结论对失败偏差稳健；
  - fixed_gap_vs_free_gap 的 2315 条配对是**幸存者面板**，65 个长 RUL 失败被同时从 fixed_gap 侧删掉；存活 fixed_gap 更容易，报告 +11.7 周的幅度很可能偏小（方向不变，但“精确配对效应”不成立）。
- 报告 RESULTS_ZH.md:8、139 只说“68 个失败均为接受率<1% 的诚实拒绝”，没有披露 65/68 集中在 fixed_gap、也没有披露失败 target 更长。这是必须补的失败语义披露。
- 另：失败率分母 total_attempts = len(preds)+len(failures) 包含 4890 个 known-zero 行（这些永远不会失败），所以 68/18990=0.36% 被稀释；按真实非 known 尝试 68/14032≈0.48%。不改变门禁结论，但报告应说明分母。
- 历史失败：0725Z receipt status=C3_INFERENCE_COMPLETE，但 queries=7864、failures=11126（59%），当时没有 >10% 门禁；0950Z status=FAILED，14100 个 NameError('out_query_start' is not defined)，failure_rate=0.742。GO_C3_INFER_20261022T1005Z 的 supersedes 字段承认了 0725；RESULTS_ZH.md 只写 1005，没有写 0725/0950。论文/报告不应把 1005 说成“一次成功”。

### E. A2：sigma、Qref、HPHᵀ、无 readout，以及 6-fit val NLL

#### E1. 机制四项（看代码，成立）

- sigma 单位：a2_model.py:115-121 明确 obs_sigma 是 Ah 标准差、obs_variance=σ²；:196-199 过程噪声 d_sigma/r_sigma 先平方再进 Q；:245 total_var=latent+σ²；:269 NLL 用 0.5(ν²/S+log S+log2π)。fit_report.json 的 model_summary：obs_sigma_ah=0.0021031、obs_variance_ah2=4.4229e-6（另两臂 0.0021505/4.6244e-6、0.0020935/4.3829e-6），平方关系一致。**成立**。
- Qref：a2_targets.py:77-106 取 cutoff 前已到达、valid、容量有限的最早 arrival（并列按 stop、index）；:116-137 写入 q_ref，anchor 读数不计分；:172-197 只把 post-anchor RPT 作为事件。prep manifest 的 G10C1 q_ref_ah=0.2827415、anchor_record_index=0；**成立**。
- HPHᵀ：a2_model.py:232-233 H=[−Q_ref e^{−D},1]，latent_var=H P Hᵀ；:248-282 Joseph 更新 K=P Hᵀ/S、P←(I−KH)P(I−KH)ᵀ+K σ² Kᵀ、对称化；:296-307 线性化阈值概率明确标注为诊断、不是事件/首达概率。fast 路径 a2_fastdata.py:183-218 与 :197 的 latent=h0²p00+2h0p01+p11 代数一致；**成立**。
- 无 readout 旁路：a2_model.py:216-246 capacity_moments 只接受 (m,P,Q_ref)，输出 Q_ref e^{−D}+R；没有 query 上下文网络/F0/均值旁路；**成立**。
- 补充（潜在假设，不是本轮错误）：a2_prep.py:101 默认 cutoff=full_history；manifest 的 rpt_arrival_from_stop_policy=2664、n_rpt_late_excluded=0，说明本数据所有 RPT 的 arrival=stop，因此训练全历史 replay 与 query-time as-of 在本数据上不冲突。若未来数据的 arrival 晚于 stop，训练会在 source 时刻使用尚未到达的读数（a2_targets.py:172-197 / a2_train_v2.py 的 replay 路径），而 inference 的 replay_asof 会排除到 arrival；那是 train/inference 口径差异，需在数据契约里写清。

#### E2. 6 fits 的 val NLL 能支持什么

- 实际是 3 个 arm × 2 个阶段（selection + refit）= 6 次拟合，不是 6 个独立 seed；只有 3 个可比的 val NLL：
  - full：selected 550 步，best val −3.0019；
  - time：selected 100 步，best val −2.8321；
  - noRPTupdate：selected 550 步，best val −1.9260。
- 选择曲线不稳：full 在 500 步 −2.7293、550 步 −3.0019、600 步 −2.7131；time 在 50 步 +2.1782、100 步 −2.8321、150 步 −2.2126；noRPT 在 500 步 −1.5980、550 步 −1.9260、600 步 −1.8680。best val 是尖峰，不是平台；没有 CI、没有第二个 split/seed。
- best_val_nll 是 **selection 阶段模型** 的值；最终保存的是 refit 模型（a2_train_v2.py:203-214，seed+1，固定 selected_steps，不再 validation）。因此 fit_report 的 −3.00/−2.83/−1.93 不是最终模型的 val NLL；最终 refit 的 val NLL 没有报告。
- 结论：full vs noRPT 差 1.076 nats 是一个**单 split、单 seed 的开发信号**，可以支持“RPT 更新在这个 split 上改善了似然”，但不能支持“RPT 更新有效”作为论文结论；更不能外推到 RUL/容量精度。time（−2.83）与 full（−3.00）只差 0.17 nats，说明 cycle 控制的增量很小；RPT 更新是主要差异，但需要 seed 重复和 C3 as-of 评估。
- 另外，train_loss 是单 batch 的损失（a2_train_v2.py:162-171），不是 epoch 平均；history 里 train_loss 有时远高于 val_nll（例如 full 500 步 +1.228 vs val −2.729）。不要用 train_loss 的下降/波动论证收敛或机制。

### F. 复现性：GO / receipt / sha256 链

#### F1. B2 compare（0-fit）

- GO_B2_RUL_COMPARE_20261022T1920Z.json 的 issued_utc=2026-10-22T11:30:00Z；输出目录 reports/b2_rul_compare_20261022T1920Z 的 mtime 是 2026-10-22 19:19:17 +0800 = 11:19:17Z，**比 GO 声明签发时间早 11 分钟**。
- eval_rul_compare.py:63-67 只校验 status/allowed/owner/source hash，不校验 issued_utc；:180-183 的 receipt 只有 status/matched/elapsed，不含 go_sha256 或 input_sha256。GO 的 input_sha256 与实际三个输入我核对过，全部一致（predictions 725bea…、samples 2dd122…、comparator 0cb15b…）；但 receipt 不绑定 GO/输入，链没有闭合。
- 结论：compare 的数值可重算，但“GO 先签发、后运行”的审计叙事不成立；应重签 GO、在 receipt 写 go_sha256+input_sha256+started/finished，并拒绝 issued_utc 晚于 started_utc 的运行。

#### F2. B2 1005 / nextjump

- receipts/c3infer-20261022T1005Z.json 有 status/queries/failures/C3_reads/C4_reads/source_sha256/checkpoints/cohorts，但**没有 go_sha256**；nextjump receipt 同样没有 go_sha256/input_sha256（只有 source_sha256 与 summary）。GO 文件本身可被事后修改而不被 receipt 发现。
- 1005 的 checkpoint/cohort/source hash 与 GO 一致；nextjump 的 comparator_sha256 与 GO 一致；这是好的部分。建议统一 receipt schema：go_sha256、input_sha256、issued/finished、C3/C4 counts、failure breakdown。

#### F3. A2

- A2 的三个 run 目录只有 fit_report.json + model_state_dict.pt，**没有 receipt.json**；a2_train.py:11 明确写“never writes a GO receipt: consumption and approval belong to the controller”，但本轮的 controller 也没有写消费回执。GO 文件里没有 consumed 字段，三份 GO 仍可被重复使用。
- GO_A2_FITV2_full.json 的 out_dir 是 runs/a2v2_full_20261022，实际输出是 runs/a2_full_20261022T110158Z；a2_train.py:127-163 的 validate_go 不校验 out_dir，a2_train_v2.py:255-257 又用 args.out_dir（未传则时间戳目录）。GO 的 out_dir 字段没有约束力。
- 三份 GO 的 issued_utc 都是 11:05:00Z（19:05 CST），GO 文件 mtime 19:01:56；full fit_report mtime 19:03:28（11:03Z），**早于声明签发时间**；time/noRPT 分别在 19:06:44、19:07:56，晚于 19:05。至少 full 的“先 GO 后 fit”不成立。
- fit_report 的 go_sha256 与 GO 文件 sha256 一致（full 41ff3450…），这是唯一闭合的环节；但无 receipt、无 consuming 记录，整体链不闭合。

#### F4. B2 checkpoint 的代码链

- fit4-20261022T0600Z.json 的 source_sha256：model.py=6f87f80b…、rollout.py=4d2d620e…；1005/nextjump 的 source_sha256：model.py=f8828e6f…、rollout.py=7575f37c…。
- 6f87 就是 v21_staging/model.py 的哈希；diff 显示当前 model.py 只多了 _checked_weights/非有限参数检查，forward/采样数学未变；rollout 的差异包括 serial 设备修复、非有限参数检查，以及**数值无效 draw 从 raise 改为拒绝**（cn>1e3 / cn<1e-6），这会改变接受率和路径。
- 因此 checkpoint 能加载、数学上大概率兼容，但“训练代码哈希 = 推断代码哈希”的字节级链条不成立；论文复现应记录“checkpoint 由 6f87/4d2d 训练，推断用 f882/7575，差异为守卫/拒绝策略”，或直接用 6f87/4d2d 重跑一次推断做对照。

#### F5. 其他

- docs/DSH_PROGRESS_20261022_ZH.md:86 记录 RESULTS_ZH.md SHA256 8df70156…a103；当前文件 sha256 是 4b9d0db8…bacd（19:22 修改后）。报告哈希已过期，需更新。
- fit4 的 n_cells=124，但 fit_ledger 的 normalization_source 写 all125_cells；建议改成 all_contributing_cells=124。

### G. C4 / raw / 凭据 / 被拦截下载

- B2：receipts/c3infer-20261022T1005Z.json 的 C4_reads=0；fit4 receipt 的 C4_reads=0、C3_reads=0；compare receipt 的 C4_reads=0、raw_payload_reads=0、model_weight_reads=0；nextjump receipt 的 C4_reads=0、fit_count=0、raw_payload_reads=0。infer_runner.py:71 的 data_scope 要求 C3_source63_development_only_no_C4_no_raw；load_dev_cells 检查 C4 cell id（:38）。
- A2：prep_v2/manifest.json 的 125 个 cell 全部是 C1/C2 train cells；a2_targets/a2_prep 不读 C3/C4；fit 只读 prepared npz。
- 未发现凭据读取、代理/DNS 修改、被拦截下载重试。G 项 **PASS**。

## 3. 必须修复的问题（按严重度）

### P0（不修就不能写论文）

1. **修 eval_rul_compare.py 的 comparator 选择**：按 model=='full' 显式过滤；同时报告 full 与 independent 两行，并注明 independent 是消融。重跑 0-fit compare，重写 RESULTS_ZH.md 的 §2、§3、§9 与 DSH 的对应段落。预计结论反转为“B2 不优于 B1 full”。
2. **撤回/改写“B2 显著优于 B1 比较器、MAE 6.38 vs 13.66”**（RESULTS_ZH.md:133-134、DSH:80）。对 B1 full，B2 的 MAE 差值是 +2.27 周 [0.75,4.17]，RMSE 16.82 vs 7.12；这是“B2 更差”，不是“更好”。
3. **A2 的“full-125 refit”**：a2_train_v2.py:203 实际只在 100 train cells 上 refit；要么改代码为全量 125（并另设选择集，否则 val 不再 held-out），要么把 GO/README/DSH 的“full-125”改成“100-cell refit + 25-cell held-out validation”。不能两者都保留。
4. **RESULTS_ZH.md:125-126 的“两者不是同一估计量，不能据此说树基线更好”**：nextcap 协议 PROTOCOL_ZH.md:5 明确模型输入含 next_query_elapsed_weeks（同一 gap 条件），target 是同一 C_next；两者都是同一 y 的预测密度，NLL 可直接比较。应改为“在单步容量上树基线明显更好；B2 的轨迹机制没有转化为单步精度”。

### P1（会显著影响可信度）

5. **known-event 披露**：RESULTS_ZH.md 表注写清 815 anchors / 1630 main rows 是规则零、被主表排除；补“加回 known 后 B2 joint 5.05 vs B1 full 3.20”的敏感性，证明排除是保守的。
6. **失败语义披露**：写清 68 失败 = main 3 + fixed_gap 65，fixed_gap 失败 target 中位数 24.54 周 vs 存活 10.25 周；fixed_gap 的 +11.7 周是幸存者面板的幅度，不是完整配对效应。补失败分层表（arm/cell/condition）。
7. **校准表重做**：对 B1 full 与 B1 independent 同时报 cov80、width80、pin10、pin50、pin90、interval score，并按 0–4/4–12/12–32/32+ 分层；不要只报 pin90；不要把“0.88”当作 B1 的校准。
8. **查询计数口径**：把 4637 改成“2320 唯一键 / 4637 模型行”，1806 改成“903 唯一键 / 1806 模型行”；表头写清 N 是 model-row 还是 unique query。
9. **A2 val NLL 的措辞**：把“RPT 更新有效”降级为“单 split、单 seed、selection 阶段的似然信号”；补 2–3 个 seed 的 mean±CI 后再谈机制；最终 refit 模型需在 held-out 上重新评估（或明确它没有 val）。
10. **审计链**：给 compare/1005/nextjump 的 receipt 加 go_sha256+input_sha256；重签 compare GO 使 issued_utc 早于 started；A2 写 receipt + 消费 GO；validate_go 校验 out_dir 与 issued_utc。
11. **checkpoint 代码链**：在报告中记录 fit4 用 6f87/4d2d、推断用 f882/7575；若审稿人要求字节级可复现，用 6f87/4d2d 重跑一次 1005 或重训 checkpoint。
12. **C3 运行史**：报告写清 0725（59% 失败但错误地 COMPLETE）、0950（NameError 0.742 失败）、1005（最终），以及 1005 的代码加固是 C3 失败驱动的。

### P2（应修但不改变结论）

13. 124 vs 125：prep 只有 124 个贡献 cell（G61C1 缺失）；所有“125 cell refit”字样改为“124 贡献 cell（125 train cells 中 1 个无合法路径）”。
14. 更新 DSH 中 RESULTS_ZH.md 的 SHA（8df7… → 4b9d…）。
15. A2 fit_report 补 train/val cell 数、split hash、refit cell 数；不要只写 n_cells=125。
16. 在 eval_rul_compare.py 加 target 等式断言（当前数据 4637/4637 相等，但代码没有保护）。

## 4. 不应写进论文的表述

- “B2 轨迹 RUL 显著优于 B1 机制比较器（MAE 6.38 vs 13.66 周）。”——比较器是 B1 independent 消融；对 B1 full 是 6.38 vs 4.11，方向相反。
- “B1 校准更接近名义值（cov80 0.88 vs 0.55–0.69）。”——0.88 是消融的过宽区间；B1 full 是 0.608，B2 independent 是 0.687。
- “B2 点精度更好、但区间更差、严重误差更多。”——对 B1 full，B2 的 MAE/RMSE/pin 都更差；severe>4w 并不更多。
- “B2 的 80% 区间过窄（width 9.9 vs 47.5）。”——B1 full 的 width 是 7.11；B2 joint 反而更宽。
- “B2 与树基线不是同一估计量，不能据此说树基线更好。”——两者都是同一 C_next、同一 gap 条件的密度；NLL 可直接比较，树基线更好。
- “RPT 测量更新有效。”——目前只有 3 个 selection 期 val NLL、单 split/单 seed、无 CI；最终 refit 未验证。
- “A2 完成 full-125 refit / 6 fits 全量重拟合。”——代码只在 100 train cells 上 refit。
- “B2 的 68 个失败都是诚实拒绝，因此结果无偏。”——失败集中在 fixed_gap 的长 RUL，固定 gap 对照的幅度不稳健；主表仅 3 个失败。
- “C3 独立确认。”——这是 C3 开发集；C4 未读。

## 5. 建议的下一轮最小验证

1. **0-fit 比较修正（当天可完成，最高优先）**：eval_rul_compare.py 显式选 model=='full'，保留 independent 作消融；加 target 等式断言；输出 full/independent 两套指标、known 敏感性、failure 分层、horizon 分层、pin10/pin50/pin90/interval score。若修正后 B2 仍输给 B1 full，就按负结果写，不要再用 13.66 的比较器。
2. **B2 的定位**：若目标是 RUL，B1 full 应作为主比较器；B1 independent 只能作为消融。若 B2 的卖点是轨迹机制，应在“同输入、同目标、同 cell/arm/query”下与 B1 full 做配对，并报告长视界校准失败。
3. **A2 最小重复**：对 full/time/noRPT 各补 2 个 seed（同 split、同 steps 选择规则），报告 val NLL 的 mean±CI；再做一次 C3 as-of 容量预测（不是 RUL）的同输入比较。若算力只够一条，优先 full vs noRPT。
4. **审计链**：重签 compare GO；在 receipt 写 go_sha256、input_sha256、started/finished；A2 写 receipt 并消费 GO；validate_go 校验 out_dir/issued_utc；把 fit4 的 6f87/4d2d 与推断的 f882/7575 差异写进报告。
5. **论文表述**：在修正前，B2 只能写成“在 C3 开发集上，B2 相对 B1 independent 消融有更低的 MAE，但相对 B1 full 更差；joint 在长视界校准失败”。A2 只能写成“机制实现与单 split 似然信号”，不能写成 RUL 结论。

## 附录：本次核查的关键字段/文件

- B2 结果：reports/multisource_20261021_B2_trajectory/RESULTS_ZH.md（当前 sha256 4b9d0db8…bacd；DSH 记录 8df7… 已过期）。
- B2 比较：experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2/eval_rul_compare.py:76、82-86、89、115-121；reports/b2_rul_compare_20261022T1920Z/{summary.json,receipt.json}。
- B1 comparator：experiments/multisource_mechanisms_20261021/evaluation_runs/run3_exact_schedule_clock/predictions_c3.csv（7530 行；full 0–3764，independent 3765–7529）；metrics_by_model_arm.csv；DESIGN_AND_INTERFACES_ZH.md；evaluate_v1.py:268。
- B2 推断：candidate_v2/runs/c3infer-20261022T1005Z/{predictions_c3_rul.csv,query_failures.json,receipt.json}；infer_runner.py:174-188、232-245。
- B2 fits：candidate_v2/runs/fit4-20261022T0600Z/{fit_ledger.json,receipt.json}；fit_runner.py:59-60、115。
- A2：a2_model.py:115-121、196-199、216-246、248-268；a2_targets.py:77-106、116-137、357-424；a2_fastdata.py:98-135、183-218、685-744；a2_train_v2.py:190-229；a2_train.py:127-163；prep_v2_20261022/manifest.json；runs/a2_*_2026102*/fit_report.json；GO_A2_FITV2_*.json。
- 进度：docs/DSH_PROGRESS_20261022_ZH.md:21、52-53、64-67、73-99。

> 本备忘录只读核查；未修改任何代码、数据、GO、receipt。所有重算均来自已保存的 predictions CSV；未读 C4、未读 raw payload、未读凭据。
