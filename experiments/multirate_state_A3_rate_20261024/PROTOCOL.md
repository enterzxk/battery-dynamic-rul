# A3 协议：个体退化速率状态（ell）机制假设 — 设计冻结（2026-10-24）

状态：DESIGN_ONLY（无代码、无拟合、无 GO）。实现 worker 只允许合成自检；真实训练/推断必须等
主控审查代码后签发新的 exact-hash GO。协议修复后的训练规范（selection 100 + refit 125）为默认。

## 1. 动机（证据链）

- A2 已证：RPT 测量更新是状态的主要信息来源（noRPTupdate 差一个数量级），机制成立；
  但 A2 在全部三臂、全部指标上仍落后同可见信息强树（raw MAE +1.97 mAh [1.29, 2.86] vs F0 HGB）。
- A2 的 `d_rate = f(u)` 不依赖个体潜在退化速率状态；RPT 校正只更新退化量 D 与可逆项 R，
  能调整当前健康水平，却不能通过显式个体速度后验持续修正未来斜率（代码结构事实）。
- full−time 差距在真·全 125 refit 后依旧（+5.38 mAh [3.68, 7.14]）：24 维循环控制以"外生驱动"方式
  进入是有害的。待检验假设：循环信号应作为**健康观测**（p(z | x, u, protocol)）而非外生控制；
  个体速率 ℓ 应作为**可被测量更新修正的状态**。

## 2. 模型（冻结定义；单位纪律：σ 单位 Ah，方差单位 Ah²，D 无量纲，ℓ 无量纲速率）

状态 x = (D, ℓ, R)，初始先验显式声明：

- dD = softplus(ℓ) · dt  —— D 路径单调不减（softplus(ℓ) > 0 恒成立）；
- dℓ = −κ (ℓ − μ_θ(u)) dt + σ_ℓ dW₁，κ = softplus(κ̃) > 0，σ_ℓ = softplus(σ̃_ℓ) > 0；
- dR = −λ R dt + σ_R dW₂，λ = softplus(λ̃) > 0，σ_R = softplus(σ̃_R) > 0（与 A2 同型）；
- 观测 y = Q_ref · exp(−D) + R + ε，ε ~ N(0, σ_y²)，σ_y = softplus(σ̃_y) > 0（Ah）。

u 为截至当前**已完成**运行条件的 past-only 摘要（禁止任何未来输入；与 A2 相同的 held-control 政策）。
μ_θ(u) 由小网络参数化（θ 共享，输入为 u 的汇总统计，不是 dt）。

离散化：精确仿射半igroup/网格不变（复用 A2 a2_model 的实现模式；无 dt 输入）。
更新：顺序 RPT 创新 NLL；(D, ℓ, R) 线性化后的 Kalman/Joseph 协方差更新（复用 A2 数值纪律），
ℓ 通过 y 对 exp(−D) 的依赖间接获得信息更新。健康代理观测更新（z 通道）**不在 A3 范围**，
列为后续假设（先验证速率状态本身的价值，避免一次引入两个未验证机制）。

## 3. 臂（4 个，全部共享参数化与 cell 划分）

| 臂 | μ_θ(u) | ℓ 的测量更新 | 目的 |
|---|---|---|---|
| full | u 的函数 | 是 | 完整机制 |
| noRateUpdate | u 的函数 | 否（只更新 D, R） | 消融速度后验更新 |
| time | 常数 μ₀ | 是 | 消融循环驱动 |
| noEll | —（ℓ ≡ softplus(c)，dD = c·dt） | 只更新 D, R | 退化还原为 A2 型结构（控制臂） |

预期判读：若 full 显著优于 noRateUpdate 且优于 time → 个体速率状态 + 循环驱动有价值；
若 noEll ≈ full → ℓ 机制无增益（诚实负结果）；任何情况下都要与同可见信息强树同键比较。

## 4. 数据与训练协议（继承修复后的规范）

- 复用 PREP v2 缓存：manifest `prep_v2_20261022/manifest.json`（sha 37492217…，npz f746edb8…），
  125 训练 cell / 774,486 事件；不新建 prep、不读 raw/C3/C4 payload。
- 训练：窗口 BPTT（复用 a2_fastdata），selection 在 100 个内部 train cell（val 25 cell），
  **最终 refit 在全部 125 cell（冻结 selection 步数，标准化在全 125 cell 拟合）**——即 fullrefit 修复后的协议。
- 优化：AdamW 1e-3 / wd 1e-4，batch_cells 8，window 256 exact 无梯度 burn-in，clip 1.0，
  val_every 50 / patience 6，seed 42 / sampling 43，CPU 8 线程 + 两把共享 CPU 锁。
- 预算：4 臂 × 2 fits = **最多 8 fits**，max_steps 3000，全部在同一训练 GO 内，GO 记录 fits_in_this_go=8。
- GO 纪律（新增）：gate 校验 request_id 未出现在 consumed-GO 登记表
  `experiments/state/consumed_gos.jsonl`（append-on-success）；成功运行后登记，防 GO 变异重消费
  （2026-10-23 GO_A2_FITV2_noRPTupdate 事件）。

## 5. 评估与比较

- C3 推断：独立 GO，复用 A2 冻结查询契约（同一 2,326 键面板：raw 903 / sparse2 463 / delay7d 960，
  61 cell），流式 walker、no_grad、RSS < 2 GB。
- 比较：统一主口径 RMSE=√(mean_cell MSE)；对象 = F0–F3 × HGB/CatBoost、旧 A2（100-cell）、
  新 A2（125-cell）、A3 四臂；5,000 次物理电芯配对 bootstrap；逐键 target 断言。
- 诚实边界：C3 开发集、单 seed；Q(q+h) 条件于给定 h；full vs noRateUpdate 的差异归因于速率更新，
  不能归因循环信息整体；Gaussian 校正后的 D 不得声称为不可逆物理真值。

## 6. 执行阶段与权限

1. **实现（本 worker，0 拟合）**：代码 + 合成 fixtures 自检（≥10 项，含 softplus 单调性、半群网格不变、
   Joseph 更新、ℓ 可观测性合成检验、四臂消融等价性、walker 等价、GO 拒绝变异、no-payload 审计）。
2. 主控审查代码与 fixtures → 签发训练 GO（8 fits）→ 训练 → receipt。
3. 签发推断 GO → 推断 → 签发比较 GO → 同键比较。
4. 结果落盘 RESULTS_ZH.md + 更新进度/综合/论文。

模型说明：实现 worker 运行于 ZCode 会话（GLM-5.3-Flash），与 DSH 时代 deepseek 约定的偏离已记录于
docs/ZCODE_CONTINUATION_20261024.json；权限与验证规则不受影响。
