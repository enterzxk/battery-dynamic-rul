电池动态 RUL 科研项目：Codex 接续执行与额度恢复交接文档
交接日期：2026-10-17
适用项目： /home/yndx/zxk/rul
SSH 入口： 本地 lab-server（已有连接配置，勿索取或复制私钥）
公开进度镜像： https://github.com/enterzxk/battery-dynamic-rul
目标： 接续既有任务，以最小必要验证尽快产出真实、可复算的实验；在额度恢复、会话压缩或新会话接管后继续推进，而不是反复规划、审计和 smoke。
执行性质： 这是给原 Codex 会话及其已配置控制器的工作交接，不是对服务器执行的授权回执。不得把本文件当成已经解锁的训练、二进制读取或测试权限。以服务器最新票据、项目锁与 AGENTS.md 为准；本文件中所有日期和指标是交接时可核实的公开快照，恢复时必须检查有没有更新。

0. 给原 Codex 会话的一键启动指令
直接读取这份文档并接管未完成工作：先按第 1 节的文件顺序核实最新服务器状态及已有 owner/锁/额度，不重复完成事项；再按第 3、4 节的优先级解决当前最早真实阻塞，取得一次真实 validation forward 或有科学意义的小规模信息增量对照。执行“理解任务 → 最小实现 → 最小验证 → 真实交付”，不以反复静态审查、smoke、报告版本递增或子代理轮转代替成果。按第 6 节复用既有 battery-rul 自动续接；额度不可用时落盘恢复状态，由后续有效调度唤醒时继续。所有指标必须有预测数据、配置、数据来源与运行回执；新想法只有通过对照实验后才称创新。遇到协议/标签真实风险时守住门槛，同时改做不依赖该门槛的有效任务，不要无休止等待。
1. 恢复现场：只读最小状态，不重新学习整个仓库
1. 先读取根目录 AGENTS.md、PROJECT_PROGRESS.md、docs/CHATGPT_CONTEXT_ZH.md。
2. 读取 automation/state/coordinator.json 所指最新交接和票据；此前的 docs/COORDINATOR_HANDOFF_20261017_V7_ZH.md / V8 只作为历史，若已有新版本以新票据为准。
3. 查看 ./rul.sh status（若脚本存在且适用）、当前 owner/项目锁/GPU 与正在运行的作业，确认无重复主控、重复写入或冲突。只检查一次必要状态；不要中断别的进程。
4. 对 PBT 读取 reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json 和其 active_contract；对动态协议读取 configs/protocols/dynamic_rul_v3_candidate.json 及更新版本；对已训练模型读取 results/development_hust_v11_seed42_v1.csv 和两个 completion_receipt.json。
5. 只检查最相关的失败日志；已验证且未变化的哈希、依赖和 DKP 键不要重扫。若存在新提交或新实验，以证据更新下列旧状态，避免重复工作。
禁止： 为“更全面”从头通读 41 篇论文、全仓库递归审计、创建新调度器、新抽象框架或追加多个无关 smoke。
2. 交接时的真实成果与缺口（核实后动态更新）
类别	已有证据	能/不能作出的结论
文献	41 篇独立论文的主文接纳记录、综合稿与逐篇附录	是有范围限制的研究积累；不是50 篇均已读全套 SI，也不是创新已成立
数据	HUST 77 电芯、作者文件名 split 47/15/15；MATR 169 电芯，88 个观测 nominal EOL crossing、81 个未观测；HUST 在名义 80% 下无观测 crossing	作者估计 EOL 与观测事件必须分轨；不能拿全部 HUST 作者标签评价严格真实 RUL
CPMLP	HUST v11、seed42、300 optimizer steps、validation cell-macro MAE 177.3831 cycles、MAPE 0.0874621	真实但有界的总寿命开发试验；非完整 paper reproduction、非动态 RUL
CPTransformer	同设置 300 steps、validation cell-macro MAE 204.5937 cycles、MAPE 0.1103205	同上；历史合计 2 fits / 600 steps，test 未推理
中位数基线	validation MAE 343.6667 cycles、MAPE 0.1927674	仅为当前作者总寿命标签的开发基线
PBT	15 个验证电芯的精确 DKP keys 已确认	valid_cycle_number 仍缺 15 个；历史有效 Namespace 缺 44 项；截至当前快照无 PBT forward/validation 性能
动态 RUL	src/rul_benchmark/queries.py、audited.py 等基础实现及草案	DRAFT_NOT_FROZEN、training_allowed=false；不是动态模型训练成功


证据入口：
- results/development_hust_v11_seed42_v1.csv
- docs/DYNAMIC_RUL_LABEL_DECISIONS_v1.md
- reports/asof_preprocessing_audit_v1/root_protocol_review_v2.md
- reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json
- reports/literature_discussion_20261017_root_v1/LITERATURE_DISCUSSION_ZH.md
- reports/literature_discussion_20261017_root_v1/PAPER_BY_PAPER_ZH.md
三种证据永远分开： 论文作者报告 / 本项目实际训练与预测 / 待验证研究推论。静态检查、合成 helper 通过、模型可 import、单次 smoke 都不算性能结果。
3. 第一优先级：关闭一个真实阻塞并交付成果
3.1 PBT 作者总 EOL 验证轨道：先解决真正缺失的信息
目标交付： 在既有项目授权流程允许且科学协议成立时，获取一次冻结的 HUST 15-cell validation-only PBT 真实预测及可重算 MAE/MAPE；不得访问 test，不可把该结果叫动态 RUL。
具体执行：
1. 不重复已完成的 DKP key v4 扫描。优先复用已有小型 receipt/manifest；只补 15 个电芯的 valid_cycle_number 及对新运行真实必要的 Namespace/config 字段。要区分「历史 checkpoint 原有效 args 未知」和「新 val-only 运行必须显式冻结的字段」：不能捏造历史配置，也不必为了无关历史字段无限阻止新的明示配置（是否满足 faithful reproduction 仍须单独评定）。
2. 核对加载路径确实不会访问 test；保持匹配的前缀、mask、DKP、scaler、原作者模型与精度语义。若原 evaluator 会读取 test，只用明确冻结并审核的 val-only harness，禁止直接调用原测试流程。
3. 需要从真实文件读取/解码时，遵守现有受限数据访问和 root GO/STOP；不要私自将静态审核当执行授权。只要关键关卡闭合，做一次最小真实 forward，有限值与形状检查通过后直接完成固定 15-cell validation 预测；不要在中间新增一批重复安全扫描。
4. 保存逐电芯预测、真实标签类型、运行日志、commit/config/data/checkpoint 哈希、metric 脚本和 receipt。与 CPMLP/CPTransformer 比较前核对 EOL label、输入预算、验证人口和评价聚合；口径不一致只列并排结果，不宣称公平领先。
5. 如果新一轮仍因实际依赖/权限或配置无法运行：给出唯一最早阻塞、对应证据、最小修复，暂停 PBT 这一支，不再循环生成 v5/v6/v7 静态审查；转第 3.2 节做独立工作。
3.2 独立支线：尽快为方向 A 做可执行人口审计
只需形成 一份小的 eligible origin 表：cell_id, dataset, split, physical_identity_status, k, actual_cycle_number, observed_alive_at_k, event_status, label_type, prefix_safe, exclusion_reason，附数据来源与最小验证，不必先开发完整统一平台。
- 优先 MATR 已观测到阈值 crossing 的子集，但不能把 88 个回顾性筛出事件的电芯直接冒称全部电池的在线总体。对删失/作者估计标签分别处理，不能混在精确 MAE 中。
- 处理 as-of 例外：源码中 b1c0 从 cycle 11、b1c18 从 cycle 39 可能引用下一 cycle；先核数据生成器和实际时间坐标，核不清则排除受影响 cell/origin 并显式记录。HUST_7-5 的 row-vs-actual cycle 偏差也不能忽略。
- 固定 EOL 分母/阈值/首次 crossing、记录可得性的“完整 cycle 结束后”时点、预注册绝对 k 网格（只能按合法覆盖选）、同一物理电芯跨划分隔离。
- 只有数据处理与当前 origin 输入边界具备可验证证据，才允许实验；不为赶指标偷偷切换 label 或使用未来容量、未来挑样、全轨迹归一化。
若严格动态人口暂无法合法构造，可在独立且明示的作者 estimated-EOL 轨道开展工程验证，保留 label bias 限制；不得把它包装为严格真实动态 RUL 科学结论。
4. 第二优先级：最小、可否证的历史信息增量实验（方向 A）
4.1 只研究一件事
控制已知年龄、当前合法状态和使用工况之后，近期退化速率是否让相同合法 origin 上的真实剩余循环寿命预测更准确？先测信息，后谈模型。暂不开发新 Transformer/Mamba/Memory、门控、MoE 或大规模多任务结构。

已有工作冲突： P24 已提出当前状态+近期演化速率并以 GPR 建模；P18 在物理仿真中讨论 deepSOH/路径依赖；P01/P03 使用早期曲线差分特征；P22 使用近期窗口；P47 具有 SOH 注入与门控。新的科学贡献不能叫“首次融合速率与状态”，更不能以 PBT/BatteryLife 作者指标冒充项目结果。针对 2026 年 adaptive history/online update（如前期讨论的 PEAT）另做原文、版本和 protocol 核实，未核实前标为待查，不把网络搜索当全文精读。
4.2 单数据集、单 seed、同人口的主实验
锁定 1 个能支持明确标签语义和前缀合法性的开发数据集/子群、固定的训练与验证物理电芯、固定合法 origin 网格、seed42。主模型只用同一个正则化线性模型（Ridge；训练集拟合 scaler 与超参），可优先用现有数据衍生的小型真实样本，禁止先跑全数据集×多 seed。
ID	输入 / 预测逻辑	验证目标
A0 固定 EOL	在固定首次合法观察点 k0 用训练得到的模型估计一次 EOL；随后 RUL_hat(k)=max(0,EOL_hat(k0)-k)；仅对 k>=k0 的同一组 origin 评测	早期静态递减基线
A1 当前状态	当前循环数/年龄、合法可测 SOH/容量或同输入权限估计值、已知工况/累积使用信息；每个 k 重新预测 EOL/RUL	新的当前状态信息是否足够
A2 状态 + 速率	严格在 A1 基础上只增加用 k 及以前窗口算出的近期容量/曲线变化速率（候选窗口20循环，须在开发前冻结）；模型家族、特征权限、目标标签、预算相同	近期速率的增量价值


若 k0=100 不满足合法覆盖/风险集要求，不强行使用100，改用审计后预先固定且三组共同拥有的首个合法 origin。同一电芯、同一 origin、同一可用通道才能比较；不能 A1 用估计 SOH、A2 偷用诊断实验室额外测量。若使用原始可测容量作为上界诊断，必须标注“测量权限上界”，再用部署可得通道做单独对照。
只在 A2 相对 A1 没有合理增益且无标签/协议问题时，条件性添加一个小型非线性模型（固定超参的树/GBDT）各跑 A1/A2 一次，排除“线性模型未利用信息”。不把超参大范围搜索当必要工作。
4.3 决策指标、分支诊断与止损
主指标：验证 cell-macro Time-MAE (cycles)，在同一固定电芯与 origin 集合上先电芯内聚合、再电芯等权；A1 vs A2 报 paired per-cell delta（改进为正），辅以偏差符号（预测RUL−真实RUL）、严重高估尾部及年龄分层。origin 若非等时间间隔，要事先固定权重，不能事后更改采样密度优化分数。
探索性决策阈值（人为预登记的参考，不是显著性定理）：
- 继续深入：A2 相对 A1 Time-MAE 下降约 >=10%，至少 >=60% 的验证电芯有益，且改善不是单独来自一两个电芯/不合理高估；在独立电芯数量足够时查看配对 CI。阈值不稳或样本过小，结论记为 INCONCLUSIVE，不声称创新。
- 停止复杂历史模型：A2 改善 <5% 且条件性非线性 A2 对照仍无稳定收益；记录 NO_GAIN，停止堆 Memory/Transformer/门控，转研究基线误差、校准或数据可预测性边界。
- 诊断标签问题：仅在 author extrapolated EOL 有收益、observed crossing 无收益，或特征直接/间接利用标签末端外推信息；分轨报告，不称真实 RUL 优势。
- 诊断协议问题：发现未来窗口、测试泄漏、相同 cell 的前缀跨角色、根据最终寿命决定 k、或不同预测人群；相关数值直接作废并最小修复。
- 诊断模型未利用信息：Ridge 无效而同输入预算的简树/GBDT 有效；只说明可能有非线性关系，仍需稳健验证，不直接设计复杂网络。
可追加的最小辅助证据：matched-current-state/age 的训练-验证分组残差分析（样本稀疏则不强做），查同龄相似 SOH 电芯是否出现与近期速率相关的剩余误差。这只是解释性关联，不是路径因果证明。
4.4 方向 B/C 的启动条件
- 方向 B：更新可靠性。只在 A2 有增益且发现跨 origin 错误修订时，比较固定不更新、每次更新和一个开发集冻结的简单平滑/变化阈值；必须同时度量预测 Time-MAE、延迟和严重高估。若只是曲线变平滑但误差或晚期警报恶化，立即停止。
- 方向 C：迁移/负迁移。只有 checkpoint 预训练暴露/物理身份与目标标签权限可解释时，比较 target-only 与 pretrained+adapt，锁定相同目标标签、无标签、origin、搜索和总计算预算；不因 source-only 差就声称负迁移。
- TSC：只有真实服务决策、资源约束及对照实验时才论证服务计算贡献；不能把单纯电池回归改名为服务框架。
5. 文献与写作的轻量任务（当 GPU/数据门阻塞时执行）
1. 复用 reports/literature_discussion_20261017_root_v1/ 的 41 篇综合与 paper_evidence.json，只精查最近邻：P24、P18、P22、P47，以及需核原文的 adaptive-history/online-update 近年工作。逐条写「已有机制→与 A1/A2/B 对照的重合→尚未覆盖的条件→具体证据页/节→是否真的构成空白」。最多 1–2 页中文冲突矩阵，不生成第二版 50 篇长综述。
2. 未满 50 篇不是训练的先决条件。除非审查证明存在直接相关缺口，否则暂不为凑 50 篇扩大阅读量。若要补论文，优先能改变实验选择的原始全文，不能把摘要阅读计为精读。
3. 对动态标签/数据不可行之处给出一条最小可执行替代，如只完成有界 cohort 和数据来源一致性表，不建设巨大通用管线。
4. 把每个真正完成的独立成果压缩为：解决的问题、执行/复算证据、正负结果、是否进入下一关；若没有实验新结果，应明确写“仅文献/协议”。
6. 额度恢复、定时任务、上下文压缩后的真正接续
已有自动化状态（2026-10-17 的项目进度记录）： battery-rul 已调整为每15分钟检查，并设为 ACTIVE；项目已加入上下文接续策略 docs/CONTINUATION_POLICY.md、本地 .control/CONTINUATION_POLICY.md。这不是自动恢复成功的保证；项目记录中还没有首次跨聊天/额度耗尽后成功接管的独立证据。
6.1 每次定时唤醒/手动重启只做以下状态机
1. 检查环境是否真的可用：应用在线、账户普通额度可用、SSH 有效、相关项目锁/owner 安全、既有任务是否正在执行；避免重复 heartbeat 与重复训练。若当前额度不足、已达到5小时/周限制、网络/认证失败或状态 UNKNOWN，则不试图绕过限制。
2. 读取唯一真实进度：本地 .control/CONTINUATION_STATE.json、服务器 coordinator 当前票据、最近 run receipt、PROJECT_PROGRESS.md；只读相应任务的上次失败点。现有长期作业如在正常运行，不因新会话重启而中断或重跑。
3. 若可继续且无活动 owner：依据项目既有合法接管和互斥锁协议恢复尚未完成的第一项获准任务；勿重新启动已完成扫描、已消费的单次执行预算或已结束的训练。
4. 任务完成/失败即落盘：更新原任务状态、精确输出路径、命令/配置、实际 seed/steps 和下一条最小动作；如失败，写可复现阻塞而非再造多个审核版本。
5. 同步 GitHub：仅有实质变化时，使用已有 automation/bin/export_github_context.py 和已授权连接按 docs/GITHUB_SYNC_ZH.md 白名单同步；验证 main 更新和回读快照，避免上传原始电池数据、checkpoint、密钥、PDF全文或私有日志。无变化不制造 commit。
额度恢复语义： 读取实际额度状态及 resetsAt /平台提供的下一可用信息，调度下一次允许的检查；不假设“恰好5小时后”必定恢复，不主动付费或购买额外额度，不使用绕过账户限制的机制。已有15分钟 heartbeat 仅在对应本地应用/控制器可持续运行且确有权限时有效；若控制器未运行，不得声称自动执行了任务。本交接不要求新建重复调度器，优先验证并维护现有 battery-rul。
6.2 上下文即将压缩/会话断开
- 依照仓库 docs/CONTINUATION_POLICY.md 和本地 .control 策略做交接。已有策略记录准备阈值约465k、窗口475k；必须以当前会话实际可查询的窗口/输入占用为准，未测得就标 UNKNOWN，不使用总输出 token 当剩余窗口。
- 在可预见的压缩前，用不超过2页的 NEXT_SESSION_HANDOFF.md 保存：活跃票据、owner/lock、当前阶段、已验收证据的相对路径与 SHA、未完成原因、下一条允许执行的命令、GPU/额度预算、测试锁定状态、GitHub 同步状态。
- 仅当机制确实支持创建 fresh session 并转移调度目标时执行；确认新会话可以实际读取交接及调度已指向新会话后，才将旧会话标为已交接。否则保留恢复文件并如实说明需要人工启动。
- 恢复后的第一条动作应是完成上次未完成的原子任务，不是重新全文阅读文献或大规模重规划。
6.3 被科学阻塞时的自动工作选择
不得擅自解锁当前为 false 的训练门。 若 PBT 阶段仍阻塞：先做第3.2节可合法开展的独立人口/来源证据；若该项也阻塞，就做第5节最近邻论文冲突审查、简短可运行实验配置/代码准备；不进行永无止境的相似静态审计。若全部获准任务已完成，记录 WAITING_FOR_AUTHORIZATION_OR_DATA 并停止无收益轮转，定时检查真正变化的条件。
7. 最小验证、成本与子代理规则
- 每个具体代码改动最多进行必要且与更改相关的一次针对性小样本验证；修复失败可重试，但每次必须对应新的故障证据。一个通过的 smoke 不应触发更多相似 smoke。
- 实验先一组真实数据、一个 seed、固定模型预算；结论足以指导下一步才扩大。最终论文验证需独立留出和足够重复，但不能拿初期探索即开多数据集×多seed矩阵。
- 不使用子代理轮流写相同审核。默认主代理直接执行；当且仅当任务真正独立时，请一个子代理核 P24/P22 原文竞争点、另一个推进合法数据或代码准备，明确不共享可变输出。GPU 串行。
- 不升级到新模型/更大模型以掩盖数据或标签问题。保持中文说明、重要 Python 改动中文注释，深度模型如涉张量说明 [B,L,D] 等形状。
- 不终止其他项目进程、不破坏数据、不覆盖有效输出；不泄露登录、SSH 凭据或非公开数据。
8. 交付与汇报：只要最有用的 5 行
每轮真正有进展时更新 PROJECT_PROGRESS.md、docs/CHATGPT_CONTEXT_ZH.md：
1. 已完成： 完成了哪个可以核验的动作（不要写“准备好”冒充实验）。
2. 证据： 路径、SHA/commit、命令、运行 receipt、预测表或训练指标。
3. 结果： 是“作者报告 / 本项目实测 / 计划推论”哪一种；性能指标的 unit、split、seed、population、预算。
4. 阻塞： 真正影响下一步的最早风险；修复需要什么。
5. 下一步： 只写一个最高价值、最小可执行动作（及通过/失败时的分支）。
任务完成定义： 有明确的成功结果或确证不能继续的外部阻塞、必需最小验证、证据落盘和下一动作。达到即停止追加报告/测试，进入后续科研任务。
附：可回读的公开依据（快照基线）
- 进度：https://github.com/enterzxk/battery-dynamic-rul/blob/main/PROJECT_PROGRESS.md
- 项目介绍：https://github.com/enterzxk/battery-dynamic-rul/blob/main/docs/CHATGPT_CONTEXT_ZH.md
- 有界模型结果：https://github.com/enterzxk/battery-dynamic-rul/blob/main/results/development_hust_v11_seed42_v1.csv
- 精读综合：https://github.com/enterzxk/battery-dynamic-rul/blob/main/reports/literature_discussion_20261017_root_v1/LITERATURE_DISCUSSION_ZH.md
- 41篇逐篇：https://github.com/enterzxk/battery-dynamic-rul/blob/main/reports/literature_discussion_20261017_root_v1/PAPER_BY_PAPER_ZH.md
- 当前PBT入口：https://github.com/enterzxk/battery-dynamic-rul/blob/main/reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json
- 动态标签：https://github.com/enterzxk/battery-dynamic-rul/blob/main/docs/DYNAMIC_RUL_LABEL_DECISIONS_v1.md
- 动态草案：https://github.com/enterzxk/battery-dynamic-rul/blob/main/configs/protocols/dynamic_rul_v3_candidate.json
- as-of风险：https://github.com/enterzxk/battery-dynamic-rul/blob/main/reports/asof_preprocessing_audit_v1/root_protocol_review_v2.md
- GitHub 同步规则：https://github.com/enterzxk/battery-dynamic-rul/blob/main/docs/GITHUB_SYNC_ZH.md
最后一条总原则： 每个额度周期结束时，应至少产生一项有判别力的真实工作成果（模型预测、合法样本表、关键阻塞的确证、决定性论文冲突对照），或者明确记录为什么不能；不要把“运行了一天”当作“科研推进了一天”。