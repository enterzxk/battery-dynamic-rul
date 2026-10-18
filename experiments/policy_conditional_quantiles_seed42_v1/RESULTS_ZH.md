# 已知工况匹配条件分位数：真实2fit，NO_GAIN

本轮补齐当前最强点模型相同7输入下的强区间基线：42fit/22281时点，固定HGB q=.1/.9两个logRUL模型；复用已有工况点预测exp(context_RUL_raw_log)，不重训中位数。输入为age/SOH/原单位past20稳健rate及4个已核静态工况effective-C；同10cal4567时点，电池等权。旧三状态分位数fits和GO仍已消费，不重跑。

| 原始输出评价 | 固定sigma区间参考 | 工况独立分位数 |
|---|---:|---:|
| Time-MAE，循环 | 36.400814 | 36.400814，点不变 |
| 端点间覆盖，全部4567/电池等权 | 78.50162% | 59.35231% |
| 逐电池绝对80%覆盖误差均值 | .213265 | .226177 |
| 全时段有效区间得分 | 148.489249 | null，存在端点倒置 |
| 与固定中位数或端点顺序冲突 | 0 | 512 |

217个时点q10>点预测，304个q90<点预测，56个q10>=q90，集合重叠后512个冲突。原始端点覆盖中的倒置时点计不覆盖，不删除分母、不排序或clipping。只有5/10电池覆盖误差改善。raw formula值191.835875及其配对差CI[-91.097562,3.910393]只为诊断，绝不能称为有效全时段区间得分/收益；端点差均值99.029678也含倒置，不能据此声称合法区间更窄。冻结gateFAIL，NO_GAIN，停止此独立端点方案，不换seed/参数/分位点救援。

失效定位已做为本轮结果检查：56个端点倒置中b2c41有52、b2c6有3、b2c21有1；真实剩余寿命范围136..356循环，53个在100..300、3个>300，0个<=100。它并非只发生在临近EOL端点；未来真RUL分段只用于事后诊断，未作输入或触发条件。

授权/证据：独立窄审reports/policy_conditional_quantiles_review_20261019_luna/review.json SHA d32faa5912add79595b8295e361fd625bc02137581adf525db2d3f500a699e27；ROOT_GO绑定3项实算SHA及review。fit_ledger真实2start/2complete，1线程180秒预算，实际不足1秒；两checkpoint只服务器保存。原始预测SHA f40d8f0469f2386f3824d619fe5d4fab12439fa6a0c9300ee566e7ca96276cd7，prediction_delta.json保存两列rawlog浮点无损增量，decoder字节核对通过。

最小验证：全部4567原CSV用独立math/statistics重算，最大指标差2.84e-14，四类crossing计数逐值一致。2CPUfit、2次cal predict各4567行，0optimizer/checkpointload/新标量估计/dev/test。累计新科研CPU16=RUL14+辅助2；神经4fit2580steps、旧MATR41另记，所有旧GO不重置。

当前新gate在任何fit前冻结逐电池覆盖误差均值改善>=.03，并要求总体覆盖误差不增加；原因是原参考总体覆盖已78.5016%，总体绝对误差仅.0149838，不可能再改善.03。它是新匹配输入对照的规则，不追改旧实验门槛；当前即使不看crossing，平均误差和总体误差也恶化，未形成收益。cal已暴露/event-only/来源ID非物理独立/完整sourceSHA缺证/固定实验室工况限制全部保留，不称独立确认、创新或完整CDF。三个分位点本就不确定Brier概率，未编造该指标。

下一步转向一个统一经验CDF参考，避免把无序端点修成结果：只在42fit中冻结3折电池隔离OOF、固定原7feature HGB参数，每cell只由未包含自身的模型预测一次；最多3新CPUfit且须独立窄审+fresh exactGO。用等电池OOF log残差经验CDF并一次中位数居中，使原policy点预测不变，再对已存10cal mu作解析评估，无新cal推理。原训练内sigma乐观问题有实证，OOF是改变残差证据来源，非重训恢复旧checkpoint；不承诺条件覆盖或conformal保证，减少每fold训练量也须报告。当前尚未开始或授权这3fits，0dev/test。
