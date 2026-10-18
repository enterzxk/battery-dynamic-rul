# 固定因果EOL平滑：NO_GAIN，停止本固定方案

同10cal/4567既有工况模型预测，alpha=2/21固定，origin100初始化绝对EOL，随后只用过去状态和当前预测递推Ehat=(1-alpha)Ehat_prev+alpha*(t+RUL_t)，输出max(0,Ehat-t)。span20为指数记忆参数，并非截断20点窗口；没有future或真实误差参与更新，无alpha/window搜索、模型推理或fit。

| 电池等权指标 | 原动态 | 因果EMA |
|---|---:|---:|
| Time-MAE，循环 | 36.400814 | 35.804016 |
| bias，循环 | -3.523895 | -3.822858 |
| 严重高估>100 | 4.25825% | 3.81888% |
| 单次EOL修订绝对值，循环 | 3.198785 | 1.033132 |
| 回溯有害更新比例 | 48.30848% | 36.49748% |
| 每步平均绝对误差减少，循环 | .180143 | .174037 |

Time-MAE仅降1.6395%，5/10电池改善，pairedcell bootstrap2000/seed42的MAE差95%区间[-1.089981,2.303030]跨零；严重高估减少0.43937个百分点。冻结门槛要求>=5%MAE下降、>=7/10改善、CI下界>0及严重高估增量<=1个百分点，故FAIL/NO_GAIN。平滑后有3个仍存活时点预测归零，完整保留。更平滑或更高有益更新比例不能替代主指标收益。

两臂各4557次更新。EMA相对当前原模型EOL的平均绝对追踪差为9.793194循环；alpha对应低频理论群延迟9.5cycle，不是实测事件响应延迟，不能把二者混同。回溯有害/有益只作评估；未来真RUL绝不进入在线回滚。

最小验证：全部4567时点用独立闭式加权卷积而非同递推复算，预测最大差4.55e-13，指标最大差1.42e-14，归零数3一致。v0曾因(100+RUL)-100与RUL的严格浮点相等断言失败，差1.42e-14，尚未产生指标；原diagnose.py、failure_v0.json与仅header的derived_predictions.v0_failed.csv保留。diagnose_v1.py只放宽初始化验证容差为1e-10，源/alpha/算法/门槛均未变。

证据在本目录protocol/diagnose_v1/metrics/per_cell_metrics/comparison/transition_audit/arithmetic_examples/completion/independent_metrics/root_decision；服务器derived_predictions.csv保存全时点，公开脚本可由已发布原预测复算。源SHA796844ff5c863a08ca7f1238c620afee39a3f22b84d68b615ec52135c48b7ea0。本轮0fit/optimizer/模型推理/新尺度估计/checkpoint/原始特征/dev/test；累计CPU14=RUL12+辅助2、神经4fit2580steps及旧MATR41不变。

限制：cal反复暴露，仅开发；event-only、来源ID而非已验证物理身份、固定实验室工况限制保留。本对照是强简单点基线，不是创新或概率模型，原点PASS及概率FAIL不变。停止此EMA，不调alpha/窗口或加seed。

下一步仅一个必要机制检验：用刚保存的42fit预测22239次连续EOL修订，冻结电池等权加权经验q90绝对修订阈值；在既有10cal4557次更新中一次比较大修订/其余的有害率与误差增益，报告电池覆盖及修订正负方向。训练外阈值不调、不触发预测门控、不新增模型/fit。检验“大修订应被抑制”是否有真实证据，再决定是否值得提出可靠更新机制；不预设越稳定越可靠。
