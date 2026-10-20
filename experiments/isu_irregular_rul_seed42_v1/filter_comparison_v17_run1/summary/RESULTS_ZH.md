# ISU 不规则 RUL 开发结果汇总

仅从保存的预测 CSV 计算；不读取原始曲线、checkpoint，不拟合或推理。端点是 source-observed 首次完成 RPT 的 Q≤0.20 Ah；属于 event-observed 开发描述，不是潜在真实 EOL 或独立确认。锁定队列读取数按 runner 协议为 0；物理电芯串行身份尚未核验。

先在每电芯内平均预测起点，再对电芯等权平均。NaN/失败不删除不修补；若任一电芯的该指标无效，总体对应均值保留 NaN，同时报告有效/无效电芯数。严重高估是预测均值减目标大于4周。

参照在每个 arm 内从 group_frozen、hgb_early_health、hgb_dynamic、aft_dynamic 四个简单模型中按最低电芯宏平均 MAE 事后选择；若任一基线含无效 MAE，则不宣称最强参照已确定。配对差为待比较模型减参照的共同电芯 MAE；正值更差。seed42 电芯配对bootstrap 95%区间。

## 每臂模型主表

| arm | model | cells | MAE weeks | >4w rate | cells any >4w | IS80 | coverage | Brier4 | Brier12 | update ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| delayed7d | aft_dynamic | 61 | 5.951 | 0.1631 | 0.3934 | 31.52 | 0.7953 | 0.1097 | 0.1264 | 0.1603 |
| delayed7d | cdf_fusion | 61 | 3.369 | 0.09824 | 0.2131 | 16.83 | 0.7903 | 0.1284 | 0.09789 | 1.122 |
| delayed7d | filter_scalar | 61 | 3.339 | 0.1161 | 0.459 | 17.69 | 0.8962 | 0.1029 | 0.1016 | 1.13 |
| delayed7d | group_frozen | 61 | 4.02 | 0.1311 | 0.1311 | 29.87 | 0.3279 | 0.1949 | 0.1262 | 0.02157 |
| delayed7d | gru_dynamic | 61 | 4.102 | 0.1045 | 0.2459 | 25.76 | 0.5124 | 0.1618 | 0.1129 | 0.2972 |
| delayed7d | hgb_dynamic | 61 | 3.378 | 0.1186 | 0.4262 | 17.87 | 0.8921 | 0.1034 | 0.1018 | 1.109 |
| delayed7d | hgb_early_health | 61 | 6.198 | 0.3841 | 0.5246 | 28.56 | 0.7869 | 0.2042 | 0.1717 | 0.9364 |
| raw | aft_dynamic | 61 | 5.746 | 0.1447 | 0.3443 | 30.69 | 0.814 | 0.09677 | 0.1197 | 0.1608 |
| raw | cdf_fusion | 61 | 3.238 | 0.07903 | 0.2131 | 16.03 | 0.8179 | 0.1235 | 0.09258 | 1.124 |
| raw | filter_scalar | 61 | 3.084 | 0.0943 | 0.3607 | 17.15 | 0.9302 | 0.09316 | 0.09063 | 1.143 |
| raw | group_frozen | 61 | 4.02 | 0.1311 | 0.1311 | 29.87 | 0.3279 | 0.1949 | 0.1262 | 0.02205 |
| raw | gru_dynamic | 61 | 4.078 | 0.1169 | 0.2459 | 25.5 | 0.5077 | 0.1631 | 0.1118 | 0.3201 |
| raw | hgb_dynamic | 61 | 3.094 | 0.09148 | 0.377 | 17.27 | 0.9234 | 0.09361 | 0.09022 | 1.111 |
| raw | hgb_early_health | 61 | 6.198 | 0.3841 | 0.5246 | 28.56 | 0.7869 | 0.2042 | 0.1717 | 0.9387 |
| sparse2rpt | aft_dynamic | 61 | 5.952 | 0.1513 | 0.377 | 31.74 | 0.8185 | 0.1032 | 0.1215 | 0.1591 |
| sparse2rpt | cdf_fusion | 61 | 3.298 | 0.07327 | 0.1639 | 16.5 | 0.7953 | 0.1269 | 0.09574 | 1.122 |
| sparse2rpt | filter_scalar | 61 | 3.197 | 0.1059 | 0.3443 | 17.14 | 0.9081 | 0.1 | 0.09529 | 1.131 |
| sparse2rpt | group_frozen | 61 | 4.02 | 0.1311 | 0.1311 | 29.87 | 0.3279 | 0.1949 | 0.1262 | 0.02155 |
| sparse2rpt | gru_dynamic | 61 | 4.137 | 0.1187 | 0.2787 | 25.79 | 0.5165 | 0.1583 | 0.114 | 0.2217 |
| sparse2rpt | hgb_dynamic | 61 | 3.205 | 0.1087 | 0.3607 | 17.47 | 0.9024 | 0.1007 | 0.09513 | 1.105 |
| sparse2rpt | hgb_early_health | 61 | 6.198 | 0.3841 | 0.5246 | 28.56 | 0.7869 | 0.2042 | 0.1717 | 0.9382 |

## 配对差异
- delayed7d / aft_dynamic vs hgb_dynamic: delta MAE=2.5731356562935632, CI95=[0.624692960218396, 5.048026451911711], 胜/平/负=24/0/37, status=OK。
- delayed7d / cdf_fusion vs hgb_dynamic: delta MAE=-0.008725898813257839, CI95=[-0.3363704678656303, 0.31799006439909927], 胜/平/负=33/0/28, status=OK。
- delayed7d / filter_scalar vs hgb_dynamic: delta MAE=-0.03918410484229637, CI95=[-0.09922444063850078, 0.018539596077953715], 胜/平/负=31/0/30, status=OK。
- delayed7d / group_frozen vs hgb_dynamic: delta MAE=0.6426608229711204, CI95=[-0.03755628986460035, 1.3366125679455474], 胜/平/负=28/0/33, status=OK。
- delayed7d / gru_dynamic vs hgb_dynamic: delta MAE=0.724064380420009, CI95=[-0.02708353021539805, 1.4863214087037189], 胜/平/负=28/0/33, status=OK。
- delayed7d / hgb_early_health vs hgb_dynamic: delta MAE=2.8201122287675626, CI95=[1.7688512951897235, 3.9183996343036123], 胜/平/负=19/0/42, status=OK。
- raw / aft_dynamic vs hgb_dynamic: delta MAE=2.6514534656417155, CI95=[0.5853962665935224, 5.237525303454422], 胜/平/负=25/0/36, status=OK。
- raw / cdf_fusion vs hgb_dynamic: delta MAE=0.14431505262864677, CI95=[-0.17247138220264263, 0.46278487552717656], 胜/平/负=30/0/31, status=OK。
- raw / filter_scalar vs hgb_dynamic: delta MAE=-0.01023342639369819, CI95=[-0.06483568766198199, 0.04381588467510585], 胜/平/负=31/0/30, status=OK。
- raw / group_frozen vs hgb_dynamic: delta MAE=0.9262598510147175, CI95=[0.3001764651029801, 1.568272507996276], 胜/平/负=25/0/36, status=OK。
- raw / gru_dynamic vs hgb_dynamic: delta MAE=0.9834206254738638, CI95=[0.29818178995518085, 1.7033419588143253], 胜/平/负=26/0/35, status=OK。
- raw / hgb_early_health vs hgb_dynamic: delta MAE=3.1037112568111596, CI95=[2.078001685910837, 4.1633825841656105], 胜/平/负=19/0/42, status=OK。
- sparse2rpt / aft_dynamic vs hgb_dynamic: delta MAE=2.747207353655458, CI95=[0.6956747338466996, 5.712884939511765], 胜/平/负=22/0/39, status=OK。
- sparse2rpt / cdf_fusion vs hgb_dynamic: delta MAE=0.09306968527976896, CI95=[-0.2409070803791802, 0.41530135971960597], 胜/平/负=29/0/32, status=OK。
- sparse2rpt / filter_scalar vs hgb_dynamic: delta MAE=-0.008162169530605431, CI95=[-0.06799482040153887, 0.04603973185653661], 胜/平/负=29/0/32, status=OK。
- sparse2rpt / group_frozen vs hgb_dynamic: delta MAE=0.8153677493451753, CI95=[0.1881859314325498, 1.487251777768401], 胜/平/负=26/0/35, status=OK。
- sparse2rpt / gru_dynamic vs hgb_dynamic: delta MAE=0.9320894955061549, CI95=[0.2537579633953111, 1.6566473661060979], 胜/平/负=25/0/36, status=OK。
- sparse2rpt / hgb_early_health vs hgb_dynamic: delta MAE=2.992819155141617, CI95=[1.9222373658963545, 4.045599881778134], 胜/平/负=18/0/43, status=OK。

逐电芯结果见 cell_metrics.csv；配对样本和bootstrap见 paired_differences.csv。本汇总不改变训练协议，也不构成模型选择后的独立性能声明。
