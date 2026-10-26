# F1/F2/F3 下一容量扩展：与 B 的同键复核

## 核对范围

本复核只读已保存的预测表：18-fit 扩展结果、B full 的下一源 RPT 容量预测，以及强基线结果中的 degradation stage 标签。没有读原始曲线，没有重拟合。将 query key 定义为 (cell_id, arm, round(query_epoch, 6))。强模型每个组合 3,579 行、61 cells，与 B full 完全同键；每个 arm 各 1,193 行。逐行核对目标容量差不超过 1e-12 Ah，预测 horizon 差不超过 1e-6 周。stage 标签来自强基线保存表，另核对其 target/horizon 与本次扩展相同。

主指标为 cell-equal RMSE = sqrt(mean_cell(mean_query(error²)))、cell-equal MAE 和 cell-equal Gaussian NLL。NLL 使用两边保存的 predictive sigma；扩展模型 sigma 来自 train OOF residual，B 使用其路径输出 next_capacity_sd。NLL 只是在各自 Gaussian 摘要假设下的条件容量预测分数，不能与 B 的自由路径 NLL 混称。 paired 95% 区间按电芯有放回抽样 5,000 次，seed=42。

## 结果

六个强模型/特征组合在这个 next-capacity conditional task 上均低于 B full 的 cell-equal RMSE/MAE。代表性 HGB-F2 组合：

| 分组 | 行 / 电芯 | HGB-F2 RMSE | B full RMSE | ΔRMSE (HGB−B) | HGB-F2 MAE | B full MAE |
|---|---:|---:|---:|---:|---:|---:|
| 全部 | 3,579 / 61 | 0.007818 | 0.019652 | −0.011835 | 0.004486 | 0.012417 |
| raw | 1,193 / 61 | 0.006630 | 0.011823 | −0.005193 | 0.003749 | 0.007529 |
| sparse2 | 1,193 / 61 | 0.007578 | 0.019014 | −0.011436 | 0.004408 | 0.012151 |
| delay7d | 1,193 / 61 | 0.009053 | 0.025638 | −0.016585 | 0.005300 | 0.017571 |

全体 HGB-F2 的 ΔRMSE 电芯配对 bootstrap 95% CI 为 [−0.015551, −0.008238] Ah；raw arm 为 [−0.007354, −0.003079] Ah。相同条件下 HGB-F2 全体 Gaussian NLL 为 −3.3704，B 为 −2.5739，Δ为 −0.7966；这不是 B 轨迹 likelihood 的比较。六个面板/模型的全体、arm、stage 与 horizon 详细结果及逐组区间见配套 CSV。

按保存的 degradation-stage 分组，HGB-F2 RMSE 分别为：SOH ≤0.85，0.01164 vs B 0.02320（1,049 行、59 cells）；0.85–0.90，0.01275 vs 0.01909（268 行、51 cells）；0.90–0.95，0.01074 vs 0.01883（403 行、58 cells）；>0.95，0.00568 vs 0.01996（1,859 行、61 cells）。时间支持集中在短 gap：3,516/3,579 行在 0–2 周，63 行在 2–4 周；没有超过 4 周的共同 next-capacity query，因此不能据此声称长跨度优势。

## 解释边界

18-fit 扩展中，F2 在下一容量点预测上最好，而 F3 在 RUL 预测上最好，体现两个监督目标的区别。这里仅报告与 B 可逐行匹配的下一容量比较：它是一个以已知评测 next-query horizon 为条件的下一容量点预测比较。双方目标、查询、arm 和 horizon 逐行一致；HGB/CatBoost 以 horizon 为显式输入，B full 的下一容量分布也在对应下一源 RPT horizon 上读取。它不能推出强模型改善了 B 的首次阈值事件时间或自由滚动轨迹质量。结果也只覆盖当前 C3 development keys，不能替代独立确认。尾部容量阈值语义仍是 source-observed first valid RPT，不是潜在物理 EOL。

## 可复现证据

- 同键清单：matched_keys.csv
- 指标：paired_metrics.csv
- 电芯配对 bootstrap：paired_cell_bootstrap.csv
- 输入/对齐元数据：metadata.json
- 扩展 GO 输出：experiments/trajectory_multisource_nextcap_20261021/runs/nextcap18-9e7d9cb1c67f/predictions_c3.csv

