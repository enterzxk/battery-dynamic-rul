# A2 状态机制原型（2026-10-22）— 实现、数学、假设与自检

目录：`experiments/multirate_state_A2_20261022/`
状态：**仅实现 + 合成 unit fixture；0 次拟合、0 次优化步、0 payload/checkpoint 读取。**
本目录是独立保留的新原型，不覆盖、不修改 A1（`experiments/multirate_state_20261021/`）与任何既有实验目录，
也不修改先前的 A2 静态草案目录 `experiments/multirate_state_A2_20261021/`（该目录保持原样）。

---

## 1. 这次要修什么（来自 A1 的实测诊断）

`reports/multisource_20261021_A_independent/RESULTS_ZH.md` 的机制诊断给出三点：

1. **锚点错**：A1 用标称 0.25 Ah 作容量基，实测首个 RPT 约 0.28 Ah，读出差约 0.03 Ah；
   状态本身 state-only RMSE 0.0314 Ah，而 readout 校正后 0.0098 Ah —— 误差被读出旁路吸收。
2. **σ 语义错**：A1 把网络输出 `softplus(-6)=0.0025` 当作**方差**，于是 σ≈0.05 Ah，
   相对真实 RPT 创新（0.032–0.039 Ah）过大，卡尔曼增益极小：每 query 都更新，但状态修正范数仅
   0.0024–0.0043 Ah，协方差 trace 只收缩 2.8%–4.2%。
3. **dt 进网络**：A1 把 `log1p(dt)` 拼进速率网络输入，速率随网格步长变化，精确半群/网格不变性不成立。

A2 只针对这三点重设计状态机制，不扩大为"再训久一点"。

---

## 2. 模型数学

### 2.1 状态与容量映射（state-only，无读出旁路）

状态均值 `m = [D, R]`，协方差 `P ∈ R^{2×2}`：

```
Q(t) = Q_ref · exp(−D(t)) + R(t)
```

- `D`：无量纲对数损伤（D 增大 → 容量下降）。
- `R`：可逆容量偏移（Ah），OU 过程，允许回弹。
- `Q_ref`：该 cell **首个"已到达"的有效 RPT 容量**，一次性锚定（见 §3），不是标称 0.25 Ah。
- **没有**任何 query 上下文网络 / F0 读出 / 均值旁路：`capacity_moments()` 只接受 `(m, P, Q_ref)`。
  因此容量误差不能再被 readout 吸收。

### 2.2 连续时间转移（输入不含 dt）

对每个"已完成且已到达"的循环记录，其 24 维控制特征 `x` 与缺失 mask 送入速率网络（输入维度 48，**无 dt 列**）：

```
r_D(x)   = softplus(b0 + f0(x))                 [D / 周]
σ_D(x)   = softplus(b1 + f1(x))                 [D / √周]      ← 标准差
λ(x)     = softplus(b2 + f2(x)) + 1e-6          [1 / 周]
R_eq(x)  = 0.15 · tanh(f3(x))                   [Ah]           ← 结构性上界
σ_R(x)   = softplus(b3 + f4(x))                 [Ah / √周]     ← 标准差
```

恒定控制下推进 Δt：

```
D' = D + r_D · Δt
R' = α·R + (1−α)·R_eq ,        α = exp(−λ·Δt)
P' = F P Fᵀ + Q ,              F = diag(1, α)
Q  = diag( σ_D² · Δt ,  σ_R² · (1 − e^{−2λΔt}) / (2λ) )
```

**精确仿射半群（网格不变性）**：速率与 σ 只依赖控制、不依赖 Δt，且

- D 漂移可加：`r_D·Δt1 + r_D·Δt2 = r_D·(Δt1+Δt2)`；
- OU 均值：`α(Δt1)α(Δt2) = α(Δt1+Δt2)`，且 `(1−α2)R_eq + α2(1−α1)R_eq = (1−α1α2)R_eq`；
- OU 积分方差可加：`V(Δt1) + α2²·V(Δt2) = V(Δt1+Δt2)`，其中 `V(Δt)=σ_R²(1−e^{−2λΔt})/(2λ)`。

所以把一段区间拆成 1 步、3 步或 97 步，均值与协方差逐元素相同（float64 下误差 < 1e−12）。
A 的 `log1p(dt)` 输入会破坏这一性质；A2 用 fixture 固定住。

### 2.3 σ 语义（2026-10-22 主控更正后的口径）

**网络输出的 σ 是标准差，单位 Ah；方差一律由 `σ²` 显式平方得到，单位 Ah²。**
高斯对数密度用 `log σ`，即 `0.5·log(2πσ²) = log σ + 0.5·log(2π)`，不再对 σ 二次平方。

- 观测噪声：`σ_obs = softplus(obs_sigma_raw)`，初值 **2e−3 Ah**；`obs_variance() = σ_obs² ≈ 4e−6 Ah²`。
- 断言带：σ ∈ [1e−3, 1e−2] Ah，方差 ∈ [1e−6, 1e−4] Ah²（fixture 强制）。
- A1 的病因正是反向解读：把 `softplus(-6)=0.0025` 当**方差**，σ=0.05 Ah。A2 明确禁止：
  fixture 断言 `|方差 − 0.0025| > 1e−4`，即 0.0025 处于 σ 带、绝不能被当成方差。
- 过程噪声同理：`σ_D`、`σ_R` 是标准差，进入协方差时平方一次。
- 输出字典字段自带单位后缀：`observation_sigma_ah`、`observation_var_ah2`、
  `innovation_sd_ah`、`innovation_var_ah2`、`capacity_var_before/after_ah2`。

### 2.4 容量观测与顺序创新 NLL

```
Q̂ = Q_ref·e^{−D} + R
H = [ −Q_ref·e^{−D} ,  1 ]
latent var = H P Hᵀ                    （Ah²，物理容量不确定度）
S = H P Hᵀ + σ_obs²                    （Ah²）
ν = y − Q̂
NLL = ½·(ν²/S + log S + log 2π)  ≡  ½·z² + log σ_tot + ½·log 2π
```

测量更新用 Joseph 形式：`K = P Hᵀ / S`，`m ← m + Kν`，
`P ← (I−KH)P(I−KH)ᵀ + K σ_obs² Kᵀ`，并做对称化。物理不确定度只报 `H P Hᵀ`（Ah²）；
**不把 `trace(P)` 当作容量不确定度**（D 无量纲、R 是 Ah，混合单位）。

### 2.5 训练目标

**顺序 RPT 创新 NLL**：对每个 cell，按来源时间顺序重放其已到达记录；每个"锚点之后"的有效 RPT
在**更新前**的预测分布上计一次 NLL，然后才做测量更新。损失 = 各 cell 内部平均 NLL 的
**cell-macro 平均**（每节电池等权，长序列不支配），锚点读数不计分（避免同一读数被条件化后又重复计分）。

不是把状态误差甩给 readout —— 本模型没有 readout。

### 2.6 三种消融（共享同一套参数化）

| 臂 | `use_cycle` | `use_rpt` | 含义 |
|---|---|---|---|
| `full` (A2_full_F2) | True | True | 循环控制推进 + RPT 测量更新 |
| `time` (A2_time_only) | False | True | 只用时间项（控制全 mask），保留 RPT 更新 |
| `noRPTupdate` (A2_no_RPT_update) | True | False | 有锚点、有循环推进，但**不做** RPT 测量更新 |

三臂用同一 `build_model(seed)`、同一 cell 划分、同一优化器/步数选择规则；
同一 seed 初始化逐张量相同（fixture 断言）。`noRPTupdate` 仍然对每个 RPT **预测并计分**，
只是从不更新（这是它的可辨识性含义：没有 RPT 校正时的预测似然）。

`use_cycle` 与 `use_rpt` 两个开关独立，四种组合都可运行；三种正式臂取
"从 full 每次只去掉一个机制"的 one-factor-at-a-time 设计（见 §8 歧义 A）。

---

## 3. Qref 锚定与迟到/迟滞协议

1. **锚点**：在 `cutoff`（query 或数据截断）之前**已到达**、有效、容量有限的 RPT 中，
   取**到达时间最早**者；并列按来源 stop、再按记录下标。其容量即 `Q_ref`，其来源 stop 即时间原点。
2. **一次性**：锚定后 `Q_ref` 不再改变（后续 RPT 只更新状态，不改 Q_ref）。
3. **锚点不计分**：该读数定义 Q_ref，不再作为创新重复计分。
4. **pre-anchor 排除**：来源 stop 早于锚点 stop 的记录（含迟到到达的）属于锚点前历史，不参与重放，
   避免负时间传播；计数保留（`n_rpt_pre_anchor_excluded` 等）。
5. **as-of 门控**：query 时刻重放只用 `source ≤ query` **且** `arrival ≤ query` 的记录。
   来源早、到达晚的记录被排除并计数（`n_late_arrival_excluded`）。
6. **锚点前无预测**：锚点尚未到达时不存在 `Q_ref`，`replay_asof` 返回
   `available=False`，不产生容量预测（A1 用标称 0.25 填这个空档，A2 明确不做）。
7. **未来不注入**：query 之后不做任何真实输入/检查计划假设。append 未来记录（或改变未来控制值）后，
   query 时刻状态与预测**逐元素完全相同**（fixture 用精确相等断言）。

### 未来预测策略

`forecast_capacity(model, seq, query, horizon_weeks, grid_steps)`：

- 先用 as-of 前缀得到 filtered state；
- 未来 horizon 用 **query 前最后一条已完成循环记录的 24 维控制与 mask，held constant** 推进；
- 没有可见循环时控制全缺失；
- `horizon` 是日历周，不是"下一个 RPT 计划"（真实检查计划未知）；
- `grid_steps` 只影响计算网格，不影响结果（fixture 断言 1 步 ≡ 43 步）。

query 与最后一条已到达事件之间的未观测区间，用**零控制（仅时间项）**推进；held-recent 控制只用于
未来 horizon。理由：避免把未观测到的操作注入 filtered state（见 §8 歧义 E）。

---

## 4. 训练/验证划分与标准化

- **按 cell 分组**，不是按 index 区间：`split_cells_by_hash(cell_ids, n_val, seed)`
  对 `sha256(f"{seed}:{cell}")` 排序，前 25 节作内部选择集，其余 100 节作内部拟合集。
  断言两集合不相交、并集完整、与输入顺序无关、不是 `ids[:100]`。
- **标准化统计量只来自训练 cell**：`TrainControlStandardizer.fit(train_sequences)`
  只累加 mask=1 的循环控制值，按维计算均值与总体标准差（ddof=0）。
- **存为 buffer**：`apply_to_model` 写入 `control_mean` / `control_scale` 两个 buffer，
  随 `state_dict` / `.to(device)` 一起走。
- **常量尺度=1 时跳过**：std ≤ 1e−8、未观测维或非有限值 → scale 强制为 1，并计数
  `n_constant_scale_one_skipped`；fixture 断言常数列 scale 恰为 1、均值等于常数。
- 验证 cell 的极端值不进入统计量（fixture 用 1e6 的验证离群值验证）。

---

## 5. 与 A1 的差异（逐条）

| 维度 | A1（`multirate_state_20261021/mechanism.py`） | A2（本目录） |
|---|---|---|
| 容量基 | 标称 `nominal_capacity_ah=0.25` | 每 cell 首个已到达有效 RPT 容量 `Q_ref`，一次性锚定 |
| 均值路径 | 状态 + `0.10*tanh(readout(context_74))` | **只有** `Q_ref e^{−D}+R`，无 readout |
| 观测噪声 | `log_rpt_noise=-6` 被当方差（σ≈0.05 Ah） | `σ_obs≈2e−3 Ah`，方差 `σ²≈4e−6 Ah²` |
| 速率网络输入 | `[x, mask, log1p(dt)]` | `[x, mask]`，**无 dt** |
| 过程噪声 | `q_d·dt`、`q_r(1−α²)`（无明确单位语义） | `σ_D²·dt`、`σ_R²(1−e^{−2λΔt})/(2λ)`（精确 OU 积分） |
| 网格不变性 | 被 dt 输入破坏 | 精确成立（fixture） |
| 初始先验 | `diag(0.02², 0.02²)` | 显式 `D0=R0=0`，`Var(D0)=(5e−3)²`，`Var(R0)=(5e−3 Ah)²` |
| 训练目标 | next-RPT 监督 + F0 上下文特征 + readout | 顺序 RPT 创新 NLL，无 readout |
| 未来输入 | 时间断口日历传播 | held-recent 控制（past-only）+ 零控制补间隙 |
| 曲线头 F3 | 可选 `curve_observation_head` | 无（先把状态机制立住） |
| 消融 | 4 臂（含 F3） | 3 臂，共享一套参数化 |

---

## 6. 合成 fixture 覆盖点

`a2_fixtures.py`，14+2 = **16 个 fixture**，全部只吃随机张量/伪造记录：

| fixture | 证明什么 |
|---|---|
| `dt_not_an_input` | 速率网络输入维度 = 2×24（无 dt 列）；D 漂移对 Δt 精确线性 |
| `grid_invariance` | 1 步 = 不等长 3 步 = 97 步；forecast 1 步 = 43 步（均值/协方差） |
| `sigma_is_std_variance_is_square` | σ 是 Ah 标准差、方差=`σ²`；σ 形式 NLL ≡ 方差形式 NLL；0.0025 不被当方差；过程噪声 `σ²` 只平方一次 |
| `qref_anchor` | Q_ref 取首个**已到达**有效 RPT；无效/迟到/pre-anchor 处理；一次性锚定；锚点前无预测；最早到达优先 |
| `no_future_input_leakage` | 追加未来记录后 query 状态/预测逐元素不变；source<q<arrival 的迟到记录被门控 |
| `cell_grouped_split` | 125 节 → 100/25，按 hash 分组、不相交、顺序无关、非 index 区间 |
| `standardizer_buffers` | 统计量仅来自训练 cell、存 buffer、常量维 scale=1、验证离群值不影响 |
| `capacity_variance_hph` | `HPHᵀ` 解析式一致；Joseph 后对称半正定；容量方差收缩 |
| `d_can_decrease_after_update` | 漂移非负，但高斯更新**可以**让 D 下降 → 不声称路径不可逆 |
| `no_readout_bypass` | 无 readout/上下文网络；`Q=Q_ref e^{−D}+R` 精确成立 |
| `replay_matches_manual_loop` | 批量 padded 重放 ≡ 逐 cell 顺序循环（NLL 与终态） |
| `three_arms_share_model` | 一套参数化三开关；同 seed 初始化逐张量相同（2794 参数） |
| `noRPT_arm_still_scored` | noRPT 臂每个 RPT 仍预测并计分、从不校正、容量方差从不收缩（回归 fixture） |
| `four_flag_combinations` | 两开关独立，四种组合可运行且互不相同 |
| `gradients_flow` | 合成 batch 反向一次（无优化器步），速率网络与 σ 参数梯度有限非零 |
| `prior_is_explicit` | 初始先验均值/方差显式、固定、不来自未来 |

---

## 7. 自检与复现

```bash
cd /home/yndx/zxk/rul/experiments/multirate_state_A2_20261022
/home/yndx/miniconda3/envs/a40_env/bin/python -m py_compile a2_model.py a2_targets.py a2_fixtures.py a2_train.py
/home/yndx/miniconda3/envs/a40_env/bin/python a2_train.py --self-check   # 仅 fixtures
/home/yndx/miniconda3/envs/a40_env/bin/python a2_train.py --dry-run     # fixtures + 三臂合成前向探针
```

实际输出见 `SELF_CHECK_LOG.txt`（含 py_compile、fixture 全量输出、文件 SHA256、python/torch 版本）。

训练路径（**本次未运行**）：

```bash
python a2_train.py --run-train --go /path/APPROVED_GO.json --manifest /path/PREP/manifest.json --arm full
```

`--run-train` 会先校验：GO 状态 APPROVED、未消费、allow_fit=true、scope 含 A2+TRAIN/FIT、
`code_sha256` 与本目录代码逐文件匹配、请求步数 ≤ GO 上限、arm 在 GO 允许列表内；
不通过即拒绝（exit 3/4），**不读取 payload、不写 GO 回执、不消费 GO、不改任何全局开关**。
数据入口只接受 PREP 产出的紧凑 npz（schema 见 `a2_train.load_prepared_sequences` 文档字符串），
且校验 `prepared_npz_sha256` 与 cell 划分。

---

## 8. 协议歧义与最小假设（需要主控确认）

**A. `time` 臂的定义（最重要）**
任务原文写"time（只用时间项，无 RPT 更新）"，但 A1 与 `multirate_state_A2_20261021/DESIGN_PROTOCOL_ZH.md` 的
`A2_time_only` 都是"无循环控制、**保留** RPT 更新"。
本实现取 **one-factor-at-a-time**：full / full−cycle / full−RPT，因为这样每个消融相对 full 只改变一个机制，
归因干净，且与 A1 可比。若主控要字面读法（time 也不做 RPT 更新），那是第四格 `(use_cycle=False, use_rpt=False)`，
代码已支持并可运行（`four_flag_combinations` fixture 覆盖），只是未登记为正式臂。**请主控裁定。**

**B. 锚点用"最早到达"而不是"最早来源"**：与 A2 草案一致，保证 query 时该读数真的已知。
代价是来源更早、到达更晚的 RPT 会被划入 pre-anchor 排除并计数。

**C. 锚点前不做预测**：没有 Q_ref 就没有容量语义。若主控要覆盖 pre-anchor query，需要另立"无锚点先验"分支，
本原型不实现（避免又回到标称 0.25 Ah 旁路）。

**D. 锚点读数不计分**：Q_ref 由该读数定义，再计分会让 σ_obs 被同一读数条件化压低。
若主控要求计分，将 `score` 置 True 即可，但需在结果中说明这一双重使用。

**E. query 与最后事件之间的空档用零控制推进**：即只走时间项基率，不把"最后一条循环控制"外推进 filtered state；
held-recent 控制只用于未来 horizon。另一种做法（用 held-recent 控制填补空档）会把假设的操作注入状态，
本原型选了更保守的一种。**这是可辩论的建模选择，请主控确认。**

**F. 未来预测的 horizon 是日历周**：真实未来 RPT 检查计划未知，因此不建模"下一次检查"，也不做 FPT/RUL 事件模拟。

**G. 未来工况策略 = 最后一条已完成循环控制 held constant**：强假设，必须在结果中披露；
若未来工况变化，预测会偏。

**H. 观测噪声是全局标量 σ_obs**：不做 heteroscedastic / 曲线条件噪声头（A1 的 F3 曲线头不在 A2 范围）。

**I. D 的高斯性与不可逆性**：漂移非负，但后验/样本路径可下降；`linearized_threshold_probability`
只是一阶高斯诊断，不是事件概率、不是首达概率，也不用于事件监督。

**J. 循环可用时间**：默认要求显式 `available_epoch`；仅当显式传入
`assume_cycle_arrival_equal_source=True` 时才用来源 stop 顶替并计数。PREP 必须同时提供两个时钟。

**K. 结构性常数**：`R_eq` 上界 0.15 Ah、先验 sd 5e−3、σ_obs 初值 2e−3、softplus 基值都是
**声明的结构先验/初始化**，不是在这批数据上调出来的；A2 不做宽度/seed/超参搜索。

---

## 9. 授权边界（本次实际做了什么）

- 只写本目录：4 个 Python 文件 + 本 README + `SELF_CHECK_LOG.txt`。
- **0 拟合、0 优化器步、0 训练**；`--dry-run` 只有一次合成反向（fixture `gradients_flow`，无 `optimizer.step()`）。
- **0 payload / processed 数据集 / checkpoint / saved prediction 读取**；没有 C3/C4 访问。
- 未创建 GO、未写回执、未消费 GO、未改 `new_fits_allowed`、未创建 heartbeat/迁移任务、未动任何锁。
- 未修改 A1、既有实验目录或先前的 A2 草案目录。
- 合成 fixture 用的是随机张量与伪造记录，不含任何研究样本。

## 10. 下一步（需要主控）

1. 审阅本实现与 §8 的 A/E 两处口径。
2. 若接受：先发 **PREP_ONLY GO**（只读 C1/C2，构造 per-cell 紧凑数组 + manifest + SHA256，0 拟合），
   再发 **FIT GO**（3 臂 × 内部选择 + 全量重拟合 = 6 fits，≤3000 步，batch 8 cells，seed 42，
   选择依据内部 25 节 cell 的 cell-macro 创新 NLL，不碰 C3）。
3. C3 推断需另发 GO；C4 仍未解封。
---

## 11. 性能设计（2026-10-22 追加：向量化加载 + 块扫描 replay + 窗口化 BPTT）

> 本节只描述**代码与性能**变更。模型数学、数据契约、损失语义、sigma 口径、锚点/划分规则一字未改：
> `a2_model.py`、`a2_targets.py`、`a2_prep.py`、`a2_fixtures.py`、`a2_train.py` 的 SHA256 与本日志上一版一致。
> 新增文件：`a2_fastdata.py`（快速数据/窗口 replay）、`a2_fixtures_fast.py`（11 个新 fixture）、
> `a2_train_v2.py`（训练入口；复用 `a2_train.validate_go`，保持唯一 GO 门禁）。

### 11.1 上一版为什么跑不动

- `a2_train.load_prepared_sequences` 对 774,486 个事件逐个构造 Python dict：22 分钟仍未返回。
- `a2_targets.replay_batch` 每个事件一个 Python 步（含一次 3 层 MLP）：单步 ~0.7–0.9 ms（fwd+bwd），
  6 fits × 3000 步不可行。
- 结果：6 个 FIT GO 已签发，但 **0 次拟合完成**、GO 未消费。本轮只修管线，不跑拟合。

### 11.2 快速加载器（`a2_fastdata.FastA2Data`，保留旧 loader 作参照）

PREP 输出的 `event_cell` 已经是按 cell 分组且非降序的，因此：

```python
counts  = np.bincount(event_cell, minlength=n_cells)
offsets = np.concatenate([[0], np.cumsum(counts)])   # N+1 个偏移，O(E)
tensor  = torch.as_tensor(npz_array)                  # 一次成型，无逐事件对象
```

校验也是向量化的：`event_cell == repeat(arange(N), counts)`、kind∈{1,2}、dt≥0、score 只在 RPT 上、
q_ref 有限为正。manifest 的 `prepared_npz_sha256` 与 `split` 逐项校验，train/val 只由 cell id 决定。

实测（服务器 YNDXTEA0034，125 cells / 774,486 events / 46 MB npz）：**0.52 s** 完成加载 + 校验
（上一版 >22 分钟）。`n_events`、`n_cycle=771,947`、`n_rpt=2,539` 与 manifest 完全一致。

标准化同样向量化：只累加 **train cells** 的 cycle 事件、mask>0.5、有限值，按维 ddof=0；
常量/未观测维 scale 强制为 1 并计数。与逐事件 float64 参照实现对比：count 完全相等、mean 差 0.0、
scale 最大差 2.9e-9（只是求和结合顺序；量级 1e-9 相对 0.05 可忽略）。

### 11.3 块扫描 replay：同一个滤波，O(log T) 深的计算图

两次 RPT 测量更新之间只有 cycle 事件，转移是仿射的，且 `F = diag(1, alpha)` 是对角阵：

```
D'   = D + r_D·dt                     -> 前缀和
R'   = alpha·R + (1-alpha)·R_eq       -> 仿射递推 (alpha, c)
P00' = P00 + sigma_D^2·dt             -> 前缀和
P01' = alpha·P01                      -> 前缀积
P11' = alpha^2·P11 + V(alpha)         -> 仿射递推 (alpha^2, q11)
```

因此一个 block 内所有事件的状态可用 `cumsum/cumprod` 一次算出；长 block 或 alpha 连乘下溢时
退回 Hillis–Steele 对数深度仿射扫描。Python 循环只发生在 **RPT 测量更新**处（每个 cell 每窗口 0–2 次），
不再每事件一次。autograd 图深度 O(log T) 而非 O(T)，这是 CPU 单步能做到几十毫秒的关键。

数值等价性（float64，见 fixture 与 §11.7）：整 cell replay 与 `a2_targets.replay_batch`
逐 cell NLL 最大差 8.2e-15；单步 block 与 `model.advance` 循环最大差 1e-12；
窗口损失与全序列对应段最大差 2.4e-12（真实 PREP 数据，含 60,370 事件 cell）。

Joseph 更新在**有梯度窗口**里仍调用 `model.correct_rpt`（唯一权威实现）；只在 no-grad burn-in
里用等价的 2×2 展开式（fixture 对 `correct_rpt` 断言 1e-12）。

### 11.4 窗口化 / 截断 BPTT

- 每个采样 cell 取连续 **L=256** 个事件（短 cell 取全序列，尾部以 dt=0 的恒等步补齐）。
- 采样只在“包含至少一个计分 RPT”的窗口里均匀取：先均匀取一个计分 RPT 位置 p，
  再在 `[max(0,p-L+1), min(p,n-L)]` 均匀取窗口起点。这样每个窗口都有梯度，不会出现 0 损失 cell。
- 窗口前做 **no-grad** burn-in；窗口内顺序创新 NLL；损失 = 每 cell 均值 NLL 的 cell-macro 平均；
  锚点不是事件（它只定义 Q_ref），因此永不计分；`noRPTupdate` 仍对每个 RPT 预测并计分、只是不更新。
- 评估用 `replay_cells`：整 cell、按长度分桶 padding、精确复现 `replay_batch`。

### 11.5 关于“W=128 burn-in 后与全序列滤波逐元素相同”的更正（重要）

任务原文假设：窗口前 128 个事件的 no-grad burn-in 后，窗口起点状态与全序列滤波逐元素相同。
**这个等式在 s>W 时不成立**，原因是 D 的漂移是累加的、不会遗忘：

```
D(t) = sum_{k<=t} r_D(x_k)·dt_k      # 没有衰减项
```

从 anchor 先验出发只 burn 最后 W 个事件，得到的是 `D(t)-D(t-W)`，漏掉了前 `t-W` 个事件的漂移；
而 R 的 OU 项和协方差确实会衰减。fixture `truncated_burnin_gap_is_real` 实测 W=128 与精确前缀
在同一窗口上差 **1.96 nats**（远大于 1e-9）。真实数据上 `last_w` 的窗口损失也系统性偏离。

因此本实现提供两种 burn-in，并**默认 exact**：

| 模式 | 含义 | 是否满足“窗口损失 == 全序列对应段” |
|---|---|---|
| `exact`（默认） | no-grad 过滤**整个前缀**（anchor→窗口起点），用块扫描一次算完 | 是（1e-12 级） |
| `last_w` | 字面 W=128 截断（`--burn-in-events 128`） | 否，仅当窗口起点 ≤ W 时成立 |

`exact` 仍然是 no-grad（窗口起点状态 `requires_grad=False`、`grad_fn=None`），只是不再人为丢弃前缀；
它满足任务要求的 **1e-9 等价性 fixture**，而 `last_w` 不能。若主控坚持字面 W=128，可显式
`--burn-in last_w --burn-in-events 128`，但必须接受损失语义偏离全序列 replay 这一事实（差距已实测记录）。

### 11.6 实测（YNDXTEA0034，torch 2.5.1 CPU，8 线程，batch_cells=8，L=256）

| 场景 | burn-in | 单步 mean | median | p90 | max | 备注 |
|---|---|---|---|---|---|---|
| 合成（24 cells × ~2.1k events） | exact | **60.5 ms** | 60.7 | 67.6 | 75.8 | 20 步，0 optimizer |
| 合成 | last_w(128) | 43.3 ms | 42.1 | 47.4 | 69.6 | 同上 |
| 真实 npz（125 cells / 774k events） | exact | **68.9 ms** | 64.7 | 78.6 | 103.7 | 20 步，0 optimizer |
| 真实 npz | last_w(128) | 37.1 ms | 36.9 | 45.1 | 66.7 | 同上 |

- 真实数据 exact 的 max=103.7 ms 来自 103,575 事件的长 cell（前缀本身 ~72 ms）；mean/median/p90 均 <100 ms。
- **线程数很关键**：服务器默认 32 线程时，小张量 `Linear(48→32)` 单次要 55 ms（配额 13 CPU + 其他负载，
  OpenMP 争用）；8 线程 0.15 ms。因此 v2 入口默认 `--threads min(8, cpu_count)`，并在日志记录。
- burn-in 统计：exact 平均 21.7 ms（合成）/ 单步 68.9 ms 总；last_w 平均 3.9 ms。
- 加载：0.52 s（774,486 events）。

### 11.7 等价性证据（真实 PREP 数据，forward-only，float64，0 优化步）

| 检查 | 结果 |
|---|---|
| 快速 loader vs 慢 loader（合成 npz，逐事件逐字段） | 完全一致；split/标准化一致 |
| 整 cell fast replay vs `replay_batch`（4 种开关组合） | 最大差 8.2e-15 |
| 窗口损失 vs 全序列对应段（合成，4 个位置 × 3 臂） | 最大差 1.4e-14 |
| 窗口损失 vs 全序列对应段（真实 cell：63 / 2,846 / 60,370 events） | 最大差 **2.4e-12** |
| burn-in 起点状态 vs 顺序全滤波（真实 cell） | mean 1.4e-17，cov 5.4e-20 |
| 划分：loader vs manifest vs `split_cells_by_hash` | 三者完全一致 |
| 标准化：fast vs 逐事件 float64 参照 | count 相等、mean 差 0、scale 差 ≤2.9e-9 |

### 11.8 复现

```bash
cd /home/yndx/zxk/rul/experiments/multirate_state_A2_20261022
PY=/home/yndx/miniconda3/envs/a40_env/bin/python
$PY -m py_compile a2_model.py a2_targets.py a2_train.py a2_fixtures.py a2_fastdata.py a2_fixtures_fast.py a2_train_v2.py
$PY a2_train.py --dry-run                    # 旧入口 16/16（未改）
$PY a2_train_v2.py --self-check --dry-run    # 16/16 + 11/11 + 三臂探针
$PY a2_prep.py --self-check                  # 6/6（未改）
$PY a2_train_v2.py --bench --bench-steps 20 --threads 8                     # 只跑合成
$PY a2_train_v2.py --bench --bench-npz --manifest prep_v2_20261022/manifest.json --threads 8
```

训练（**本轮未运行**，需主控发 FIT GO）：

```bash
$PY a2_train_v2.py --run-train --go <APPROVED_GO.json> --manifest prep_v2_20261022/manifest.json \
    --arm full --steps 3000 --batch-cells 8 --window-events 256 --burn-in exact --threads 8
```

### 11.9 未改变的东西 / 未做的事

- 未改 `a2_model.py`（24b23883…）、`a2_targets.py`（9c736968…）、`a2_prep.py`（3b45d148…）、
  `a2_fixtures.py`（0dc22f20…）、`a2_train.py`（11cf19e4…，与上一版日志相同，故无 diff）。
- 未训练、未做 optimizer step 于任何研究数据、未读 payload/C3/C4/checkpoint、未写 GO/回执、未创建后台任务。
- 0 次 fit；6 个旧 FIT GO 仍未消费；本轮不产生任何科学结论。

## 声明更正（2026-10-22 20:05，独立审稿发现）

本目录 v2 的三次“full125 refit”**实际只在 100 个建模 cell 上重训**：`a2_train_v2.py` 的 refit 复用
`data.train_index`（100 cells），25 个内部验证 cell 从未进入最终模型。因此：

- 正确表述是：**内部选择用 100 train cells / 验证用 25 cells；最终 refit 仍用这 100 cells**。
- `GO_A2_FITV2_*.json` 的 scope 与 README §训练 中的 “full-125” 字样**不再有效**，以本声明为准。
- 这不改变已发布的 6 次拟合与 3 个 val NLL 数值（−3.00/−2.83/−1.93），但它们的含义是
  “100-cell 模型在 25 个留出 cell 上的选择期验证”，且只有单 split/单 seed、无置信区间 → 不能写成“RPT 更新有效”。
- 真·全 125 refit 需要单独的新 GO（3 次 refit，复用已选步数与全 125 标准化），留给下一轮；在完成之前，
  任何使用这三个 checkpoint 的 C3 推断都必须标注“100-cell refit 模型，25 个验证 cell 未参与最终训练”。
