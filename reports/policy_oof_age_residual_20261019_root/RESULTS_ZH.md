# 固定年龄三组 OOF 残差与漏覆盖诊断

## 判定
完成0fit诊断。存在描述性年龄组差异，但逐电池方向、均值与中位数并不一致，不支持从本诊断直接扩展age-only分布模型或预测修正：NO_GO_FOR_AGE_ONLY_CALIBRATION_FROM_GROUP_MEANS。旧全局CDF NO_GAIN、点预测PASS/概率联合FAIL均不改变。

## 冻结口径
数据仅为已存42cell/22281条OOF和10cell/4567条cal预测，实际origin循环分组[100,200)、[200,400)、[400,+inf)。不使用完整寿命比例来定义可部署分组。每组先平均每cell再平均组内存在的cell；另报原总体电池等权1/(Ncell*ncell)的年龄贡献，二者分母不同，不能混称或直接等权拼接。

OOF参考残差为log(trueRUL)-OOFmu减原冻结median_center；cal为log(trueRUL)-savedmu，不再给cal中心化。两者与同一冻结CDF的q10/q90偏移比较；同时保存raw残差均值。OOF总体约80%是构造内性质，不能当独立校准成功。

| 数据 | origin组 | 电池数/条数 | 80%覆盖 | 下侧漏覆盖 | 上侧漏覆盖 |
|---|---|---:|---:|---:|---:|
| OOF | 100–199 | 42 / 4200 | 73.7857% | 8.4524% | 17.7619% |
| OOF | 200–399 | 42 / 8235 | 76.9890% | 7.5172% | 15.4938% |
| OOF | ≥400 | 40 / 9846 | 82.8180% | 10.8068% | 6.3751% |
| cal | 100–199 | 10 / 948 | 59.0333% | 25.4667% | 15.5000% |
| cal | 200–399 | 9 / 1800 | 74.8889% | 13.0000% | 12.1111% |
| cal | ≥400 | 9 / 1819 | 85.1636% | 8.6578% | 6.1786% |

## 固定电池组成后
保留同时出现在三个组的40OOF/9cal电池，比较每cell早晚差。
- OOF：下侧漏覆盖均值8.8750%→10.8068%，29/40增加。上侧18.6500%→6.3751%，但仅14/40下降；其余并非都同向改善。
- cal：下侧漏覆盖均值18.1111%→8.6578%，但6/9电池反而增加，逐cell差中位数+2.1053个百分点。MATR_b4c14与MATR_b4c7两cell的下降贡献大于总体净下降，其余7cell合计反向。
- cal上侧均值17.2222%→6.1786%，仅2/9下降，分别是MATR_b2c6与MATR_b4c29；两cell降幅贡献超过总体净改善，其余cell合计反向。
- 同40OOF参考残差均值早→晚0.051803→-0.005980，但电池等权混合中位数0.003745→0.006381，未呈相同方向。cal同9cell均值0.052555→-0.010021，中位数0.044304→-0.024633；不足以确认为可转移的统一年龄偏置。

固定电池成员只排除了成员进出变化，未排除每cell时间窗长度、终点临近性及存活选择。每个prefix不是独立物理重复。本报告没有因果年龄效应、显著性、模型改善或创新确认结论。

## 最小验证与证据
protocol.json在读取诊断数据前冻结分组/指标/解释边界；source SHA核对。各组条数精确加和为22281/4567。Fraction总体权重/漏覆盖贡献精确重组，同旧CDF下/上漏覆盖20.289055%/9.941149%一致；一个标量用例b2c1 100–199为44/48下侧漏覆盖、0/48上侧。0fit/模型构造/新推理/旧checkpoint/原特征/devtest，CPU预算19不变。
运行命令：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/reports/policy_oof_age_residual_20261019_root/diagnose.py；create-only claim与输出防重复。
summary.json、per_cell_age_metrics.json、population_contribution.json、common_cell_comparison.json、paired_concentration.json、minimal_validation.json、completion.json和root_decision.json为可检验结果。cal反复开发、event-only、physicalserial/fullsource未知、已知固定policy及OOF28vs原42训练量限制保留。

## 下一步
准备一个强简单参考：仅复用OOF残差和已存4项policy，按42fit policy的train-only标准差距离为每个cal选固定5个最近sourcecell，等cell经验CDF并中位中心化保留旧点预测，与旧全局固定sigma和全局OOFCDF比较。0新模型fit/原始特征读取/模型推理/devtest；无邻居数/距离/尺度搜索，已暴露cal仅作开发。本报告不授权执行；先冻结距离/零方差/并列规则与已有联合门槛，一次必要窄审+fresh exactGO后只做一次真实有界比较。它是条件残差强基线，尚无创新或收益结论。
