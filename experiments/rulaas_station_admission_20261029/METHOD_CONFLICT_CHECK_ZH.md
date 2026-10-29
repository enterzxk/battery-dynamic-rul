# 本轮方法冲突核查（2026-10-29）
性质：定向定义/公式核查，不是完整综述或忠实复现。当前接纳基线不是创新方法。

1. Arafa & Yates, Age and Value of Information Optimization for Systems with Multi-Class Updates，arXiv:2408.12589v1（2024）。
原文 §II–IV、式(1)–(19)、Theorem 1 已建模服务完成后交付、繁忙时丢弃和空闲时门控；在其独立同分布类别/服务时间与Poisson机会假设下，给出年龄和衰减价值目标的阈值解。不能把“年龄+价值+接纳”本身称新颖，也不能把其最优性直接移用到当前多电芯实测轨迹。
https://arxiv.org/html/2408.12589v1

2. Zou & Subramaniam, On the Value of Information in Status Update Systems，Entropy 24(4):449（2022）。
原文 §2、式(1)–(5)、§3.1 明确区分产生价值和交付时价值，允许价值随时间衰减至截止时刻归零，并分析不同缓存/丢弃规则。结果到达晚导致价值损失已有直接先例；当前工作必须解释RUL预测损失的价值如何从真实训练轨迹估计，以及共享检测站与迟到寿命监督的影响。
https://pmc.ncbi.nlm.nih.gov/articles/PMC9030661/

3. Fauriat & Zio，Optimization of an aperiodic sequential inspection and condition-based maintenance policy driven by value of information，RESS 204:107133（2020）；以及 Inspection schedule for prognostics with uncertainty management（2022）。
本轮只检索到出版方元数据/片段，全文访问返回403；方法公式与实验未核实。仅登记为后续必须取得可读作者版的直接近邻，不凭摘要认定方法差异或等价。
https://www.sciencedirect.com/science/article/pii/S0951832020306347
https://www.sciencedirect.com/science/article/pii/S0951832022000667

本轮实测中陈旧程度基线已经出现约30.7%占站节省的点估计权衡，意味着方法门槛应提高。下一项应检验：在训练数据中，给定同样的陈旧程度和现有预测不确定性，某次检测在实际报告可用后带来的预测损失改善是否仍可预测。不可把额外新结构数量作为创新证据。
