# README — a3_train_frac.py（A3 分数池训练入口 / R2 数据效率 阶段 A）

状态：IMPLEMENTED + SYNTHETIC SELF-CHECK（0 真实拟合、0 payload、0 checkpoint、0 GO）。
训练执行必须由主控签发**新的 exact-hash frac GO**；本入口不创建、不消费任何 GO。

## 1. 目的

检验"机理先验换取样本效率"（R2 阶段 A）：把训练池从全部 125 cell 缩到
25% / 50%，在**同一协议、同一臂（full）**下重训 A3_full，与强树在同分数池
上的退化速度比较。本文件是唯一新增的训练入口；`a3_train.py`、`a3_model.py`
字节冻结，未做任何修改。

## 2. 安全模型（与 a3_train.py 同构）

- **默认自检**：无参数（或 `--self-check`）只跑合成 fixtures——合成张量 +
  临时目录里的合成 GO/manifest 替身；不读 payload（`data/`、`reports/`、
  `prep_inputs/`、`prep_v2`）、不读任何 checkpoint（含 `run1_fits/`）、不写
  checkpoint 文件、不创建/不消费 GO。唯一落盘：向 `SELF_CHECK_LOG.txt`
  **追加**（append-only，`--no-log-append` 可关闭）+ 系统临时目录的 fixtures。
- **训练路径 `--run-train`**：仅在接受一个 APPROVED、fresh、exact-hash 的
  frac GO 后才动；成功后经 `a3_train.register_consumed_go` 把 request_id
  **追加**进登记表 `experiments/state/consumed_gos.jsonl`（append-once、
  重复拒绝、坏行 fail-closed），同一 GO 永远无法二次消费。
- **CPU 锁**：复用 `a3_train.SharedCpuLock`（两把共享项目 CPU 锁，协议
  "CPU 8 线程 + 两把锁"不变）。
- **数据**：仅 PREP v2 紧凑 npz 缓存（`load_prepared_fast`），从不读
  raw/C3/C4 payload；manifest 的 path+sha 由 GO 钉死。

## 3. 子集语义（冻结设计）

记 PREP manifest 装载后的 125 cell 为池（100 内部 train + 25 内部 val，
run 路径强校验该形状，不满足即 REFUSED，exit 6）。设 `--fraction f`、
`--fraction-seed s`（默认 42）：

1. **池排序**：`all = sorted(125 个 cell id)`。
2. **无放回抽样**：`idx = numpy.random.default_rng(s).choice(125, size=k,
   replace=False)`（对**排序后 id 列表的索引**抽样），`chosen = sorted(all[i]
   for i in idx)`，`k = round(f × 125)` → f=0.25/0.5/1.0 时 k = 31/62/125。
   同 seed 必得同子集；f=1.0 时 chosen 恒等于全池排序结果。
3. **选择期划分**（在 chosen 内部，按原 100/25 归属）：
   - `sel_val = chosen ∩ 原25val`，`sel_train = chosen ∩ 原100train`；
   - **回退规则（设计决定，冻结）**：若 `|sel_val| < 3`（含为空），则
     **延续同一个 rng 流**（紧接第 2 步抽样之后）做 `permutation(k)`，留出
     前 `max(1, round(0.20 × k))` 个作为选择期 val，其余（原 train 与原 val
     一视同仁）作为选择期 train。阈值 3 的理由：cell-macro NLL 在 <3 个
     cell 上方差过大，早停信号不可靠。回退**只影响 selection 阶段**。
4. **最终 refit**：用**全部抽中 cell**（k 个），控制标准化器在全部抽中
   cell 上重新拟合，抽样 seed `--refit-seed`（默认 43）——与 R1
   （selection 冻结步数 → 全量 refit）协议同构，只是"全量"换成"全抽中"。
5. 每次训练 = 2 fits（selection + refit），单臂 full，一个 GO、一个
   request_id、登记一次。

实现落点：`select_fraction_cells()`（纯函数，进 fit_report 的记录）、
`build_frac_data_view()`（浅拷贝 FastA2Data，事件张量共享、split 属性指向
选择子集；**原对象绝不改写**）、`frac_train_one_arm()`（逐字复用
`a3_train.train_one_arm`，仅把返回报告里的 refit_scope 标签改为
`frac_pool` 并附加分数记账字段——唯一有意的偏差，训练行为零改动）。

**确定性边界**：上述 rng 语义在锁定环境（a40_env，numpy 1.26.4 的
`default_rng`/PCG64）下成立；换 numpy 大版本重跑需复核流兼容性。

## 4. 复用与冻结清单

| 来源 | 复用方式 |
|---|---|
| `a3_train.py`（字节冻结） | `train_one_arm`（内部驱动 `_train_steps`：窗口 BPTT、早停、冻结步数 refit）、`validate_go_a3` 的门控模式、`SharedCpuLock`、`register_consumed_go`/`load_consumed_request_ids`/`request_id_is_fresh`、`DEFAULT_CONSUMED_REGISTRY`、`_a3_scope_text` |
| `a3_model.py`（字节冻结） | `ARM_CONFIGS`、`VERSION`（经 a3_train 间接）；臂=full |
| `a2_fastdata.py`（原样 import） | `load_prepared_fast`、`fit_control_standardizer`（refit 标准化器经 train_one_arm 使用；自检里对其做逐位交叉核对）、`synthetic_fast_data`（自检） |
| `a2_train.py`（原样 import） | `validate_go` 基础门（HERE 临时指向 A3 目录的复用模式，与 `validate_go_a3` 完全一致；fail-closed） |
| `a3_fixtures.py`（自检内 import） | `OpenAuditor`、`_is_forbidden_path`（no-payload 审计；另加 `run1_fits`、`checkpoints` 规则） |

无任何 monkey-patch；`a2_train.HERE` 的临时切换仅在 gate 校验期间、
`finally` 恢复，与 `a3_train.validate_go_a3` 的既有模式逐字同构。

## 5. GO 契约（frac 专用）

`validate_go_frac()` = 基础门（APPROVED、allow_fit/allow_train、未消费、
scope 含 A3 与 TRAIN/FIT、代码哈希逐文件核对、max_steps）+ 以下 frac 检查：

| GO 字段 | 要求 |
|---|---|
| `code_sha256` | 必须同时钉 `a3_model.py`、`a3_train.py`、`a3_train_frac.py` 三者 |
| `arms` | **恰为 `["full"]`**（`--arm` 亦只接受 full） |
| `refit_scope` | **必须为 `"frac_pool"`**（all125 的 GO 会被本门拒绝；frac GO 也会被 `validate_go_a3` 拒绝——两门互斥，自检专项验证） |
| `fraction` | ∈ {0.25, 0.5, 1.0} 且与命令行 `--fraction` 一致 |
| `fraction_seed` | 与命令行 `--fraction-seed` 一致 |
| `prepared_manifest` + `prepared_manifest_sha256` | path+sha 与 `--manifest` 一致 |
| `out_dir` | 必须不存在（fresh；`--out-dir` 覆盖同样要 fresh） |
| `fits_in_this_go` | ≥ 2（单臂 selection+refit） |
| `request_id` | 不得出现在 consumed-GO 登记表（每次 fresh） |
| `seed`/`window_events`/`burn_in`/`burn_in_events`/`batch_cells` | 与命令行一致（expect 契约，同 a3_train） |

**GO 模板**（主控签发时替换哈希与路径；命令行须用完全相同的
fraction/fraction_seed/window/seed 值）：

```json
{
  "status": "APPROVED",
  "allow_fit": true,
  "allow_train": true,
  "scope": "A3 FRAC TRAIN/FIT: fraction-pool data-efficiency run (R2 stage A), arm full only, selection on the fraction selection subset + frozen-steps refit on the chosen fraction pool, exactly 2 fits in this GO",
  "request_id": "A3_FRAC_F25_SEED42_20261024_RUN1",
  "owner_thread_id": "<主控线程 id>",
  "issued_utc": "<UTC>",
  "issued_by": {"controller": "<主控会话>"},
  "code_sha256": {
    "a3_model.py": "<sha256>",
    "a3_train.py": "<sha256>",
    "a3_train_frac.py": "<sha256>"
  },
  "max_steps": 3000,
  "arms": ["full"],
  "fraction": 0.25,
  "fraction_seed": 42,
  "seed": 42,
  "refit_seed": 43,
  "batch_cells": 8,
  "window_events": 256,
  "burn_in": "exact",
  "burn_in_events": 128,
  "lr": 0.001,
  "weight_decay": 0.0001,
  "val_every": 50,
  "patience": 6,
  "threads": 8,
  "refit_scope": "frac_pool",
  "fits_in_this_go": 2,
  "prepared_manifest": "/home/yndx/zxk/rul/experiments/multirate_state_A2_20261022/prep_v2_20261022/manifest.json",
  "prepared_manifest_sha256": "3749221779d7becfdd90525077b3b8a89766a6503face6619d36e8f271dac012",
  "out_dir": "/home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024/run_frac_f25_seed42",
  "data_scope": "PREP v2 compact npz cache only; no raw archive, no C3/C4 payload, no old checkpoint reads",
  "registry": "/home/yndx/zxk/rul/experiments/state/consumed_gos.jsonl",
  "post_run": "fit_report_full.json + model_state_dict_full.pt + consumption_record.json in out_dir"
}
```

三份代码的当前 sha256 见 `SELF_CHECK_LOG.txt` 尾部最近一次自检的
`code_sha256` 行（每次自检自动记录）。

## 6. 用法

```bash
cd /home/yndx/zxk/rul/experiments/multirate_state_A3_rate_20261024
PY=/home/yndx/miniconda3/envs/a40_env/bin/python

# 自检（默认；结果追加 SELF_CHECK_LOG.txt）
$PY a3_train_frac.py

# 训练（GO 签发后；f=0.25 示例，f=0.5/1.0 换 fraction、request_id、out_dir 再签新 GO）
$PY a3_train_frac.py --run-train \
    --go GO_A3_FRAC_F25_20261024_RUN1.json \
    --manifest /home/yndx/zxk/rul/experiments/multirate_state_A2_20261022/prep_v2_20261022/manifest.json \
    --arm full --fraction 0.25 --fraction-seed 42
```

退出码：0 成功；3 GO 校验失败；4 无 manifest；5 out_dir 已存在；6 manifest
池形状违反冻结设计（非 125 = 100 + 25）。

## 7. 产物（out_dir 内）

- `fit_report_full.json`：除 a3_train 全部字段（history、selected_steps、
  best_val_nll、两级 standardizer 等）外，**新增**：`fraction`、
  `fraction_seed`、`n_pool_cells`、`n_chosen_cells`、`selected_cell_ids`
  （抽中 cell id 列表）、`selection_train_cell_ids`/`selection_val_cell_ids`、
  `n_selection_train`、`n_selection_val`、`selection_val_source`
  （`original_val_split` | `rng_holdout_20pct`）、
  `selection_val_fallback_used`、`refit_n_cells`、`refit_scope="frac_pool"`、
  `refit_scope_note`。
- `model_state_dict_full.pt`、`consumption_record.json`（含 fraction 字段）。
- 登记表追加一行 `{"finished_utc", "go_sha256", "request_id"}`。

## 8. 自检项（默认全部运行；追加 SELF_CHECK_LOG.txt）

1. `fraction_sampling_determinism` — 同 seed 同子集（全记录逐字典相等）、
   k=31/62/125、排序+唯一、异 seed 子集不同；
2. `fraction_full_pool_identity` — f=1.0 抽中=全池、选择划分=原 100/25、无回退；
3. `selection_split_original_and_fallback` — 原划分分支、回退分支（rng 续流
   逐位复现）、边界 2/3 个原 val cell 切换分支、划分互斥且并为 chosen；
4. `frac_data_view_isolation` — 视图共享张量、独享 split、原对象零改写；
5. `fraction_smoke_train_loop` — 合成 6 cell、f=0.5、**2 步**窗口训练冒烟
   （仅合成张量），refit 标准化器与 `fit_control_standardizer(pool)` 逐位相等、
   refit seed 43；
6. `frac_report_fields_and_refit_scope` — fit_report 必备字段与
   refit_scope=frac_pool 强制；
7. `frac_go_accepts_wellformed` — 合成良构 GO 0 拒绝；
8. `frac_go_separated_from_all125_gate` — frac GO 被 `validate_go_a3` 拒绝
   （点名 refit_scope）：两门互斥；
9. `frac_go_refuses_mutations` — **24 类变异全部拒绝**（三类代码哈希+缺钉、
   status、allow 旗标、consumed 标记、scope 缺 A3、refit_scope all125/缺失、
   arms 多臂/非列表、fraction 不符/非法/缺失、fraction_seed 不符/缺失、
   request_id 重用、manifest sha/path、out_dir 非 fresh、max_steps、window
   契约、fits 预算）；
10. `consumed_registry_append_and_duplicate_refusal` — append-once、重复拒绝、
    坏行 fail-closed（仅临时路径）；
11. 全局 `open()` 审计 — 0 个禁止路径（禁则 = a3_fixtures 规则 + `run1_fits`
    + `checkpoints`）。

## 9. 边界与注意

- 若某 cell 无 scored RPT：训练采样器自动丢弃该 cell（a2_fastdata 既有
  行为），验证宏平均将其剔除；若回退出的选择 val 全体无 scored RPT，早停
  得到 NaN 信号 → selected_steps=1 兜底。真实 PREP v2 池 125 cell 均含
  scored RPT，此路径不会触发。
- f=0.25 时若抽中原 val cell ≥ 3，则选择 val 用原 val 归属（不回退）；
  是否回退完全由数据决定并在 fit_report 里留痕（`selection_val_source`），
  跨 fraction 比较时须读该字段。
- 本入口**不做**任何 C3/C4 评估、不读任何旧 checkpoint；比较由主控另行
  签 GO。
