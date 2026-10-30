# 四周迟到监督与删失：定向方法冲突核查

本文件用于排除已知方法包装，不是系统综述或复现结论。用户要求的可投稿证据尚未形成。

1. **电池 EOL 与真实删失已有 AFT 生存分析先例。** Santhira Sekeran、Živadinović、Spiliopoulou，*Transferability of a Battery Cell End-of-Life Prediction Model Using Survival Analysis*，Energies 15:2930，2022，[论文全文](https://mdpi-res.com/d_attachment/energies/energies-15-02930/article_deploy/energies-15-02930-v2.pdf?version=1650272070)。第 3.2 节、表 1：NMC 源数据 122 电芯中 85 个删失，NCA 目标数据 100 电芯中 62 个删失；第 3.4.1 节、式 (1)–(3)：使用含协变量的 Weibull 加速失效时间模型和生存函数；第 3.5 节、表 4：通过多种参数迁移配置在目标数据集训练/验证。其数据可用性受限。故“电池寿命 + 生存模型 + 删失”本身不能声称新颖；本项目还需证明因果可用的监督到达、动态预测和受约束服务决策的可验证贡献，不能凭题目声称优于该方法。

2. **跨领域删失 RUL 与强树基线已有先例。** Lillelund 等，*A probabilistic estimation of remaining useful life from censored time-to-event data*，2024，[全文](https://arxiv.org/abs/2405.01614)。第 4.3–4.4 节及第 5.1 节：该文在 XJTU-SY 轴承数据中根据信号事件检测进行标注，并在完整事件数据上人为生成 25%/50%/75% 删失，比较包括随机生存森林在内的模型；其事件检测式 (6) 中参数包含完整记录终点 L，文中也指出真实工业场景无法直接获得 L，讨论以 L10 等替代。该文不是电池或报告队列实验，但说明“概率寿命 + 右删失”及生存森林对照不是新概念，也提醒不能把完整寿命 L 带进在线前缀。

3. **有限资源信息价值调度已有近邻。** 当前项目已核过 Arafa–Yates 2024 的接纳/丢弃、信息年龄和价值公式，以及 Zou–Subramaniam 2022 的生成/交付时信息价值，见 [已有方法冲突核查](../rulaas_station_admission_20261029/METHOD_CONFLICT_CHECK_ZH.md)。因此“有在途报告时不再检测”或“报告晚到则价值降低”不构成独立创新。Kim、Choi、Kim 2022 [论文](https://web.mae.ufl.edu/nkim/Papers/paper135.pdf) 的作者版全文本次读取超时；其方法公式与实验细节本轮标记 **unverified**，不能根据摘要认定其与本项目的差异。

4. **当前已完成实验的解释。** 仅在假设参考登记端收到所有既有检测的条件下，固定截止点额外成熟 279 条四周阴性；这个计数不能证明真实策略不检测时仍会有外部标签。后续如果提出迟到/删失反馈机制，应在同等可见前缀与资源预算下，至少对比四周成熟标签、仅完整 EOL 标签、适当生存/截尾强基线，分别记录标签证据到达与未成熟状态，并在独立工况/数据和服务风险上验证；不得重复已停止的 F3 风险或简单在途配置。
