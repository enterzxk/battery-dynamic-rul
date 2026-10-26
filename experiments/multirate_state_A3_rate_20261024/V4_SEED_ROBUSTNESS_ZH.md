# V4 第二 seed 稳健性判定（2026-10-24）：机制与密度结论稳健；"点精度追平"是 seed 敏感的

执行：GO_A3_FIT_SEED43_20261024.json（seed 42→43 / refit 43→44，四臂 8 fits，2,045 s，已登记）→
GO_A3_SEED43_C3_INFER_20261024.json（548 s，0 fits）→ GO_A3_SEED43_COMPARE_20261024.json
（2,326 共同键，SUCCESS）。全部消费登记；0 C4。

## 结果（raw 臂；seed-43 臂记 A3s43_*）

| 臂 | seed-42 MAE | seed-43 MAE | 结论 |
|---|---:|---:|---|
| full | 0.003062 | 0.003533 | +0.47 mAh [+0.18, +0.75]（配对，CI 不含 0） |
| time | 0.003426 | 0.003417 | −0.009 mAh [−0.020, +0.001]（逐位级复现） |
| noRateUpdate | 0.007095 | 0.010141 | 方向保持（劣化，且更大） |
| noEll | 0.006171 | 0.006059 | −0.011 mAh（逐位级复现） |

## 判定（诚实）

**稳健（两 seed 一致）**：
1. **机制排序**：full(3.53) > noEll(6.06) > noRateUpdate(10.14) mAh @seed43——速率状态机制贡献不变；
2. **NLL 对树显著占优**：A3s43_full vs F0_hgb −0.472 [−0.560, −0.361]（raw）、−0.499（sparse2）；
   vs F2_hgb −0.418/−0.427——两 seed 全部 CI 不含 0，这是论文最稳的定量主张；
3. time/noEll 臂的确定性复现（±0.01 mAh）说明训练管线本身确定、波动来自 full 臂的
   μ_θ 网络初始化对循环控制学习的影响。

**不稳健（如实降级）**：
4. **"点精度追平最强树"是 seed 敏感的**：seed-42 A3_full vs F2_hgb +12 µAh [−354, +414]（打平）；
   seed-43 +0.483 mAh [+0.198, +0.767]（显著落后）。两 seed 合并解读：A3 full 臂点精度在
   最强树的 0–0.9 mAh 邻域内波动，**不能声称稳定追平**；论文表述改为
   "within 0.5 mAh of the strongest trees on accuracy (seed-dependent) and consistently
   superior on the full predictive density (0.42–0.50 nats, both seeds)"。
5. 对 R2（数据效率）的影响：R2 全部为 seed-42 内部配对（A3@50% 零退化 vs 树退化、NLL 全占优），
   这些相对主张不受影响；但"A3@50% 绝对水平追平树@100%"一句需加 seed 敏感性限定
   （±0.5–0.9 mAh 量级）。

## 论文修正（已应用到 FULL_DRAFT_V1.md）

Abstract/§5.1/§5.2 的"matches the strongest trees on point accuracy"改为
"within 0.5 mAh of the strongest trees (seed-dependent), consistently superior on the full
predictive density"；§5.5 填入本表。

## 产物

runs_seed43/run1_fits/（4 checkpoint + fit_report + consumption_record）、
c3_eval_seed43_20261024/、seed43_compare_run1/（全指标 + 配对 CI）、三个 GO + receipts；
登记表 13 条。
