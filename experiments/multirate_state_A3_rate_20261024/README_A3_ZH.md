# A3：个体退化速率状态（ℓ）状态空间模型 — 实现说明（2026-10-24）

协议：`PROTOCOL.md`（DESIGN_ONLY 冻结设计）。本目录只含实现与合成自检；**0 次真实拟合、
0 次 payload 读取、0 次 checkpoint 读取、0 次 GO 创建/消费**。真实训练必须等主控签发
exact-hash GO。

## 文件

| 文件 | 内容 |
|---|---|
| `a3_model.py` | 三态模型 (D, ℓ, R)、四臂配置、精确仿射半群离散化、3×3 Joseph 更新、段式 replay 引擎 |
| `a3_train.py` | GO 门控训练入口（默认=合成自检）、consumed-GO 登记表、selection→冻结步数→全 125 refit |
| `a3_fixtures.py` | 17 个合成 fixture（含 open() 审计包装、GO 拒绝变异、训练结构合成冒烟） |
| `SELF_CHECK_LOG.txt` | 服务器自检输出（UTC 头 + 版本） |

## 模型（单位纪律：σ 一律是标准差；方差=σ²；D、ℓ 无量纲，速率 1/周，R、y 单位 Ah）

- 状态 x=(D, ℓ, R)：dD=softplus(ℓ)dt（均值漂移恒正）；dℓ=−κ(ℓ−μ_θ(u))dt+σ_ℓdW₁；
  dR=−λRdt+σ_RdW₂；y=Q_ref·exp(−D)+R+ε，σ_y=softplus(σ̃_y)。
- κ/σ_ℓ/λ/σ_R/σ_y 为全局 softplus 标量参数（下限 1e-8 防浮点下溢）；**唯一样本相关项是 μ_θ(u)**：
  与 A2 相同的标准化 24 维 past-only 循环控制汇总+缺失掩码（48 维输入，无 dt 列）。
- 初始先验显式（anchor 处 D=R=0；ℓ~N(−5.8, 1²)，softplus(−5.8)≈3e-3/周，与 A2 d_rate 初值一致）。
- **离散化=冻结线性化的精确仿射半群**：每个"测量更新之间的段"用段首后验均值冻结
  b=sigmoid(ℓ̄)、a=softplus(ℓ̄)−b·ℓ̄，把 dD=(a+bℓ)dt 的线性 SDE **闭式精确积分**（含分段常数 μ 的
  均值路径扫描与积分-OU 协方差闭式，κT<1e-3 时用级数防灾难性消去）。冻结系数下"一步==拆两步"
  到 float64 舍入（<1e-10）；(a,b) 作为**携带状态**只在测量更新后刷新，故 batch 拆分、窗口 exact
  burn-in 均不改变单 cell 滤波（fixture 证明）。

## 四臂（共享参数化；行为开关）

| 臂 | μ_θ(u) | ℓ 测量更新 | 说明 |
|---|---|---|---|
| full | 网络 | 是（经 y 对 exp(−D) 的依赖，H_ℓ=0，间接更新） | 完整机制 |
| noRateUpdate | 网络 | 否（K_ℓ 置零后再 Joseph；只更新 D,R） | 消融速度后验 |
| time | 常数 μ₀=mu_base | 是 | 消融循环驱动（嵌套于 full） |
| noEll | —（ℓ≡softplus(c) 点质量，ℓ 先验方差结构为 0） | 只更新 D,R | dD=c·dt 精确；A2 型退化控制臂 |

## 与 A2 的差异（复用清单）

- 复用不改：`a2_fastdata`（FastA2Data/WindowSampler/WindowBatch/load_prepared_fast/
  fit_control_standardizer/合成数据/`_affine_scan`/`_chunk_by_length`）、`a2_targets.hash_file`、
  `a2_train.validate_go`（base guard）。
- 必然新写：三态滤波核（`_event_scalars_a3/_segment_advance/_run_events_a3/
  _burn_in_state_a3/replay_windows_a3/replay_cells_a3/eval_cell_macro_a3`）——A2 核硬编码 2 态。
- GO 门：`validate_go_a3` = a2_train.validate_go（把 a2_train.HERE 临时指向 A3 目录、剔除唯一一条
  "does not name A2"投诉，fail-closed）+ A3 增查（pin a3_model.py/a3_train.py hash、manifest
  path+sha、fresh out-dir、request_id 未在 consumed_gos.jsonl、refit_scope=="all125"、四臂在内、
  fits_in_this_go≥8、窗口契约一致）。
- **发现的 A2 缺陷（A2 只读未改，需主控裁决）**：`a2_fastdata._burn_in_state` 返回按 chunk
  （长度排序）顺序拼接的结果，未逆置换回原 batch 顺序——混合 burn 长度的 batch 会把 burn-in 状态
  分配错行（服务器合成数据验证：输出行严格等于 sorted-order 至 1e-17）。A3 的
  `_burn_in_state_a3` 已显式 scatter-back。

## 训练结构（真实 GO 后执行，本 worker 0 次执行）

`python a3_train.py --run-train --go <GO> --manifest <prep_v2 manifest>`：selection（manifest 内部
100 train cell，val 25 cell，seed 42）→ 冻结 best 步数 → refit（全部 125 cell、标准化全 125 拟合、
采样 seed 43）。默认 `--arm all` 单进程跑四臂（2 fits×4=8），成功后向
`experiments/state/consumed_gos.jsonl` append 一行 `{"request_id","go_sha256","finished_utc"}`
（不存在则创建；重复 request_id 拒绝）。fit_report 记录 n_fit_cells/refit_scope/selected_steps/
go_sha256/arm。CPU 8 线程 + 两把 flock 共享锁（state/a3_cpu_lock_{0,1}.lock）。

## 自检

`python a3_train.py`（无参数）= 17 fixtures + 全局 open() 审计；RESULT: OK (17 passed / 0 failed)
为通过。任何真实数据路径（rul/data、rul/reports、rul/prep_inputs、prep_v2 缓存、真实
consumed_gos.jsonl、任何 npz）在自检中被打开即失败。

## GO 模板字段清单（主控签发用；本 worker 不建 GO）

```json
{"status": "APPROVED", "allow_fit": true, "allow_train": true,
 "scope": "A3 TRAIN/FIT: ...",                      // 必须含 "A3" 与 "TRAIN"/"FIT"
 "request_id": "a3-fit-<date>-<arm-scope>",          // 不得出现在 consumed_gos.jsonl
 "code_sha256": {"a3_model.py": "<sha>", "a3_train.py": "<sha>"},
 "max_steps": 3000,
 "arms": ["full", "noRateUpdate", "time", "noEll"],  // 四臂必须齐全
 "refit_scope": "all125",                            // 必须恰为 "all125"
 "seed": 42, "refit_seed": 43, "batch_cells": 8, "window_events": 256,
 "burn_in": "exact", "burn_in_events": 128,
 "lr": 0.001, "weight_decay": 0.0001, "val_every": 50, "patience": 6, "threads": 8,
 "fits_in_this_go": 8,
 "prepared_manifest": "<prep_v2_20261022/manifest.json 绝对路径>",
 "prepared_manifest_sha256": "37492217...",           // 3749221779d7becfdd90525077b3b8a89766a6503face6619d36e8f271dac012
 "out_dir": "<不存在的绝对路径>",                      // 必须全新
 "issued_utc": "...", "issued_by": {...}}
```
