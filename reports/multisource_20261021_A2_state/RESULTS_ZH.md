# A2 状态机制 C3 评估：Qref 锚定 + state-only 容量 + 顺序 RPT 创新 NLL

日期：2026-10-22（Asia/Shanghai）｜执行者：DSH 委托主控 session-2d48bcb9-ed32-45fe-9647-dff556b5bf81，
deepseek-v4.1-flash / reasoning max｜owner 01a15c3a-1a06-7d61-8517-27b70b246183

## 1. 运行事实（可复核）

- 推断 GO：`GO_A2_C3_INFER_V2_20261022.json`（sha256 c0a241b7…4c14），脚本 `a2_infer.py` sha256 1b290fc5…76fc。
- 结果：`c3_eval_v2_20261022/`，63 个开发 cell、2,350 个 as-of query、7,050 条模型行；fits 0、C4 0、raw 0；
  rerun 前曾出现一次 30 GB RSS 事故（autograd 图逐 query 累积），已 kill 并标记 `c3_eval_20261022/INCOMPLETE_NOT_A_RESULT.json`，
  修复为 `torch.no_grad()` 后重跑，本文所有数字来自修复后的 run。
- 模型：3 个 arm 共享同一参数化（2794 参数）：full（循环控制 + RPT 更新）、time（控制全 mask + RPT 更新）、
  noRPTupdate（循环控制、无测量更新）。三个 checkpoint 均来自 6 次拟合中的 refit（注意：refit 用的是 100 个建模 cell，
  25 个内部验证 cell 未进入最终模型，见 §6）。

## 2. 方法与这次修正了什么（相对 A1）

- **Qref**：每个 cell 取“已到达”的有效 RPT 中**到达最早**者的容量，一次性锚定；C3 上实测 Qref ≈ **0.279–0.287 Ah**，
  而 A1 用标称 0.25 Ah —— 这正是 A1 读出偏移 +0.019~+0.026 Ah 的来源。
- **state-only**：容量只用 `Q = Qref·exp(−D) + R`，无 F0 读出旁路；物理不确定度用 `H P Hᵀ`（Ah²）。
- **σ 语义**：网络输出是标准差（Ah），方差显式取 σ²（Ah²）；观测 σ≈2.1e-3 Ah。
- **输入不含 dt**：速率/噪声只依赖 24 维已完成循环的控制（或全 mask），所以精确仿射半群成立、网格不变。

## 3. 全体 next-jump 指标（三臂混合，cell-macro）

| 模型 | cells | 计分行 | NLL/Ah | RMSE (Ah) | MAE (Ah) | cov95 |
|---|---|---|---|---|---|---|
| full | 62 | 2,343 | −2.697 | 0.0259 | 0.0151 | 0.956 |
| time | 62 | 2,343 | −2.861 | 0.0144 | 0.00738 | 0.937 |
| noRPTupdate | 62 | 2,343 | −1.514 | 0.0555 | 0.0431 | 0.842 |

（全体混合含 sparse2/delay7d，目标 gap 与 raw 不同；决定性比较见 §4。）

## 4. 与强基线的精确同键比较（raw、query==anchor stop、903 键 / 61 cells）

| 模型 | NLL/Ah | RMSE (Ah) | MAE (Ah) |
|---|---|---|---|
| A2 time | −3.107 | 0.00755 | 0.00506 |
| A2 full | −2.897 | 0.01572 | 0.01109 |
| A2 noRPTupdate | −1.514 | 0.04659 | 0.04316 |
| 18-fit 树基线（同键） | **−3.465** | **0.00456** | **0.00330** |

配对 cell bootstrap（5,000 次，61 cells）：
- A2 time − 树：NLL +0.358 [+0.277, +0.462]；MAE +0.00176 Ah [+0.00105, +0.00260]。
- A2 full − 树：NLL +0.568 [+0.384, +0.768]；MAE +0.00778 Ah [+0.00608, +0.00956]。
- full − time：MAE +0.00603 Ah [+0.00414, +0.00794]（**time 显著更好**）。

## 5. 结论（诚实）

1. **A2 机制成立且有效**：Qref 锚定 + 顺序 RPT 更新把下一跳容量误差从 A1 的 0.031 Ah（state-only）/
   0.0098 Ah（读出校正后）降到 **0.0076 Ah（无读出）**；noRPTupdate 退化到 0.0466 Ah，说明**测量更新是主要信息来源**，
   与 A1“更新几乎无效”形成明确对照。
2. **但仍不如同输入强树基线**：A2 最好的 time 臂比 18-fit 树差 1.76 mAh MAE（CI 1.05–2.60 mAh）与 0.36 NLL，
   差距小但显著。不能说 A2 优于树基线。
3. **24 维循环控制在本数据上是有害的**：full 比 time 差 6.0 mAh（CI 4.1–7.9），说明 150+ 个控制被 mask/标准化后
   仍引入噪声或过拟合；下一版应做控制降维/正则或改用更稳的运行摘要，而不是加容量。
4. 与 B2 对比：B2 的联合轨迹模型在同键 next-jump 上 NLL +3.55 / RMSE 0.0091，明显不如 A2；B2 的轨迹优势也未成立（见 B2 报告更正）。

## 6. 限制（必须与结论同页）

- A2 的三个 checkpoint 是 **100-cell refit**：内部选择用 100 个建模 cell、25 个验证 cell 只用于选择；
  25 个验证 cell 未进入最终模型。README/GO 中的 “full-125” 已更正；真正的全 125 refit 需要新的 3-fit GO。
- 单 split、单 seed（42）；val NLL（−3.00/−2.83/−1.93）没有置信区间，best-val 是尖峰，
  因此“RPT 更新带来似然增益”这句话只在“这次 split/seed 下”成立。
- 本结果是 C3 开发集，不是独立确认；C4 未读、未推断、未训练。
- 固定视界（1/4/12/32 周）只对恰好落在视界容差内的记录计分，覆盖率有限，未在此作为主结论。

## 7. 复现

- GO：`GO_A2_C3_INFER_V2_20261022.json`；receipt：`receipts/c3_eval_v2_20261022_receipt.json`；
  summary：`c3_eval_v2_20261022/summary.json`；预测：`c3_eval_v2_20261022/predictions_c3_a2.csv`（7,050 行）。
- 同键比较脚本仅读 saved CSV（无模型、无 payload），可重放。


## 2026-10-23 Codex independent aggregation correction

The raw same-key RMSE values .00755/.01572/.00456 in section4 use mean(cell RMSE), a descriptive alternative. The project primary sqrt(mean(cell MSE)) values are .009992 (A2 time), .019076 (A2 full), and .005736 (F3 CatBoost). MAE and NLL reproduce. Full source data, checkpoint and old report numbers remain preserved; current explicit 11-model,2326-key comparison is reports/codex_takeover_20261023_root/saved_a2_all_trees_run2/. A2 full vs time is specific to this model/forecast policy, not proof that Cycling information is intrinsically harmful. All125 final refits are now complete; their separately gated C3 evaluation is running.
