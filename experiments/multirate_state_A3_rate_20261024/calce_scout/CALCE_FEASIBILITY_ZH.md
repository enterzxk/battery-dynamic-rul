# CALCE CS2 勘察备忘录（A4 第二数据集 as-of 验证可行性）— worker #9 只读勘察

2026-10-24。0 拟合、0 GO、0 payload 外写操作；仅写本目录。所有 sha 为服务器实测。

## 1. 资产清单

### reports/ 八个目录（全部只读取证）
- calce_cs2_metadata_20261019_root：官方协议元数据。CS2 为 CALCE 1100mAh 批次，35/36/37/38 四电芯列于 1C 放电组；0.5C CC→4.2V、CV→<0.05A、放电截止 2.7V。登记角色：35=candidate_train、36=candidate_development、37/38=locked_candidate（仅角色登记，数据未取）。
- calce_cs2_head_preflight_20261019_root：服务器 DNS 解析失败 STOP（无数据）。
- calce_cs2_local_head_20261019_root：本地控制端 HEAD 证据（37,056,519B、application/zip、ETag）。
- calce_cs2_35_acquisition_20261019_root：官方 CS2_35.zip 获取完成，两端流式 sha256=84d88cb98a43c02049f16c78806a78ec19084776ea5df8a4b7c2f8f7ba4589e5。
- calce_cs2_35_firstfile_20261019_root：首文件 8_17_10 真读，17 字段、1091 采样、1 循环；容量计数 1.138460Ah 与部分积分差 0.00085%。
- calce_cs2_35_series_20261019_root：10/24 文件读毕，第 10 个（10_29）因新增 Statistics 汇总表致 schema 歧义 STOP；counter 为跨循环累计、不可盲差分。
- calce_cs2_35_repair_20261020_root（权威 DataV1_v3 交付）：全 25 文件、266,914 采样记录；936 源循环片段=854 VALID + 32 UNCERTAIN + 50 精确重复别名（2_4 与 2_10 文件信号全同）。容量=同源循环同主放电步 counter 差，与积分中位差 6.25μAh。
- calce_cs2_35_session_evidence_20261020_v16：归档内仅 25 个 XLSX；10/29 Info 有 Start_DateTime 与 Schedule 文件名 CS2_1C.sdu 但无正文、无跨 session 累计循环记录 → 全局循环年龄不可建。

### data/ 权威产物（processed/CALCE_CS2_35_DataV1_v3/；v1/v2/repair_v1 为中间版本保留）
- capacity_series.csv 284,787B sha 8818441b59d405ab34948eaf57824a79780591c13d795a15caca2be2643212ea（937 行含头）。
- discharge_measurements.jsonl sha 013faaee2994548dbd4f70d8520bdcc2ac266aa7f757ef5ed23930a325d3f85b。
- endpoint_labels.json sha 6c1e8aa98ffc9e78ac46988408bfa499dea6cadb0e4ad96994c619d5b0711956；manifest.json sha 795836f846a5e97489599a14f4b42ab5c8a26d32a1ade0e2241b903e3cb51929。
- 25 份 <date>.xlsx.records.jsonl.gz（逐条采样缓存，服务器专属；sha 见 repair/reconstruction_summary_v3.json）。
- raw：data/raw/CALCE/cs2_35_official_v1/CS2_35.zip（sha 同上 84d88cb9…）。

### 记录结构与时间戳语义
- Excel Channel 表 17 字段：Data_Point, Test_Time(s), Date_Time, Step_Time(s), Step_Index, Cycle_Index, Current(A), Voltage(V), Charge/Discharge_Capacity(Ah), Charge/Discharge_Energy(Wh), dV/dt, Internal_Resistance, Is_FC_Data, AC_Impedance, ACI_Phase_Angle。
- 缓存 records.jsonl.gz 仅存 11 字段（datetime/time_s/step_time_s/step/cycle/data_point/current_A/voltage_V/charge|discharge_counter_Ah/source_row）——能量(Wh)、IR、阻抗列未缓存（仅 raw ZIP 有）。
- capacity_series.csv 17 列：source_file/cycle/occurrence、step、start/end/discharge_end_datetime、baseline/end_counter_Ah、counter_delta、step_time_integral、capacity_Ah、soh_nominal、status、flags、duplicate_of、fingerprint。
- 时间：真实日历时钟存在（Date_Time，时区未知）。跨度 2010-08-16T17:22:57 → 2011-02-03T18:09:46（171 天）；9 个 >2d 缺口（最大 11.0d）；24 文件边界中 21 个 Cycle_Index 重置；1 个负 walltime 边界。854 个唯一 VALID 容量 0.3036–1.1385Ah。

## 2. 对照 ISU as-of 协议的可行性判定
ISU 契约（a2_prep.py 输入语义 + A3 PROTOCOL + hybrid README）：per-cell 事件流 = 循环事件(24 维控制+mask，source=arrival=完成时刻) + RPT 容量(source stop + arrival clock)；anchor=首个已到达有效 RPT；门控 source≤arrival≤query；horizon=日历周；面板 125 train/63 dev specs，C3 2,326 键(raw 903/sparse2 463/delay7d 960)；F0=10 通用+64 组 onehot，F2=98=10+64+24 cycle 特征；目标=首观测 RPT Q≤0.20Ah(80% nominal) 的观测标签。

- 时钟与三臂：可支撑。日历时钟真实存在；raw=容量即放电结束可见，sparse2=隔一取一，delay7d=+7d 模拟延迟（ISU 三臂同为可见性政策构造，非实测延迟）。anchor=2010-08-16 首个有效容量 1.138460Ah。
- 目标标签：可定义同构“首观测有效 Q≤0.88Ah(80%×1.1Ah)”=2010-12-16T07:23:52（0.876295Ah，12_20 文件 cycle 22）；越阈前 578 个、越阈后 276 个有效观测（后续 7.06 周，末值 0.3036Ah）。ISU 目标同为观测标签（非潜伏 EOL）→ 语义兼容。
- train/dev 按 cell 划分：不可行。本地仅 1 cell（35）；36/37/38 未获取，全部获取也仅 4 cell（vs ISU 125/63）。cell-macro 平均与 cell 配对 bootstrap 在 1 个 dev cell 上失效。
- 特征依赖缺口：(a) F0/F2 的 64 个组 onehot 是 ISU cohort 专属 → CALCE 无定义（全零出支撑域，须双侧删列重比或作缺失披露）；(b) 24 维控制与 F2 cycle 特征各有 4/2 个能量(Wh)维，缓存已弃该列，需 raw ZIP 重解析（新 GO）或接受 mask=0/缺失（HGB 原生 NaN 可容）；(c) 无 RPT/cycling 分离——容量观测与循环控制出自同一次放电，与 ISU“独立参考测试”结构不同，必须披露。
- 硬门禁：endpoint_labels.json 冻结 RUL_labels_allowed=false、models_fit_or_infer_allowed=false、independent_confirmation_ready=false；repair 报告明确“不足以开展宣称独立确认的全寿命 dynamic-RUL 评估”。任何 fit/infer 需新 GO 显式解锁并改口径。

## 3. 两条候选路线
- R1 直接在 CALCE 重训（不推荐作主路线）：先获取 36/37/38（3 次有界下载，仿 35 票据）+ 每 cell 25 文件级重建；A3 四臂×2=8 fits 机械可跑，但 3/1 cell split 无 cell 级置信区间；树/HYB 无法同构重训（≤3 训练 cell，HGB 64 onehot 无意义）。预算 ≥8 fits + 3 次下载 GO + 4 套重建 GO；风险高、论文主张弱。
- R2 ISU 训练→CALCE 零样本（推荐）：0 fits。复用 A3 walker checkpoints（seed42/43/44；full sha 4b46c929…）+ F0–F3 树 + HYB，仅做 CALCE 版 prep（读 DataV1_v3，0 拟合；如需能量维再开 raw 重解析 GO）+ 单 cell as-of 面板 + 观测事件评估。叙事=“跨数据集零样本泛化”，与 A4 的 as-of 验证目标最契合。风险：协变量移位（1C 放电、LCO 1100mAh 体系 vs ISU）、组 onehot 出支撑域、时区未知、缺口不可证无漏循环、单 cell 无统计力（只能个案级证据）。可选加做 few-shot 微调 2–4 fits（须新 GO 且受 RUL 门约束）。

## 4. 明确不可行项
- 树+A3+HYB 三模型在 CALCE 上同构重训比较：训练 cell 数（≤4）不足。
- 全局原生循环年龄 RUL（按循环计数标签）：21/24 边界重置 + 无 session 日程，循环连续性未证。
- “独立确认”或全寿命 dynamic-RUL 声称：session 证据缺口（v16 已核验无正文）。
- 真实 reporting-delay 观测：CALCE 无到达延迟记录，delay7d 只能是模拟政策。

## 5. 建议 GO 结构草案（仅草案，不建 GO）
- CALCE 侧输入（逐文件 sha 如上 §1）：capacity_series.csv、discharge_measurements.jsonl、endpoint_labels.json、manifest.json、DATA_DICTIONARY_ZH.md、源归档 sha 84d88cb9…；25 份 records.jsonl.gz 按 v3 目录 + reconstruction_summary_v3.json 实测 sha 逐份登记；raw ZIP 仅在启用能量维时列入并另签解析预算。
- ISU 侧沿用 hybrid GO 模板：prep_v2 manifest/npz、cohort.json、F2 train/dev 特征与 rows、A3 checkpoint（4b46c929…）等原 sha。
- 面板规则：仅 status=VALID 且 duplicate_of 为空的行作容量观测；source=arrival=discharge_end_datetime；anchor=首个有效容量；事件=首观测 Q≤0.88Ah；arms raw/sparse2/delay7d；query 在有效放电结束时刻按 A3 walker 口径（anchor 去重+可见阈值）采样；horizon 日历周；组 onehot 全零披露或双侧删列；能量维缺失走 mask=0/NaN 纪律。
