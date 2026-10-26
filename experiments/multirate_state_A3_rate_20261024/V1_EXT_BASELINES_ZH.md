# V1 外部基线：论文主表的"与别的论文方法对比"（P1 完成）

执行：2026-10-24。ext_baselines.py（worker #5；RUN1 特征名顺序差异在门内失败留痕，
v1.1 名称对齐修复后自检 18/18；RUN2 GO de67c7da…，4 fits=2 模型×(OOF σ+全量)，432s，已登记）。
两个外部方法在**同一 as-of 协议、同一冻结查询面板**（与树 CSV 逐键相等 3579）下复现：
- **EXT_GRU**：序列神经代表（竞品标配架构）；RPT 序列 token + as-of 上下文 + 24 维 control 前缀，
  NLL 训练，OOF σ。
- **EXT_ENET**：Li et al. 2024 Cell Reports 风格（204 维早期特征增量 + 循环条件 + 弹性网），
  as-of 化=只用已到达 RPT 的特征。
比较 GO_EXT_COMPARE_20261024.json → ext_compare_run1/（2,326 共同键，SUCCESS，0 拟合）。

## 主表（raw / sparse2 / delay7d，MAE Ah，RMSE=√mean_cell MSE，NLL/Ah，cov90）

raw：A3_full 0.003062/0.006585/−3.928/0.959；EXT_GRU 0.003351/0.006068/−3.339/0.988；
EXT_ENET 0.019223/0.022235/−2.342/0.995；F0–F3 树 0.00302–0.00330（参照）。
sparse2：A3 0.002525 vs EXT_GRU 0.003081 vs EXT_ENET 0.019110。
delay7d：A3 0.006484 vs EXT_GRU 0.006127（打平）vs EXT_ENET 0.020503。

## 配对结论（5,000 cell bootstrap）

1. **A3 vs EXT_GRU（序列神经代表）**：sparse2 MAE **−0.000556 [−0.001008, −0.000119] 显著更优**；
   raw −0.000289 [−0.000786, +0.000180] 与 delay7d +0.000357 [−0.000264, +0.000950] 打平；
   **NLL 三臂全胜（−0.31 ~ −0.72，CI 均不含 0）**。
2. **EXT_GRU vs 最强树**：点精度打平（vs F0 +0.000255 CI 含 0）但 NLL 较差（+0.118 [0.080, 0.157]），
   delay7d 点精度也落后 F2（+0.001120 [0.000248, 0.002108]）——序列神经在 124 电芯小样本上
   未能超过树，与文献中神经方法在小数据集的表现一致。
3. **EXT_ENET 显著弱于全部方法**（MAE 差 14–17 mAh，CI 不含 0）——如实呈现并解释任务错配：
   早期特征线性家族的设计目标是**一次性早期总寿命预测**（Li et al. 2024 的任务是 log 寿命），
   对"给定 as-of 前缀预测下一已到达 RPT 容量"的在线条件预测任务不适配。这个负结果本身是论文的
   有价值对照：说明该任务家族需要的是在线状态更新（A3/树/GRU），不是早期特征回归。

## 论文主表结构（V1 后的完整版）

A3_full / A2v3_full（机理家族）；F0–F3 × HGB/CatBoost（内部强树）；EXT_GRU（外部序列神经）；
EXT_ENET（外部早期特征线性）；past_slope（朴素）。全部同协议同键，逐键 target 断言。

## 诚实边界

- EXT_GRU 为小型实现（TinyGRU 16 隐层，冻结超参）——代表架构家族而非任何单篇论文的完整复现；
  论文中表述为"sequence-NN representative (GRU)"，不声称复现某具体论文。
- EXT_ENET 特征为 204 维全量（未做 Li et al. 的前向选择/2 特征求精）——是家族的强版本而非
  原文复现；其弱表现的归因（任务错配 vs 特征选择）在论文中作为讨论点，不作为对原论文的贬低。
- delay7d 上 A3 对 EXT_GRU 打平（CI 含 0），不是全臂全胜。

## 产物

ext_baselines/（ext_baselines.py 20849b6e…、README、GO RUN1/RUN2、runs/ext_run2_20261024/
含 predictions_ext.csv 7,158 行、fit_report、receipt）；ext_compare_run1/（all_model_metrics/
paired/per_cell/summary/receipt）；A3-vs-EXT 直接配对（本轮补算，写入 ext_compare_run1/）。
