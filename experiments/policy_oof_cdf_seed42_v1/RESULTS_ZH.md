# 固定三折电池隔离 OOF 残差 CDF：NO_GAIN

## 实际结果
已执行且仅执行3次新CPU HGB拟合。42fit电池排序后seed42一次置乱，固定三折各14个留出电池；每折28个训练电池，全部22281条OOF预测均由未训练自身电池的模型产生。7个因果/已知工况输入、log RUL目标与HGB参数保持原协议。

经验残差分布按电池等权构造，离散左逆分位数使用精确Fraction累计。仅减去OOF中位残差-0.015500609349306416一次；q10/q50/q90的log偏移为[-0.19111881762503913,0,0.24815106228790018]。对已有10cal/4567条raw mu解析应用，不重新加载旧模型、不新增cal推理、不读取18dev/test。

| Cell-equal指标 | 旧固定sigma | OOF经验CDF |
|---|---:|---:|
| Time-MAE/cycle | 36.400814 | 36.400814 |
| 80%区间覆盖率 | 78.5016% | 69.7698% |
| 平均逐电池绝对覆盖误差 | 0.213265 | 0.249444 |
| IS80，越低越好 | 148.489249 | 152.213299 |
| 平均区间宽/cycle | 116.169090 | 102.662875 |
| Brier100 | 0.01401752 | 0.01277359 |
| Brier300 | 0.05651083 | 0.05609614 |

0次分位数/端点次序冲突，全部区间有效。IS反而上升2.5080%，paired-cell差值95%CI为[-19.140823,8.403278]；逐电池覆盖误差仅6/10改善，未满足>=7。平均Brier改善0.0008293通过该单项护栏，联合预设gate仍FAIL。中位点预测完全不变；OOF可构成一致分布并不意味着概率可靠性成立。

## 有界失败解释
以下为事后描述，不用来修改分位数、门槛或模型。平均逐电池下侧漏覆盖由旧11.9896%上升至20.2891%，上侧9.5088%变成9.9411%。OOF中心化q10偏移-0.1911较旧正态q10约-0.2550更接近中位数，原方案的下界上移。MATR_b4c7覆盖77.44%降至49.30%，MATR_b4c14覆盖88.98%降至58.27%，MATR_b2c1覆盖18.75%降至8.33%；这些描述不能证明条件校准失败的唯一原因。
这次结果排除了“只要使用单一有序CDF就会修复可靠性”的简单救援；并未否定所有OOF或条件分布方法。停止当前全局残差CDF方案，不搜索fold/seed/尺度/quantile，不把Brier单项收益提升为联合PASS。

## 验证、复现与证据
- 主runner、protocol、cohort、ROOT_GO、独立预GO review与旧review阶段澄清记录保留。
- 独立math/statistics/Fraction重算全部22281OOF的电池排除与CDF，以及4567校准预测；最大预测差9.09e-13，最大指标差1.42e-13，通过。
- predictions_lossless.json与decode_predictions.py保留OOF和校准CSV原字节；解码SHA分别cf9a5a173550013f553e53dd3b379c791956ecbf92f19c2682705ec7261da9b2和56a0bdec581437729dd525e3b0e7c075feef811d48ebee3eea62479fe83fd993。服务器原CSV和checkpoints不变。CDF完整support保留服务器empirical_cdf.json；公开OOF原始预测及协议足以重构。
- 原始调用：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/experiments/policy_oof_cdf_seed42_v1/runner.py。此唯一GO和3fit预算已消费，invocation.claim阻止重复执行；复算使用同目录independent_recompute.py，已有输出create-only。
- 结果边界：10cal已反复用于开发；event-only，物理serial/full-source SHA未知，固定已知labpolicy；OOF模型每折28训练电池而既有点模型42，残差可迁移性没有保证。不称独立确认、conditional coverage或conformal保证。

## 下一条动作
0fit固定年龄区间[100,200)、[200,400)、[400,+inf)，仅使用现有OOF/校准预测及标签，比较电池等权的log残差与两侧漏覆盖；先冻结，不按校准结果改分组，不实施预测门控或新模型。检验单一全局残差分布是否掩盖可见预测时点的异质性，不能将诊断当作改进方法确认。
