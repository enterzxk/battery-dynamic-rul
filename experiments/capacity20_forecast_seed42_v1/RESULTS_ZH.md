# 20cycle容量变化预测：真实单fit能力比较
## 2026-10-18：主动换向完成一次真实容量预测fit，强简单基线比较通过能力门
- **已完成**：线性RUL→容量代理失败后，改为直接监督未来20cycle容量变化；复用42fit/10cal、21441/4367同窗口样本，窄审+freshGO下1辅助CPUfit。capacity-MAE(mSOH)容量不变9.588254、robust20外推1.972894、HGB1.031446，较强简单基线降47.7191%、9/10cell改善，通过冻结能力门。
- **证据**：experiments/capacity20_forecast_seed42_v1/RESULTS_ZH.md、runner/protocol/cohort/ROOT_GO/fit_ledger/completion、calibration_predictions.csv、metrics/per_cell_metrics/comparison/independent_metrics、published_predictions.json；checkpoints/auxiliary_hgb.pkl SHA5022a619e9cc86c725be57faabc8ab0a191e084d58c342f67ac303f6fb9ea006仅服务器。审查reports/capacity20_forecast_review_20261018_luna/review.json SHA b058db8b89d2d9cc1bf52b8acf8966c66894edb7493f0e7945ca53af67c8e7e3。
- **最小验证**：2真实fit/cal pair确认输入仅s、未来s+20仅label；4367预测CSV独立重算3指标×3arm，最大差4.44e-16；原CSV无损解码哈希匹配。无重复smoke。新增1辅助CPUfit0optimizer0dev/test；GO已消费，checkpoint已存不可重复fit。
- **阻塞/风险**：这是已用于开发的10cal容量预测能力，不是RUL增益/创新/独立确认。b2c6反而从1.0354差到2.3666mSOH，保留失败个体；其他源ID/物理serial/fullsource SHA/事件队列限制不变。名义1.1Ah时1mSOH=.0011Ah，HGB约1.1346mAh、robust20约2.1702mAh；不能与RUL循环MAE混用。
- **下一步**：仅用已存容量预测和同10cal的RUL预测，固定t=s+20的实际容量变化减预测变化为可观测innovation，对比其与回顾RUL误差的方向/rank关系以及robust20预测残差和原容量变化控制；0fit/0forward/0dev/test，先确认反馈信息增量才设计RUL修正。不得把真实RUL残差作为在线输入。

| 校准10cell等权 | MAE(mSOH) | bias(mSOH) | 每cell RMSE再均值(mSOH) |
| --- | ---: | ---: | ---: |
| 容量不变 |9.5882540153|9.5621193301|13.0356524809|
| 过去20cycle Theil-Sen斜率外推 |1.9728936895|1.8071723790|3.2238539089|
| 固定HGB |1.0314458076|.3401398200|1.7164879429|

输入仅s时点的actual age、SOH_s和past20稳健斜率；监督target为(SOH_(s+20)-SOH_s)*1000，两端都在已有pre-event记录内。未来容量是训练/评估标签，未作为预测输入。两简单基线和模型共用同一批4367个cal pair。
HGB固定150iter、leaf7、depth3、lr.05、minleaf50、L2=1、seed42；等cell训练权重；未调参、未重新拆分、未读取18dev feature。性能只适用于这项受限容量预测。
对robust20 MAE降47.7191%，对persist降89.2426%；9/10改善，唯一恶化b2c6保留（1.035351→2.366557mSOH）。无独立显著性/跨数据集/论文创新声称。
运行的指定Python及环境版本见completion，模型由本次自己训练后只pickle.dump保存，不做反序列化、不接触PBT/旧RULcheckpoint；未来如需前向复用仍需该阶段的scoped GO。原runner invocation.claim已存在，不能重跑。
独立重算命令：指定Python执行本目录independent_metric_recompute.py；原结果create-only，不覆盖已有证据。公开三arm校准预测为published_predictions.json无损压缩，可用decode_public_predictions.py恢复原始CSV。
