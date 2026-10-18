# 可逆schedule：条件存活与动态更新的固定尺度强对照

## 实际结论
0fit，仅使用已有10cal/4567条预测，比较新lossless模型origin100初始分布经存活条件更新、其逐时点动态分布，以及旧compressedpolicy动态参考。所有arm统一固定sigmaA=.19898311654196568，不估新尺度、不做新推理。

动态点MAE相对同模型早期存活基线55.242118→33.027239改善40.2137%，9/10cell改善、paired差95%CI[10.098087,35.133490]为正；但严重高估>100由.2791%升至3.1631%，增2.8840个百分点，超过冻结+1个百分点护栏。点联合gateFAIL，概率联合gate亦FAIL。判定NO_GO_LOSSLESS_DYNAMIC_ACCURACY_RISK_TRADEOFF_FIXED_SCALE；保留点均值与电池差证据，不扩模型/seed/尺度。

| Cell-equal指标 | 新模型早期条件存活 | 新模型动态 | 旧compressed动态 |
|---|---:|---:|---:|
| Time-MAE/cycle | 55.242118 | 33.027239 | 36.400814 |
| severe over100 | .2791% | 3.1631% | 4.2582% |
| coverage80 | 79.2520% | 79.4309% | 78.5016% |
| width80/cycle | 205.784494 | 116.668763 | 116.169090 |
| IS80 | 266.317886 | 149.873353 | 148.489249 |
| Brier100 | .08211333 | .01391046 | .01401752 |
| Brier300 | .07973755 | .05652744 | .05651083 |

相对自身早期存活，IS改善43.7239%、Brier改善，但逐cell覆盖误差仅6/10改善，聚合覆盖误差改善.00178893未达旧.03门槛。旧门槛不修改，也不能把接近80%的总体覆盖当条件覆盖成功。
相对旧compressed动态，新模型MAE均值改善9.2679%但仅6/10、CI跨0，上一阶段扩展NO_GO不变；IS略恶化.9321%，仅2/10cell覆盖误差改善。

## 关键风险证据
同一b4c7电池，动态MAE81.598126→55.713292变好，severeover100却从2.7907%升至23.7209%。这说明MAE收益与严重寿命高估冲突不仅是跨cell平均混合；它在同一cell内也存在。
总体风险增量来自b4c7、b4c14和b4c29，原始逐cell早期/动态MAE及风险在risk_change.json。以上是开发集上的描述，不建立因果风险机制或独立物理泛化。

## 分布定义与证据边界
初始T~LogNormal(mu100,sigmaA)，当前elapsed d=origin-100。仅存活更新：
Fsurv(r)=1-S_T(d+r)/S_T(d)，r>0。
动态Fdyn(r)=Phi((log(r)-mu_current)/sigmaA)。初始mu100只取该cell第100循环预测，elapsed是可见实际循环，不取真实EOL或全寿命比例。真实RUL只用于最后评分。
sigmaA来自旧3state训练残差，并非新lossless或compressedpolicy模型的独立校准；概率/Brier与早期分布中位数均依赖这个固定参考尺度假设。因此这是同尺度参考诊断，不是概率可靠性、conditionalcoverage、conformal或机制确认。cal已反复开发、event-only、物理serial/fullsource未知、固定已知labpolicy限制保留。

## 最小验证、输出和复现
独立对13701条派生记录重算指标、正向CDF/风险，最大指标差2.84e-14、风险差3.77e-15、分位CDF误差1.40e-14；3个代表时点用独立二分法替代逆正态算分位数，最大差4.55e-13。全部区间正且有序。
0fit/模型构造/新模型推理/旧checkpoint/新尺度/rawfeatures/devtest；CPU20=RUL18+辅助2不变，神经4fit2580steps及旧MATR41另记。
reports/lossless_survival_probability_20261019_root/含protocol/diagnose、metrics/per_cell_metrics/comparisons/arithmetic_examples/risk_change、completion/independent_recompute/independent_metrics/root_decision。derived_distribution_predictions.csv仅服务器保留，其SHA在completion；公开已有源模型预测无损档案、协议和脚本足以重算全部派生量。
原调用：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/reports/lossless_survival_probability_20261019_root/diagnose.py。输出create-only，禁止重跑覆盖。

## 下一条有界行动
一个固定强简单概率参考：Fmix=.5Fsurv+.5Fdyn，唯一等权，不学习或搜索权重。必须计算实际混合CDF的q10/q50/q90，不能把两个中位数平均冒充混合中位数；Brier概率为两arm风险均值。仅已有预测，0fit/新推理/尺度/checkpoint/devtest。冻结同原早期基线的点/风险门槛，一次窄审+fresh exactGO后只执行一次完整比较，检验普通等权概率混合能否缓解风险冲突；所有旧gate/NO_GO不追改，不把该基线当创新或独立确认。失败后不搜权重或再造融合模块。
