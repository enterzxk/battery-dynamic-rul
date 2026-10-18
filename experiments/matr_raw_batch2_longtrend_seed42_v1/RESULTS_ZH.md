# 原始MATR第二批：非线性与长期速率真实对照
2026-10-18。一次限定GO、3次CPU预测fit、0 optimizer steps、0 test读取。全部既有结果保留；本实验使用独立目录和消费账本。

| 固定方法 | Time-MAE(cycles) | signed bias | P(over>100) | 80%coverage | 80%width | Brier100 | Brier300 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 稳健20速率线性 |35.843670|-9.257261|0.004390|0.838727|160.711576|0.030709|0.106387|
| B 同输入非线性强基线 |27.632472|-4.745870|0|0.723864|52.690693|0.013385|0.082398|
| C B仅增加稳健100速率 |27.438338|-5.056428|0|0.709610|50.278905|0.014384|0.080256|

26train/9development，9445/3586实际源循环origin；先电芯内全时段平均再电芯等权。所有35颗事件均观测到，无test。输入age/SOH/稳健20速率；B/C相同固定HGB超参，C只多100速率。训练权重每电芯总量相等后缩放均值1；缩放/残差sigma只用train。没有改窗口、阈值、seed或选择验证最优epoch。

## 根判断
- B相对A平均Time-MAE降22.9084%，但仅4/9cell改善，电芯配对bootstrap区间[-10.0630%,38.9812%]跨0，覆盖率下降11.4864个百分点；不通过冻结开发门。可保留为点预测强对照，不称普遍改善/可靠分布。
- C相对B只降0.7026%，区间[-8.6538%,3.8005%]，5/9cell改善，未达到5%及6/9门。结论NO_GAIN_FOR_ADDING_RAW100_RATE，NO_GO_LONG_RATE_COMPLEXITY_OR_SEED_EXPANSION。加长期速率不是论文贡献，不能用更多seed救结果。
- 本次三组新fit已消费；旧52/19的3+1CPU、旧MATR41CPU与神经4fit2580steps分账。原全局new_fits_allowed=false保持。

## 真实失败机制线索：个体支持与区间异质性
只用现存预测和资产做0fit诊断。训练事件范围148..561；开发b2c47事件713超出训练上限，B的MAE116.1286、bias-110.5774，51.8760%前缀低估超过100，覆盖率23.8173%。b2c46则事件429在训练范围，95.44%查询的各特征都在训练边际范围内，仍有MAE41.2259、bias+41.2259、覆盖率11.8541%。边际范围正常不等于联合支持或可靠预测，不能据此造一个简单范围门控。
这表明下一问题应是训练支持之外的寿命外推及个体区间失准；不是继续加一个长期特征。原sigma为train内残差估计，不能当作已校准的不确定性。以上为开发集描述，尚未识别原因或验证在线可靠性判别器。

## 最小验证与来源链
一次独立审查：reports/matr_raw_longtrend_review_20261018_luna/review.json，子代理请求配置gpt-6-luna/high；运行时身份未独立证明。主线程请求配置gpt-6.1-sol/high，负责最终GO/科学判断。审查绑定runner/protocol/manifest，修复HGB导入后主线程只验证一次import，不构造模型或额外smoke。
ROOT_GO绑定最终runner SHA0a4a592d937789b5d8d44657334aaedd9c4aff9c4b710b0cbffc9b068ab8bb3b、protocol SHAd5b4395d83bc26633cff7b7f8736017a3581fa2a7997d80a176b80604ba8fc60、数据manifest SHAfcbedb9ee4ea9da83efe3239cda3d56d629678b3dbbd90b675039f6456ad32c1和review SHA。review抽查b2c2行数文案339由GO说明更正：100..437为338个查询，模型使用manifest及完整运行断言。
从10758行已保存预测独立重算全部7指标，最大绝对差8.1713e-14；3组同cell同origin、真值T-t及概率/分位数边界一致。预测SHA8813407210851ba05bc96b40cd9607827ff91aa28f8e570b01e8f06e2600a004。没有重复训练、额外预测、test或追加测试。

## 边界与下一动作
9颗development曾用于先前工程开发，当前仍是适应性开发证据；同批次、event-only、source-ID边界，不是独立确认、自然删失收益或跨物理电芯泛化。完整原始文件SHA UNKNOWN，原始输入以官方文件ETag/范围块SHA绑定；两颗单循环Qd与summary核验通过，不冒称全文件下载完成。
停止当前长期速率候选，保留B作为后续对照。下一项优先推进已有研究所需的其它原始批次DataV1，以冻结训练/开发群体后再决定一次train-cell留出的不确定性校准对照；现阶段不开放该fit、不调开发覆盖率、不用真实验证误差回滚。原test继续封存。若其它批次端点/测量不能兼容，则保留分域，不能靠混合数据消除负结果。

复现入口：本目录runner.py、protocol.json、ROOT_GO.json、fit_ledger.jsonl、development_predictions.csv、completion.json、independent_metric_recompute.py。GO与create-only invocation已消费，不重复运行；指标复核使用已保存CSV即可。
