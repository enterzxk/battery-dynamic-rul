# A3 C3 推断入口 a3_infer.py 使用说明（2026-10-24）

四臂 A3 状态 (D, ℓ, R) 的 C3 as-of 推断入口。默认无参 = 合成自检；真实推断必须持
APPROVED、未消费的精确哈希 GO。自检：0 拟合、0 payload、0 checkpoint、0 GO 创建/消费。

## 用法

```bash
cd /home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024
PY=/home/yndx/miniconda3/envs/a40_env/bin/python
$PY a3_infer.py --self-check --append-log SELF_CHECK_LOG.txt   # 合成自检（默认）
$PY a3_infer.py --go <GO.json> --threads 8 --verbose           # 真实推断（GO 门控）
```

拒绝路径不写任何文件、不读数据、不消费 GO；成功后把 request_id 登记进
`experiments/state/consumed_gos.jsonl`（append-only，防重复消费）。

## GO 字段清单（全部必填，缺一拒绝）

| 字段 | 要求 |
|---|---|
| status | 恒等于 `"APPROVED"` |
| allow_inference / allow_fit / allow_train / allow_C4 | true / false / false / false |
| owner_thread_id | `01a15c3a-1a06-7d61-8517-27b70b246183` |
| data_scope | `C3_source63_development_only_no_C4_no_raw` |
| device / no_grad / max_rss_gb | `cpu` / `true` / 数值（默认 2.0，超限即失败） |
| max_runtime_seconds | 60..21600 |
| expected_cell_count | 63（C3 开发 cell） |
| request_id | 非空，且不在 consumed_gos.jsonl |
| registry | （如给）必须等于规范 registry 路径 |
| code_sha256 | 10 个文件：a3_infer/a3_model/a3_train.py + a2_infer/prep/targets/fastdata/model/train/fixtures.py |
| cohort / data_manifest / cycling_manifest / rpt_manifest | 各 {path(绝对), sha256}，四项全 pin |
| checkpoints | 恰好 full/noRateUpdate/time/noEll 四臂，各 {path, sha256}；若给出可选 `checkpoint_subset` 则只需恰好钉子集内各臂（见文末追加节） |
| output_dir / receipt_path | 绝对路径，且必须全新（fresh） |
| query_contract | （如给）必须与 A2 冻结契约逐键一致 |

## 输出（output_dir 内）

- `predictions_c3_a3.csv`：列结构与 a2_infer 相同（query_id、arm、model_key、
  24 维 control、next-jump、4 个固定视界），状态列扩为 3 维：`state_ell`、
  `state_P02`、`state_P12`、`state_P22`，新增 `model_ell_state`；每查询 × 4 臂。
- `summary.json`：cell-macro NLL / RMSE=√(mean_cell MSE) / MAE / cov90 /
  over_20mAh / over_50mAh（|误差|>0.020 / 0.050 Ah 占比），分 next_jump
  （overall/by_arm/by_model/by_arm_model）、rpt_innovations、fixed_horizons。
- `receipt.json`：状态、elapsed、RSS 峰值、0 fits / 0 C4、四臂 checkpoint
  sha256 记录、GO 登记（registration）。

## 与 a2_infer 的差异

1. **四臂** full/noRateUpdate/time/noEll（A2 三臂）；ℓ 经 D 相关间接更新，
   noRateUpdate 置零 ℓ 增益，noEll 退化为 dD=c·dt 点质量。
2. **Walker** 携带冻结线性化 (a,b)（a3_model 段引擎语义），查询切分按精确
   仿射半群组合；A2 无 ℓ、无此携带量。自检证明 walker == 逐查询重滤波
   （96 状态 max|dm|=max|dP|=0）且 == a3_model 引擎与 NLL trace（0 误差）。
3. **float64 滤波**：checkpoint(float32) 严格加载后 `model.double()`。
4. GO 门控新增 no_grad=true、max_rss_gb（超限中止）、request_id 成功后登记；
   status 用 `APPROVED`（沿用 A3 训练 GO 惯例），四清单全 pin（A2 的 cycling 可省）。
5. 代码哈希集合是真实 import 闭包（A3 树无 a3_targets.py/a3_fastdata.py，
   a2_* 模块按 import 复用——与 a3_model.py/a3_train.py 的既有做法一致）。
6. 查询网格、阈值跳过、视界容差逐键复用 a2_infer 的冻结代码对象（非重写）。

## 追加：checkpoint_subset —— 单臂/子集推断（R2 阶段 A，2026-10-24）

新增**可选** GO 字段 `checkpoint_subset`，支持只对部分 A3 臂的 checkpoint 做
推断（数据效率实验的子集 checkpoint，如
`run_frac_f25_seed42/model_state_dict_full.pt`）。

- **省略（或显式 null）**：行为与此前完全一致——`checkpoints` 必须恰好钉
  full/noRateUpdate/time/noEll 四臂。**向后兼容**：既有四臂 GO 全部照常工作，
  summary 顶层新增 `checkpoint_subset: null`（纯增量字段）。
- **给出时**：必须是非空列表，元素为已知 A3 臂键（经 `_canonical_model_key`
  别名归一，如 `a3_full`→`full`），顺序自由、不得重复；本实验用 `["full"]`。
  - `checkpoints` 必须恰好等于子集：缺子集臂、多出子集外臂、空对象均拒绝。
  - 若 GO 同时给 `arms` 字段，必须与 `checkpoint_subset` 一致（别名归一后比较）。
  - 拒绝情形：空列表 / 非列表 / 未知臂 / 全未知 / 重复 / checkpoints 缺失、
    多余、为空 / arms 与 subset 不一致或仍写四臂。自检 `subset_gate`：
    4 条正路径（plain、别名、缺省、显式 null）+ **10 条拒绝变异**。
- **行为**：只为子集内的臂装载 checkpoint 并产出预测行与指标；CSV 的
  `model_key` 列格式不变（取值范围限于子集）；summary.json 的 `by_model` /
  `by_arm_model` / `fixed_horizons` / `model_arms` / `checkpoints` /
  `n_models` 只含子集臂；顶层新增 `checkpoint_subset` 记录本次臂集。
  receipt 同步（`go_info.checkpoint_subset`、四臂字样改为实际臂集）。
- **等价性**：自检 `subset_pipeline` 证明——仅 full 的子集运行的 full-arm
  预测行与四臂参考运行**逐字节一致**（确定性合成模型、n_rows == n_queries），
  且四臂默认路径的全部既有断言不变。其余门控（代码哈希闭包、registry、
  query_contract、no_grad、RSS 上限、fresh 路径、成功后登记）完全不变。
- **既有怪癖（本次未改动，保持四臂行为逐字节兼容）**：
  `summary.metrics.rpt_innovations.by_model` 的组键实为
  `("rpt_model", 查询臂, 模型臂)`，但条目的 `model_key` 字段装的是查询臂
  （k[1]）；按模型臂聚合请用 `next_jump.by_model` / `by_arm_model`。
  子集模式下该列表同样只含子集模型参与的组（每组数 = 查询臂数）。
- **frac 推断 GO**：在四臂 GO 模板上加 `"checkpoint_subset": ["full"]`，并把
  `checkpoints` 缩为 full 一项（path+sha256 指向
  `run_frac_f25_seed42/model_state_dict_full.pt` 等）；request_id 用
  `A3_FRAC_INFER_20261024_RUN1`。注意：本文件修改后哈希变化，frac GO 的
  `code_sha256.a3_infer.py` 必须钉**新**哈希（见 SELF_CHECK_LOG.txt 最新
  自检头部的 code_sha256 行）。
