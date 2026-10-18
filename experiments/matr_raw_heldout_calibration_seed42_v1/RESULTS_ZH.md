# 单次训练的独立电池尺度校准对照
## 2026-10-18：一次真实训练完成，独立电池全局尺度校准NO_GAIN
- **已完成**：按固定源ID哈希每批留出5颗校准，42fit/10calibration/18development；独立窄审与fresh精确GO后执行1CPUfit。两arm共享点预测Time-MAE43.644383；heldout尺度未通过冻结标准，NO_GAIN，不扩seed/重复fit。
- **证据**：experiments/matr_raw_heldout_calibration_seed42_v1/RESULTS_ZH.md、cohort/protocol/ROOT_GO/fit_ledger/completion、三角色原始prediction CSV、fit_parameters/metrics/comparison/independent_metrics/root_decision；公开published_predictions.json可逐字节解码三CSV。review为reports/matr_heldout_scale_review_20261018_luna/review.json，请求gpt-6-luna/high。
- **最小验证**：新增interval_score的唯一手算用例通过；从22281fit/4567cal/9561dev原始预测CSV独立重算尺度与8指标，最大差2.56e-13；无重复smoke。1predictivefit、2标量残差估计、0optimizer、0test，本次GO已消费。
- **阻塞/风险**：尺度0.19898→0.26624，coverage83.38%→91.30%偏离80%，width136.66→184.42增34.95%，interval_score202.94→210.67差3.81%，Brier均变差，只有4/18cell覆盖误差改善。校准10cell前三贡献67.38%残差均方，79.63%均方来自cell有向均值平方，提示个体偏差不能靠统一加宽处理；此为描述而非因果证明。18dev暴露/事件队列/源ID与不完整SHA限制保留，勿与旧52/19或不同训练队列直接比总指标。
- **下一步**：只对10cal已存预测与past容量做一个固定20cycle容量反馈代理诊断，检验预测时可观测信号能否对应持续有向RUL误差，再决定是否设计因果个体修正；0fit、0dev/test读取，不使用目标电池真实RUL作为在线反馈、不事后调阈值。全局尺度路线关闭，训练总门仍false。

| 指标（电池等权） | A训练残差尺度 | B留出电池尺度 |
| --- | ---: | ---: |
| Time-MAE（cycle） |43.6443826005|43.6443826005|
| 80%覆盖率 |0.8338286900|0.9129772224|
| 80%区间宽度（cycle）|136.66182696|184.42030907|
| 80%区间评分（越小越好）|202.94483221|210.66912674|
| Brier100 |0.0157817647|0.0177118574|
| Brier300 |0.0693575882|0.0708817389|

概率输出完整定义为lognormal(mu_log_RUL, sigma)：各角色CSV保存mu与真实评价标签，fit_parameters保存两个sigma；由此可复原每一分位数/CDF/风险。中位数exp(mu)相同，不将提高覆盖率单独当收益。独立重算使用Python NormalDist/erf，与runner scipy分开。
每cell所有origin等权、再cell等权。留出10颗从原official train选出；是对当前模型的训练留出，不能抹去整个研究中的历史开发暴露。没有conformal/单cell条件覆盖保证。
两个困难cell b2c47/b4c33 coverage仍仅56.61%/59.11%，11颗却>95%；平均覆盖率掩盖异质性。两cell偏差分别-90.126/+89.355cycle，统一放宽不能修正方向。
复现命令（已消费，一般只运行独立重算和解码）：指定Python执行本目录runner.py，原始一次账本/GO/claim保留；禁止覆盖或重跑。模型HGB固定150轮、leaf7、depth3、lr.05、minleaf50、L2=1、seed42；输入age/SOH/past20稳健速率，无额外长期速率、神经/PBT或测试。

下一诊断仅是代理假设：以s=t-20时点预测剩余寿命，把到0.8SOH的变化作线性外推，得到t时点容量代理；再与实际已观察容量比较。这不是模型已训练的容量预测，线性退化假设必须注明。真实RUL残差只作回顾性评价，不能进入在线更新。
