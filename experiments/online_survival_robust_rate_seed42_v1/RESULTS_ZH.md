# 固定稳健速率对照：真实结果
已完成1次CPU Ridge预测fit，0optimizer steps，未访问test。52train/19validation，26796/10002origin。唯一改变为20cycle窗口全部190对斜率的中位数（Theil-Sen），其余与旧F3冻结协议一致，所有旧臂复用保存预测。
- Time-MAE F2=68.2840994294，F3=58.6026461399，F4=56.8379599892。
- F4vsF2改善16.7625%，探索配对电池95%区间[6.5909%,24.4995%]，13/19改善；F4vsF3改善3.0113%，区间[0.5681%,6.7695%]，11/19改善，未达冻结5%扩展标准。
- 严重高估>100cycles比例10.14445%，F3为10.37427%；80%coverage83.9692%，width252.1692；Brier100/300=.02843973/.10417127。
- 先前已冻结b2c22 origin256..268：MAE385.3614→32.5354；b4c28 origin100..426：71.3287→77.7856。稳健速率解决一类尖峰，未解决持续个体失配。
- 从10002行保存预测独立重算7项指标，最大差0；190pair斜率只做一次线性序列针对校验，无重复smoke。
主决策：保留强简单基线；NO_GO_FOR_COMPLEX_GATE_OR_SEED_EXPANSION_FROM_THIS_COMPARISON。进入原始数据因果预处理和封存独立确认集，不再在同19val上连续调窗调模型。
范围：processed-source event-only工程开发；物理serial/实际v11生成器不完整，非strict-online/自然删失收益/独立泛化/创新确认。旧所有负结果保留。
复现命令：/home/yndx/miniconda3/envs/a40_env/bin/python experiments/online_survival_robust_rate_seed42_v1/runner.py（一次预算已消费，不原地重跑）。
证据：protocol/ROOT_GO/root_delta_review/fit_ledger/completion_receipt/metrics/comparisons/independent_metrics，原CSV在validation_predictions/。公开published_predictions_columnar.json是仅验证预测的精确float64压缩编码；decode_public_predictions.py可无模型恢复全部10002预测行，值字节SHA已校验，非原始电池数据或checkpoint。未上传重复CSV和模型参数。
路线详见docs/PAPER_FAST_PATH_20261018_ZH.md。
