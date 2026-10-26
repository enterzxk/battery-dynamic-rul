# 竞品定位表（论文 Related Work 骨架 · V2）

基于 reports/multisource_20261021_literature/COMPETITION_REVIEW_ZH.md（2026-10-21，全部一手来源已核；
unverified 项如实标注）。用途：论文 Related Work + Intro 的差异化论证。原则：不把摘要当全文、
不越审查划定的创新边界、我们的每条主张都有实验编号支撑。

## 主张边界（先立后破）

**不主张新**：连续时间/连续采样建模（BatteryCDE spline-CDE；ESWA 2026 liquid-CRN）；概率
RUL/首达分布（两阶段 Wiener IEEE Access 2024 解析 FPT；Gamma+Gibbs Energy 2025；RUL-QMoE 分位数）；
在线/新观测后更新（Wiener Bayes 更新先例；Sci Rep 2024 UKF 回弹滤波；landmark-GBM 动态生存）。

**主张的差异（候选 A 的实证版，本项目已完成）**：高频**运行信号驱动个体速率状态 ℓ** 在运行时钟
上传播 + 稀疏 RPT **到达**触发的创新校正（测量更新消融证明是主要信息来源）+ 测试到达/延迟/
查询三时刻显式分离的严格 as-of 协议 + **三段实验证据**（E1 机制/E2 样本效率/E3 调度）。

## 逐篇定位

| 竞品（已核范围） | 协议/estimand | 机制 | 我们做了什么他们（已核范围内）没有 |
|---|---|---|---|
| BatteryCDE, IEEE TTE 2025（官方摘要） | 不规则/缺失容量序列→未来容量+跨电池迁移；缺失至 50% | spline 连续路径+两级 neural CDE | 观测**到达语义**驱动的状态校正（as-of 创新更新）；数据效率曲线（50% 训练池对比）；调度价值。其缺失鲁棒是**输入级插值**，我们是**到达级滤波** |
| Zhang et al., ESWA 2026（仅摘要，unverified） | 公开数据在线 RUL | Wiener drift/diffusion + liquid 连续时间循环，联合优化+在线精化 | 与其重叠最高；我们可区分点：到达/延迟/查询三时刻分离的协议化评估、样本效率与调度两个**决策层**结果、消融归因（其公式/协议未核，不臆测） |
| Li et al., Energy 2025（正文片段） | 25 公交 4 年运营稀疏 BMS→容量轨迹/车队可靠性 | 温度/倍率修正+rainflow 等效循环+Gamma 过程 Gibbs | 运行信号驱动的**在线隐状态+RPT 到达校正**（其为离线轨迹重建）；个体速率状态；NLL 口径的完整预测密度对比 |
| Sci Rep 2024 UKF 回弹 | NASA B5–B7 在线 RUL，解释回弹 | 4 HI+SVR/GPR+UKF，白噪声注入模拟回弹 | 回弹=可逆状态 R 显式建模+测量误差可识别分解（非噪声注入）；稀疏 RPT 到达协议；调度 |
| 两阶段 Wiener, IEEE Access 2024（全文方法节） | FPT 解析 RUL，perfect measurement 假设 | 两阶段 Wiener+随机漂移+EM，新观测 Bayes 更新 | 运行控制输入驱动（其漂移无高频控制）；测量误差/可逆项分解；同输入强基线（含梯度提升树）对比协议 |
| EntroLnn, SAC'26（全文 HTML） | MIT-Stanford 124 LFP SoH/CFT refinement | 熵修正+liquid ODE 隐状态，滑窗延伸 | 目标不同（SoH 轨迹非到达时间/调度）；我们的速率后验可修正**未来斜率**的机制消融 |
| NREL 可解释早期寿命 2024（repo 已核） | ISU-ILCC 早期寿命分类/回归 | Fused Lasso/PLSR 曲线特征 | 任务不同（一次性早期预测非在线 as-of）；其特征资产已用作我们的 B-EXT-2 外部基线（P1） |
| Li et al., Cell Reports Phys Sci 2024（全文） | 225 NMC 早期总寿命，OOD 按 DoD | 早期 dQ/dV 增量+循环条件，弹性网/HBM | 其"健康特征加法不一定提高 OOD"与我们的机理先验样本效率主张互补；我们复现其弹性网作 as-of 外部基线（P1） |
| RUL-QMoE 2025 / MINE-Graph-Mamba 2025（摘要级） | 概率区间 RUL / SOH+RUL | 分位数 MoE / 图+Mamba 编码 | 架构类贡献；无到达语义/调度/样本效率主张（已核范围内） |

## 我们三段证据的对应实验编号

- E1 机制与点/密度精度：A3_RESULTS_ZH.md（R1）+ same_key_compare_v3_run1（R1b 归因）。
- E2 样本效率：R2_DATA_EFFICIENCY_ZH.md 阶段 A+B（同池树重训，相对退化 CI）。
- E3 调度价值：R3_SCHEDULE_VALUE_ZH.md（严格占优固定 h4；校准负结果如实）。
- 外部基线（V1，进行中）：B-EXT-1 as-of GRU（序列神经代表）、B-EXT-2 as-of 弹性网
  （Cell Reports 2024 风格）——同面板同键并入主表后，主表将含：A3/A2v3、内部强树 F0–F3×2、
  外部 EXT_GRU/EXT_ENET、past_slope 朴素基线。

## Related Work 叙事线（三段式）

1. 不规则/缺失退化数据建模：插值/CDE/连续时间循环（BatteryCDE、ESWA2026）——输入级连续化。
2. 随机退化过程与在线更新：Wiener/Gamma FPT、Bayes/UKF 更新——无高频运行控制输入、无到达语义协议。
3. 我们：运行驱动速率状态 + 到达创新校正 + 决策层评估（调度）——并用数据效率与同输入外部基线
   证明机理先验的可量化价值。
