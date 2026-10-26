# A3 方差校准（P2/V3）：a3_calibrate.py（worker #5，2026-10-24）

R3 发现：A3_full 风险调度 α=5% 名义 → 实际违规 19.1%（cell-macro，all 臂，≈4α）——预测方差系统性低估。
修复 = **训练内部**的闭式方差校准因子 s，绝不读 C3 调参（C3 只做校准后复评，不参与 s 的估计）。

## 设计冻结
1. **s（闭式，0 拟合）**：`s = Σ(y−μ)² / Σ pred_var_total`（冻结的 pooled 方差比估计量；其定义性质：校准后方差 s·v 下 **pooled 标准化二阶矩恒等于 1**；自检含手算 0.808 例与该性质。异方差下逐点 MLE 应为 mean(r²/v)——作为诊断量一并写入 report 的 `s_mle_per_point_mean_diagnostic`，**施加的因子恒为冻结式**）。数据 = ext_baselines 已验证的训练查询推导（125 train cell × raw/sparse2/delay7d，**6498 键**；y=下一 source RPT 容量，即树面板 nextcapacity 任务）。A3_full checkpoint（GO pin path+sha）经 a3_infer 的 **AsOfWalkerA3**（与 C3 推理同一分段引擎，float64、no_grad、按 (cell,arm) 流式 O(events+queries)）过滤到 q，再以 a3_infer `_advance_horizon`（held-recent-control 策略）前推 gap 周——与 C3 CSV 的 pred_mean_ah/pred_var_ah2 完全同一计算。0 优化步、0 C3/C4 读取（C4 封存）。
2. **C3 校准后复评（0 拟合，只动方差）**：A3_full 行（c3_eval_a3_20261024_run2/predictions_c3_a3.csv，GO pin）；校准方差 = s×pred_var_ah2（及 s×h{1,4,12,32}_var_ah2），均值不变；重算 NLL/cov50/cov90/cov95（pooled+cell-macro，分臂+overall）。**完整性门**：s=1 重算必须逐行复现 CSV 自带 nll_per_ah/covered_* 列，否则拒绝。
3. **调度前沿复评**：schedule_eval 语义逐字复刻（可行 h=max{h: Φ((EOL−mean)/sd)≤α}，否则 h=1，否则 min；violation=truth<EOL；pooled+cell-macro；"all"=跨臂合并点）。**前后一致性门**：s=1 重算必须与 GO pin 的 R3 `run_schedule_eval_20261024/policy_table.csv` A3_full risk 行逐格相等（计数精确、比率 1e-9），否则拒绝。校准后 sd=√s·sd 重算 α∈{0.02,0.05,0.10} → 前后前沿对比（违规率/平均间隔）。
4. **诚实报告**：校准后 α=5% cell-macro 违规（all 臂）仍 >10% → `TRAIN_CALIBRATION_INSUFFICIENT`："训练内校准不足以修复，需过程噪声重设"，附证据（分臂 s、残差-方差 10 分箱散点摘要 ratio_emp_over_model）。

## 复用（全部只读，不改既有文件）
ext_baselines（面板规则/Store 审计/registry 纪律）、a3_infer（AsOfWalkerA3、reference_asof_state_a3、_control_for_output、_advance_horizon）、a2_infer._b2_arm_records（arm 保留规则交叉契约断言：我的 keep 集+到达时==B2 规则）、a2_prep.cell_sequence、a3_model.build_arm_model（checkpoint strict 载入→eval→double）。

## GO 模板（worker 不创建/不签署）
必填：`status="APPROVED"`；**`allow_fit=false`（true 直接拒绝——纯推理）**；`scope` 含 "CALIBRATE"；`request_id`（fresh + 非 BURNED["EXT_BASELINE_20261024_RUN1"]）；`owner_thread_id="01a15c3a-1a06-7d61-8517-27b70b246183"`；`issued_utc`(<24h)；`seed=42`；`device="cpu"`；`threads=4`；`max_runtime_seconds∈[600,14400]`；`code_sha256`（pin 实际导入闭包 11 文件：a3_calibrate.py, ext_baselines.py, a3_infer.py, a3_model.py, a3_train.py, a2_infer.py, a2_prep.py, a2_targets.py, a2_model.py, **a2_fastdata.py**, a2_train.py——注：A3 树**无 a3_targets.py**，A3 以 a2_targets.py 复用，a2_fastdata 由 a3_model/a3_train 导入故在闭包内）；`checkpoint={path,sha256}`（run1_fits/model_state_dict_full.pt）；`assets`={prep_manifest, prep_npz, rpt_manifest, tree_csv, c3_predictions_csv, **schedule_dir**（目录摘要=sorted{rel:sha256} 的 sha256）}；`panel_contract={n_train_queries:6498, arms:[raw,sparse2,delay7d]}`（运行时重推导并强断言）；`s_definition`（须等于脚本冻结串）；`eol_threshold_ah=0.2`；`menu_weeks=[1,4,12,32]`；`alphas=[0.02,0.05,0.1]`；`consumed_registry`；`output_dir`（runs/ 下新目录）；`receipt_path`。成功后 append 登记（重复拒绝）。拒绝则不写任何文件。

## 输出（runs/<out>/）
`calibration_report.json`（s、s_parts、分臂/分 cell s、方差分箱、C3 前后指标、schedule 前后前沿、诚实报告、payload 审计、optimizer_steps=0/fits=0）；`train_walker_predictions.csv`（cell/arm/q/gap/y/μ/var）；`c3_reeval_metrics.csv`（before_s1/after_calibrated × scope）；`schedule_frontier_calibrated.csv`（before/after × arm × α）；receipt.json。

## 自检（默认 --self-check，≥8 项实为 13 项）
合成世界（tmp：PREP/RPT/树CSV/checkpoint(seed3)/C3 CSV/policy 表/registry）；0 真实资产打开；s 手算+MLE 性质；**walker==逐查询重滤波**（a3_infer reference 逐位相等，3 臂×多切点，含 delay7d 幽灵窗）；无泄漏（未来事件扰动不变）；arm 规则==B2 交叉契约；GO 变异 ≥12（含 allow_fit=true 拒绝、scope 无 CALIBRATE、burned、schedule_dir 摘要、s_definition 篡改）；登记表 append/重复拒绝；schedule 语义手算（risk_choose/evaluate/aggregate/policy_table 交叉校验+坏表拒绝）；C3 指标重算（s=1 门+s=2 手算）；诚实旗标（0.12 触发/0.08 不触发）；完整合成守卫跑（COMPLETE、0 fits、before==合成 policy 表、前后前沿输出）。RESULT 行追加 SELF_CHECK_LOG.txt。
