# 固定5邻居工况局部 OOF 残差 CDF：NO_GAIN

## 实际执行与判定
一次真实0fit分析已完成。42fit电池的4个已知工况特征按电池等权mean和population SD(ddof0)标准化；每个10cal目标固定选择5个最近sourcecell，距离只用policy，不看cal标签。按未四舍五入float64平方距离及sourcecell ID排序。每个局部CDF只使用已存OOF残差，每sourcecell总质量1/5，精确Fraction左逆q10/q50/q90，仅减局部OOF中位残差一次，保留旧点预测。不存在新模型fit、模型构造/推理、旧checkpoint加载、原始特征或dev/test读取。

判定：NO_GAIN_FIXED5_POLICY_LOCAL_OOF_CDF_STOP_NO_NEIGHBOR_OR_SCALE_SEARCH。原固定sigma是主要参考；globalOOF仅次要参考，二者都失败。预执行独立窄审PASS及主控fresh exactGO已落盘并消费，禁止调邻居数/距离/尺度救援。

| Cell-equal指标 | 原固定sigma | 全局OOF | 工况局部固定5 |
|---|---:|---:|---:|
| Time-MAE/cycle | 36.400814 | 36.400814 | 36.400814 |
| severe over100 | 4.2582% | 4.2582% | 4.2582% |
| coverage80 | 78.5016% | 69.7698% | 62.5373% |
| mean-cell绝对coverage误差 | .213265 | .249444 | .271472 |
| IS80越低越好 | 148.489249 | 152.213299 | 190.184645 |
| width80/cycle | 116.169090 | 102.662875 | 108.622475 |
| Brier100 | .01401752 | .01277359 | .01306195 |
| Brier300 | .05651083 | .05609614 | .06158851 |

相对原固定sigma，IS恶化28.0797%，pairedcell差95%CI[-101.816263,10.566924]；仅4/10电池coverage误差改善。平均Brier增量.00206106超过冻结.002护栏；不以“接近门槛”为由修改容差。0分位数冲突，区间均有效，仍联合FAIL。相对globalOOF的IS也恶化24.9461%，不构成救援。

## 固定结果的失败描述
下侧漏覆盖均值25.4910%，上侧11.9716%。b2c1仅4.1667%覆盖，b2c6仅4.8662%；后者上侧漏覆盖94.6472%。b4c14/b4c7覆盖约48%，b4c19/b4c29又过宽到约95–98%覆盖。各target的5source名单、距离、OOF条数、局部中位数及分位偏移均在local_CDF_parameters.json，不能用cal结果重新选邻居。
对b2c1最近的b2c0工况距离为0，但已知raw_policy字符串分别为2C(10%)-6C与1C(4%)-6C。这提示4项积分有效倍率可能把不同细分schedule压到同一个表示；目前只是已有字段例子，不把它宣称为本次失败原因或新特征收益。

## 最小验证和复现
独立重算训练mean/SD（最大差1.78e-15）、全部邻居列表、10个局部CDF的Fraction分位数和4567条预测/指标：最大预测差1.14e-13，指标差2.84e-14，通过。原CSV无损zlib/base64字节SHA核对通过，服务器原件保留。没有重复模型fit或calforward；累计CPU19=RUL17+辅助2不变，神经4fit2580steps及旧MATR41另记。1个train-only变换（4mean4SD）和10个OOF局部CDF已消费。

路径：experiments/policy_local_oof_cdf_fixed5_v1。原命令为/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/experiments/policy_local_oof_cdf_fixed5_v1/runner.py；invocation.claim及输出create-only阻止重复执行。independent_recompute.py为指标复算，predictions_lossless.json+decode_predictions.py恢复calibration_distribution.csv原字节。review位于reports/policy_local_oof_cdf_fixed5_review_20261019_luna/review.json。所有关键文件SHA见root_decision.json。

限制：已反复暴露cal，仅开发；event-only、physicalserial/fullsource未知、固定已知labpolicy、OOF模型28训练vs旧point42训练；5cell局部分布有效电池样本少。不称conditionalcoverage、conformal保证、独立确认或创新。

## 下一条实际动作
仅0fit审计现有52行policy表与原encoder：不同raw_policy schedule是否被4个effectiveC输入映射成同一向量。固定绝对1e-12C编码等价容差，仅定位表示碰撞/信息丢失，不搜索容差，不读取电池原始特征、模型或dev/test，不据cal误差重编码或拟合新模型。先判定是否存在可修复的输入表示问题，再决定是否值得新的最小对照。当前邻居/全局残差后处理均关闭，不继续参数救援。
