# V3 校准判定：训练内缩放校准不足（诚实负结果，2026-10-24）

执行：a3_calibrate.py（worker #5，sha 045545c1…，自检 13/13 ×2；walker==逐查询重滤波 1e-12；
C3 s=1 重算逐行复现自带列 2343/2343；schedule 语义 12/12 匹配 R3 政策表）。
GO_A3_CALIBRATE_20261024_RUN2.json（sha 9b5ad6b6…；RUN1 因目录摘要算法定义不一致在门内失败
0.065s 烧毁留痕；RUN2 前两次启动的拒绝为门内验证与生成竞态，前台复跑前已逐位核实 GO 摘要与
目录一致）。0 拟合 / 0 优化步 / 0 C3 调参 / 0 C4。

## 结果

- **s = 1.3407**（训练内闭式 pooled 方差比；6,498 个 train-cell as-of 查询的 A3_full walker 残差；
  0 优化步）。预测方差系统性低估 **34%**——但不是 4 倍。
- **C3 复评（只变方差）**：cov50 pooled 0.841→0.877（all）；cov90 0.974→0.980（本已保守）；
  pooled NLL −3.909→−3.834（**略差**）——二阶矩校准对重尾分布不改善 NLL，重尾证据明确。
- **调度前沿**：α=0.05 cell-macro 违规 19.1%→**18.2%**（all），未达 ≤10% 目标。
- **诚实旗标：TRAIN_CALIBRATION_INSUFFICIENT**（脚本自动判定，阈值 10%）：
  "training-internal variance calibration is NOT sufficient … a process-noise redesign is required"。

## 判定与论文表述

- 方差**缩放**校准只能解释超额风险的约 1/4（19.1→18.2）；主要病灶是**结构性误设**：
  正态近似低估重尾 + 过程噪声不足。修复需要过程噪声重设（模型修订），不是后处理缩放。
- 论文写法：如实报告"risk-guided scheduling 的名义风险与实现风险存在差距；闭式方差缩放
  （训练内、无 C3 调参）只能部分修复（α=5%→18.2%），指向状态空间过程噪声的结构性改进方向"。
  这与 E3 的正结果（对固定 h4 严格占优）并存：调度价值主张不依赖完美校准，但完美校准是 future work。
- 方法论正资产：整个校准-复评管道（训练内估计、C3 只复评、逐行完整性门、前后一致性门）
  是可复用的严谨流程，代码与回执全部落盘。

## 产物

ext_baselines/runs/calib_run1_20261024/（calibration_report.json、train_walker_predictions.csv、
c3_reeval_metrics.csv、schedule_frontier_calibrated.csv、receipt.json）；
GO_A3_CALIBRATE_20261024_RUN1/RUN2.json + receipts；登记表 11 条。
