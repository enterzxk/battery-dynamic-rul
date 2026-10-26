# CALCE CS2_35 零样本容量条件推断（A4）— worker #10

## estimand 声明（冻结，与 GO/metrics.json 一致）
任务 = **给定截至日历时刻 q 的已到达观测前缀，预测下一个已到达观测的容量**（ISU
nextcapacity / A3 next-jump 同构）。**不做 RUL/事件时间预测**：endpoint_labels.json 的
RUL_labels_allowed=false 继续冻结且被尊重；0.88Ah 首观测穿越（2010-12-16T07:23:52，
0.876295Ah）仅作评估上下文（事件前/后分桶），绝不是标签。
endpoint_labels.models_fit_or_infer_allowed=false 由本 GO 显式改口径覆盖为
"capacity-conditioned inference only, 0 fits"（理由：容量序列本身是已验证资产）；
覆盖记录于每个 GO 的 estimand 字段。

## 设计冻结
1. 观测 = capacity_series.csv 中 status==VALID_SAMPLED_CC_DISCHARGE 且 duplicate_of 为空
   （854 个唯一；82 行排除 = 32 UNCERTAIN + 50 别名）；source=arrival=discharge_end_datetime；
   **时区未知按 UTC-naive 解析**（offset=0，全产物披露，从不"修正"）。
2. anchor = 首个有效观测 1.138460076Ah（2010-08-16T17:22:57）；q_ref = anchor 容量
   （ISU 构造）。
3. 三臂 = a2_infer._b2_arm_records 原样复用（anchor_index=0）：raw=放电结束即可见；
   sparse2=保留 (序号-0)%2==0；delay7d=到达 +604800s（模拟政策，CALCE 无实测延迟）。
4. 查询 = 每个观测 stop 上：q>=anchor+1 周、可见数>=3（ISU MIN_VISIBLE_RECORDS）、
   按 (arm, anchor index) 去重、目标=全记录中下一个观测（严格晚于 q）、无目标查询丢弃。
   **对 ISU 网格的一处刻意偏离**：去掉 ISU 的 visible_threshold 跳过，使事件后查询存在
   （事件后 275 个观测）；ISU 模型从未在越阈后状态被查询过，属额外出支撑域，逐行标注
   event_bucket。自检 F10 证明：恢复 ISU 阈值+warmup 后与 a2_infer.build_queries 逐键一致。
5. 序列 = a2_prep.cell_sequence 原样复用：全部 854 观测出 cycle 事件（稠密控制流，ISU
   结构），RPT 容量事件按臂保留（a2_infer._rpt_records_for_arm）。CALCE 中控制与容量来自
   同一次放电（ISU 是独立 RPT 测试）——已知语义差异，如实披露。
6. 单 cell 无配对 bootstrap：报 per-arm 全量指标 + 事件前/后分桶（metrics.json）。

## ISU→CALCE 24 维控制映射（a2_prep.CONTROL_FIELDS 顺序；缺维 mask=0，值=0）
片段 = discharge_measurements.jsonl 的 first/last_source_row 圈定的 records 缓存样本；
charge 腿 = current_A>+1mA，discharge 腿 = current_A<-1mA（rest 剔除）；t=time_s。
Q 统计用设备计数器做腿内锚定（前一样本计数为基线，复现 repair 协议 baseline→end 口径；
腿起于片段首样本时退化为首样本锚定）；缺失规则 = a2_prep.CONTROL_MISSING_RULE 原文。

| dim | 字段 | CALCE 来源 |
|---|---|---|
| 0/1 | dur_{charge,discharge}_weeks | 腿内 (t_last-t_first)/604800 |
| 2 | gap_charge_discharge_weeks | (discharge 首样本 t - charge 末样本 t)/604800，>=0 才有效 |
| 3-8 | q_{last,mean,span}_{charge,discharge}_ah | 腿内锚定计数器序列的末/均值/极差 |
| 9-12 | v_{mean,last}_{charge,discharge}_v | 腿内 voltage_V 均值/末值 |
| 13-16 | i_{mean_abs,max_abs}_{charge,discharge}_a | 腿内 abs(current_A) |
| 17-20 | e_*_wh | **records 缓存无 Wh 列 → 恒 mask=0**（能源维缺口） |
| 21 | capacity_charge_ah | charge 腿锚定计数器总量（==dim3，单调计数器下同义） |
| 22 | capacity_discharge_ah | capacity_series 的验证容量 capacity_Ah |
| 23 | throughput_ah | dim21+dim22（两腿均有效时） |

交叉验证：854 片段 max|dim22-dim4| = 1.8e-7 Ah；mask 率：dim2=7.4%（充电在放电后的片段），
dim17-20=100%，其余 20 维 =0。

## 模型（全部零样本，0 拟合、0 梯度步、0 C4）
- A3 三 seed full：a3_infer._load_arm_model_a3 校验 sha 后 float32→float64，经
  **a3_infer.AsOfWalkerA3 原样**滤波（delay7d lag=7d），预测 = 查询时刻状态容量矩；
  checkpoint = run1_fits / runs_seed43 / runs_seed44 的 model_state_dict_full.pt。
- F0_hgb：**未运行**——strong-baselines run2 目录只有 CSV，无持久化模型文件；重拟合会
  破坏 0 拟合主张。其不可加载性如实入 receipt（f0_hgb_status）。
- 朴素参照：hold_last / past_slope（ISU run_baselines.py 语义：对下一个观测的实际 stop
  时刻外推最近两个可见观测）。

## GO 模板（本目录 GO_A3_CALCE_ZEROSHOT_20261024_RUN1.json 为实例）
status=APPROVED；allow_inference=true、**allow_fit=false**、allow_train=false、
allow_C4=false；scope 含 CALCE-ZEROSHOT；estimand（quantity/rul_labels_used=false/
endpoint_role=evaluation_context_only/go_override）；owner_thread_id、device=cpu、
no_grad=true、max_rss_gb、max_runtime_seconds∈[60,21600]；request_id fresh（成功后登记
experiments/state/consumed_gos.jsonl）；code_sha256 = 真实 import 闭包 11 文件
（calce_zero_shot.py + a3_{infer,model,train}.py + a2_{infer,prep,targets,fastdata,
model,train,fixtures}.py；A3 树无 a3_targets.py——按 import 复用 a2_targets.py）；assets：
CALCE 4 文件 + 25 records gz 逐文件 path+sha256 + A3 checkpoints×3 + PREP manifest
（控制语义参照）；output_dir/receipt_path 必须 fresh。拒绝路径零写入；读审计断言所有
payload 读 ⊆ GO 钉的资产集。

## 关键结果（run1_eval_20261024；详见 metrics.json / receipt）
- 面板：raw 822 / sparse2 412 / delay7d 483 查询（事件前 1121、事件后 596）。
- raw 臂 MAE(Ah)：A3 seed42/43/44 = 0.0075/0.0068/0.0078，hold_last = 0.0038，past_slope = 0.0076；RMSE 0.0102/0.0093/0.0106 vs 0.0062/0.0443。
- 出支撑域/校准失效（主张的核心证据）：A3 预测 sd 中位数 0.0016Ah 而中位误差 0.0057Ah
  → NLL 12-16（delay7d 223-235）、cov90≈0.26-0.31（delay7d≈0.07，名义 0.90）；state_R
  漂移至 -0.73Ah（ISU 0.25Ah 尺度的 R 态吸收 1.1Ah 体系的错配）；CALCE 的 Ah 级控制
  （0.31-1.10Ah）远出 ISU 标准化范围。点预测尚可但不敌 hold_last，不确定性欠覆盖。
- 事件后恶化：raw 臂 A3 MAE 0.0052（前）→ 0.0105-0.0128（后）；hold_last 0.0033→0.0046；
  delay7d 臂整体 ≈7 倍于 raw（0.053 vs 0.0075）——都支持"支撑域退化"方向。
