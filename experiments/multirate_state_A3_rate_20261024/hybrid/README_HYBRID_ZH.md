# HYBRID：A3 机理状态 + F2 最强树的混合实验（hybrid/）

问题：A3_full 与最强树（HGB on F2 98 维缓存 + h）点精度打平。把 A3 的 per-query
滤波后验作为附加特征喂给 HGB，能否显著超过原版最强树？（机理状态的信息增量）

## 设计冻结
- 模型 A `baseline_F2_hgb`：HGB on [F2 缓存 98 | h]（99 列）。管线复现门：
  dev 3579 键 cell-macro MAE 与冻结 F2 原版 CSV（nextcap18-9e7d9cb1c67f）
  相对差 ≤ GO 门限（0.05），超差即 FAIL（0 输出、0 登记）。
- 模型 B `hybrid_F2_A3state`：HGB on [F2 98 | h | 9 维机理特征]（108 列）：
  state_D, state_ell, state_R, state_P00, state_P11, state_P22, pred_mean_ah,
  (pred_mean_ah − visible_capacity_min_ah)/gap_weeks（隐含斜率）, pred_sd_ah。
- 机理特征 = 冻结 A3 walker（AsOfWalkerA3 + a3_infer._row_for_query 状态记录
  语义 + _advance_horizon 持有近期控制策略），即 C3 CSV 背后的同一计算；
  checkpoint = run1_fits/model_state_dict_full.pt（sha 4b46c929…），0 再训练。
- σ：树管线 OOF 纪律——两折 cell-isolated（V18 hgb_models._two_cell_folds
  语义：RandomState(42).shuffle(sorted) 后奇偶分折；注意不是 sha256 排序，
  那是 ext/a2 惯例），σ=√(逐 cell 均方 OOF 残差的 cell 平均)。
  HGB 超参冻结：max_iter=150, max_leaf_nodes=15, l2=1, random_state=42，
  sample_weight=1/cell 行数。预算 6 fits（A 2 折+全量，B 同）。
- 评估：dev 3579 键面板（= F2 原版 CSV 同键，已验证与 ext 推导逐键一致）。
  MAE/RMSE(=√cell 均方 MSE 均值)/NLL/cov90/over20/over50，cell-macro+pooled、
  分臂+总体；5000 次 cell 配对 bootstrap（seed 20261024）：B vs A、B vs F2
  原版（全面板）；B vs A3_full、B vs ENS3（三 seed 等权混合、矩匹配，
  compare_ens3 语义；A3 公共键面板）。

## 接口事实（与任务书差异，如实报告）
1. C3 CSV（dev 侧）只覆盖 3579 键中的 2326（A3 查询网格更稀：anchor 去重+
   0.20Ah 可见阈值），另有 17 个 A3 独有键。因此 dev 侧特征由 walker 在
   完整树面板上重算（dev cells 经 a2_infer.load_cell/_build_dev_specs 按
   cohort+data/cycling/RPT manifests 加载，与 C3 GO 同路径）；C3 CSV 用作
   公共键完整性交叉校验（状态列位级一致门）+ A3_full/ENS3 参考预测。
2. 训练侧 6498 键 = ext 冻结规则推导，已验证 ⊆ 树缓存（0 缺失）；join 全配。
3. 任务书 code pin 列表中的 a3_targets.py 不存在（A3 复用 a2_targets.py）；实际 import 闭包 13 文件见 GO 模板。

## 运行与输出
`python hybrid_aug.py`（合成自检，默认：15 检查、≥12 GO 变异拒绝）；
`python hybrid_aug.py --run-train --go GO_HYBRID_....json`（真实 6 fits）。
输出 runs/<run>/：{baseline_F2_hgb,hybrid_F2_A3state}/predictions_c3.csv（树
CSV 同列，panel 列 F2/HYB）、fit_report.json、compare_summary.json、receipt；
成功后登记 request_id 到 consumed_gos.jsonl。

## GO 模板（签发时补 issued_utc/request_id/code_sha256 的实际值）
```json
{
  "status": "APPROVED", "allow_fit": true, "allow_C4": false,
  "scope": "HYBRID TRAIN/FIT: F2 cache + A3 mechanistic state -> HGB, 6 fits, dev 3579 panel, 0 C4",
  "request_id": "HYBRID_F2_A3STATE_20261024_RUN1",
  "owner_thread_id": "01a15c3a-1a06-7d61-8517-27b70b246183",
  "issued_utc": "<签发时刻>", "seed": 42, "device": "cpu", "threads": 4,
  "max_runtime_seconds": 14400, "fits_in_this_go": 6,
  "model_config": {"hgb": {"max_iter": 150, "max_leaf_nodes": 15, "l2_regularization": 1, "random_state": 42, "early_stopping": false}},
  "replication_gate": {"f2_mae_cell_macro_rel_tol": 0.05},
  "code_sha256": {"hybrid_aug.py": "<sha>", "a3_calibrate.py": "<sha>", "ext_baselines.py": "<sha>", "a3_infer.py": "<sha>", "a3_model.py": "<sha>", "a3_train.py": "<sha>", "a2_infer.py": "<sha>", "a2_prep.py": "<sha>", "a2_targets.py": "<sha>", "a2_fastdata.py": "<sha>", "a2_model.py": "<sha>", "a2_train.py": "<sha>", "a2_fixtures.py": "<sha>"},
  "checkpoint": {"path": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/run1_fits/model_state_dict_full.pt", "sha256": "4b46c92902925c972ac6f5fbbf80396c915a93c6bca1ac07547a78772c6b5820"},
  "assets": {
    "prep_manifest": {"path": "/home/yndx/zxk/rul/experiments/multirate_state_A2_20261022/prep_v2_20261022/manifest.json", "sha256": "<sha>"},
    "prep_npz": {"path": "/home/yndx/zxk/rul/experiments/multirate_state_A2_20261022/prep_v2_20261022/a2_prep_sequences.npz", "sha256": "<sha>"},
    "rpt_manifest": {"path": "/home/yndx/zxk/rul/reports/multisource_20261021_signals/all188_rpt_features_v1/manifest.json", "sha256": "f431eb082f09f455e8edec1cc62e944e116cea1a97544ca3b18abe5d6064c255"},
    "cohort": {"path": "/home/yndx/zxk/rul/reports/isu_ilcc_capacity_probe_20261020_root/cohort.json", "sha256": "4469f7f5b6eb8c26a522fa46c4291ec6d03d98e7ae5c20ce7ae77e835b849ae0"},
    "data_manifest": {"path": "/home/yndx/zxk/rul/reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json", "sha256": "68f53dc481dfc212896658a9bcb69780b5ed7285d853cc870a4002ae658726e1"},
    "cycling_manifest": {"path": "/home/yndx/zxk/rul/reports/multisource_20261021_signals/cycling_all188_feature_manifest.json", "sha256": "51e4c87fc7e59cee6afe2bb79fabb9e72070d98ca6d457c124c553d0b05018cb"},
    "f2_train_features_npz": {"path": "/home/yndx/zxk/rul/experiments/multisource_factorial_20261021/run2_clocksafe/train_features.npz", "sha256": "9c3794064e64d3b0a437c3fde82e7f8a423aa983d37621d0808088bbcbbf9a15"},
    "f2_development_features_npz": {"path": "/home/yndx/zxk/rul/experiments/multisource_factorial_20261021/run2_clocksafe/development_features.npz", "sha256": "dc0a84ffc091be064f1d7e00963270c8279ffb7505be17057e4a61449664ea3f"},
    "f2_train_rows": {"path": "/home/yndx/zxk/rul/experiments/multisource_factorial_20261021/run2_clocksafe/train_rows.jsonl", "sha256": "1b081d57a41bcc12697fae0b9742b5e734290dd1aac0b3b0e82591abd1489537"},
    "f2_development_rows": {"path": "/home/yndx/zxk/rul/experiments/multisource_factorial_20261021/run2_clocksafe/development_rows.jsonl", "sha256": "bb64c57a1bc09df34b18f5f4c486ddb152d50a4f73b385e235899af54bddd5e3"},
    "f2_feature_schema": {"path": "/home/yndx/zxk/rul/experiments/multisource_factorial_20261021/run2_clocksafe/feature_schema.json", "sha256": "11e50dcf7e2b1f2ae9e05597b6159472ee34d3d0bedb0223531bea69b01fafa7"},
    "f2_reference_csv": {"path": "/home/yndx/zxk/rul/experiments/trajectory_multisource_nextcap_20261021/runs/nextcap18-9e7d9cb1c67f/predictions_c3.csv", "sha256": "0c69390362cba156cd20158ce760d23c837d73963b3dd53bac0539649e364410"},
    "c3_seed42_csv": {"path": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/c3_eval_a3_20261024_run2/predictions_c3_a3.csv", "sha256": "9aa4871d498d2ab7dcb847ad0ca0647c33fc7a72be7344a7b346d513a4bf523b"},
    "c3_seed43_csv": {"path": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/c3_eval_seed43_20261024/predictions_c3_a3.csv", "sha256": "139497ad8d7e46825c91fd9e886ef52b1171e077a1f713fcdd3ea6b984341a3f"},
    "c3_seed44_csv": {"path": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/c3_eval_seed44_20261024/predictions_c3_a3.csv", "sha256": "d67e4a82b2941e9b89beb0e7ca88cde2b17d9a98bfa630d823c72102625e479b"}
  },
  "panel_contract": {"n_train_queries": 6498, "n_dev_keys": 3579, "arms": ["raw", "sparse2", "delay7d"], "n_train_cells": 125, "n_dev_specs": 63},
  "consumed_registry": "/home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl",
  "out_dir": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/hybrid/runs/<fresh>",
  "receipt_path": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/hybrid/receipts/<fresh>.json"
}
```
（prep_manifest/prep_npz 与 code_sha256 的 sha 在签发时用 sha256sum 补齐。）
