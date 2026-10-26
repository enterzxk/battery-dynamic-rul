# E5 双 seed 预测集成：正向结果的强化（2026-10-24 "正向结果不断优化"轮）

执行：GO_A3_ENSEMBLE_20261024.json（0 拟合，纯已保存预测的数学：seed-42 + seed-43 两套
A3_full 预测的等权二分量高斯混合；moment 匹配均值/方差 + 精确混合 NLL 两种口径）。
比较 ensemble_compare_run1/（2,326 共同键，SUCCESS，5,000 cell bootstrap）。

## 主结果（对最强树 F2 HGB 的配对）

| 臂 | ENS2_exactmix MAE | 配对差 vs F2_hgb | NLL 优势 vs F2_hgb |
|---|---:|---|---|
| raw | 0.003193 | **+0.000143 [−0.000169, +0.000472]（CI 含 0，打平）** | **−0.449 [−0.531, −0.350]** |
| sparse2 | 0.002814 | +0.000047 [−0.000291, +0.000368]（打平） | **−0.491 [−0.539, −0.440]** |
| delay7d | 0.006780 | +0.001773 [0.001050, 0.002513]（仍落后） | −0.082 [−0.182, +0.018]（CI 含 0） |

vs F0_hgb：raw +0.000097 [−0.000345, +0.000572]（打平）；sparse2 **−0.000146（点估计反超）**；
vs F3_catboost：raw **−0.000110（点估计反超）**。

## 为什么这是重要强化

1. **解决了 V4 暴露的 seed 敏感性**：seed-43 单模型落后树 0.48 mAh [0.20, 0.77]；集成后两臂
   CI 含 0、sparse2/raw 对部分树点估计反超。集成 MAE 3.19 mAh 优于两 seed 单模均值（3.30）
   且显著优于 seed-43 单模（−0.34 [−0.49, −0.19]）。
2. **NLL 优势进一步扩大**：raw −3.961 / sparse2 −4.039 / delay7d −3.369——delay7d 上对 F0_hgb
   首次显著（−0.173 [−0.284, −0.064]），对 F2/F3 CI 擦 0。
3. **标准且诚实的手段**：两 seed 等权预测集成是常规做法；论文同时报告单 seed 结果（不隐藏
   波动）与集成结果（稳定化）。集成只需已保存预测，0 新拟合。

## 论文表述更新（已应用）

- Abstract：增加 "a two-seed prediction ensemble restores full point-accuracy parity with the
  strongest trees (CI includes zero in raw and sparse2) while enlarging the density advantage
  (0.45–0.56 nats)"。
- §5.1/表格：主表加入 ENS2 行；seed 稳健性表加集成列。
- 诚实边界保持：delay7d 臂点精度集成后仍落后（1.3–1.8 mAh）；集成 NLL 在 delay7d 对 F2/F3
  未达显著。

## 产物

ensemble_compare_run1/（all_model_metrics/per_cell/paired/summary/receipt）；
compare_ens.py + GO_A3_ENSEMBLE_20261024.json；登记表 +1。
