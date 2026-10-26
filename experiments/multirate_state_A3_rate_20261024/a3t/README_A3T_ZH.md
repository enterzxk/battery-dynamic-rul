# A3-T：A3 机理滤波器的 Student-t 创新版（结构性校准修复候选）

目录 `a3t/`。动机：A3 点精度与最强树打平、NLL 大胜，但正态近似低估重尾、
风险调度 α=5% 名义下实际违规 ~18%（目标 ≤10%）。

## 模型语义（相对 A3 仅两处改动，其余全部复用）

1. **t 创新**：计分 RPT 创新 u_r 改为 `t(0, S_r, ν)`，尺度
   `S_r = H_rPH_r'+σ_y²` 不变；ν = 2+softplus(nu_raw)（下限 2），初值
   10。创新 NLL = 负的精确 t 对数密度：
   `-lgamma((ν+1)/2)+lgamma(ν/2)+½log(νπS)+((ν+1)/2)·log1p(u²/(νS))`，
   ν→∞ 逐点收敛到 A3 高斯 NLL（fixture：差 <3e-5，mpmath 复核 <6e-14）。
2. **过程噪声可学倍率**：σ_ℓ_eff=σ_ℓ·softplus(q_ell_mult_raw)、
   σ_R_eff=σ_R·softplus(q_R_mult_raw)，倍率初值恰为 1（起点=A3）。覆写
   `sigma_ell()/sigma_R()` 访问器后，A3 全部传播代码
   （advance/_segment_advance/frozen_coeffs）零改动即生效。

## 矩匹配更新（标准 robust filtering 两步）

t 创新 = Gamma 尺度混合 u|ξ~N(0,S/ξ)，ξ~Ga(ν/2,ν/2)，一步 EM：

- 第 1 步（创新加权）：`w=E[ξ|u]=(ν+1)/(ν+u²/S)`∈(0,(ν+1)/ν]，离群点 w→0；
- 第 2 步（高斯几何更新，协方差被 w 修正）：以 `R_eff=σ_y²/w` 做
  A3 原版 Joseph 更新（含 noRateUpdate 增益掩零）。

精度（fixture，1 维精确 t 后验求积）：量测主导区（HPH'≤0.25σ_y²）
均值/方差差 <0.05σ_y（ν∈{3,5,12}，|u|≤6σ_y；实测 ≤0.028σ）；先验
主导区平滑退化（文档化近似）。离群鲁棒：30σ_y 离群下状态移动 <高斯
版一半，后验容量方差只增不减。

## 与 a3_model 的复用点（原文件字节冻结，零修改）

- 子类 `A3TStateModel(A3StateModel)`：四臂 ARM_CONFIGS、冻结线性化
  离散（精确仿射半群）、OU 协方差闭式、锚点先验、Joseph 更新几何全部
  继承；同 seed 下 mu_net 初始化与 A3 逐位相同，ν=1e7、倍率=1 时全量
  replay 与 A3 一致（损失差 <2e-8）。
- `_run_events_a3t` 仅替换创新 NLL 与量测更新两处语义，分段结构、carried
  (a,b)、批处理不变；burn-in/walker 同构镜像（scatter-back）。
- 训练入口复用 `a2_train.validate_go`、`a3_train` 的消费登记表与共享
  CPU 锁、`a2_fastdata` 全套窗口 BPTT；GO 中 A3/A2 复用文件的 pin 在其
  真实目录解析校验（fail-closed）。

## GO 模板（由主控创建审批；worker 绝不创建/写入/消费）

```json
{"status": "APPROVED", "allow_fit": true, "allow_train": true,
 "scope": "A3T TRAIN/FIT: Student-t innovation variant of the A3 four-arm individual-rate state model, selection 100 + refit all125, exactly 8 fits in this GO",
 "request_id": "<唯一>", "issued_utc": "<UTC>",
 "code_sha256": {"a3t_model.py": "<sha>", "a3t_train.py": "<sha>",
                 "a3_model.py": "<sha>", "a3_train.py": "<sha>"},
 "max_steps": 3000, "arms": ["full","noEll","noRateUpdate","time"],
 "refit_scope": "all125", "seed": 42, "batch_cells": 8,
 "window_events": 256, "burn_in": "exact", "burn_in_events": 128,
 "lr": 1e-3, "weight_decay": 1e-4, "val_every": 50, "patience": 6,
 "fits_in_this_go": 8, "prepared_manifest": "<PREP v2 manifest json 绝对路径>",
 "prepared_manifest_sha256": "<sha>", "out_dir": "<新目录，不得已存在>"}
```

执行（仅主控）：`python a3t_train.py --run-train --go <GO> --manifest <manifest>`；
单 GO 4 臂×2 fits=8 fits，request_id 恰登记一次。fit_report 新增
`a3t_params`（ν 学到值、两倍率）与 `refit_val_eval_on_manifest_val_cells`
（与 A3 同一 val 集的 t NLL 与高斯型 NLL 并排，直接对比）。

## 自检（16 项全过，见 SELF_CHECK_LOG.txt）

`python a3t_train.py`（默认 0 拟合/0 payload/0 GO）：t NLL 正确性与
ν→∞ 收敛、矩匹配 vs 精确 t 后验、全量退化=A3、倍率语义、重尾上 t 优于
高斯（真参数差 0.466 nats）、ν 收敛（10→6.46，真值 5）、梯度、四臂
结构、walker 等价、无泄漏、离群鲁棒、GO 拒 20 类变异、no-payload
审计、登记表复用、宏/配对语义、训练冒烟。
