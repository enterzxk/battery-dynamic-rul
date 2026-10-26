# A2 真·全 125 cell 最终 refit 与 14 模型同键比较：协议修复完成，结论不变

执行：2026-10-23（实验链 10:36–10:56 北京时间，Codex 接管主控）；本报告 2026-10-24 由继续接管会话
依据回执与产物落盘。owner thread 01a15c3a-1a06-7d61-8517-27b70b246183 全程保留。

## 0. 执行链与互斥

- 2026-10-22 DSH 主控（deepseek-v4.1-flash）在 DeepSeek 传输故障后 goal 置为 paused、turn 被用户中止。
- 2026-10-23 用户直接回复确认暂停；`docs/CODEX_RETAKEOVER_20261023.json` 记录 Codex 恢复主控
  （dsh_control_stopped=true，02:35Z）。
- 实验链（refit → C3 推断 → 同键比较）在互斥 claim（claims/*.claim）与两把共享 CPU 锁下由 Codex 主控执行；
  当前无存活持有者（进程已消亡），锁文件为空。
- 2026-10-24 用户委托 ZCode 会话继续推进；本会话只做报告落盘与后续设计，未发新拟合 GO。

## 1. 协议修复内容

独立审稿（docs/INDEPENDENT_REVIEW_B2_A2_20261022.md P0#2）指出：旧"full-125 refit"实际只在 100 个建模 cell 上
refit，25 个内部验证 cell 从未进入最终模型。本实验（PROTOCOL.md）执行真正的修复：

- 最终 refit 使用全部 125 个训练 cell（含原 25 个内部验证 cell），标准化同步改在全 125 cell 上拟合；
- 冻结内部选择步数 full=550 / time=100 / noRPTupdate=550（不重选、不按 C3 调参）；
- seed 42 / sampling seed 43，AdamW 1e-3 / wd 1e-4，batch 8，window 256 exact 无梯度 burn-in，clip 1.0；
- 恰好 3 次拟合 / 1,200 优化步；GO `ROOT_GO_RUN1.json`（sha256 19bb51ce…，max_fits=3，allow_C4=false，
  只读 PREP 缓存 npz f746edb8…）。

## 2. 运行事实（receipts）

| 步骤 | 状态 | 关键数字 |
|---|---|---|
| run1 三臂 refit | SUCCESS（receipts/run1.json） | 3/3 fits、1200 优化步、65.7 s；C4/C3/raw/旧 checkpoint 读取全 0 |
| C3 推断 run1 | PREFLIGHT_REFUSED（receipts/c3_run1_preflight_failure.json） | 时间戳解析拒绝（ISO 带小数 +00:00）；0 读取/0 拟合，receipt 保留 |
| C3 推断 run2 | SUCCESS（receipts/c3_eval_run2.json） | 881.6 s；GO ROOT_GO_C3_RUN2.json sha 7799587b… |
| 同键比较 | summary.json | 2326 共同键（raw 903 / sparse2 463 / delay7d 960）、61 电芯、逐键 target 断言 |

## 3. 统一口径

主口径 **RMSE = sqrt(mean_cell MSE)**（2026-10-23 Codex saved-review run2 修正；DSH 10-22 报告中的
0.00755/0.01572 是 mean_cell RMSE 口径）。两种口径下所有胜负关系一致。MAE 与 NLL 口径不变、可独立复现。

## 4. 主表（14 模型 × 3 臂）

新 A2_* = 全 125 cell refit；Old_A2_* = 10-22 的 100-cell refit；F0–F3 × HGB/CatBoost = 已保存的树模型预测。
全部为容量条件预测（单位 Ah，不是 RUL 周）。

**raw 臂**（903 queries / 61 cells）

| 模型 | MAE (Ah) | RMSE (Ah) | NLL/Ah | cov90 |
|---|---:|---:|---:|---:|
| A2_full | 0.010503 | 0.017047 | -2.754 | 0.984 |
| A2_time | 0.005123 | 0.010094 | -3.122 | 0.954 |
| A2_noRPTupdate | 0.047203 | 0.058567 | -1.439 | 0.837 |
| Old_A2_full | 0.011088 | 0.019076 | -2.897 | 0.963 |
| Old_A2_time | 0.005061 | 0.009992 | -3.107 | 0.956 |
| Old_A2_noRPTupdate | 0.043161 | 0.055861 | -1.514 | 0.783 |
| F0_hgb | 0.003096 | 0.005812 | -3.457 | 0.982 |
| F1_hgb | 0.003019 | 0.005416 | -3.422 | 0.991 |
| F2_hgb | 0.003050 | 0.005612 | -3.511 | 0.980 |
| F3_hgb | 0.003121 | 0.005475 | -3.443 | 0.989 |
| F0_catboost | 0.003171 | 0.006119 | -3.464 | 0.981 |
| F1_catboost | 0.003115 | 0.005601 | -3.440 | 0.985 |
| F2_catboost | 0.003253 | 0.005998 | -3.515 | 0.967 |
| F3_catboost | 0.003304 | 0.005736 | -3.465 | 0.979 |

**sparse2 臂**（463 queries / 61 cells）

| 模型 | MAE (Ah) | RMSE (Ah) | NLL/Ah | cov90 |
|---|---:|---:|---:|---:|
| A2_full | 0.008896 | 0.012518 | -2.862 | 0.993 |
| A2_time | 0.004309 | 0.007769 | -3.261 | 0.981 |
| A2_noRPTupdate | 0.045963 | 0.057609 | -1.473 | 0.841 |
| Old_A2_full | 0.009519 | 0.015178 | -3.060 | 0.976 |
| Old_A2_time | 0.004251 | 0.007669 | -3.231 | 0.981 |
| Old_A2_noRPTupdate | 0.041803 | 0.054789 | -1.568 | 0.793 |
| F0_hgb | 0.002960 | 0.005437 | -3.475 | 0.987 |
| F1_hgb | 0.002799 | 0.004869 | -3.443 | 0.998 |
| F2_hgb | 0.002767 | 0.004882 | -3.548 | 0.995 |
| F3_hgb | 0.002898 | 0.004969 | -3.463 | 0.998 |
| F0_catboost | 0.002968 | 0.005706 | -3.485 | 0.987 |
| F1_catboost | 0.002928 | 0.005102 | -3.461 | 0.987 |
| F2_catboost | 0.002906 | 0.005215 | -3.561 | 0.988 |
| F3_catboost | 0.003011 | 0.005040 | -3.496 | 0.996 |

**delay7d 臂**（960 queries / 61 cells）

| 模型 | MAE (Ah) | RMSE (Ah) | NLL/Ah | cov90 |
|---|---:|---:|---:|---:|
| A2_full | 0.019874 | 0.030446 | -2.359 | 0.984 |
| A2_time | 0.010090 | 0.018573 | -2.542 | 0.908 |
| A2_noRPTupdate | 0.046785 | 0.057935 | -1.443 | 0.843 |
| Old_A2_full | 0.020911 | 0.033937 | -2.474 | 0.946 |
| Old_A2_time | 0.009963 | 0.018370 | -2.559 | 0.919 |
| Old_A2_noRPTupdate | 0.043391 | 0.055601 | -1.510 | 0.794 |
| F0_hgb | 0.005442 | 0.009804 | -3.195 | 0.956 |
| F1_hgb | 0.005313 | 0.009193 | -3.221 | 0.965 |
| F2_hgb | 0.005007 | 0.008869 | -3.287 | 0.948 |
| F3_hgb | 0.005198 | 0.008811 | -3.258 | 0.963 |
| F0_catboost | 0.005400 | 0.009653 | -3.214 | 0.941 |
| F1_catboost | 0.005286 | 0.009052 | -3.243 | 0.961 |
| F2_catboost | 0.005099 | 0.008916 | -3.291 | 0.931 |
| F3_catboost | 0.005189 | 0.008878 | -3.270 | 0.956 |

## 5. 关键配对结论（5,000 次物理电芯 bootstrap）

| 臂 | 比较 | 指标 | Δ [95% CI] |
|---|---|---|---|
| raw | A2_time vs Old_A2_time | MAE_Ah | +0.000062 [+0.000021, +0.000100] |
| raw | A2_time vs Old_A2_time | NLL_per_Ah | -0.015373 [-0.030881, +0.003556] |
| raw | A2_full vs Old_A2_full | MAE_Ah | -0.000585 [-0.001049, -0.000168] |
| raw | A2_full vs Old_A2_full | RMSE_Ah | -0.002029 [-0.003601, -0.000958] |
| raw | A2_full vs Old_A2_full | NLL_per_Ah | +0.142606 [+0.024787, +0.229421] |
| raw | A2_noRPTupdate vs Old_A2_noRPTupdate | MAE_Ah | +0.004042 [+0.002009, +0.006064] |
| raw | A2_full vs A2_time | MAE_Ah | +0.005380 [+0.003681, +0.007138] |
| raw | A2_time vs F0_hgb | MAE_Ah | +0.002027 [+0.001336, +0.002943] |
| raw | A2_time vs F2_hgb | MAE_Ah | +0.002073 [+0.001411, +0.002881] |
| raw | A2_time vs F3_catboost | MAE_Ah | +0.001820 [+0.001101, +0.002655] |
| raw | A2_time vs F0_hgb | NLL_per_Ah | +0.335027 [+0.244314, +0.466423] |
| sparse2 | A2_time vs Old_A2_time | MAE_Ah | +0.000059 [+0.000020, +0.000097] |
| sparse2 | A2_time vs Old_A2_time | NLL_per_Ah | -0.030327 [-0.039601, -0.018060] |
| sparse2 | A2_full vs Old_A2_full | MAE_Ah | -0.000624 [-0.001275, -0.000092] |
| sparse2 | A2_full vs Old_A2_full | RMSE_Ah | -0.002660 [-0.004809, -0.000948] |
| sparse2 | A2_full vs Old_A2_full | NLL_per_Ah | +0.197694 [+0.125241, +0.256475] |
| sparse2 | A2_noRPTupdate vs Old_A2_noRPTupdate | MAE_Ah | +0.004159 [+0.002252, +0.006104] |
| sparse2 | A2_full vs A2_time | MAE_Ah | +0.004586 [+0.002934, +0.006216] |
| sparse2 | A2_time vs F0_hgb | MAE_Ah | +0.001349 [+0.000699, +0.002026] |
| sparse2 | A2_time vs F2_hgb | MAE_Ah | +0.001542 [+0.000917, +0.002202] |
| sparse2 | A2_time vs F3_catboost | MAE_Ah | +0.001298 [+0.000639, +0.002018] |
| sparse2 | A2_time vs F0_hgb | NLL_per_Ah | +0.213919 [+0.143773, +0.285909] |
| delay7d | A2_time vs Old_A2_time | MAE_Ah | +0.000127 [+0.000048, +0.000203] |
| delay7d | A2_time vs Old_A2_time | NLL_per_Ah | +0.016755 [-0.007917, +0.045499] |
| delay7d | A2_full vs Old_A2_full | MAE_Ah | -0.001037 [-0.001825, -0.000280] |
| delay7d | A2_full vs Old_A2_full | RMSE_Ah | -0.003491 [-0.004984, -0.002222] |
| delay7d | A2_full vs Old_A2_full | NLL_per_Ah | +0.114891 [+0.044863, +0.174830] |
| delay7d | A2_noRPTupdate vs Old_A2_noRPTupdate | MAE_Ah | +0.003394 [+0.001647, +0.005199] |
| delay7d | A2_full vs A2_time | MAE_Ah | +0.009784 [+0.006616, +0.012919] |
| delay7d | A2_time vs F0_hgb | MAE_Ah | +0.004648 [+0.003268, +0.006301] |
| delay7d | A2_time vs F2_hgb | MAE_Ah | +0.005083 [+0.003726, +0.006705] |
| delay7d | A2_time vs F3_catboost | MAE_Ah | +0.004901 [+0.003522, +0.006447] |
| delay7d | A2_time vs F0_hgb | NLL_per_Ah | +0.652965 [+0.496029, +0.851066] |

读法：

1. **协议修复本身的效应很小**。time 臂 raw MAE 仅 +0.00006 Ah [0.00002, 0.00010]（显著但约 6 µAh，工程上可忽略）；
   full 臂点精度小幅改善（raw MAE −0.00059 Ah、RMSE −0.0020 Ah）而 NLL 变差（+0.14 [0.02, 0.23]）；
   noRPTupdate 点精度变差（+0.0034~+0.0042 Ah MAE）。→ 执行缺口是真实的，但不是 A2 落后的原因。
2. **A2 仍全面落后同可见信息强树**。A2 time（全 125 refit）对 F0 HGB：raw MAE +1.97 mAh [1.29, 2.86]、
   sparse2 +1.35 [0.70, 2.03]、delay7d +4.65 [3.27, 6.30]，NLL 同向（raw +0.335 [0.244, 0.466]）。
   对 F2/F3 HGB、F0–F3 CatBoost 结论一致。
3. **循环控制在该参数化下仍有害**。新 A2 full − time：raw MAE +5.38 mAh [3.68, 7.14]、sparse2 +4.59、delay7d +9.78。
   注意限定（CODEX_REVIEW）：这是当前状态参数化、训练样本规模与未来 held-control 策略下的结果；
   同一循环信息在 F2 树实验中仍有价值，不能外推为"循环信号无信息"。
4. **机制主张维持**。noRPTupdate（去掉 RPT 测量更新）RMSE 退化一个数量级（raw 0.0586 Ah vs time 0.0101 Ah），
   RPT 测量更新确实是状态的主要信息来源。

## 6. 诚实判定

- 审稿 P0#2 的执行缺口已修复并复核：最终 checkpoint 确实由全 125 训练 cell 拟合（fit_report n_fit_cells=125）。
- 修复不改变科学结论：A2 机制成立、显著优于 A1 与 B2，但**仍未超过同输入强树基线**；
  声明边界从"selection 100 + refit 100"更新为"selection 100（冻结步数）+ refit 125"。
- 不把本修复称为架构改进；A2 仍缺少个体化潜在退化速率状态（见第 8 节）。

## 7. 限制

- C3 开发集，非独立确认；单 seed（42）/单 split。
- 查询面板沿用旧 A2 预阈值/去重锚面板（2,326 键 / 61 电芯），不是完整原始正式网格。
- Q(q+h) 条件于给定预测时距 h（使用实现的下一次源检查间隔），不构成未知下次检查时间的联合预测或物理首达。
- full−time 差异不能唯一归因于"循环信息有害"：可辨识性与训练规模混杂。

## 8. 下一优先（承接 CODEX_REVIEW_AND_NEXT_ACTION_20261023_ZH.md）

不是重复本结构或给输出加校准，而是检验"个体退化速度可观测性"假设：
候选状态 x=(D, ℓ, R)，dD = softplus(ℓ)·dt，dℓ = −κ(ℓ − μ_θ(u))·dt + σ_ℓ dW，dR = −λR·dt + σ_R dW，
RPT 观测 y = Q_ref·exp(−D) + R + ε；ℓ 是可被测量更新修正的个体速度状态。
循环信号拆分为"截至当前已完成的运行条件 u"与健康代理 z，考虑 p(z | x, u, protocol) 做观测更新。
需在训练内部检查健康代理的工况可比性，锁定未来运行/检查政策，分别消融速度后验更新、循环观测更新与
仅时间推进，再与同可见信息强树比较。GAUSSIAN 状态校正后的 D 不得声称为不可逆物理真值。

## 9. 附带事件记录（协议缺口，非本实验链）

2026-10-23 10:35（北京时间）一次 `a2_train_v2.py` 复跑消费了已消费且此后被改动的
`GO_A2_FITV2_noRPTupdate.json`（fit_report 记录的 go_sha256 与 10-22 运行记录不一致：764e6d61… vs 33ffdc6a…）。
输出 checkpoint 与 10-22 版本逐字节一致（sha256 d2c60a0e…），反证该臂训练确定性；科学结果不受影响。
但事件暴露 GO 门控无一次性消费强制：**建议后续 gate 加入 consumed-GO 登记校验**（新 GO 签发时校验
request_id 从未被消费）。已同步记入 docs/DSH_PROGRESS_20261022_ZH.md §4j。

## 10. 产物清单

- run1/（三臂 fit_report + model_state_dict.pt）、receipts/run1.json、ROOT_GO_RUN1.json
- c3_eval_run2/（predictions_c3_a2.csv、summary.json、receipt.json）、ROOT_GO_C3_RUN2.json
- same_key_compare_run1/（all_model_metrics.csv、paired_cell_bootstrap.csv、per_cell_metrics.csv、
  summary.json、schema.json、receipt.json）、ROOT_GO_COMPARE_RUN1.json
- 上游协议：PROTOCOL.md、refit_all125.py（sha256 见 ROOT_GO_RUN1.json code_sha256）
