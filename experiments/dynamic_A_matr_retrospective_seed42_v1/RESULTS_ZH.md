# MATR方向A：回顾性已处理记录信息增量实验

运行完成：2026-10-17T15:41:38.008606+00:00。主控请求gpt-6.1-sol/high，独立reviewer请求gpt-6-luna/high；实际运行时身份未独立内省。

结论：**NO_GAIN_FOR_COMPLEX_HISTORY_EXPANSION_ON_THIS_DIAGNOSTIC**。近期速率有小幅预测关联，但未达预登记继续门槛，不推进复杂历史模型，不改seed救结果。

本实验仅评价已处理记录前缀、完整循环测量容量与作者总EOL的一致性。实际v11生成器与其余物理serial未知，strict_online_eligible=0；不能宣称严格在线、I/V-only部署、物理独立泛化、完整复现或创新成立。

## 真实运行与指标

训练99个源ID；验证34个源ID、每电池k=50/100/150/200共136时点；观测到nominal crossing的19电池/76时点单独报告。固定seed42，3fold grouped train-only CV，scaler逐训练fold拟合；三个Ridge模型39次fit含CV，条件固定GBDT2次，总41；optimizer_steps=0。test未访问。旧CP两次fit/600steps独立保留。

Time-MAE先电池内平均、再电池等权，单位循环。全34列含15个作者外推标签，只表示作者标签一致性；19列是回顾性观测事件条件子群。

| 模型 | 全34作者EOL Time-MAE | 19观测事件 Time-MAE | 全34 bias |
|---|---:|---:|---:|
| A0 | 151.9080 | 90.2058 | -45.7119 |
| A1 | 152.5449 | 91.5955 | -41.1682 |
| A2 | 148.4576 | 86.8838 | -40.2046 |
| GBDT_A1 | 159.6220 | 104.6789 | -34.8871 |
| GBDT_A2 | 153.7740 | 102.5455 | -33.6243 |

A0：k50一次估EOL后递减；A1：年龄、当前SOH、累计Ah和batch；A2：A1仅加过去20cycle容量斜率。

Ridge A2 vs A1：全34下降2.679%，21/34改善；配对电池bootstrap探索区间[0.977%,5.801%]。观测19下降5.144%，13/19改善。固定GBDT全34下降3.664%，18/34改善，区间[-2.105%,8.766%]；观测19下降2.038%，8/19改善。条件GBDT由同验证集结果触发，非独立确认。

A1并未优于A0：全34误差增0.419%，观测19增1.541%。速率增益也未达到约10%推进幅度。

## 误差、尾部与年龄分层

15个未观测事件电池的作者EOL MAE：A1=229.7474，A2=226.4512；这仍非真实EOL测量。

Ridge全34整体bias -41.17→-40.20（负值为低估）；观测19为+21.72→+17.45。全34电池内最坏高估的P90由146.61增至157.65；GBDT由197.50增至218.21，至少一次高估>=200循环的电池3增至6。平均MAE下降未同步改善所有尾部。

| k | 全34 A1 | 全34 A2 | 观测19 A1 | 观测19 A2 |
|---|---:|---:|---:|---:|
| 50 | 154.5262 | 150.7300 | 92.3999 | 88.3927 |
| 100 | 154.1932 | 149.5774 | 93.8870 | 88.4806 |
| 150 | 151.6221 | 147.2276 | 91.0892 | 85.7199 |
| 200 | 149.8380 | 146.2955 | 89.0059 | 84.9418 |

## 验证与复现

独立标准库脚本从全部680条逐模型预测复算全部MAE/bias，检查clip(EOL-k)、41条开始/41条完成账本匹配；没有重复fit或smoke。独立复算源代码`independent_metric_recompute.py`。

原运行命令（一次性claim已消费，**不得直接重跑或覆盖**）：`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 /home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/experiments/dynamic_A_matr_retrospective_seed42_v1/runner.py`。`ROOT_GO.json`绑定code/input/protocol SHA及独审SHA；`completion_receipt.json`保存原始输出，`validation_predictions.csv`允许独立重算。

主证据：`independent_metrics.json`、`per_cell_paired_deltas.json`、`selection.json`、`fit_ledger.jsonl`、`root_decision.json`。独审`reports/dynamic_A_matr_retrospective_independent_20261017_luna/review.json`仅PASS_RETROSPECTIVE_ONLY，非性能结论。已知别名关系来自旧文本证据；排除的四个cell是next-cycle mapping风险，不能把它们统称续测alias。

下一步：仅用现有预测诊断高误差删失电池与作者尾段外推标签，不新增模型fit。PBT一次结构读取entry_cap失败预算保持消费，不重跑、不切分片、不开放模型/test门。
