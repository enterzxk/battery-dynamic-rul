# 固定20cycle容量反馈代理：未获支持
## 2026-10-18：容量线性反馈代理真实诊断失败，转向可验证的短期容量预测
- **已完成**：冻结20cycle公式后只对10cal已有预测及past容量计算4367时点；无新模型/前向/fit、无dev/test读取。信号方向平衡准确率37.2132%、电池内rho中位数-0.0910，仅5/10正相关；未通过预设筛选，关闭该线性代理修正路线。
- **证据**：reports/causal_capacity_feedback_20261018_root/protocol.json、diagnose.py、diagnostic.json、minimal_validation.json、root_decision.json、RESULTS_ZH.md；diagnostic_rows.csv仅服务器审计不公开。protocol SHA73f3bc3c81cbd7d9db5ccd67ed7f1592cb57ef670d6b4c07357266241d89f7e0，runner SHA2243e9c67f72a61296aee7e3ae60caeb5cc49c3188c0c8999e4c93930539e7b6。
- **最小验证**：单例SOH1.00→.98、旧RUL100的20cycle代理差+.02手算正确；10cell第一有效时点截断prefix后结果相等、源CSV/manifest/feature SHA一致、s=t-20<t。标签只用于回顾评价，从未进入反馈公式。没有重复smoke或改horizon/阈值救结果。
- **阻塞/风险**：九颗mean innovation>0而部分持续高估RUL，如b4c7信号+.005607却真实剩余误差mean-120.27cycle。相对实际容量变化/仅模型隐含项的rho增量中位数-.0423/-.5751；没有额外可用信息的证据。反复时点相关、短cell仅28点，不作独立统计确认；线性路径只是代理，不能当模型预测容量。
- **下一步**：改为先检验可被直接评分的20cycle容量预测：复用42fit/10cal，固定一个HGB预测SOH(s+20)-SOH(s)，与persist0和past20 TheilSen外推比较；独立窄审和fresh exactGO后最多1CPUfit。只在cal容量MAE优于两简单基线至少5%且>=6/10cell改善时才继续研究其反馈残差；否则关闭该辅助预测路线。此次不运行RUL修正、dev/test或旧模型重训。

公式在读取计算结果前冻结：
s=t-20，d_model=(SOH_s-0.8)*20/exp(mu_s)，innovation=SOH_t-SOH_s+d_model。
期望方向是innovation正→旧预测退化过快→RUL低估，但这需要假定从s到终点的容量路径近似线性。此路径不是一个训练过的容量预测。
回顾性评价y=true_RUL_t-exp(mu_t)，只用来检验信号，在线部署不可观测。
同一20cycle观察窗附加actual容量变化、model-only隐含下降量、age三个控制，以避免把共用模型预测或时间趋势造成的相关当新信息。

| 汇总 | 数值 |
| --- | ---: |
| cell等权方向准确率 | 47.3209% |
| 平衡方向准确率（9颗有正负两类） | 37.2133% |
| innovation rho中位数 | -0.0910 |
| 正相关cell | 5/10 |
| 相对observed-change的rho增量中位数 | -0.0423 |
| 相对model-only项的rho增量中位数 | -0.5751 |
| 冻结筛选 | FAIL |

最好常数方向的87.77%是使用标签得到的事后描述，不是可部署对照成绩；不能拿它冒充在线预测。b2c1只有28时点，b4c7误差全负，balanced指标按预先规则缺失并保留。不同电池差异完整见diagnostic.json。
没有产生新RUL预测或收益，不反转创新符号/挑horizon/调阈值。下一项用真实可评分的容量未来20cycle目标检验辅助模型能力，保持简单基线强度和独立cal角色，之后才决定反馈修正是否值得做。
