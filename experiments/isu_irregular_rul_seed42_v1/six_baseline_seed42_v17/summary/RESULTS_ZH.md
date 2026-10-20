# ISU 不规则 RUL 开发结果汇总

仅从保存的预测 CSV 计算；不读取原始曲线、checkpoint，不拟合或推理。端点是 source-observed 首次完成 RPT 的 Q≤0.20 Ah；属于 event-observed 开发描述，不是潜在真实 EOL 或独立确认。锁定队列读取数按 runner 协议为 0；物理电芯串行身份尚未核验。

先在每电芯内平均预测起点，再对电芯等权平均。NaN/失败不删除不修补；若任一电芯的该指标无效，总体对应均值保留 NaN，同时报告有效/无效电芯数。严重高估是预测均值减目标大于4周。

参照在每个 arm 内从 group_frozen、hgb_early_health、hgb_dynamic、aft_dynamic 四个简单模型中按最低电芯宏平均 MAE 事后选择；若任一基线含无效 MAE，则不宣称最强参照已确定。配对差为待比较模型减参照的共同电芯 MAE；正值更差。seed42 电芯配对bootstrap 95%区间。

## 每臂模型主表

| arm | model | cells | MAE weeks | >4w rate | cells any >4w | IS80 | coverage | Brier4 | Brier12 | update ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| delayed7d | aft_dynamic | 61 | 5.951 | 0.1631 | 0.3934 | 31.52 | 0.7953 | 0.1097 | 0.1264 | 0.1603 |
| delayed7d | cdf_fusion | 61 | 3.369 | 0.09824 | 0.2131 | 16.83 | 0.7903 | 0.1284 | 0.09789 | 1.122 |
| delayed7d | group_frozen | 61 | 4.02 | 0.1311 | 0.1311 | 29.87 | 0.3279 | 0.1949 | 0.1262 | 0.02157 |
| delayed7d | gru_dynamic | 61 | 4.102 | 0.1045 | 0.2459 | 25.76 | 0.5124 | 0.1618 | 0.1129 | 0.2972 |
| delayed7d | hgb_dynamic | 61 | 3.378 | 0.1186 | 0.4262 | 17.87 | 0.8921 | 0.1034 | 0.1018 | 1.109 |
| delayed7d | hgb_early_health | 61 | 6.198 | 0.3841 | 0.5246 | 28.56 | 0.7869 | 0.2042 | 0.1717 | 0.9364 |
| raw | aft_dynamic | 61 | 5.746 | 0.1447 | 0.3443 | 30.69 | 0.814 | 0.09677 | 0.1197 | 0.1608 |
| raw | cdf_fusion | 61 | 3.238 | 0.07903 | 0.2131 | 16.03 | 0.8179 | 0.1235 | 0.09258 | 1.124 |
| raw | group_frozen | 61 | 4.02 | 0.1311 | 0.1311 | 29.87 | 0.3279 | 0.1949 | 0.1262 | 0.02205 |
| raw | gru_dynamic | 61 | 4.078 | 0.1169 | 0.2459 | 25.5 | 0.5077 | 0.1631 | 0.1118 | 0.3201 |
| raw | hgb_dynamic | 61 | 3.094 | 0.09148 | 0.377 | 17.27 | 0.9234 | 0.09361 | 0.09022 | 1.111 |
| raw | hgb_early_health | 61 | 6.198 | 0.3841 | 0.5246 | 28.56 | 0.7869 | 0.2042 | 0.1717 | 0.9387 |
| sparse2rpt | aft_dynamic | 61 | 5.952 | 0.1513 | 0.377 | 31.74 | 0.8185 | 0.1032 | 0.1215 | 0.1591 |
| sparse2rpt | cdf_fusion | 61 | 3.298 | 0.07327 | 0.1639 | 16.5 | 0.7953 | 0.1269 | 0.09574 | 1.122 |
| sparse2rpt | group_frozen | 61 | 4.02 | 0.1311 | 0.1311 | 29.87 | 0.3279 | 0.1949 | 0.1262 | 0.02155 |
| sparse2rpt | gru_dynamic | 61 | 4.137 | 0.1187 | 0.2787 | 25.79 | 0.5165 | 0.1583 | 0.114 | 0.2217 |
| sparse2rpt | hgb_dynamic | 61 | 3.205 | 0.1087 | 0.3607 | 17.47 | 0.9024 | 0.1007 | 0.09513 | 1.105 |
| sparse2rpt | hgb_early_health | 61 | 6.198 | 0.3841 | 0.5246 | 28.56 | 0.7869 | 0.2042 | 0.1717 | 0.9382 |

## 配对差异
- delayed7d / aft_dynamic vs hgb_dynamic: delta MAE=2.5731356562935632, CI95=[0.624692960218396, 5.048026451911711], 胜/平/负=24/0/37, status=OK。
- delayed7d / cdf_fusion vs hgb_dynamic: delta MAE=-0.008725898813257839, CI95=[-0.3363704678656303, 0.31799006439909927], 胜/平/负=33/0/28, status=OK。
- delayed7d / group_frozen vs hgb_dynamic: delta MAE=0.6426608229711204, CI95=[-0.014555420253371894, 1.2790682905656623], 胜/平/负=28/0/33, status=OK。
- delayed7d / gru_dynamic vs hgb_dynamic: delta MAE=0.724064380420009, CI95=[-0.012821116779691463, 1.5267644279085761], 胜/平/负=28/0/33, status=OK。
- delayed7d / hgb_early_health vs hgb_dynamic: delta MAE=2.8201122287675626, CI95=[1.7346689576528103, 3.894923358773925], 胜/平/负=19/0/42, status=OK。
- raw / aft_dynamic vs hgb_dynamic: delta MAE=2.6514534656417155, CI95=[0.601101909315644, 5.460383361161051], 胜/平/负=25/0/36, status=OK。
- raw / cdf_fusion vs hgb_dynamic: delta MAE=0.14431505262864677, CI95=[-0.1549388948382675, 0.47547548521782085], 胜/平/负=30/0/31, status=OK。
- raw / group_frozen vs hgb_dynamic: delta MAE=0.9262598510147175, CI95=[0.2559412419684135, 1.5758824533954614], 胜/平/负=25/0/36, status=OK。
- raw / gru_dynamic vs hgb_dynamic: delta MAE=0.9834206254738638, CI95=[0.2653360019343724, 1.758658486100613], 胜/平/负=26/0/35, status=OK。
- raw / hgb_early_health vs hgb_dynamic: delta MAE=3.1037112568111596, CI95=[2.087919534968467, 4.223978793878451], 胜/平/负=19/0/42, status=OK。
- sparse2rpt / aft_dynamic vs hgb_dynamic: delta MAE=2.747207353655458, CI95=[0.6229614037684837, 5.4726835287468285], 胜/平/负=22/0/39, status=OK。
- sparse2rpt / cdf_fusion vs hgb_dynamic: delta MAE=0.09306968527976896, CI95=[-0.23925873636536807, 0.41619053380637594], 胜/平/负=29/0/32, status=OK。
- sparse2rpt / group_frozen vs hgb_dynamic: delta MAE=0.8153677493451753, CI95=[0.1526052299113854, 1.4758797934373653], 胜/平/负=26/0/35, status=OK。
- sparse2rpt / gru_dynamic vs hgb_dynamic: delta MAE=0.9320894955061549, CI95=[0.2513875799207254, 1.6931608820953816], 胜/平/负=25/0/36, status=OK。
- sparse2rpt / hgb_early_health vs hgb_dynamic: delta MAE=2.992819155141617, CI95=[1.9794513408978691, 4.077273212431923], 胜/平/负=18/0/43, status=OK。

逐电芯结果见 cell_metrics.csv；配对样本和bootstrap见 paired_differences.csv。本汇总不改变训练协议，也不构成模型选择后的独立性能声明。
