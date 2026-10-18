# 生成容量轨迹首过80%：失败与训练端点覆盖修复
## 2026-10-18：真实first-passage rollout失败，已实际修复训练端点标签覆盖
- **已完成**：freshGO复用自训checkpoint一次，0fit，对10cal4567前缀作固定20step/2000cycle首过预测；100batch/75031row forward，191noncross，原gateFAIL。随后只审42fit源数据，确认原容量训练遗漏EOL及之后840个合法target；新建端点标签DataV2，22281pair，未修改任何旧结果。
- **证据**：experiments/capacity_firstpassage_seed42_v1/RESULTS_ZH.md、protocol/ROOT_GO/completion/calibration_predictions/independent_metrics/comparison/training_endpoint_coverage；审查reports/capacity_firstpassage_review_20261018_luna/review.json SHA634ecb543db58e6e770b3878bdd58f19daeea84b9c76820e9cb98f99789c64fe。新data/processed/capacity20_endpoint_targets_v2/fit_pairs.csv SHA47fb353d8788c74b515a10bbd250c6b93ed7393cfcc0df6faf44f7067cb1f679及manifest；构建automation/bin/build_capacity20_endpoint_targets_v2.py。
- **最小验证**：独立CSV重算差1.42e-14、保留全部4567；不读取真实未来作为rollout输入。42训练cell源hash一致，21441旧preEOL target逐值差0，新增42target在EOL、798target在EOL之后，全部真实存在且有效；输入只到s，未来s+20容量仅监督label，target_phase绝不能进入特征。新标签构建0fit/forward，未读calraw/dev/test。
- **阻塞/风险**：原directRUL TimeMAE58.113698；rollout139.206680只是包含191个2000cycle非端点下界cap的全样本诊断分数，不是有效完整point MAE；5/10改善，193前缀未来age越训练source范围。短期容量PASS未变，长程首过FAIL。EOL训练域缺口已证实，但补齐是否修复rollout尚未证明；生成线性轨迹/外推假设和既有cal暴露仍限制结论。
- **下一步**：新端点target数据下仅1CPUfit的匹配v2（同42fit/10cal、相同HGB/seed/20step/100call），一次窄审+fresh exactGO后立即执行容量比较及同10cal首过比较；不得再训v1或调horizon/强制下降。新fit回答标签覆盖修复，不是已消费预算重跑；0dev/test，保留所有noncross与原始EOL。

本阶段没有新增fit。self-trained auxiliary checkpoint SHA5022a619e9cc86c725be57faabc8ab0a191e084d58c342f67ac303f6fb9ea006只加载一次（Python3.9/numpy1.26.4/sklearn1.6.1验证后），模型生成未来容量和斜率，绝不读取未来真实容量/RUL作为输入。默认本轮forward预算已消费，不重跑。
191noncross约占4.18%；未删这些原点，所有诊断分数均保留。noncross cap只是已生成2000cycle未跨阈值的下界，不是合法的终点预测；不能用139.21和58.11的差当作正式可比预测误差结论。gate已因noncross直接失败。
原辅助预测runner明确t<event，故21441训练target全部早于首次80%事件；原容量预测PASS只代表此域。实际读取42fit已有raw-derived cycles CSV后证实，每颗都还有事件行与至少19个后续有效容量记录。以同一preEOL source输入补齐future20 target，新增840，不改变旧21441target值（差0）。监督label可以在训练电池的未来，输入不可以；标签的phase仅审计不得成为模型特征。postevent观测未强制单调、未改EOL来求通过。
新数据已完成，模型未开始。下一匹配fit将只改变训练target覆盖范围，其余模型/seed/输入/rollout规则不变；评价10cal已经暴露，不是独立确认或条件RUL分布完成。
