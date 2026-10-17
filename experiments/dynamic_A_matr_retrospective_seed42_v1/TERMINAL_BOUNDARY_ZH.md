# 各batch记录终点、阈值事件与标签分支

本阶段完成方向A既有预测的终点语义诊断；不再用新增子群或阈值变体寻找增益。NO_GAIN与原指标/标签/人口保留。

当前合格133个train/val源ID的完整文本metadata表明：batch1/3末次SOH略高于0.8、没有观测nominal crossing；batch2/4则保留了显著更多阈值后记录。观测状态与batch的完全混杂对应不同的已处理记录终点，不能按随机缺失或单纯标签类型效应解释。

| split | batch | 电池数 | 末次SOH最小 | 末次SOH最大 | crossing后保留循环范围 | 作者EOL减末次观测 |
|---|---:|---:|---:|---:|---|---|
| train | 1 | 19 | 0.800051 | 0.802952 | 未观测crossing | [-1, 3] |
| train | 2 | 26 | 0.750086 | 0.752290 | [21, 36] | [-36, -21] |
| train | 3 | 28 | 0.800013 | 0.801518 | 未观测crossing | [-1, 1] |
| train | 4 | 26 | 0.228173 | 0.762355 | [33, 256] | [-256, -33] |
| val | 1 | 11 | 0.800059 | 0.802107 | 未观测crossing | [-1, 2] |
| val | 2 | 9 | 0.750036 | 0.751909 | [20, 37] | [-37, -20] |
| val | 3 | 4 | 0.800004 | 0.801031 | 未观测crossing | [-1, 0] |
| val | 4 | 10 | 0.233766 | 0.755290 | [23, 273] | [-273, -23] |

全部71个已观测crossing电池均在首次crossing后继续留有记录，零个在首次crossing即结束；其中训练52、验证19。62个未观测电池的终点接近80%，不是已证寿命仍很远，也不证明随机行政删失。作者标签在这些记录上使用末20SOH回归，因此作者EOL约等于记录末端附近的位置，但不能代替实际事件证据。

## 可证与不可证

- 可证：在当前已处理记录上，终端SOH、nominal crossing是否可见、所选作者标签分支彼此对应。`Extract_life_labels.py:121-145`用最后cycle SOH决定排除、末20回归或crossing分支；`147-155`才扫描首次<=0.8。`preprocess_MATR.py:168-206`遍历所提供cycle并含已知特例映射，`237-252`归一化时间并返回BatteryData；本次仅阅读，未执行这些代码。
- 不可证：实际v11包由哪次generator运行生成、原始各batch采集停止条件、是否有额外截断或插值、physical serial独立性。pinned代码的存在与既有重建吻合，不能补足真实生成过程。没有证据时不把末端差异归因于某种人为处理或物理机制。
- 不允许：为让事件都可见而改80%阈值、把作者EOL改为末次观测+1、重新挑子群或用未来终点生成预测特征。已有结果只保持回顾性processed-record作者标签诊断，strict_online_eligible=0。

## 最小验证与闭合

133份metadata SHA与冻结cohort一致，SOH末值与既有标签审计一致（差<1e-12），observed标记与metadata crossing非空一致；未重读cycle曲线、pickle或test摘要，未重跑标签回归或模型。new_fits=0、optimizer_steps=0。机器记录`terminal_boundary_diagnosis.json`保留每cell终点、crossing、标签分支和来源SHA；`terminal_boundary_diagnosis.py`可重算，旧create-only文件不得覆盖。

方向A诊断链已闭合：41次原始拟合、全体/观测子群指标独立复算、长寿命失败下界、作者标签边界、特征/目标支持、误差贡献及batch终点混杂均保留。未达到复杂历史模型继续门槛，不再追加seed/更大模型或重复诊断来挽救结果。汇总绑定见`diagnostic_closure.json`。

下一条有界动作：只核官方MATR_v11发布metadata是否给出准确generator commit/配置或版本映射，不下载已核数据、不读二进制、不重做文献；若没有，明确记录provenance缺证并停止从pinned代码反推实际生成器。原PBT一次读取预算消费和模型/test门不变。
