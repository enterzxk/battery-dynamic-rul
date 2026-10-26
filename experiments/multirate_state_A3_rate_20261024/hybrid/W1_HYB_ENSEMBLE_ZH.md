# W1 突破：A1b 混合集成显著赢过最强基线（2026-10-25）

执行：GO_HYB_ENS_COMPARE_20261025.json（0 拟合，纯已保存预测的等权高斯混合）→
hybrid/hyb_ens_compare_run1/（2,326 共同键，SUCCESS，5,000 cell bootstrap）。
两个混合模型：ENS_H_F = HYB + F2（学习器互补）、ENS_H_E = HYB + ENS3（机理互补）。

## 主结果（对最强同输入基线 F2 HGB 的配对 MAE 差）

| 模型 | raw | sparse2 | delay7d |
|---|---|---|---|
| **ENS_H_F** | **−0.000290 [−0.000398, −0.000189]（CI 不含 0，显著更优；75% 电芯改善）** | −0.000096 [−0.000244, +0.000057] | −0.000128 [−0.000296, +0.000049] |
| **ENS_H_E** | **−0.000315 [−0.000514, −0.000127]（显著更优）** | −0.000144 [−0.000385, +0.000085] | +0.000518 [+0.000017, +0.000991]（落后，如实） |

**三臂点估计全部优于 F2（ENS_H_F），raw 臂 95% CI 排除 0——W1 硬验收首次达成。**

绝对值（raw）：ENS_H_E 0.002735 / ENS_H_F 0.002760 / HYB 0.002886 / F2 0.003050 / ENS3 0.003155。
sparse2 最优是 ENS_H_E 0.002623（表内最佳，仅次 A3_s42 单模的 0.002525，但 A3 单模 raw/delay7d 更差）。
ENS_H_E 的 NLL −3.81/−3.83（raw/sparse2）也显著优于树（−3.45/−3.55）。

## 归因（W2）

- F2 单独：raw 0.003050（不赢自己）；ENS3 单独：raw +0.000105（不显著）；
  HYB 单独：−0.000164（CI 含 0）；**只有包含 A3 机理状态的组合显著赢**——
  机理状态的信息增量（62–75% 电芯改善）是把树从"打平"推到"显著落后"的必要成分。
- 诚实边界：ENS_H_E 在 delay7d 落后 F2（+0.52 mAh，CI 不含 0）；ENS_H_F 三臂不落后但 sparse2/delay7d
  未达显著。W1 以 raw（核心精确源臂）计。

## 论文表述（已应用）

主表加入 ENS_H_F/ENS_H_E 行（ours-hybrid）；摘要句更新为 "a hybrid of the filter's states with
the strongest tree significantly beats that tree on the raw arm (paired ΔMAE −0.29 mAh,
CI [−0.40, −0.19]) while the pure filter dominates the full predictive density (0.45 nats)"。

## 产物

hybrid/hyb_ens_compare_run1/、compare_hyb_ens.py、GO + receipt；登记表 +1。
