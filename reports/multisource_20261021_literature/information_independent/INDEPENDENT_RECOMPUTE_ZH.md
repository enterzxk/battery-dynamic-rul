# 多源信息增量：保存预测的独立统计复算

## 输入与边界

按已批准的 0-fit GO INFORMATION_SAVED_PREDICTIONS_INDEPENDENT_RECOMPUTE_20261021 读取其 allowlist 中的三个输出文件并逐个核对 SHA-256：predictions.csv=f5a295810e47889244487d27ac87e9a54fa67f82ceef58b3eccffa5cb4615783；arm_summary.csv=39ca2485259d33de0452e09f8267c9b81bf895c82673283a40c5a90cc6d6a4c5；cell_metrics.csv=ccf306ce3c8ed293dd11866839d6326de5d190f6d772450aad7c6d90f477b32e。重算仅用已保存预测，未加载模型或原始数据、未拟合/推断、未读 C4。共22,590行，6个模型变体，3臂。

从每行重新计算 event Brier=(p_event-y_event)^2；仅当 target_rul_weeks 非空时计算均值MAE、q10–q90 coverage及80% interval score=width+10*lower miss+10*upper miss。逐行结果与原预测文件已有 event Brier、MAE、coverage、IS80字段一致。先按电芯求每项指标均值，再对电芯等权平均。RUL指标有61个有目标电芯；事件Brier有62个有标签电芯。配对bootstrap按电芯有放回重采样20,000次，seed=20261021。F2-F0等“改进”定义为基线cell-MAE减F2 cell-MAE，正数有利于F2；受害>2周定义为F2的cell-MAE比基线高超过2周。

## cell-macro三臂结果

MAE单位：周；Brier越低越好；coverage目标为0.80；IS80越低越好。

| 模型 | 臂 | F0 MAE / Brier / cov / IS80 | F1 MAE / Brier / cov / IS80 | F2 MAE / Brier / cov / IS80 |
|---|---|---:|---:|---:|
| HGB | raw | 2.037 / 0.0001 / 0.937 / 10.308 | 2.037 / 0.0002 / 0.925 / 9.928 | 1.794 / 0.0004 / 0.894 / 9.251 |
| HGB | sparse2 | 2.238 / 0.0074 / 0.898 / 10.761 | 2.202 / 0.0090 / 0.894 / 10.457 | 1.931 / 0.0068 / 0.867 / 10.002 |
| HGB | delay7d | 2.350 / 0.0314 / 0.863 / 11.344 | 2.296 / 0.0185 / 0.889 / 10.712 | 2.010 / 0.0162 / 0.851 / 10.449 |
| CatBoost | raw | 2.135 / 0.0008 / 0.880 / 10.275 | 1.951 / 0.0006 / 0.900 / 9.868 | 1.791 / 0.0014 / 0.886 / 9.072 |
| CatBoost | sparse2 | 2.216 / 0.0074 / 0.849 / 10.589 | 2.082 / 0.0085 / 0.870 / 10.427 | 1.861 / 0.0085 / 0.870 / 9.671 |
| CatBoost | delay7d | 2.414 / 0.0235 / 0.824 / 11.531 | 2.206 / 0.0182 / 0.844 / 10.912 | 1.940 / 0.0184 / 0.846 / 10.184 |

## F2相对F0/F1的按电芯配对MAE变化

括号内为按电芯bootstrap 95% CI（基线减F2，周）。改善电芯比例表示cell MAE降低比例；受害列是F2比基线差>2周的电芯数/61。

| 模型比较 | 臂 | 平均改善（周）[95% CI] | MAE改善电芯 | 受害>2周 |
|---|---|---:|---:|---:|
| HGB F2−F0 | raw | 0.243 [-0.004, 0.484] | 60.7% | 2/61 |
| HGB F2−F1 | raw | 0.243 [-0.006, 0.485] | 67.2% | 2/61 |
| HGB F2−F0 | sparse2 | 0.307 [0.029, 0.564] | 65.6% | 2/61 |
| HGB F2−F1 | sparse2 | 0.271 [0.000, 0.533] | 67.2% | 2/61 |
| HGB F2−F0 | delay7d | 0.341 [0.073, 0.605] | 70.5% | 2/61 |
| HGB F2−F1 | delay7d | 0.287 [0.009, 0.557] | 63.9% | 1/61 |
| CatBoost F2−F0 | raw | 0.344 [0.123, 0.580] | 70.5% | 0/61 |
| CatBoost F2−F1 | raw | 0.160 [-0.068, 0.400] | 62.3% | 0/61 |
| CatBoost F2−F0 | sparse2 | 0.355 [0.130, 0.586] | 68.9% | 1/61 |
| CatBoost F2−F1 | sparse2 | 0.221 [0.006, 0.456] | 55.7% | 0/61 |
| CatBoost F2−F0 | delay7d | 0.474 [0.251, 0.703] | 72.1% | 0/61 |
| CatBoost F2−F1 | delay7d | 0.266 [0.054, 0.502] | 62.3% | 0/61 |

F2的容量曲线在两模型与三臂的MAE均优于F0；相对F1，raw臂两个模型CI均跨0，sparse2/delay7d的改善较一致，但数值幅度小（约0.22–0.29周）。这是一项开发集保存预测的增量信号，不足以单凭MAE确立新的退化动力学机制。HGB raw F2−F0和F2−F1的95% CI轻微跨零；应按不确定增益报告。改善电芯比例较高不消除少数电芯的退化，尤其HGB有1–2个cell受到>2周伤害。

## 同F2：HGB与CatBoost权衡

下表差值为HGB减CatBoost；对MAE/Brier/IS80，正值表示CatBoost较低/较好；coverage为HGB减CatBoost，正值表示HGB覆盖较高。

| 臂 | 指标 | HGB | CatBoost | HGB−CatBoost [paired bootstrap 95% CI] |
|---|---|---:|---:|---:|
| raw | MAE周 | 1.794 | 1.791 | 0.003 [-0.136, 0.159] |
| raw | event Brier | 0.00043 | 0.00145 | -0.00102 [-0.00243, 0.00003] |
| raw | coverage | 0.894 | 0.886 | 0.008 [-0.010, 0.028] |
| raw | IS80周 | 9.251 | 9.072 | 0.179 [-0.134, 0.506] |
| sparse2 | MAE周 | 1.931 | 1.861 | 0.070 [-0.076, 0.224] |
| sparse2 | event Brier | 0.00679 | 0.00852 | -0.00173 [-0.00341, -0.00029] |
| sparse2 | coverage | 0.867 | 0.869 | -0.002 [-0.023, 0.019] |
| sparse2 | IS80周 | 10.002 | 9.671 | 0.331 [0.087, 0.588] |
| delay7d | MAE周 | 2.010 | 1.940 | 0.070 [-0.065, 0.214] |
| delay7d | event Brier | 0.01625 | 0.01837 | -0.00213 [-0.00601, 0.00080] |
| delay7d | coverage | 0.851 | 0.846 | 0.005 [-0.015, 0.024] |
| delay7d | IS80周 | 10.449 | 10.184 | 0.265 [-0.061, 0.593] |

Head-to-head没有单一全胜者：F2的CatBoost在sparse2的IS80较优，但其事件Brier较差；raw臂MAE近乎相同，HGB事件Brier较低而CatBoost IS80数值较低（区间均跨0）；delay7d的MAE/IS80差异区间跨0，事件Brier方向仍偏向HGB但不确定。报告信息增益时需保留概率与区间校准权衡，不能只挑MAE。

## 科学解释与边界

这次复算支持“已观测RPT电压曲线特征对当前冻结动态基线有小幅预测增量”的开发集结论，特别在稀疏/延迟臂相对F0可见；F2对F1的额外收益更有限。结果不能归因于独立的新机理：当前F2仅是已有容量RPT历史摘要增加Q(V)/dQdV固定网格，没有运行时序信号，也未证明latent SOH状态或未来容量路径的因果/物理结构。不能外推到C4、部署或独立确认，也不能把source-observed阈值事件改称潜在EOL。适当结论是保留候选特征层级进行独立协议确认，同时把跨模型概率校准、受害电芯和noT边界作为主要限制。

## 可复现材料

- recompute.py：仅hash校验允许文件、重算行指标和cell macro/paired bootstrap的脚本；0 fits / 0 model loads。
- row_metrics_recomputed.csv：22,590行重算值。
- independent_results.json：全部模型、臂、增量比较和head-to-head指标。
