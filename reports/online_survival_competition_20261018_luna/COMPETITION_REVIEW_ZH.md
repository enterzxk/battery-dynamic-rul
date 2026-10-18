# 单电池在线条件 RUL 分布：竞争核查
日期：2026-10-18。仅核三篇，不是系统综述。未训练、未读数据二进制、未改共享状态。

## 结论
将既有寿命分布按“当前仍存活”作条件化，是标准剩余寿命计算，不会自动利用当前新测得的退化信息。Dynamic-DeepHit 已直接覆盖一般的“纵向测量到来后动态更新事件时间/生存预测”：其摘要明确写明使用重复测量历史，而非只用最后一次测量。故生存条件化公式本身不能作创新，纵向动态生存预测的一般机制也不能称新。

电池领域已有 Cox/CoxPH/CoxTime/DeepHit/MTLR 用于电池 RUL 生存分析的 2025 预印本。作者仓库给出 Toyota 第 50 周期表征、362 节电池（174 事件、188 删失）和 T-AUC/C-index/IBS；这否定“电池 RUL 尚无人用 Cox/DeepHit”的宽泛说法，但未证实逐循环新观测驱动的动态预测。

PEAT 是电池在线观测适配的真实先例：根据实测容量变化率选择 10/20/30 周期历史跨度，并更新轻量 adapter 和 SOH head；稳健变体增加触发、留出早停、回滚。它优化点 RUL/SOH，不是右删失条件事件时间分布。其在线目标包含 RUL loss，但全文阅读范围内没有证明部署时可获得真实 RUL 标签， operational causal status 需要核实。

窄问题“电池 as-of 条件 RUL 分布结合右删失似然，并由新观测更新”仍未核实。本三篇筛查不能证明新颖，也不支持首次用于电池。

## 来源与阅读范围
1. **Dynamic-DeepHit**：Lee, Yoon & van der Schaar (2020), IEEE TBME 67(1), 122–133，[DOI](https://doi.org/10.1109/TBME.2019.2909027)、[PubMed 摘要](https://pubmed.ncbi.nlm.nih.gov/30951460/)、[作者代码](https://github.com/chl8856/Dynamic-DeepHit)。读 PubMed 元数据/摘要及作者 README。摘要支持重复纵向测量驱动动态竞争风险生存预测；示例为英国囊性纤维化登记队列。全文地址本轮一次 502，精确页节和删失似然未核实。
2. **电池 Cox/DeepHit**：Xue et al. (2025), [arXiv:2503.13558](https://arxiv.org/abs/2503.13558)、[作者仓库](https://github.com/OKIC-CA/RUL)。读摘要及仓库 README 实验/运行说明和结果表（网页行 197–329），未读全文。README 的 Toyota 设置取第 50 周期特征，362 节，174 未删失、188 删失；列 Cox 系列、DeepHit、MTLR 与 T-AUC/C-index/IBS。精确删失假设和逐时点更新协议未核实。
3. **PEAT**：Ren et al. (2026), Energies 19(9):2135，[期刊 DOI](https://doi.org/10.3390/en19092135)、[可读预印本](https://www.preprints.org/manuscript/202603.2447)。读预印本 v1 第 3.1–3.5、4.1–4.10 节及结论。3.3 节为 adapter/SOH head 更新；3.4 节用容量变化选历史跨度；4.7 节触发、留出早停、回滚；4.1 节 77 节（55 源/22 测），容量阈值定义 EOL。期刊页一次 429，未重试，按预印本核查。

## 竞争边界
- 存活条件化不等于新观测更新。
- Dynamic-DeepHit 是一般纵向动态生存先例。
- Xue 等已将 Cox/DeepHit 生存方法用于电池 RUL。
- PEAT 已将电池新观测用于在线历史选择和参数适配，但不是条件生存分布。
- 三篇不足以得出系统新颖性结论；“右删失 + 电池 as-of 条件分布 + 新测量驱动分布更新”组合仍未核实。
