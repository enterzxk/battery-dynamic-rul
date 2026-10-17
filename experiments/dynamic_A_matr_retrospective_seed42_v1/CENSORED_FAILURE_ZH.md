# 删失电池误差诊断（仅已有预测）

{
  "at_utc": "2026-10-17T15:46:45.902009+00:00",
  "status": "COMPLETE_EXISTING_PREDICTION_FAILURE_DIAGNOSIS",
  "question": "Are dominant errors merely remote author-tail extrapolation, or already incompatible with processed-record observed followup?",
  "training_author_EOL_range": [
    147.0,
    1834.0
  ],
  "top2_share_of_total34_equal_cell_absolute_error": 0.4367584749342024,
  "mean_censored_underprediction_lower_bound_A1": 175.25164425117285,
  "interpretation": "Underprediction lower bound uses only recorded survival through last observed cycle; actual crossing is unobserved. This is retrospective processed-record evidence, not a new target or train feature. No removal/reweighting/refit. Short author extrapolation gaps in top outliers would rule out long extrapolation distance as the sole cause, not validate labels or generator.",
  "new_fits": 0,
  "optimizer_steps": 0,
  "test_access": false,
  "binary_reads": 0,
  "predictions_sha256": "b336f3b69219d9f8c1a4044e68bb8e6b9a365b7227673d722118e3b750ca0c22",
  "next_action": "Inspect existing train/validation early-prefix feature support for the two dominant surviving outliers using text only; no fitting or changing primary cohort/labels."
}

| 电池 | 观测末循环 | 作者EOL | 外推差 | A1作者MAE | 已观测存活给出的低估误差下界 |
|---|---:|---:|---:|---:|---:|
| MATR_b1c2 | 2235 | 2237 | 2 | 1381.393 | 1379.393 |
| MATR_b3c38 | 1933 | 1932 | -1 | 883.866 | 884.866 |
| MATR_b3c11 | 815 | 815 | 0 | 219.669 | 0.000 |
| MATR_b3c34 | 1156 | 1156 | 0 | 146.483 | 146.483 |
| MATR_b1c43 | 649 | 649 | 0 | 140.548 | 0.000 |

下界=max(0,末次观测循环-k-预测RUL)，先origin平均再电池等权。末次观测只用于回顾性诊断，不加入训练输入、不充当真实EOL；未观测事件不能算精确RUL误差。不得删除离群电池美化主要指标。实际v11生成器和完整物理身份限制保持。

补充标签边界：MATR_b3c38作者EOL=1932，但完整文本记录存活至1933且nominal crossing未观测；存在1循环边界不一致，需核已有标签算法的外推/取整语义。不得把作者标签当精确真实EOL，不修改或删除既有结果；下一动作优先核此边界，再看训练特征支持。
