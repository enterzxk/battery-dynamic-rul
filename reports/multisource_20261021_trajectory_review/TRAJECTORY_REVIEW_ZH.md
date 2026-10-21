# B 路径轨迹候选：同键强基线独立评审

日期：2026-10-21。范围仅限保存的 C3 预测、收据、论文草稿与正式特征缓存的清单；没有读取原始数据、模型检查点或 C4，也没有拟合。

## 主要结论

B-full 与 HGB/CatBoost 的预测按完全相同的 (cell_id, arm, query_epoch) 对齐，共 7,158 行（每 arm 1,193 行），覆盖每 arm 相同的 61 个 C3 电芯。标签和 horizon 最大绝对差均为 0。主 RMSE 采用强基线收据口径：先算每个电芯内查询均方误差，再对电芯取均值并开方，即 sqrt(mean_cell(mean_query(error^2)))。HGB/CatBoost 在每个 arm 的下一源 RPT 容量点误差和保存尺度的高斯 NLL 均优于 B-full，配对电芯 bootstrap 区间不跨零。结论限于该 C3 目标和保存模型，不是概率轨迹或自然检查日程下 RUL 的胜负结论。

| arm | 模型 | 主 RMSE Ah | B-full 主 RMSE Ah | cell-macro MAE Ah | B-full cell-macro MAE Ah | Gaussian NLL | B-full Gaussian NLL |
|---|---|---:|---:|---:|---:|---:|---:|
| raw | HGB | 0.007087 | 0.011823 | 0.003758 | 0.007529 | -3.3883 | -2.9515 |
| raw | CatBoost | 0.007371 | 0.011823 | 0.003816 | 0.007529 | -3.3879 | -2.9515 |
| sparse2 | HGB | 0.008662 | 0.019014 | 0.004851 | 0.012151 | -3.2840 | -2.6351 |
| sparse2 | CatBoost | 0.008471 | 0.019014 | 0.004756 | 0.012151 | -3.3098 | -2.6351 |
| delay7d | HGB | 0.010542 | 0.025638 | 0.005891 | 0.017571 | -3.1323 | -2.1350 |
| delay7d | CatBoost | 0.010135 | 0.025638 | 0.005675 | 0.017571 | -3.1711 | -2.1350 |

Gaussian NLL 逐查询使用各模型保存的预测标准差，再按电芯等权汇总；HGB/CatBoost 的 sigma 来自 C1/C2 OOF 残差，B 的 next_capacity_sd 来自 B 路径采样。它仅评估该近似正态边际容量预测，不评估联合路径质量。HGB 与 CatBoost 的 MAE 配对差异区间覆盖零，不能声称一个架构稳定更强。

B-full 的 teacher-forced source-trajectory NLL 优于独立增量消融：raw -2.8314 对 -2.6825、sparse2 -2.7928 对 -2.6187、delay7d -2.8543 对 -2.6812（per-transition，越低越好）。这只支持当前路径监督下递归状态改善 transition likelihood 的窄机制结果。该 NLL 沿真实训练轨迹逐段计分，不能当成自由运行样本路径质量、路径校准或事件/RUL 优势。

B 使用确定性重复 train-gap 检查日程生成 128 周首达分布。它对应指定的检查干预策略，不等同自然未来 source-RPT 检查序列；没有未来检查过程模型时，自然检查策略下的 RUL 事件时间尚未识别。事件标签是首次有效源 RPT capacity <= 0.20 Ah 的源观测阈值事件，不是潜在连续物理 EOL。未观察到事件的有限窗口仍为未知，不能自动视为独立删失。known-event restricted RUL MAE 只描述有已知源事件标签的受限支持。

## 草稿改写边界

[论文问题与方法草稿](../../paper/multisource_dynamic_rul_20261021/PROBLEM_METHOD_DRAFT.md) 已经正确区分源 stop 与信息到达、观测阈值事件与潜在 EOL、容量路径与事件时间。正式结果中应把上述同键强基线结果写入 Q4 和贡献边界，并明确 B 尚未显示强下一容量点预测优势；teacher-forced NLL 与自由运行路径/事件质量分开；结果列区分下一源 RPT 条件容量、train-gap-policy 首达 RUL、未识别的自然检查策略事件时间。A 方案的早期 query 日历传播没有更早测量事件锚定，若报告 A 结果需保留该限制。

分层表为描述性分析；长 horizon (>1.5 周) 只有 25 个电芯，不能作稳定亚组结论。

## 可复核文件

- 独立逐行复算：same_key_checks.json、same_key_metrics.csv、paired_cell_bootstrap.csv、stage_lead_metrics.csv。
- 两份原预测与 receipt 位于 experiments/multisource_mechanisms_20261021/evaluation_runs/run3_exact_schedule_clock/ 和 experiments/trajectory_strong_baselines_20261021/runs/q4_strong_baselines_20261021_run2/。
- 对齐键 (cell_id, arm, query_epoch)；7,158 行，目标和 horizon 最大差 0；30,000 次配对电芯 bootstrap，seed 20261021。
