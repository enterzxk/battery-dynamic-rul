# 外部基线 EXT_GRU / EXT_ENET（B-EXT-1 / B-EXT-2，worker #5，2026-10-24）

同协议外部基线：与树面板（3579 键）与 A3 同输入、同查询面板、同评估（nextcapacity 任务）。
- **EXT_GRU**：GRU 序列基线 = 序列神经方法代表（架构参照 isu_irregular_rul_seed42_v1/baselines.py `make_gru` TinyGRU，重新实现，不 import 该实验）。
- **EXT_ENET**：弹性网早期特征基线 = Li et al. 2024 Cell Reports 风格（204 维容量/Q-V/dQdV 特征**增量** + 循环条件 + ElasticNet；特征资产 all188_rpt_features_v1）。

## 查询面板（冻结，已对树 run2 逐键验证）
- dev 面板 = 树参考 CSV `experiments/trajectory_strong_baselines_20261021/runs/q4_strong_baselines_20261021_run2/predictions_c3.csv` 的 3579 键（61 dev cell × raw/sparse2/delay7d）；输出面板列逐字复用 CSV。
- 训练查询 = 125 train cell 用同一冻结规则自行构造：行=有效 RPT（按 (stop_utc, 原始 source_rpt_index) 排序、stop 严格递增）；anchor=第 2 行；查询=行 stop q ≥ anchor.stop+1 周且**每个 arm** 在 q 已到达 ≥3 行；arm 到达：raw/sparse2=stop、delay7d=stop+7d；sparse2 另隐藏 i>1 且 (idx−anchor.idx)%2==1（**原始索引**）；y=stop>q 的下一行容量Ah，h=(下一stop−q)/周；末行查询（无下一行）剔除。语义镜像 v18 `make_examples` + B `build_targets`（只读学习后重实现）。验证：train 6498 / dev 3579 与树 run2 receipt 完全一致；dev 全部 3579 行 target/h/lastcap/known_event 与 CSV 0 偏差。
- 前缀仅用 arrival≤q（RPT）/ source≤q（cycle）事件，任何 t 后信息不进入特征（自检含扰动不变断言）。

## 特征冻结（v1.1）
- **特征名对齐（v1.1，修 RUN1）**：各 cell JSON 的每条 valid record 自带 `feature_names`，同一 204 集合但**跨 cell 顺序不同**（实测 G10C1 vs G1C1 首分歧在位置 5）。规则：cell 内所有 valid record 的名**集合**必须一致（不同→拒绝，重复名→拒绝）；向量一律按**冻结参照序 = 名集合的字典序 sorted**（等价于首个加载 cell 的 sorted 集合，全体同集）由 values 按名重排；同集不同序的 record 得到**逐位相同**的向量；跨 cell 集合不同→拒绝（自检含乱序归一化与集合漂移拒绝两 fixture）。ENET 的 204 增量含义不变。
- 共同：q_ref=首个有效 RPT 容量；control 前缀=source≤q 的 cycle 24 维按 mask 加权均值（无 mask 维=0）；cycle 来自 PREP npz（train）/ cycling_features_v3（dev，经 a2_prep 冻结适配器+role 投影）。
- **EXT_GRU**：token(L×4)=[cap/q_ref, Δcap(vs 上一可见RPT), Δt周, 距首可见RPT周数]；ctx(32)=[h周, lastcap, lastcap/q_ref, 斜率Ah/周(最后两可见), n_visible, n_cycle, throughput_field23 累计(源单位), 距row0周数]+control24；GRU(4→16,batch_first)+last hidden⊕ctx→Linear(48→2)=(μ,logσ²)，Gaussian NLL，logσ²∈[−12,4]，Adam lr=1e-2 wd=1e-5，300 epoch，batch 256，seed 42，token/ctx/y 用拟合集统计标准化；报告 σ 用标量 OOF（与树同法，头 σ 不用于报告）。
- **EXT_ENET**：x(233)=[204 维（最新可见 RPT 向量−**第 0 个有效 RPT** 向量；None→0）]+control24+[lastcap, q_ref, h, n_visible, 距row0周数]；Pipeline(StandardScaler→ElasticNet(alpha=0.05, l1_ratio=0.5, max_iter=50000, tol=1e-7, selection=cyclic))；超参先验冻结，无调参。
- 拟合（共 4）：eligible train cell 按 sha256("42:"+cell) 排序二折 foldA/foldB；每模型 fit1=foldB 训练→foldA 残差 σ=sqrt(Σw r²/Σw)（w=1/cell 行数，树同式）；fit2=全训练行终拟合。样本权重=cell 均衡。

## GO 模板（worker 不创建/不签署；由控制者填写）
必填字段（`validate_go` 逐项校验，拒绝不写任何文件）：
`status="APPROVED"`；`allow_fit=true`；`scope` 含 "EXT-BASELINE"；`request_id`（≥8 字符，须不在 consumed registry）；`owner_thread_id="01a15c3a-1a06-7d61-8517-27b70b246183"`；`issued_utc`（<24h）；`seed=42`；`models=["EXT_GRU","EXT_ENET"]`；`fits_in_this_go=4`；`fit_plan`（须等于脚本 FIT_PLAN 字符串）；`device="cpu"`；`threads=4`；`max_runtime_seconds∈[600,14400]`；`code_sha256`={ext_baselines.py, a2_prep.py, a2_targets.py, README_EXT_BASELINES_ZH.md 各自 sha256}；`assets`={prep_manifest, prep_npz, rpt_manifest, tree_csv, cohort, data_manifest, cycling_manifest}（各 {path, sha256}，逐字节校验；per-cell 文件再对各自 manifest inventory sha 校验）；`panel_contract`={n_keys:3579, arms:[raw,sparse2,delay7d]}；`consumed_registry="/home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl"`；`output_dir`（=本目录 runs/ 下不存在的新目录）；`receipt_path`（=本目录 receipts/ 下不存在）。
资产路径：PREP=`experiments/multirate_state_A2_20261022/prep_v2_20261022/{manifest.json,a2_prep_sequences.npz}`；RPT=`reports/multisource_20261021_signals/all188_rpt_features_v1/manifest.json`；树 CSV=上文；cohort=`reports/isu_ilcc_capacity_probe_20261020_root/cohort.json`；data manifest=`reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json`；cycling=`reports/multisource_20261021_signals/cycling_all188_feature_manifest.json`。
成功后脚本自动 append 登记 request_id（重复拒绝）。

## 输出
`runs/<out>/predictions_ext.csv`（列名/列序与树 CSV 完全一致；model=EXT_GRU/EXT_ENET；panel 列逐字复用；predicted_mean_ah / predicted_sigma_ah / error_ah / abs_error_ah 同树命名）；`fit_report.json`（折、σ、超参、行数）；`fit_01..04.json`+`progress.json`+`receipt.json`。

## 防重放
代码内 `BURNED_REQUEST_IDS=("EXT_BASELINE_20261024_RUN1")`：RUN1 于面板构建期失败（特征名对齐 bug，receipt 如实记 fits 0/0、未登记 consumed registry），该 request_id 永久拒绝，重跑须用新 request_id + 新 out_dir。

## 自检（默认 --self-check）：16 项
合成世界（tmp 内自建 PREP/RPT/cycling/processed/树CSV/registry）；真实 data/ reports/ 资产 0 打开；GO 变异 ≥12 拒绝；前缀无泄漏；面板键一致；ENET/GRU 确定性；σ 复现；登记表 append/重复拒绝；fit 预算第 5 次拒绝；输出 schema/逐字面板列；重跑拒绝。RESULT 行写入 SELF_CHECK_LOG.txt。
