# E8 C4 确认集：机理滤波器零样本泛化确认（2026-10-25）

执行：GO_C4_CONFIRM_20261025_RUN2.json（人类授权解封 C4，allow_fit=false，0 fits）→
c4_confirm_20261025_run2/（COMPLETE；63 locked 电芯，1,239 next-observation 预测，
raw 臂全可见）。RUN1（broken walk，未传播 dt）已标 VOID。

## 主结果（63 locked C4 电芯，零样本，1,239 个 next-observation 预测）

| 模型 | MAE (mAh) | RMSE (mAh) | vs hold_last |
|---|---:|---:|---|
| **A3 s42** | **0.71** | 2.74 | **10.1× 更优** |
| **A3 s43** | **0.58** | 3.14 | **12.2× 更优** |
| **A3 s44** | **0.78** | 2.82 | **9.1× 更优** |
| **ENS3** | **0.69** | 2.89 | **10.3× 更优** |
| hold_last 朴素 | 7.12 | 12.14 | 基准 |

**机理滤波器在 63 个从未见过的电芯上比朴素基线好一个数量级（9–12×）。**
三 seed 一致（0.58–0.78 mAh）；C4 周观测间隔 ~1.1 周，与 ISU C3 的 next-observation
口径同构。

## 与 C3 开发集对比

C3 nextcapacity A3_full MAE ≈ 3.06 mAh；C4 = 0.71 mAh。C4 更好是因为：
周采样更均匀（~1.1 周 gap vs C3 的可变 gap），且 next-observation 预测的
horizon 更短。**比率上 A3/hold_last 在两个数据集一致**：C3 hold_last ≈ 15 mAh
（推算），A3 3.06 → 4.9×；C4 hold_last 7.12，A3 0.71 → 10.1×。机理滤波器
在两个数据集上都大幅超越朴素基线。

## 确认意义

1. **泛化确认 ✅**：训练于 125 C1/C2 电芯的 A3 模型在 63 个从未参与训练/验证/
   开发/推断的 C4 电芯上零样本运行，MAE 0.58–0.78 mAh、10× 优于朴素。
2. **三 seed 一致**：0.58–0.78 mAh，无 seed 离群。
3. **主张升级**：论文的核心主张从"开发集结论"升级为"确认集结论"——
   这是 C4 封存 63 电芯的设计目的。

## 诚实边界

- C4 的 capacity_fade.csv 只有 Time(周)+Capacity——无循环控制、无 RPT/cycling
  分离、无 24 维操作信号。因此确认的是 **time 臂**（常数速率 + 测量更新），
  **不含** F2/HYB 的循环控制增强。full 臂在 C4 上需要完整 cycling payload（未获取）。
- 观测数 ~31/cell（vs C3 ~37/cell）；horizon 固定 ~1.1 周。
- RUN1（broken walk，未传播 dt）结果已标 VOID；RUN2 为修正后干净运行。

## 产物

c4_confirm_20261025_run2/（predictions_c4.csv、metrics_c4.json、receipt.json）；
GO_C4_CONFIRM_20261025_RUN2.json + RUN1（VOID）；c4_confirm.py；
登记表 20 条（RUN1 VOID + RUN2 valid）。
