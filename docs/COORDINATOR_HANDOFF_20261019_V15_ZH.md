# Battery Dynamic RUL V15 fresh 接续交接

request_id=V15-second-compaction-20261019T013056Z；前驱thread=01a1508e-83e9-7232-a0e4-07606110b443。
V14第一次实际压缩2026-10-19T00:15:08.960Z已checkpoint；第二次2026-10-19T01:30:56.688Z、compaction_count=2已核。新聊天以自身只读元数据建立基线，第一次checkpoint、第二次才fresh；465000准备/475000窗口保障不变，累计cost不是上下文。此交接是控制迁移，不是新实验完成。

## 当前边界与接管
本地E:/桌面/rul根仅AGENTS.md/agent.md，Windows控制只.control；科研只SSH lab-server:/home/yndx/zxk/rul。Python=/home/yndx/miniconda3/envs/a40_env/bin/python，3.9、numpy1.26.4、sklearn1.6.1。主协调请求gpt-6.1-sol/high，独立必要窄审gpt-6-luna/high；不静默换模型，不自称独立内省运行身份。
每轮先get_usage_limits，仅ordinaryUsageAllowed=true且适用窗口未耗尽/无支出限制继续；本次codex primary50%/secondary86%、primary.resetsAt1792386909、spendControlReached=false。下轮重查；不付费/reset券/换账号模型绕额度。
读取本地四入口与STATE/本交接核SHA，再远端AGENTS、PROJECT_PROGRESS末尾、coordinator当前handoff/hash和next_bounded_action；复用./rul.sh status精简queue/process，不全库重读。保留Windows BatteryRUL-Controller。
前驱当前owner/thread=self、actual_cwd正确、takeover_verified=true；coordinator.lock和online_survival_cpu.lock均可独占，pending_experiment=null、global new_fits_allowed=false，旧队列141done/6needs_attention。只在两锁无冲突且owner仍self时释放为AWAITING_SUCCESSOR；新聊天核真实owner/心跳/进程，在coordinator.lock写自身owner/thread_id/heartbeat_utc/actual_cwd/takeover_verified。别的活跃owner不抢。
累计新科研CPU20=RUL18+辅助容量2，神经4fit2580steps，旧MATR retrospective41另记；所有旧GO已消费，不重训/加载旧checkpoint/扩大预算。PBT2250966byte entry_cap失败已消费，不重读/扩cap/换分片/model/forward/test。当前无有效待执行GO。

## 第一条未执行实际行动：固定20cycle观测上报延迟压力测试
此项尚未实现/冻结/窄审/签GO/运行，不能冒充已完成。问题是容量历史上报延迟20循环后，仅通过已知当前存活能否保留动态预测收益；不是之前已失败的容量残差门控诊断，也不重开recursiveEOL。
只用保存的lossless原点模型rawmu_(s-20)，最新容量历史可见through a=s-20；当前存活已知，对lognormal剩余寿命分布做 S_a(20+r)/S_a(20)，sigma固定既有.19898311654196568。不要重新模型推理、读checkpoint或rawfeatures，不再估尺度/权重/delay/seed。
所有比较臂统一s>=120的4367origin/10cal，a>=100；前20每cell总200行排除不补值。先冻结确切臂与判据（建议已存早期存活、当前动态、当前等权CDF、lag20动态及lag20等权CDF，最终以一次审查冻结协议为准），不能看新输出后换臂/门槛。当前三臂旧4567指标不能直接当共同4367指标；必须同键评分。真值只用于评分，不输入预测。
最小实现/合并键与公式定向验证，一次必要独立窄审，然后主控fresh exact hash 0fit GO，一次执行并交付。0新fit/学习模型构造推理/checkpointload/rawfeatures/devtest；不是训练许可。解析CDF计算须先门控，不以0fit绕过GO。
风险：旧sigma不是新模型独立校准、存活选择、已暴露10cal、未知物理serial/源身份、event-only、已知固定实验policy。结果只开发稳健性，不称条件覆盖/conformal/未知工况/独立泛化/创新已证。旧不可达coverage gate保持历史FAIL，新问题前置冻结解释性标准，不能追改旧结论。

## 最新实际成果，不要重跑
1. policy固定3fold OOF3CPUfit完成，随后policy局部5neighbor/age诊断均NO_GAIN/NO_GO；lossless schedule1CPUfit完成，研究CPU16→20。固定新point TimeMAE36.400814→33.027239改善9.2679%，6/10且paired CI跨0，NO_GO扩模型/seed。改善99.8365%来自b4c14/b4c29，b2c1变差，不解释成因果。
2. 纯动态存活分布 vs早期存活：10cal4567宏MAE33.027239 vs55.242118，但over100 3.1631% vs.2791%增2.884pp失败；b4c7精度改善同时严重高估23.7209% vs2.7907%。旧sigma不独立校准。
3. experiments/lossless_equal_CDF_mixture_v2：固定Fmix=.5Fsurv+.5Fdyn，真实完整CDF分位数；MAE35.452043，相对早期改善35.8243%，10/10、CI[11.107744,28.785172]，over100.6047%增.3256pp，点/风险开发PASS。vs动态MAE恶化7.3418%，风险减少2.5584pp。coverage83.31%、仅3/10覆盖误差改善，完整概率FAIL。旧宏coverage误差.748pp却要求降3pp数学不可达，保留旧FAIL，逐cell条件也独立失败。b2c1 mixturecoverage8.33%、b2c6 32.85%，不称个体可靠性。
v1曾在CDF前行序断言失败；v2仅cell/origin唯一键对齐修复，delta审查+freshGO，两GO消费。root_decision SHA92ab57f118497c828109c17289b3b869c36dda13a2af79d56b8f1f2337c34e4b。8列完整CSV服务器，public_quantiles_lossless.json/decoder精确保存三分位原字节；不要重跑。
4. reports/post_mixture_methods_conflict_20261019_root：已有P20 RUL-QMoE arxiv2512.23725v1 Methods §3–4/5.2–5.5/appendix、P40 arxiv2603.24475v1 §3.2.3主文公式读核；NO_GO_GENERIC_MIXTURE_OR_CONFORMAL_NOVELTY_CLAIM。分位池化≠CDFpool但差别不证明新颖，单步SOH覆盖≠首次EOL分布，submittedACC≠accepted；不扩41综述。
5. reports/delayed_capacity_reliability_20261019_root：已有s-20→s容量残差代理0fit诊断已完成，4367行原始正相关6/10、一阶差分6/10、同时4/10，冻结7/10失败；NO_GO_DELAYED_CAPACITY_RESIDUAL_GATE_FROM_CURRENT_DIAGNOSTIC。不重跑/调门控。根决策SHAdbe2eae86bd4ad68d8a0798f65dea42fb697ae3b194cef6dd8a31e393b3c921a。
6. experiments/causal_linear_threshold_fixed20_v1：同10cal4567、past20 TheilSen SOH/cycle解析(soh-.8)/(-rate)，实际全部有限。MAE1488.745941、bias+1488.659946、over10069.1636%、max109335.8353；9/10劣于动态/混合，b2c1例外4.988488。一次缺失解析顺序修复+delta窄审后0fitGO消费；不clip/rate/window/horizon救援。root_decision SHAc252aebca9845dc87d6f1533e2ed52e2c8031ef62dd8897fb1ed7a2eed37ba04。完整8列predictions.csv可复用四臂原始点，公开4列lossless包。
7. paper/EMPIRICAL_RESULTS_DRAFT_ZH.md v3，SHA dfb8eaf101273ae33405b7106607537c0e2209127039dfe3b37c8d90d7f42868。Results/Limitations、24源证据表，不是完整可投稿论文/新颖性证明。
8. paper/figures/empirical_reliability_v1：真实四面板已交付，a40条10cell四臂MAE配对，b三臂coverage，c/d完整b2c1 48origin与b4c7 430origin轨迹，log轴保留极端值/亚周期正值，无有利窗口/平滑。SVG SHA8383db6c2d0dd178f9d141ca0cebd3b74db2ba905bfc2d6092293cddd966252e，PDF+600dpiPNG服务器，SVG公开。alignment1.5ptPASS/fontmin6.2pt/collision0FAIL0WARN、彩色灰度复核完成，初版裁出亚周期显示问题保留_qa/initial_render，最终已修复，不重复QA。绘图不训练/推理/读features。
Naturefigure skill已用，Windows只.control/figure_qa_v1；remote _qa/deps内隔离PyMuPDF1.24.14依赖已安装，不改全局/重装；helper/wheel/deps不公开。这里只描述开发集，不作个体覆盖保证。

## 第一行动直接复用源与哈希
- experiments/policy_lossless_schedule_point_seed42_v1/calibration_predictions.csv SHA98a0ef87f4ab9ea2a9ff0588dbde2890f56768cae5be3585cba4510eeb55aa0c；核实际header的schedule_RUL_raw_log；旧policy context_RUL_raw_log不要混用。
- reports/lossless_survival_probability_20261019_root/derived_distribution_predictions.csv，13701三臂（lossless_early_survival_conditioned/lossless_dynamic/compressed_policy_dynamic_reference）；可复用旧三臂CDF来源，旧标签勿冒充新holdout。
- experiments/lossless_equal_CDF_mixture_v2/mixture_predictions.csv，SHA2874159abbe8bfbe3c03a434b5182c9472874d1994f1db67a3cac37c2e43e781；核实际schema。
- experiments/matr_raw_heldout_calibration_seed42_v1/fit_parameters.json SHAca95515be2d4977aa5160f9aa520acb996c6bd83eff5618ab72e8655f34711e5；cohort.json SHA42535de5825f6857e3aa69a596306a909a9a1b3ac087c43631032f6d293ef289。
70有效sourceID=52train+18dev，52train拆42fit22281/10cal4567；b4c31错位隔离。origin100..实际首次EOL-1，QDischarge<=.88Ah/nominal1.1Ah，trueRUL=event_cycle-origin，保留actualcycle。SOH率单位SOH/cycle非mSOH。18dev/test门不开。
DataV1 batch2manifest SHAfcbedb9ee4ea9da83efe3239cda3d56d629678b3dbbd90b675039f6456ad32c1；batch4 SHA862d796f8b1ba2d0d865884de1d77e32f2e7ce00480327299209d966c73bbe8e。不为本次压力测试重新读取features。
早期S0是cycle100的RUL分布，elapsed=s-100，不是totalage；延迟动态条件化d=20，不是把旧median直接减20冒充完整分布。

## GitHub与事务
当前已验证科学main=d6ff31a275d0adc31b07daf69527f19b43ffa7d1，tree07ec45f7e038947b9471064fa59b5def61be4224，snapshot内容SHA c9c042835c299ebf2b6f9e04ad76c9711c610c5714b430615325bd66c6f3073a，911源文件12536133bytes，12MiB cap剩46779bytes。当前无上轮未同步变化，新增交接另按同步回执核，不把导出当上传。
每阶段五项更新PROJECT_PROGRESS与CHATGPT_CONTEXT，执行automation/bin/export_github_context.py白名单，已连接GitHub基于最新main tree/createcommit/expected_sha+force=false，回读snapshot与关键入口才成功。当前public仅选定SVG，不上PDF/PNG/原始数据/checkpoint/全文/凭据/会话/原controllerlog。
多组完成静态/ledger/plaintext/eligibility/finite/CPTransformer与CPMLP预测已create-only无损归档，原服务器/旧Git历史保留。不要删除所有不在新manifest的远端文件；只删明确已归档替换的flatpath，不重压已有压缩包。cap不得扩大。
本次先保存远端交接SHA及同字节.control交接、requestID/真实阶段，再create_thread同rul项目local fresh请求gpt-6.1-sol/high，不fork；记录ID再迁移现有battery-rul，完整旧prompt保留并末尾添加V15最新状态，15minACTIVE不新建。回读target+list_threads项目/cwd/status、若接管再核远端owner字段；navigate打开新聊天，旧聊天停止派发但不归档。创建不等于迁移/接管成功，不预写VERIFIED；失败保留旧有效任务/已创建ID，下轮修复不重复创建。
