# 工况模型自身训练残差尺度：NO_GAIN

问题是上一轮共用旧三状态sigmaA是否造成工况模型概率失配。本轮复用已训练工况checkpoint，一次仅42fit/22281时点predict，估计一次sigma=max(.05,sqrt(42电池等权平均的log残差均方))；不重新fit，也不对cal做模型推理。新sigma=0.15480400973451397，旧sigmaA=0.19898311654196568，比值0.7779756013。训练内残差可能乐观，不能视为独立校准。

| 同一工况mu、不同尺度 | 旧sigmaA | policy自身fit sigma |
|---|---:|---:|
| Time-MAE，循环 | 36.400814 | 36.400814 |
| bias，循环 | -3.523895 | -3.523895 |
| 严重高估>100循环 | 4.25825% | 4.25825% |
| 名义80%覆盖 | 78.50162% | 66.71529% |
| 80%宽度，循环 | 116.169090 | 89.992210 |
| 80%区间得分，循环 | 148.489249 | 155.088652 |
| Brier100 | .01401752 | .01273099 |
| Brier300 | .05651083 | .05694456 |

区间宽度缩小22.5334%，区间得分恶化4.4444%，覆盖减少11.7863个百分点；仅4/10电池覆盖误差改善。平均两horizon Brier略改善0.0004264，不能抵消区间与覆盖恶化。预先声明的尺度诊断screen FAIL，NO_GAIN。两个分布的中位数逐时点完全相同，原工况点收益保留；此前正规早期vs动态的风险护栏FAIL、全部概率联合FAIL也保留。不在cal调sigma、换分位/偏置或加seed救结果。

授权与执行：reports/policy_fit_scale_review_20261019_luna/review.json独立窄审PASS，SHA451fcf88eb9232017c32e3c520e35a1eed659ba1cae5359017ae2d185fcb07f3；ROOT_GO精确绑定runner/protocol/cohort/原点模型protocol四hash及review。checkpoint SHA97241e1c5966d179a23902270993c0de5f84c5c3e6de2cb3798ec41728efe541与原真实fit completion一致，只在服务器读取，未公开。0fit/optimizer，1checkpoint load、1predict/22281fit rows、1scalar、0calforward/dev/test，180秒预算内完成。

最小验证：AST确认无fit调用，单predict/单pickle.load；独立标准math/statistics重算全部22281训练残差和4567cal评估，sigma逐值一致，指标最大差1.99e-13。fit_residual_predictions_lossless.json无损保存22281条训练标签/新预测四列，可由decode_fit_residual_predictions.py解包；字节SHA核对通过，既无原始容量/曲线数据，也无checkpoint。原始全列预测仍保存服务器fit_predictions.csv，SHA97d11dd456fe2836160010f7112fe5bc69572b96a9179018fc061fee168f95b4。

审查元数据有一项日期/时区错误：review自填UTC晚于实际工具交付和GO。原review/hash保留，review_timestamp_annotation.json注明真实执行顺序为先收到独审、核状态及四hash、再签GO和运行；不以该错误时间戳证明授权先后，也不重跑。

限制：10cal多次暴露，仅开发；event-only、物理serial/fullsourceSHA缺证、固定实验室policy可用性边界保留。本轮排除了一个具体修复假设，不能证明所有不确定度方法无效，也不能将较宽旧sigma选择为正式校准成功。

下一项仅已有预测的强简单更新基线：固定alpha=2/21、origin100初始化的绝对EOL因果EMA，对比未平滑动态Time-MAE/严重高估/更新延迟。只有当前或过去模型输出进入递推，真误差不进入在线回滚；固定20记忆沿用现有窗口，不搜索alpha/window，不fit/推理/估新尺度/dev/test，不当概率模型或创新。回答风险是否可由简单平滑改善，若失败即停止本固定对照。

复现：/home/yndx/miniconda3/envs/a40_env/bin/python experiments/policy_fit_scale_seed42_v1/runner.py 为一次性已消费GO，禁止重跑；指标只运行independent_recompute.py时也须另设create-only输出，避免覆盖。累计科研CPU14=RUL12+辅助2不变，神经4fit2580steps与旧MATR41另记。
