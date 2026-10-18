# 唯一50/50完整CDF混合：点与风险门槛通过，完整概率联合仍失败

## 一次真实比较
固定Fmix=.5Fsurv+.5Fdynamic，仅复用已有lossless预测和旧sigmaA，不估权重/尺度。q10/q50/q90在真实混合CDF上求逆，以两个component的同分位数作括号，64次二分；不是平均中位数。0fit/新模型推理/rawfeatures/checkpoint/devtest。

| Cell-equal指标 | 早期条件存活 | 纯动态 | 固定等权CDF混合 |
|---|---:|---:|---:|
| Time-MAE/cycle | 55.242118 | 33.027239 | 35.452043 |
| severe over100 | .2791% | 3.1631% | .6047% |
| coverage80 | 79.2520% | 79.4309% | 83.3103% |
| width80/cycle | 205.784494 | 116.668763 | 176.212745 |
| IS80 | 266.317886 | 149.873353 | 209.495934 |
| Brier100 | .08211333 | .01391046 | .03419614 |
| Brier300 | .07973755 | .05652744 | .06312134 |

相对主要参考“早期条件存活”：混合MAE改善35.8243%，10/10cell改善，pairedcell差95%CI[11.107744,28.785172]；严重高估增量.3256个百分点小于原+1个百分点护栏，原点/风险四项gate全部PASS。该通过仅指暴露cal上的强简单基线开发筛选，不是独立确认。
完整概率联合仍FAIL：聚合coverage偏至83.31%，覆盖误差相对早期反而增加.025624，逐cell覆盖误差仅3/10改善；IS/Brier改善不能救联合失败。原legacy .03覆盖门槛不修改。
相对纯动态：MAE均值增7.3418%、IS增39.7820%、Brier变差，但严重高估由3.1631%降至.6047%。普通等权概率混合已能在点精度和尾部高估之间做明显折中，任何后续可靠性机制都应与该强简单基线比较。无权重搜索、无创新确认。

## v1工程失败与最小修复边界
v1在比较源表顺序的断言失败，尚未进入CDF求逆，也未生成混合预测；独立重算因无预测文件未运行成功。原runner/protocol/ROOT_GO/failure和失败日志保留，v1 GO消费且不重跑。
两个component文件按cell排序，而源point表是原cohort顺序，4567个唯一(cell_id,origin)键及trueRUL全部一致。v2只按键重排component到源表顺序，并检查重复/键集合/标签。数学算法、权重、sigma、二分和门槛没有改变；最小对齐检查+独立delta审查PASS，签新exactGO后只执行这一次实际CDF比较。该修复不是参数或科学结果救援。

## 最小验证与公开证据
4567记录的独立CDF/风险/指标复算通过：指标最大差2.84e-14、分位CDF误差6.61e-15、风险差2.55e-15；3代表时点用独立标量CDF二分，最大分位差2.27e-13。所有区间正且有序。
experiments/lossless_equal_CDF_mixture_v2/保存protocol/runner/ROOT_GO/key_alignment_validation、metrics/per_cell_metrics/comparisons/numeric_validation/completion、independent_recompute/metrics/root_decision。原8列mixture_predictions.csv及其完整309894byte无损档案保留服务器；公开public_quantiles_lossless.json+decode_public_quantiles.py给4567条3分位数列的原字节SHA无损档案，并绑定原point预测行序SHA。风险可由公开原point预测及等权CDF公式重构；完整CSV SHA在completion。没有把仅3列公开归档冒充完整8列字节归档。
前置审查及工程delta审查位于reports/lossless_equal_CDF_mixture_review_20261019_luna；v1失败目录experiments/lossless_equal_CDF_mixture_v1保持原样。
原调用：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/experiments/lossless_equal_CDF_mixture_v2/runner.py。create-only与claim防重复，两个GO均消费。CPU20=RUL18+辅助2不变，0fit/推理/权重或尺度估计/devtest。为维持12MiB，3份已完成历史静态证据271252→39406bytes无损归档，原件/历史保留。

## 科学限制和下一步
旧sigma不是新模型独立校准，故这些概率及混合中位数依赖固定参考尺度。cal反复开发、event-only、物理serial/fullsource未知、固定已知labpolicy等限制保留。旧全局/局部CDF和lossless点模型扩展NO_GO不撤销，本次不解锁训练或独立确认。
停止继续搜索混合权重/新校准模块。下一项仅窄范围创新冲突审查：从已有主文证据选择最多2篇最接近动态分布更新/可靠性融合的论文，逐一核Methods/公式与实际全文可达范围，形成“现有方法—本项目已证事实—尚未证明的最小增量”对照。不重读41篇、不从摘要推断、不训练；明确普通等权CDF基线后，才判断是否还有值得验证且非重复的可靠性更新问题。
