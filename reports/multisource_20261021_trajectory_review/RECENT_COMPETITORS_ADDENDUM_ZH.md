# 新近竞争工作补充：联合输出与观测过程

日期：2026-10-21。本补充只围绕新检索的三项相关工作，聚焦“联合模型是否已解决电芯容量路径、检查过程与观测事件 RUL 的一致性”。未读取研究数据、检查点或 C4；未训练模型。arXiv 工作按其方法、III-B、IV-C 阅读；其他两项分别限于期刊论文可检索正文/官方记录与 McMaster 官方摘要，未据摘要推断未公开的细节。

## 1. 2026 arXiv：联合 RUL 与容量的双任务头

Tran 等人的 [arXiv:2609.21932v1](https://arxiv.org/abs/2609.21932) 已经明确做 partial-charging 输入下的联合 RUL/容量回归，故“联合训练两个电池输出”或“长短时间尺度信息互补”本身不能作为新颖性。方法里长时支路以过去 30 周期窗口选 10 个 10 分钟局部充电段，GRU 自编码预训练后由 CNN/GRU 汇总；短时支路读最近连续 10 个 40 分钟局部充电段的统计描述，经 CNN/Transformer 汇总。短时表征用 FiLM 调制长时表征，末端共享线性头输出两个标量。训练先以重建加两项 MSE 预训练编码器，再独立预训练两个专家，最后冻结专家并优化 FiLM/共享回归头，目标仍为加权 RUL MSE 与容量 MSE（方法 II-C–D）。

这是多任务点预测。两个输出来自同一表示与联合损失，但架构没有逐时容量路径、检查间隔/源索引模型，亦没有由容量路径定义的首次观测阈值命中分布；因此它不保证多个 horizon 的容量预测可以组成物理连贯轨迹，也不通过采样检查过程导出 RUL。文章使用 RUL 和容量标签监督；“输入未使用完整历史容量”不等于容量没有参与训练。

其 III-B 按电芯分区：Dataset I 使用 41/43/40 cells，后两组沿用原研究 primary/secondary test 的角色作验证/测试；40 个测试电芯来自较晚批次。Dataset II 用 55 development cells 切 train/validation，并将 22 cells 留作 test。预处理只在训练部分拟合；窗口特征只用预测时可见记录；配置和 checkpoint 由 validation 选取，test 留作报告。每个结果对 5 次模型预测先平均，再按测试电芯汇总均值和标准差。该协议比前缀按行随机拆分更合适，但不改变目标是周期轴点 RUL 与单点容量回归。

IV-C 的消融不支持“某个复杂融合器天然更优”。短/长输入视图会使两项误差朝不同方向变化；例如 partial-charge 表征中较短窗口更利于其 RUL 指标，统计容量表征则在更长窗口下容量误差更低。作者也指出早期 XGBoost 输入消融与最终神经架构并非全部单因子可比。最终同一专家的融合器比较里，FiLM 容量 RMSE 最低，注意力/拼接的 RUL RMSE 均略低；差距相对跨电芯波动很小，需要配对电芯比较。减小容量损失权重把平均 RUL RMSE 降低约 2 cycles，却将容量 RMSE 提高约 25%；所以联合头只是权衡机制，不等于两种输出之间有路径约束或机制一致性。具体对照见 III-B、IV-C1–6 与表 XV–XVI。

## 2. Informative visiting：访视过程应进入概率模型

Thomadakis 等人的 [Biostatistics 论文 kxae041](https://doi.org/10.1093/biostatistics/kxae041) 面向纵向标志物、可能信息性的访视过程与终末竞争事件，明确比较 gap-time 与 calendar-time 访视模型，并允许过程通过共享/相关随机效应及已观测历史相联系。它是“测量日程不能默认无信息”这一原则的强先例。其应用语境、标志物和竞争风险是临床纵向数据；这不是电池容量路径方法，不能直接说明 battery-RUL 的具体构造已解决。

与当前电池问题最相关的转移是：把“下一条有效 RPT 的时间”看成一个应建模/积分的随机过程，而不是固定重复 gap 的模拟网格。还需更严谨地区分 source stop、被抽取/可见的报告及报告 arrival；真实电池源检查之间隔可能受测试程序安排，数据里的到达延迟则是另一个机制。只有记录/协议能识别的过程才应拟合，不能把实验员安排或稀疏化政策臆称为由潜在健康驱动的 informative visiting。

## 3. 已有联合退化轨迹与生存风险/粒子更新

Brumm 等人的 2025 论文 [QRE 3673](https://doi.org/10.1002/qre.3673)，本次方法细节只采用 [McMaster 官方条目摘要](https://experts.mcmaster.ca/scholarly-works/3486240)：条目称方法联用变点一般路径退化模型与神经网络 Cox 时间事件模型，再通过 Bayesian 更新/递归粒子滤波做在线 RUL 推断。故“将退化路径、事件时间风险和粒子在线更新放在联合框架里”也不是可单独宣称的新意。官方摘要没有列出 battery-specific inspection process、报告到达屏蔽或源阈值事件定义；这些细节在本评审中标为 unverified，不从摘要外推。该论文期刊正式卷期为 41(2), 607–624 (2025)。

## 4. 对 B 下一条研究假设的判断

B 当前把真实训练路径的 capacity increments 放进 teacher-forced transition likelihood，但首达评估用固定 train-gap 重复网格。因此它仍缺少从 as-of 到达历史到自然未来 source-observed threshold event 的检查过程桥接。建议把下一候选写成可证伪的**联合标记更新过程**，先作为研究假设，不要命名或宣称为新方法：

在每个实际源检查点联合预测下一 gap、源索引/删减标记以及容量增量，条件可用历史状态、上次已到达 RPT 和 query 时可见操作摘要。对 raw、sparse2、delay7d 使用各自预先固定的抽取/arrival 规则：推断 query 前发生但尚未到达的源检查，并对“到 q 为止没有其它报告抵达”的事实形成条件；再按冻结的训练集可用信息抽未来检查与容量路径，首个 source capacity <= 0.20 Ah 的源检查时点定义 RUL。未知的未来操作量必须积分于训练期估得的条件操作分布，或清楚报告固定操作情景；不得代入 C3/C4 的实际未来操作或真实未来检查时刻。这样得到的是指定自然/反事实采样机制下的源观测事件分布，不是潜在连续物理 EOL。

理论前提是检查点完整记录、source index 可映射、arrival/删减政策可复现；如果没有这些依据，格点仍然不可识别。Sparse2 是确定性每隔一条保留时，模型里应把保留规则当成已知观测政策，不把它误学成电芯随机检查行为。Delay arm 则把 source time 和 arrival time 分开。未来操作过程不被识别时，估计 RUL 依赖强的条件外推假设，应显示敏感性。

最低可证伪消融要保持同一状态、容量转移、训练预算和查询支持，仅比较：固定 train-gap 网格；无条件的 train-only renewal gap；条件于可见历史并对 query 前隐藏 checks 做 arrival/no-report 条件化的联合 marked-renewal。另将联合 gap–mark–capacity coupling 替换为互相独立的边缘抽样，检验提升是否来自过程依赖而非额外参数。成功标准不是 teacher-forced NLL 单项变好，而是在共同 query 上提升有支持的源事件 Brier/生存分布评分与容量/路径误差，并报告每电芯配对差异、tail 未命中率、未知终点遮罩和每个 arm 的校准。若完整观测/到达政策无法确认，或耦合模型不能优于独立组件，就保留 B 当前限定结论并停止扩建。

新颖性边界：临床 informative visiting 和工程 joint degradation–event 先例均已存在；本候选最多是 battery-specific、as-of-valid 的源检查/到达/删减过程与容量路径的联合建模问题。提出它不等同 novelty established；在实验前还需做更广文献覆盖和精准相似性比较。

## 来源范围

- arXiv HTML：方法 II-C–D；实验 III-B；结果与消融 IV-C1–6（特别表 XV–XVI）。
- Biostatistics 2025, 26(1), kxae041：期刊论文全文/摘要及其 gap-time visiting formulation。
- Brumm et al., Quality and Reliability Engineering International 41(2), 607–624 (2025)：只依据 McMaster 官方条目摘要；更细的模型假设标为 unverified。
