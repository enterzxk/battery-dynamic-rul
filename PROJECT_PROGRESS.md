# Battery Dynamic RUL — 当前进度入口

本文件于 2026-10-17（北京时间）首次建立，补充现有交接与真实结果，不替代历史记录。科学状态以 `automation/state/coordinator.json` 指向的最新交接、票据和落盘结果为准。

## 2026-10-17：执行效率规则与额度恢复续接

- **已完成**：将用户提供的七部分《Codex 执行效率与最小验证规则》完整加入 `/home/yndx/zxk/rul/AGENTS.md`，保留旧约束并注明新规则冲突时优先；创建 `agent.md -> AGENTS.md`。创建并启用绑定当前对话的每小时额度检查/继续研究任务 `battery-rul`（Battery RUL 额度检查与继续研究）。本阶段仅修改指令与调度设置，`new_fits=0`、`optimizer_steps=0`。
- **证据**：安装回执 `/home/yndx/zxk/rul/automation/control_updates_20261017_efficiency/installation_receipt.json`；旧指令备份同目录 `AGENTS.before.md`；新增规则原文同目录 `execution_efficiency_rules_20261017.md`。更新后 AGENTS SHA256：`1e2ce2ad47b40c85522eb5a0b2fed9d827e5fca8a737b63a1cdb7c4c9790ceb8`。应用调度接口返回 `automationId=battery-rul,status=ACTIVE`。设置时额度接口返回 `ordinaryUsageAllowed=true`，5 小时已用 2%、周已用 0%；这是设置时观测，后续必须实时查询。
- **最小验证**：已验证原文件 SHA 与修改前一致、原文完整备份、七部分补充逐字节写入、两个入口内容相同；已核当前交接 SHA `7f582b822075dded2cd32cec5760519081bc5388b8e024d7c9984736285e1549` 与 coordinator 声明一致，并读取 `./rul.sh status`。无需模型测试。
- **阻塞/风险**：当前 coordinator 仍为 `READY_FOR_SUCCESSOR`，`new_fits_allowed=false`；设置定时任务不代表已完成科研接管或开放训练。最新交接 `/home/yndx/zxk/rul/docs/COORDINATOR_HANDOFF_20261017_V7_ZH.md` 记录 PBT 的 15 电芯 valid_cycle_number 证据缺口及其他受限阶段，须按最新票据处理。每轮检查真实锁、进程及预算，防止与现有 BatteryRUL-Controller 或其他主控重复执行。额度不足/未知时不启动科研；认证失败如实报告。定时唤醒依赖本机应用及连接可用，尚未观察到首轮自动触发。
- **下一步**：下次唤醒在额度可用且确认无活跃主控后，按当前交接完成锁内接管，从 `/home/yndx/zxk/rul/reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json` 读取缺证票据，推进 15 电芯 valid_cycle_number 缺证的下一项获准动作；只补确实缺失的关键证据，满足既有科研门槛后立即进入已授权的最小真实实验，不重复旧静态审计或 smoke。


## 2026-10-17：GitHub 公开镜像与 GPT 阅读入口

- **已完成**：用户明确选择公开仓库 `enterzxk/battery-dynamic-rul`。实现白名单文本导出，提供 `docs/CHATGPT_CONTEXT_ZH.md` 中文项目解释入口和 `docs/GITHUB_SYNC_ZH.md` 同步规则；已将每阶段更新/补同步接入现有每小时任务 `battery-rul`。此阶段没有训练或模型推理。
- **证据**：`automation/bin/export_github_context.py`；导出清单 `automation/github_export/public_snapshot.json`；待上传内容 `automation/github_export/bundle.json`。清单列出实际导出的文件路径、大小与原始 SHA256，包含真实开发结果和 validation 预测。首次发布成功后的提交 SHA/URL 与回读记录以 `automation/state/github_sync.json` 为准；该文件缺失或 status 非 SYNCED 时不能报告上传成功。
- **最小验证**：已在真实服务器运行一次导出；白名单路径/文本大小/UTF-8/常见凭据格式检查通过。没有读取原始数据、checkpoint 或论文全文，没有重跑 smoke 或训练。
- **阻塞/风险**：仓库创建阻塞已由用户手工创建解除；公开性、写入权限和 main 分支已核对，首批上传并回读成功。每小时任务依赖额度、应用、网络与授权可用。公开镜像只代表清单时点，清单之外引用的服务器材料没有自动公开。
- **下一步**：按科学主线解决当前最早真实阻塞；每个实质阶段完成后同步新进度和证据，无变化不提交。

首次发布回执：215 个文件已更新到 main，三个关键入口回读逐字一致。提交 [865a6037039b](https://github.com/enterzxk/battery-dynamic-rul/commit/865a6037039bc66ae3df653c117c107fc2b79342)。后续同步以 `automation/state/github_sync.json` 与仓库最新提交为准。

## 2026-10-17：41篇精读结论与后续方向讨论稿

- **已完成**：综合41篇已接纳主文的活动精读笔记、独立审查与主控附注，形成详细讨论稿、41篇逐篇附录和结构化证据。优先建议检验“当前状态/年龄之外的近期速率及历史信息增量”，其余候选为可靠性更新和匹配资源的迁移比较；均为待验证假设。本轮没有新读全部原文，也没有训练。
- **证据**：`reports/literature_discussion_20261017_root_v1/LITERATURE_DISCUSSION_ZH.md`、`PAPER_BY_PAPER_ZH.md`、`paper_evidence.json`、`manifest.json`。保留源文冲突、负面结果、版本及SI范围，作者报告与项目开发实测分开。GitHub提交与回读结果见 `automation/state/github_sync.json`。
- **最小验证**：41个unique paper_id、41个逐篇条目与活动精读SHA对应通过；源记录中独审/源附注绑定已核。主稿中的已有开发指标核对现存CSV，不重算或重训。P05旧主文record中的SI待修文字已标历史，单独SI接纳不增加主文篇数。
- **阻塞/风险**：这是一份对既有证据的讨论综合，不是完成50篇系统检索/综述、创新性确认或新增实验授权。当前其他活跃主控继续其既有任务；本轮不接管、不改训练/数据读取门槛。最新V8仍仅接纳合成helper，真实valid-cycle采集及模型运行未获GO。
- **下一步**：与用户/网页版GPT优先讨论方向A的最小合法信息增量对照；实际执行仍先关闭现有科学主线最早阻塞，再按获准协议推进。本轮 `new_fits=0`、`optimizer_steps=0`。


## 2026-10-17：本地指令与长上下文自动接续

- **已完成**：本地根目录建立agent.md及同内容AGENTS.md入口，写入475k上限/465k准备阈值、压缩提前交接、fresh对话创建、任务实际迁移和验证规则；现有battery-rul更新为ACTIVE每15分钟检查，保留额度恢复、未完成科研推进及GitHub同步。
- **证据**：本地 `.control/CONTINUATION_POLICY.md`、`.control/CONTINUATION_STATE.json`、`.control/read_context_status.py`；远端 `docs/CONTINUATION_POLICY.md` 与AGENTS第9节。状态文件记录最近输入token/窗口/压缩元数据，累计消耗量只用于成本语义。
- **最小验证**：当前会话真实元数据读取成功，窗口475000、设置时输入约308k、压缩0；本地两个指令入口核同内容，任务配置回读核每15分钟、ACTIVE和当前target。阈值未到，本轮未创建新聊天，不冒充已验证跨聊天迁移。
- **阻塞/风险**：定时唤醒依赖应用、账号额度和服务器连接；没有实时采样硬中断钩子，准确占用缺失记UNKNOWN。五小时恢复按实际resetsAt与可用查询判定，不保证额度耗尽期间还能运行。其他科研owner保持不变，现有训练/test门不解锁。
- **下一步**：按每轮及定时检查继续未完成的获准工作；触发465k准备/实际压缩后才创建并验证fresh接续，同时实际迁移现有heartbeat。无待办则根据最新进度选择最早真实阻塞。本轮new_fits=0、optimizer_steps=0。

## 2026-10-17 15:31 UTC：按用户交接推进PBT真实读取与动态RUL候选

- **已完成**：用户交接原样存入docs；锁内接管后只推进两个有界动作：PBT首分片一次真实结构读取，以及既有MATR文本数据上的动态信息增量候选表。PBT读取2250966字节触发entry_cap停止，未取得valid_cycle_number；MATR 544时点中530工程候选，99train/34val，未新读binary/test摘要。本轮新增predictive fits=0、optimizer_steps=0。
- **证据**：`docs/Battery_RUL_Codex_Handoff_20261017_ZH.md`（SHA96486eb216e711c1e32808717f94892def2e70da4dcf5b05ad372625e92e729a）；`reports/pbt_valid_cycle_production_io_20261017_luna/shard1.v2.receipt.json`（FAILED_STOP_NO_RETRY）；同目录root_review_v2/ROOT_GO/root_launch_receipt；`reports/dynamic_A_eligible_20261017_root/`候选表/冻结候选配置/源SHA；待执行`experiments/dynamic_A_matr_retrospective_seed42_v1/runner.py`。
- **最小验证**：PBT复用已核helper，root仅审修复后的worker授权入口并绑定三项SHA；实际执行一次失败即停止，没有重跑旧smoke。MATR按既有拆分提取train/val、已知别名合并与错移电池排除，保存前缀范围和来源。候选表不是模型性能证据。
- **阻塞/风险**：首分片一次性预算已消费，不扩entry cap或切分片重试；PBT模型运行仍未开放。MATR实际v11生成器与其余物理serial未知，strict_online_eligible=0，只可经独立窄审判定回顾性工程诊断资格；原严格动态训练/test门保持false。明确上下文压缩已发生，正在事务交接，不宣称未验证的迁移成功。
- **下一步**：在fresh接续对话核候选protocol+runner一次，若隔离工程lane可接受，立即执行A0/A1/A2同cohort CPU Ridge对照并交付逐电池预测/Time-MAE；39次fit含CV，上限41次含条件固定GBDT。当前不冒称实验完成。接续入口为`docs/COORDINATOR_HANDOFF_20261017_V9_ZH.md`。


## 2026-10-17 15:40 UTC：方向A首次真实信息增量对照完成（回顾性工程lane）

- **已完成**：V9 fresh接管、同一battery-rul迁移和项目/cwd/active核验完成。独审PASS_RETROSPECTIVE_ONLY后root签发exact SHA GO，一次执行A0/A1/A2及条件固定GBDT；39 Ridge含CV+2GBDT=41 fits，optimizer_steps=0，test未访问。
- **证据**：`experiments/dynamic_A_matr_retrospective_seed42_v1/RESULTS_ZH.md`、`validation_predictions.csv`、`completion_receipt.json`、`independent_metrics.json`、`root_decision.json`与fit_ledger；独审`reports/dynamic_A_matr_retrospective_independent_20261017_luna/review.json`。全34作者EOL Time-MAE：A0 151.9080、A1 152.5449、A2 148.4576；GBDT A1 159.6220、A2 153.7740。
- **最小验证**：从全部原预测独立复算全34及观测19的cell-macro MAE/bias、paired改善比例、年龄层和尾部；全部匹配，41开始/完成账本匹配。未加smoke或重复训练，旧CP2fits/600steps未混记。
- **阻塞/风险**：判NO_GAIN_FOR_COMPLEX_HISTORY_EXPANSION_ON_THIS_DIAGNOSTIC：Ridge增益2.679%/21of34，GBDT3.664%/18of34且bootstrap跨0；未达约10%推进幅度。观测19 Ridge增益5.144%仍不足。尾部未一致改善。v11实际生成器/其余physical serial未知、strict_online_eligible=0，容量权限为完整循环测量；全34含15作者外推标签，不能称严格在线或独立泛化。PBT已消费entry_cap失败不重跑。
- **下一步**：仅用现有逐电池预测诊断高误差删失电池与作者外推标签偏差，不启动复杂历史模型/新seed或新增fit；阶段公开同步以`automation/state/github_sync.json`核回读为准。


## 2026-10-17 23:47 北京时间：已有预测的删失误差诊断

- **已完成**：仅分析15个删失电池的现有validation预测及哈希绑定文本metadata，未新fit。前两大误差电池占全34电池A1等权绝对误差的43.68%；其作者EOL较末次观测仅多2/-1循环，A1低估误差下界为1379.39/884.87循环。不能把大误差单独归咎于长距离尾段外推，也不证明作者标签/生成器有效。
- **证据**：`experiments/dynamic_A_matr_retrospective_seed42_v1/censored_failure_diagnosis.json`、`CENSORED_FAILURE_ZH.md`；保留逐cell来源SHA和预测SHA。
- **最小验证**：15份metadata SHA与原cohort一致，每模型每电池4时点；低估下界不当精确EOL，不改主指标。
- **阻塞/风险**：strict_online/physical serial/generator限制不变，PBT一次预算消费不重跑。普通额度本轮已用97%，真实重置timestamp1792264349；恢复仍需实查。new_fits=0、optimizer_steps=0。
- **下一步**：只用已有文本比较两大长寿命离群电池的早期特征训练支持范围；不改标签/删电池/新增fit。

补充标签边界：MATR_b3c38作者EOL=1932，但完整文本记录存活至1933且nominal crossing未观测；存在1循环边界不一致，需核已有标签算法的外推/取整语义。不得把作者标签当精确真实EOL，不修改或删除既有结果；下一动作优先核此边界，再看训练特征支持。


## 2026-10-18 03:20 北京时间：额度恢复后完成标签边界与特征支持诊断

- **已完成**：实查额度从已用100%恢复至4%，核owner/交接SHA/真实进程无冲突后继续保存动作。解释b3c38回归浮点1932.623本身小于末次观测1933，int再截至1932；检查两只长寿命离群电池8个早期时点的训练特征支持，未新fit。
- **证据**：`experiments/dynamic_A_matr_retrospective_seed42_v1/LABEL_BOUNDARY_SUPPORT_ZH.md`、`label_boundary_feature_support.json`、`label_boundary_support_diagnosis.py`；绑定原预测/标签审计/源码SHA。
- **最小验证**：已存回归值int后吻合作者标签，源码SHA匹配；133个合格源ID标签记录、每k训练角色特征范围和feature-only同batch邻居。没有重跑回归或smoke；new_fits=0、optimizer_steps=0。
- **阻塞/风险**：47训练/15验证尾段回归标签中41/11个不晚于观测末端，不能当真实未来事件；两个大误差电池EOL2237/1932均超过训练最大1834，但早期特征均在全训练边际范围内，边际包含不能证明联合支持/可预测性。v11生成器、物理serial、PBT/test门保持原限制，NO_GAIN不变。
- **下一步**：仅用既有预测按训练寿命支持范围内/外及观测/删失分解误差贡献，不改标签/主要指标或新增fit。


## 2026-10-18 03:34 北京时间：固定人口误差分解与batch混杂

- **已完成**：从已有预测完成训练寿命范围内/外、观测/删失及交叉组的误差贡献分解。超训练范围两电池占A1绝对误差43.676%，但仅占Ridge速率净改善11.662%；范围内32电池Ridge/GBDT速率增益4.202%/3.989%，NO_GAIN保持。
- **证据**：`experiments/dynamic_A_matr_retrospective_seed42_v1/ERROR_CONTRIBUTION_ZH.md`、`error_contribution.json`、`batch_observation_cross_tab.json`及两份可复算诊断程序。
- **最小验证**：3种划分均覆盖同34电池/136时点；每组加权贡献重构全部5模型原始MAE（<=1e-8），原预测SHA吻合。new_fits=0、optimizer_steps=0，无binary/test。
- **阻塞/风险**：合格训练/验证中batch1/3全部未观测事件、batch2/4全部已观测，观测/删失误差差异与batch完全混杂，不能归因为标签或删失单独效应。作者标签/strict_online/physical serial/generator限制及PBT/test门保持。
- **下一步**：仅查已有各batch末次容量、观测终止位置与pinned标签分支的可证对应，解释混杂的边界；不猜实际生成器、不改阈值/标签/人口或新增fit。


## 2026-10-18 03:48 北京时间：各batch终点核对与方向A诊断闭合

- **已完成**：核133个合格train/val源ID末次SOH、事件可见性与标签分支。batch1/3末端SOH约0.8000..0.8030无crossing，batch2约0.7500..0.7523，batch4约0.2282..0.7624。全部71个观测事件电池在首次crossing后仍有记录；验证batch2/4分别保留20..37/23..273循环。方向A诊断链闭合为NO_GAIN，不追加seed/模型或阈值救结果。
- **证据**：`experiments/dynamic_A_matr_retrospective_seed42_v1/TERMINAL_BOUNDARY_ZH.md`、`terminal_boundary_diagnosis.json`、`terminal_boundary_diagnosis.py`、`diagnostic_closure.json`。
- **最小验证**：133份metadata SHA与原cohort吻合，末SOH与旧标签审计差<1e-12，observed标记与crossing存在性相符；仅已有文本，无cycle曲线/binary/test摘要读取，new_fits=0、optimizer_steps=0。
- **阻塞/风险**：可证processed-record终点差异，不能推断原始采集停止或实际v11截断/插值机制。实际generator commit/config与完整physical身份未核；pinned源码及标签重建不是来源证明。原PBT消费预算和模型/test门保持。
- **下一步**：仅做一次官方MATR_v11发布metadata的generator版本凭证核查，不重复下载数据或反推；若发布记录未给出，则记录缺证STOP。


## 2026-10-18 04:04 北京时间：MATR v11官方来源核查（有界STOP）

- **已完成**：查官方Zenodo v11页及链接的Version11说明。发布身份/日期和MATR.zip MD5与旧下载回执一致；MATR具体更新为b3c0 seen/unseen分类，已读材料未给出归档精确generator commit/config绑定。
- **证据**：`reports/matr_v11_release_provenance_20261018_root/PROVENANCE_CHECK_ZH.md`、`web_source_observations.json`、`acquisition_receipt.json`、`root_review.json`；官方URL在报告中。
- **最小验证**：MD5比对旧已核回执、pinned版本说明SHA留存；没有重读归档/下载数据/new fit或test。new_fits=0、optimizer_steps=0。
- **阻塞/风险**：完整API metadata未取得；web工具不可访问API，服务器一次API请求DNS临时失败，不改DNS/代理、不循环重试。只称已读HTML/更新说明未发现绑定，API字段UNKNOWN，不能声称全metadata缺失。STOP_ACTUAL_V11_GENERATOR_PROVENANCE_NOT_CLOSED，方向A闭合NO_GAIN与旧PBT/模型/test门保持。
- **下一步**：转P1只读已有CP完成回执/冻结配置/checkpoint清单与stat，判断独立预算下的忠实复现可推进性；不加载checkpoint、不重跑fit或重置旧600步，不启动训练。


## 2026-10-18 04:21 北京时间：补同步与P1检查点接续判定

- **已完成**：上轮MATR来源核查已补发布并回读，提交2e794b2758a3f33839918e7b1bb5f7c6712a8d3f。核已有CP两次运行：各300步=146+146+8批，checkpoint003是partial epoch3，旧剩余预算0；不能自动resume。已形成一个独立HUST官方配方适配候选（DRAFT，不是新训练）。
- **证据**：`reports/p1_cp_checkpoint_inventory_20261018_root/P1_CONTINUATION_REVIEW_ZH.md`、`inventory_review.json`、`next_cpmlp_recipe_candidate.json`；旧完成回执/账本/源代码/配置SHA与checkpoint stat对应。
- **最小验证**：两份runner/config SHA与完成回执一致，300步账本连续，checkpoint事件146/292/300与epoch批次146/146/8匹配；只读源码/JSON/stat，未加载checkpoint、构造模型或fit。new_fits=0、optimizer_steps=0。
- **阻塞/风险**：源码保存模型/Adam/RNG但无batch排列/游标，且旧completion与预算门禁止恢复。不能把文件名epoch003当完整epoch。旧pilot的HUST/seed42/LR3e-4/执行方式不同于官方CALB或MIX脚本，不能称全论文复现。
- **下一步**：创建一个独立CPMLP适配runner/config（LR5e-5、官方早停patience5且least_epochs5、诚实partial标记）；一次停止/保存边界检查后root判exact GO，旧结果/600步预算不动。


## 2026-10-18 04:43 北京时间：CPMLP真实完整配方适配运行完成（负面结果保留）

- **已完成**：独立runner实现与窄审后执行一次真实CPMLP HUST作者EOL配方适配，10完整epochs/1460steps，early-stop完成，选epoch3；MAE194.0073、MAPE0.10136755，比旧pilot177.3831差9.3719%，6/15电池改善，无性能增益。
- **证据**：`experiments/cpmlp_hust_recipe_adapt_seed42_v2/{RESULTS_ZH.md,completion_receipt.json,independent_metrics.json,validation_predictions_epoch_003.csv,root_result_decision.json}`，`results/development_hust_cpmlp_recipe_adapt_seed42_v2.csv`；独审`reports/p1_cpmlp_recipe_review_20261018_luna/review.json`。
- **最小验证**：停止/partial逻辑与修复deadline边界定向检查；未重复旧smoke。已选1500条预测独立复算吻合，1460连续步/10个完整验证epoch。v1缺batteryml启动失败fit0/step0保留，v2只改目录/使用已有项目环境，未扩大1fit预算；实际wall126.79s<1200s。
- **阻塞/风险**：HUST/seed42/singleGPU/val-only为配方适配偏离，非CALB/MIX完整论文复现/strict在线RUL。旧600步与MATR41CPU fits分开，新神经训练累计2060steps；新旧配方/初始化顺序/时长改变，不能孤立归因学习率。PBT/test/物理身份和生成器限制保持。
- **下一步**：只用既有新旧预测分析误差上升的电池与早期prefix位置；不换seed/模型或追加训练救分。


## 2026-10-18 04:52 北京时间：CPMLP已有预测的配对误差分解

- **已完成**：V10锁内接管并核同一battery-rul已绑定；按file_name/prefix_index对齐旧epoch2和新epoch3的15电池/1500验证预测。MAE177.3831→194.0073，净增16.6242循环（9.3719%）；9电池恶化、6改善。恶化前三HUST_2-8/10-1/9-1占全部正向恶化74.4896%，全局贡献+34.9835循环；全部恶化+46.9644、改善抵消-30.3402。
- **证据**：reports/cpmlp_recipe_error_diagnosis_20261018_root/ 内 DIAGNOSIS_ZH.md、diagnosis.json、per_cell.csv、per_cell_prefix_segment.csv、paired_prediction_deltas.csv、diagnose.py。五个prefix序号段均恶化，21–60贡献净增60.3167%；全局bias -71.1230→-34.9644，但电池绝对bias均值158.0395→179.7695，正负抵消不等于改善。
- **最小验证**：两份源预测SHA匹配冻结指标，1500唯一键、15×100前缀、标签完全一致、文件名train/val隔离；cell/分段/交叉贡献均重构净增（误差<1e-8），原主指标吻合。new_fits=0、optimizer_steps=0、model_loads=0、test_access=false；未重跑旧独立复算/smoke。
- **阻塞/风险**：只作算术来源定位，不能孤立归因LR（初始化RNG/时长亦不同）；同15电池重复开发选模，不能声称独立确认、CALB/MIX完整复现或strict在线RUL。prefix_index按CSV序号，不新增物理循环/raw-asof认证。NO_GAIN与PBT消费预算/旧训练/test门均保持。
- **下一步**：只读现有逐epoch验证预测与epoch_metrics，检查冻结MAPE选模点相对各自MAE最小点的差异；不改选择规则、不重选汇报checkpoint、不新增推理/训练。
