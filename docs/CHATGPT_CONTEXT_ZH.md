# 当前研究主线更新：单电池在线条件 RUL（用户2026-10-18授权）

最新用户全文在docs/USER_SINGLE_BATTERY_ONLINE_RUL_20261018_ZH.md。主线不再以迁移、预训练或早期总EOL为创新中心；原成果保留。最新真实结果请先读experiments/online_survival_observed_pilot_seed42_v1/RESULTS_ZH.md及root_decision.json。

首轮3CPUfits/0optimizer、52train19val观测event源ID、完整100后pre-event整数origin。F0冻结/F1仅存活/F2状态/F3状态速率的cell-equal Time-MAE为71.5000/72.0725/68.2841/58.6026。F3vsF2降14.18%、19cell探索bootstrap区间4.38%–21.59%，12cell改善/7cell受损，两batch分别14.32%/14.11%。这只是event-selected processed工程lane：62自然删失源ID排除，物理serial/实际generator未核，不能宣称strict在线、删失处理收益、独立泛化或创新成立。F1没有改善，F2改善未过探索门。

优先研究有害速率修正为何发生，而非先堆生存网络/门控。自然删失建模待更可辨识数据；条件生存公式是标准机制，DynamicDeepHit/电池CoxDeepHit/PEAT均为直接先例。文献阅读范围与两份十篇身份去重、P01引用冲突见本轮报告，未把41+20计为新全文。旧MATR2.68%/NO_GAIN与CALB/PBT门保持，新GO3fits已消费，全局new_fits_allowed=false、test锁保持。

同一battery-rul仍ACTIVE每15min、target为当前V11；coordinator.next_action已转为新研究真实下一动作，不再因HUST单来源等待阻塞整个项目。后文是历史快照，读者须按日期和当前入口解读。

---

# 给网页版 GPT 的 Battery Dynamic RUL 项目入口

本页帮助解释项目，不把规划、程序检查或文献作者数值当作本项目实验成果。请先查看 `public_snapshot.json` 的快照时间与文件哈希，再读 `PROJECT_PROGRESS.md`。这里记录的是发布快照，服务器当前状态可能已推进。

## 最新执行增量：2026-10-17 15:40 UTC

方向A已实际完成一次MATR回顾性已处理记录诊断：99训练/34验证源ID，136验证时点，seed42。全34作者总EOL Time-MAE：A0 151.9080、A1 152.5449、A2 148.4576 cycles；加速率下降2.679%，21/34改善。条件固定GBDT下降3.664%，18/34改善且配对区间跨0。观测19电池单列：Ridge A1 91.5955→A2 86.8838（5.144%），固定GBDT仅2.038%。未达约10%推进目标，root判NO_GAIN：不扩复杂历史模型，不改seed救结果；不是证明速率绝无信息。尾部未一致改善。41 fits含39 Ridge交叉验证/最终拟合+2固定GBDT，optimizer_steps=0；历史CP2fits/600steps分开。详见experiments/dynamic_A_matr_retrospective_seed42_v1/RESULTS_ZH.md及原始validation_predictions.csv/independent_metrics.json/root_decision.json。

全34含15个作者外推EOL，只代表作者标签一致性；观测19为条件子群。实际v11生成器及其余物理serial仍未知，strict_online_eligible=0，完整循环测量容量也不能称I/V-only部署输入。本次exact GO只开放隔离工程lane，原严格动态/PBT/test门保持。PBT首分片真实读取2250966字节entry_cap失败预算已消费，不重跑/扩cap/切分片。新聊天owner已实际接管，同一battery-rul每15分钟任务已迁移核对；本轮已观察到一次真实耗尽后恢复并执行保存动作；不推广为每次唤醒均保证成功。

补充失败诊断：前两大误差电池占全34电池A1等权绝对误差的43.68%；其作者EOL较末次观测仅多2/-1循环，A1低估误差下界为1379.39/884.87循环。不能把大误差单独归咎于长距离尾段外推，也不证明作者标签/生成器有效。 证据见`experiments/dynamic_A_matr_retrospective_seed42_v1/CENSORED_FAILURE_ZH.md`。本诊断新增fit=0。

## 2026-10-18 03:20 北京时间增量：标签与支持范围

已完成首次实际额度耗尽后恢复，并接着完成保存的文本诊断。b3c38作者EOL1932来自已存末20SOH回归1932.623再int；浮点值已小于末次观测1933，不能只称取整问题。合格训练47/验证15个尾段回归标签中41/11个不晚于观测末端，作者标签不能当精确真实未来事件。两个大误差电池EOL2237/1932超过训练最大1834，但k50/100/150/200的SOH/累计Ah/速率均在全训练边际范围内；边际包含不证明联合支持或因果机制。完整证据见`experiments/dynamic_A_matr_retrospective_seed42_v1/LABEL_BOUNDARY_SUPPORT_ZH.md`及机器记录。原标签/预测/NO_GAIN保留，本轮fit=0，没有重跑标签回归或test推理。

## 2026-10-18 03:34 北京时间增量：误差分解与batch混杂

现有34电池完整误差分解已完成：两只超训练寿命范围电池占A1绝对误差43.676%，但仅占Ridge速率净改善11.662%；范围内32电池Ridge/固定GBDT改善4.202%/3.989%，原NO_GAIN保持，不删离群点美化。合格train/val中batch1/3全部未观测阈值事件，batch2/4全部已观测；观测组和删失组差异与batch完全混杂，不能单独归因于标签类型或删失。证据见`experiments/dynamic_A_matr_retrospective_seed42_v1/ERROR_CONTRIBUTION_ZH.md`及机器记录。全34主指标未改，新增fit=0。

## 2026-10-18 03:48 北京时间增量：终点语义与诊断闭合

133个合格train/val记录的终点核对完成：batch1/3停于约80.00%..80.30% SOH且无nominal crossing，batch2约75%，batch4保留到更低且分散的容量。全部71个观测crossing电池在阈值后继续有记录；验证batch2/4分别有20..37/23..273个后续循环。观测状态差异对应显著不同的processed-record终点，不能当随机删失或单独标签效应。不能据此确认实际v11生成器或原始实验停止规则。方向A诊断链已闭合NO_GAIN，不追加模型/seed/改阈值救结果；本阶段fit=0。见`experiments/dynamic_A_matr_retrospective_seed42_v1/TERMINAL_BOUNDARY_ZH.md`、`diagnostic_closure.json`。下一项仅核官方发布metadata的版本凭证，缺失保持STOP。

## 2026-10-18 04:04 北京时间增量：官方来源核查STOP

一次官方MATR v11来源核查已结束：Zenodo record19688272的v11/发布日期2026-04-22及MATR.zip MD5可核，与既有下载回执一致；版本说明中的MATR变更是b3c0 seen/unseen分类。已读HTML/Version11文档没有精确generator绑定；完整API metadata获取失败（web不可访问，服务器一次请求DNS失败），其字段UNKNOWN，不能扩大为“所有官方metadata无凭证”。actual v11 provenance保持未核，严格在线/PBT/test门未改，方向A闭合NO_GAIN。证据见`reports/matr_v11_release_provenance_20261018_root/PROVENANCE_CHECK_ZH.md`及root_review；新增fit=0。下一项转P1已有完成回执/配置/checkpoint清单静态核对，不自动训练或重置旧600步。

## 2026-10-18 04:21 北京时间增量：P1接续判定

上轮来源核查已补同步2e794b27。CPMLP/CPTransformer旧运行各300步实际为epoch1/2各146批、epoch3仅8批；checkpoint003是partial epoch3，不能称3完整epoch或无损自动恢复。源码有模型/Adam/RNG但无batch游标，且旧completion及预算耗尽门保留。核查没有加载checkpoint或新fit。旧pilot不是完整论文复现；已具体准备一个HUST官方配方适配CPMLP的DRAFT候选（1fit/14600步/1200秒拟议，未分配/未GO），下一项是独立runner最小实现与一次停止边界检查。证据见`reports/p1_cp_checkpoint_inventory_20261018_root/P1_CONTINUATION_REVIEW_ZH.md`。不挽救MATR NO_GAIN，不重置旧600步或访问test。

## 2026-10-18 04:43 北京时间增量：真实CPMLP配方运行完成

已完成1次CPMLP HUST作者EOL完整配方适配：10完整epoch/1460steps，early-stop完成，选epoch3。15验证电池/1500prefix独立复算EOL-MAE194.0073、MAPE0.10136755；比旧短pilot177.3831差9.3719%，仅6/15电池改善，负面结果保留。首次v1启动缺batteryml，fit0/step0失败证据保留；v2仅输出目录与已有项目runtime修复，沿用未消费1fit预算，无全局安装。旧CP600步不动，神经训练累计2060步，MATR41CPU fits另列。配方HUST/seed42/singleGPU/val-only偏离明示，非完整论文复现、strict在线或动态真实RUL。证据见`experiments/cpmlp_hust_recipe_adapt_seed42_v2/RESULTS_ZH.md`及原预测/receipt/independent_metrics。下一步仅现有预测误差分析，不追加训练救分。

## 项目在研究什么

研究电池随着循环数据逐步到达时，如何合法、准确地更新剩余使用寿命（RUL）。核心问题是：动态更新能否优于“早期预测总寿命 EOL，再减去当前循环数”的固定预测基线？必须先解决标签定义、物理电池拆分、前缀可见性和归一化问题，再比较模型。路线为 P0 数据审计 → P1 BatteryLife 最小可信复现 → P2 PBT checkpoint/适配复现 → P3 动态 RUL → P4 失败模式 → P5 最小创新验证。路线不是完成清单。

## 最近一次已核科学状态：2026-10-17

- HUST 原始文件与标签版本已经做过审计；文件名拆分为 47/15/15。物理身份独立核验、作者 EOL 标签与实际观测循环的关系仍须保留限制，不能直接宣布严格在线动态 RUL 数据协议成立。
- 已完成 CPMLP、CPTransformer 两次 seed=42 的有界开发试验，每次 300 个优化器步骤，共 600 步。完成回执状态均为 `BUDGET_EXHAUSTED_AFTER_PARTIAL_EPOCH`：这是预算内试验结束，完整论文复现尚未完成。没有测试集推理。
- PBT 已完成若干静态检查和一次限定的精确 DKP 键元数据采集，15 个验证电芯的键映射已找到。当前仍缺 15 个 `valid_cycle_number` 证据和 44 项历史实际 Namespace 字段；完整新运行配置尚未闭合。静态通过不等于模型运行、预测性能或训练许可。
- 文献主文接纳记录按独立 paper_id 计为 41 篇。接纳的是带限定的阅读证据，不代表公平复现、动态 RUL 性能或创新成立。原文矛盾和未核实事项保留。
- 原严格动态与PBT模型门继续关闭；最终test保持锁定。上述隔离回顾性lane已完成41 CPU fits，无新增梯度优化器步骤，不能冒充严格动态训练授权。

## 已有真实开发结果

以下是 HUST v11、作者总 EOL 估计任务、seed=42、15 个 validation 文件的 cell-macro 指标。它们不是动态 RUL 结果、测试结果或完整论文复现结果。

| 方法 | 优化器步骤 | 验证 MAE（循环） | 验证 MAPE（比例） |
| --- | ---: | ---: | ---: |
| CPMLP | 300 | 177.3830694173177 | 0.08746210065255396 |
| CPTransformer | 300 | 204.59365958658847 | 0.11032053245455888 |
| 训练电芯 EOL 中位数基线 | 0 | 343.6666666666667 | 0.19276743429488932 |

原始表：[`results/development_hust_v11_seed42_v1.csv`](../results/development_hust_v11_seed42_v1.csv)。对应 `experiments/` 中保存配置、运行/完成回执、逐 epoch 指标、预算账本和 validation 预测记录，可追溯原指标。模型选择使用 validation prefix-MAPE；不要把它与报告中的 cell-macro 指标混成两个独立确认试验。单 seed、小开发样本结果仅用于下一步决策。

## 当前最有价值的行动

按最新进度和交接确认当前最早阻塞；PBT 的权威准备入口是 [`reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json`](../reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json)。不要重复已消费预算的 DKP 采集。补齐实际缺失证据，达到既定合法性与运行门槛后马上做获准的最小真实对照。另一条独立的长文处理适配仍未接入生产控制器，合成测试不算新增论文阅读。

## 阅读顺序与证据边界

1. `README.md`、本页、`PROJECT_PROGRESS.md`：先了解问题和进度。
2. `results/` 和 `experiments/*/fit_runs/*/completion_receipt.json`：核对真实运行与结果。
3. `configs/`、`src/`：核对配置和实现；上传代码不代表已执行全部功能。
4. `reports/`：核对数据标签、as-of 协议、PBT 当前缺证及文献综合；旧版本不自动代表最新裁定。
5. `literature/accepted/`：看接纳范围和限制。论文全文和完整逐篇阅读笔记没有放入公开镜像；引用到但未上传的文件，只能说明服务器保留证据，不能声称你已读过。

绝对服务器路径作为原始证据保留；在本仓库查找时可去掉 `/home/yndx/zxk/rul/` 前缀。`public_snapshot.json` 列出本次实际上传的文件；清单以外材料不能假定已在仓库中。

## 可以交给网页版 GPT 的请求

请先读取本仓库 README.md、docs/CHATGPT_CONTEXT_ZH.md、PROJECT_PROGRESS.md 和 public_snapshot.json，再用中文介绍：项目研究问题、实际完成的实验与结果、仍未完成的事项、当前唯一最优先行动。关键判断引用具体仓库文件；区分作者报告、本项目实测和待验证推测。不要把规划、metadata PASS、smoke 或文献接纳写成模型性能。若无法访问仓库，明确说无法读取，不能假装看过文件。

## 详细精读结论

新增[41篇主文精读结论与方向讨论稿](../reports/literature_discussion_20261017_root_v1/LITERATURE_DISCUSSION_ZH.md)，含逐篇附录、证据和三个可否证候选方向；讨论方向优先读它。本次复用既有精读，不声称新读41篇PDF。

补充标签边界：MATR_b3c38作者EOL=1932，但完整文本记录存活至1933且nominal crossing未观测；存在1循环边界不一致，需核已有标签算法的外推/取整语义。不得把作者标签当精确真实EOL，不修改或删除既有结果；下一动作优先核此边界，再看训练特征支持。


## 2026-10-18 04:52 北京时间：CPMLP已有预测的配对误差分解

- **已完成**：V10锁内接管并核同一battery-rul已绑定；按file_name/prefix_index对齐旧epoch2和新epoch3的15电池/1500验证预测。MAE177.3831→194.0073，净增16.6242循环（9.3719%）；9电池恶化、6改善。恶化前三HUST_2-8/10-1/9-1占全部正向恶化74.4896%，全局贡献+34.9835循环；全部恶化+46.9644、改善抵消-30.3402。
- **证据**：reports/cpmlp_recipe_error_diagnosis_20261018_root/ 内 DIAGNOSIS_ZH.md、diagnosis.json、per_cell.csv、per_cell_prefix_segment.csv、paired_prediction_deltas.csv、diagnose.py。五个prefix序号段均恶化，21–60贡献净增60.3167%；全局bias -71.1230→-34.9644，但电池绝对bias均值158.0395→179.7695，正负抵消不等于改善。
- **最小验证**：两份源预测SHA匹配冻结指标，1500唯一键、15×100前缀、标签完全一致、文件名train/val隔离；cell/分段/交叉贡献均重构净增（误差<1e-8），原主指标吻合。new_fits=0、optimizer_steps=0、model_loads=0、test_access=false；未重跑旧独立复算/smoke。
- **阻塞/风险**：只作算术来源定位，不能孤立归因LR（初始化RNG/时长亦不同）；同15电池重复开发选模，不能声称独立确认、CALB/MIX完整复现或strict在线RUL。prefix_index按CSV序号，不新增物理循环/raw-asof认证。NO_GAIN与PBT消费预算/旧训练/test门均保持。
- **下一步**：只读现有逐epoch验证预测与epoch_metrics，检查冻结MAPE选模点相对各自MAE最小点的差异；不改选择规则、不重选汇报checkpoint、不新增推理/训练。


## 2026-10-18 04:55 北京时间：CPMLP选模目标差异核查闭合

- **已完成**：仅核已有旧3/新10条验证事件，旧epoch3为8batch partial。旧MAPE与MAE均在epoch2最小，新均在epoch3最小，MAE选模惩罚均0；排除“冻结MAPE选模点与已记录MAE最小点不同”解释当前回退，原选择和NO_GAIN保持。
- **证据**：reports/cpmlp_selection_diagnosis_20261018_root/SELECTION_DIAGNOSIS_ZH.md、selection_diagnosis.json、epoch_comparison.csv、diagnose_selection.py。相同292steps旧/新MAE177.3831/201.0238，差+23.6407（13.3275%）；新epoch10 MAE241.7783比所选epoch3多47.7711循环。
- **最小验证**：13事件各15电池×100前缀，per_cell独立求均值吻合MAE/MAPE（<1e-8/<1e-10）；冻结最小MAPE点吻合completion。源JSONL/receipt及程序SHA绑定。new_fits=0、optimizer_steps=0、new_inference=0、model_loads=0、test_access=false。
- **阻塞/风险**：同15验证电池重复开发选择，不是独立确认；相同步数仍有LR/初始化混杂，后期验证变差不证明一般性过拟合机理。不称CALB/MIX完整复现或strict在线RUL，不换checkpoint救分，原预算/门不变。
- **下一步**：转回P1，只读官方CPMLP CALB脚本及已有数据/标签/拆分凭证、stat，确定完整忠实复现最早缺失项；不加载数据、构造模型或训练，不重复HUST开发调参。


## 2026-10-18 05:11 北京时间：P1官方CALB忠实复现缺口定位

- **已完成**：只读pinned官方CPMLP脚本、loader和拆分AST，定向stat项目data/现有stage。官方CALB seed2021、2进程×16、LR5e-5 constant；固定文件名拆分17/5/5唯一且两两无交集。当前项目data无CALB路径、无已展开CALB_labels.json，首个真实阻塞为数据/标签未获取并落入受审stage。
- **证据**：reports/p1_calb_reproduction_gap_20261018_root/GAP_REVIEW_ZH.md、gap_inventory.json、inventory.py；含源码URL/行号与SHA。现有v11官方API快照列CALB.zip 12,671,967 bytes、MD5 2b1006e96e0ca42765a732060f964687；已有Life_labels_v11.zip stat12,586 bytes可复用候选，未打开、不重下。
- **最小验证**：AST只解析三个拆分静态列表，核源码参数/loader路径和test调用具体行，项目内CALB路径stat为空。new_fits=0、optimizer_steps=0、archive_reads=0、model_loads=0、test_access=false；不把文件名隔离当物理身份通过。
- **阻塞/风险**：pinned run_main.py:211构造test、:370逐epoch评估test，直接官方入口冲突当前test锁；双进程runtime未验证，HUST单GPU结果不替代。元数据为保存快照，本轮未实时验证；CALB标签覆盖、来源/asof审计均未完成。原PBT/HUST预算与new_fits_allowed=false保持。
- **下一步**：实时核公开v11 CALB元数据/响应头和当前传输预算后，单次有界获取约12.7MB CALB归档并核checksum；复用已有标签包，固定17train+5val成员/CRC/标签覆盖，test内容不读，不反序列化/模型/训练。


## 2026-10-18 05:27 北京时间：CALB v11真实获取与固定22覆盖完成

- **已完成**：实时核官方v11 API/HEAD后单次GET获取CALB.zip 12,671,967字节，官方MD5吻合；固定17train+5val成员CRC/SHA和标签文件名键覆盖22/22。首轮代理拒绝连接失败0artifact请求/0字节保留；确认原隧道PID退出后按既有参数仅恢复项目隧道，独立v2继续，未启动控制器/队列。
- **证据**：reports/calb_acquisition_20261018_root_v2/ACQUISITION_ZH.md、live_source_metadata.json、head_receipt.json、acquisition_receipt.json、archive_coverage.json、completion_receipt.json、transport_repair_review.json；原失败reports/calb_acquisition_20261018_root/failure_receipt.json。归档data/raw/CALB/acquisition_v11_20261018_root_v2/CALB_v11.zip，SHA153dc6230d445d23b4928ce4dc993f37b331651de8473497f8df01ed9bafe7a3。
- **最小验证**：官方size/MD5、22固定成员CRC/SHA（合计41,987,581解压字节）及复用标签包SHA吻合，标签只扫22键、未解码任何数值；test PKL0打开、test标签数值0解码，不冒称全包逐成员CRC。源阶段加本轮估计7,834,285,913<21,474,836,480。new_fits=0、optimizer_steps=0、new_inference=0、model_loads=0。
- **阻塞/风险**：共享标签成员读取字节仅做键扫描，测试数值未解码/保留。归档结构覆盖不等于语义/asof/物理身份或安全载入通过；CALB双进程和官方入口test冲突未闭合，训练门仍false。失败/旧预算/NO_GAIN不覆盖。
- **下一步**：隔离固定22train/val stage，先审序列化可允许类型，安全时用受限加载检查1train+1val真实样本字段/形状/标签/有效前缀；不普通unpickle、不读test、不构造模型/fit。


## 2026-10-18 05:42 北京时间：CALB固定22隔离与两样本真实字段审计

- **已完成**：已核22train/val成员与仅22键标签create-only隔离到data/source_audit/calb_v11_trainval_stage_20261018_root。primitive-only门因验证样本NumPy scalar停止0载入，原失败保留；独立v2固定符号惰性float64替身安全载入1train+1val，不导入/调用NumPy原构造器。
- **证据**：reports/calb_trainval_sample_audit_20261018_root_v2/SAMPLE_AUDIT_ZH.md、sample_audit.json、ROOT_TYPED_LOAD_REVIEW.json、audit_typed_samples.py及原目录serialization_gate.json/failure_receipt.json。stage_manifest SHA512db20103ecb56e72686577970bf8c7f05f281b10e128068925c358e1637146。
- **最小验证**：CALB_35_B229训练实际99cycle/EOL1171、CALB_0_B187验证100cycle/EOL189，可用前缀99/100；两者58Ah、五必需字段长度对齐、非有限值/负容量点/循环内时间倒退均0，cell_id吻合。复用已扫两文件SHA不重扫；新fits=0、optimizer_steps=0、model_loads=0、new_inference=0、testPKL0、test标签值0解码。
- **阻塞/风险**：仅2/22样本字段审计，不宣称全cohort合法；[100,3,300]仍为源码预期而非测量张量。99cycle不能默认为100prefix。实际重采样/归一化/mask、train-only label scaler和其余20类型未核；物理身份/strict在线/官方test入口/双进程限制保持。
- **下一步**：固定同两样本执行pinned曲线重采样/归一化和prefix mask定向检查，核99cycle补零与100cycle边界；不重载全cohort、不fit scaler/模型或读test。


## 2026-10-18 05:55 北京时间：CALB两样本官方数值预处理通过

- **已完成**：仅同两固定样本，提取调用pinned四个曲线/样本方法，未初始化Dataset_original或模型；未使用增强分支作identity stub。真实生成[100,3,300]，99cycle训练样本第100槽零且仅99prefix，100cycle验证样本100prefix。
- **证据**：reports/calb_two_sample_preprocessing_20261018_root/PREPROCESSING_ZH.md、preprocessing_check.json、check_preprocessing.py、source_identity_verification.json。两个曲线数组SHA、源码函数行和stage/decoder/source SHA绑定；原数据不公开。
- **最小验证**：全部曲线有限、每个prefix mask前i=1/后=0且遮罩后未来槽0；真实cycle电压max1误差0，首cycle三个通道独立归一化重算差0。loader SHA与既有完成回执一致，不重复运行。new_fits=0、optimizer_steps=0、model_loads=0、new_inference=0、scaler_fits=0、testPKL0。
- **阻塞/风险**：仅2/22预处理，完整Dataset_original/增广/label scaler未运行，数值mask不证明模型或strict asof成立；仍有物理身份/标签/官方test入口/双进程边界。99/100前缀差异需并报官方prefix聚合及cell-equal指标。
- **下一步**：只检查剩余20成员序列化/字段/官方预处理并复用已过2样本结果，形成17/5完整有效prefix清单和train-only scaler准备判定；失败不扩dtype/global映射，不读test或模型/fit。


## 2026-10-18 06:11 北京时间：CALB剩余20一次审计与17/5完整前缀清单

- **已完成**：剩余20固定成员各一次静态预检/受限载入/字段/官方基础曲线与mask检查，原2成员证据复用未重载；固定22 cohort通过该范围数据subgate，未扩大dtype/global映射。
- **证据**：reports/calb_remaining20_audit_20261018_root/COHORT_AUDIT_ZH.md、cohort_audit.json、cohort_inventory.csv、static_scan_remaining20.json、audit_remaining.py。17train1689prefix（11×99+6×100）、5val497prefix（3×99+2×100）；train存储99–208cycle、val99–100cycle，作者EOL范围104–1352/189–1411。
- **最小验证**：22电池必需字段长度对齐、raw非有限值0/负容量点0、实际[100,3,300]曲线有限、mask/缺cycle零填充/真实cycle电压max1通过、cell_id匹配。仅17train unique标签预期scaler mean852.294117647059、scale532.436659000628（ddof0），val/test未参与；scaler.fit未执行。new_fits=0、optimizer_steps=0、model_loads=0、new_inference=0、testPKL0。
- **阻塞/风险**：完整Dataset_original/实际增强/共享train-only scaler仍未运行；物理身份/generator/strict asof与真实在线标签、官方test调用、2GPUruntime/模型训练门保持。前缀不等权，后续需同时报官方prefix与cell-equal，不能补造1700/500。
- **下一步**：同stage只初始化pinned train/val Dataset_original一次，固定受限pickle映射核真实1689/497、shared train-only label scaler和一个真实batch形状/mask；不建test loader或模型/fit。


## 2026-10-18 06:27 北京时间：CALB完整train/val与实际batch接口核验

- **已完成**：pinned Dataset_original真实train/val各初始化一次（含实际增强），固定22不同PKL，1689/497及逐cell分布、共享train-only label scaler通过。末batch断言预期误写[32]而非官方[32,1]失败，原exit1/回执保留；只用首个真实cell前32prefix定向重建官方getitem/collate修复，不全cohort重跑或refit。
- **证据**：reports/calb_dataset_trainval_20261018_root_v2/DATASET_CHECK_ZH.md、targeted_batch_check.json、check_targeted_batch.py；原目录failure_receipt.json、execution_receipt.json、check_dataset.py。batch实际[32,100,3,300]、mask[32,100]、labels[32,1]，全部有限、mask未来槽0、标签逆变换吻合。
- **最小验证**：label scaler只fit17train unique标签（mean852.2941176470588/scale532.4366590006279），val共享同对象且参数不变；另life_class_scaler fit1689train rows，总2次预处理fit均train_init，修复新增0。predictive_fits=0、optimizer_steps=0、model_instances=0、testPKL0。
- **阻塞/风险**：数据接口通过不等于模型性能或正式复现；singleGPU/val-only相对官方2GPU/test有偏离，物理身份/generator/strict在线边界不变；全局new_fits_allowed=false，旧HUST消费GO不能复用。
- **下一步**：最小适配已审HUST runner为独立CALB seed2021单GPUval-only配方，冻结候选1fit/5200steps（52batch×100epoch）/1200s和源哈希/停止条件；仅主控新scoped GO且全部适用门满足后才真实运行，不开放test。


## 2026-10-18 06:42 北京时间：CALB官方配方适配首次真实训练完成

- **已完成**：复用已审runner最小适配并签发独立scoped GO，一次CALB seed2021单GPU train/val真实fit，10完整验证epoch/520steps早停，prefix-MAPE选epoch2。5cell/497预测独立复算cell-equal EOL-MAE61.634743、MAPE0.078686577；训练中位数基线MAE350.4，4/5改善，下降82.4102%。
- **证据**：experiments/cpmlp_calb_recipe_adapt_seed2021_v1/RESULTS_ZH.md、config/runner/ROOT_GO、completion_receipt.json、validation_predictions_epoch_002.csv、independent_metrics.json、root_result_decision.json、连续账本；results/development_calb_cpmlp_recipe_adapt_seed2021_v1.csv。预测SHAbffadd1558ba46cd210f9c74145296dd300a9d0aec04bf72ec8e9011c7a3755c。
- **最小验证**：原stop/deadline/partial逻辑AST一致，不重复smoke；实际首batch有限loss/gradient/shape，497唯一配对键与99/100分布、原指标及10×52/连续520步账本吻合。原标签往返最大1.53e-5cycle，精确作者标签MAE61.634746。实际wall18.74s<1200；独立1fit/5200step预算已消费。
- **阻塞/风险**：仅弱全局train-median与5开发验证电池，同集选模不是独立确认/SOTA/创新；singleGPU/val-only偏离，非完整2GPU/test论文复现或strict在线RUL。HUST/MATR NO_GAIN保留。神经累计4fits2580steps，MATR41CPUfits另记，全局new_fits_allowed=false/PBT消费/test锁不变。
- **下一步**：只用已有CALB预测和17train标签，核有训练支持的文件组条件中位数对照（无支持组回退全局中位数），分解全局弱基线优势来源；不新fit/seed/model/inference/test或改标签/选模。


## 2026-10-18 06:55 北京时间：CALB训练专用组先验缩小模型证据（停止扩展）

- **已完成**：只用既有497预测与train17标签，按预先冻结文件组中位数/无支持回退全局规则完成对照。group35/0/45训练支持10/6/1，25无支持。整体模型MAE61.634746、组prior91、全局prior350.4；组prior在算术上覆盖原全局增益89.8308%。
- **证据**：reports/calb_group_prior_diagnosis_20261018_root/GROUP_PRIOR_ZH.md、group_prior_diagnosis.json、per_cell_comparison.csv、protocol.json、root_diagnostic_decision.json、diagnose.py。支持组4cell模型54.584443>prior51；无支持25单cell模型89.835955<回退251，净余量集中于该cell。CALB_0_B187占全局增益70.4364%。
- **最小验证**：原预测SHA/5cell固定，共用精确作者标签，模型精确MAE吻合旧独立值；三模型差值分解重构（<1e-8），先验无val/test参与拟合。new_fits=0、optimizer_steps=0、model_loads=0、new_inference=0；原native浮点口径/选模/结果不改。
- **阻塞/风险**：判NO_GO_FOR_CALB_MODEL_OR_SEED_EXPANSION_FROM_CURRENT5，保留开发fit完成但不据弱全局基线82.41%称强模型或创新证据。整体对组prior仍改善32.2695%/3of5，支持组4cell却差7.0283%；5开发cell单seed与45组1train、25组0train限制不隐去，非因果/独立泛化确认。神经累计4fits2580steps、原HUST/MATR/PBT/test门保持。
- **下一步**：只读已存官方v11完整API JSON及旧MATR来源回执，核实际generator commit/config绑定并区分保存快照与live未知；无绑定保留缺证STOP，不重新下载/扫描PBT或训练。


## 2026-10-18 07:14 北京时间增量：保存完整 API 已核，实时未知

MATR来源补充核查已完成：已存record19688272完整API（SHA 5b79e36abb25fc0721aef484cf92605c7e8d559df7bffba90003b291475238ae）实际存在且已读；description明示v11，metadata.version无键。custom只给仓库/语言，related_identifiers/references/notes无键，swh为空；文件大小/MD5与既有MATR回执吻合，但未给出实际归档到generator commit/config/run绑定。旧报告的网络失败保留，不能继续把“完整API未读”用于已存快照；实时API当前UNKNOWN、保存获取时间未验证。见reports/matr_v11_release_provenance_20261018_root/SAVED_API_ADDENDUM_ZH.md及saved_api_addendum.json。来源STOP/方向A NO_GAIN/CALB扩展NO_GO/PBT消费与test锁保持，本阶段fit/steps/model/inference/binary/network均0。下一项只用现有P0索引和源码定位物理身份/重叠证据缺口。


## 2026-10-18 07:25 北京时间增量：CALB命名身份边界

仅源码/旧CSV核官方27名单：去掉温度前缀后basename27唯一、跨角色/温度重名0。pinned代码以温度目录+源文件basename生成cell_id，因此旧22条cell_id_matches不构成独立物理serial证明。报告reports/calb_identity_text_audit_20261018_root/IDENTITY_AUDIT_ZH.md及identity_audit.json。不同别名/跨来源/预训练身份仍未知，实际生成器STOP/原CALB扩展NO_GO保持。文件组prior可按pinned命名解释为温度层prior，不能作因果温度结论。test仅源码5文件名，本轮fit/step/model/inference/binary/network=0。下一项只用既有小摘要核eol<=100筛选的实际origin排除。


## 2026-10-18 07:40 北京时间：EOL门槛风险的实际边界

现有固定MATR136/HUST62 trainval全部作者EOL>100（最小147/1164），所以官方eol<=100整cell筛选实际移除0cell/0origin。完整结局依赖仍存在，不能称这批已被该门槛删除；其他缺记录/别名排除原因未在此评估。见reports/early_eol_filter_realization_20261018_root/FILTER_REALIZATION_ZH.md与filter_realization.json。本轮无fit/step/model/inference/binary，strict在线与test门不变。下一项仅现有CALB10epoch选模目标诊断。


## 2026-10-18 11:44 北京时间：CALB选模目标一致

额度恢复首次可执行检查后完成已保存动作：10epoch的prefix-MAPE/cell-MAE/prefix-MAE/cell-MAPE最优均epoch2；cell-MAE61.634743，次优epoch4为64.673063。原选模没有与整体cell-MAE冲突，不能靠重选既有epoch得到更低整体MAE。原预测/回执保持，CALB当前5cell扩展NO_GO不变，per-cell事后选epoch不允许。见reports/calb_selection_diagnosis_20261018_root/SELECTION_DIAGNOSIS_ZH.md及机器记录。新fit/step/model/inference/binary/test均0。下一项仅HUST既有原始来源metadata身份凭证核对。


## 2026-10-18 11:47 北京时间：HUST来源身份仍缺独立映射

已存Mendeley公开metadata可核原始DOI/版本，但没有files键、size0不能解释为空数据；旧manifest记录文件清单接口400。pinned preprocess_HUST以原file.stem拼HUST_后赋cell_id，不提供独立serial。当前只在已读保存材料中缺证，不声称所有原始材料都无映射。见reports/hust_saved_source_identity_20261018_root/SOURCE_IDENTITY_ZH.md和机器回执。原门控保持、本轮fit/steps/model/inference/binary/test/network均0。下一项一次公开v2文件清单metadata查询，不下载raw或改权限。


## 2026-10-18 12:02 北京时间：HUST实时库存入口受限

官方v2页可读，但正文没有展开Files；一次候选公开库存端点被网页工具报告不可访问，没有可核HTTP状态或文件清单，路由正确性也未证。已停止不重试，不把旧400/size0/动态列表未提取解释为空库存或无身份映射。见reports/hust_saved_source_identity_20261018_root/public_inventory_attempt.json与PUBLIC_INVENTORY_ACCESS_ZH.md。原source/physical identity门仍未闭合；需要新可读官方inventory/README/serial凭证或访问变化，再恢复此有界来源任务，不循环当前查询。本轮raw/fit/model/inference/test=0，研究整体未宣称完成。

## 2026-10-18：动态 RUL 时间预测十篇聚焦精读

新增十篇聚焦讨论稿：`reports/rul_time_prediction_literature_20261018_root/LITERATURE_REVIEW_ZH.md`。它从既有41篇精读档案挑选来源，区分早期总寿命、动态 RUL(t)、轨迹阈值推导，并提出尚未验证/未完成新颖性检索的“创新量触发稀疏更新”候选。MATR历史结果仍为NO_GAIN，不扩模型/seed；本轮训练0、optimizer steps 0、新推理0。报告SHA256：`4e220d42634c16da592fb2e80ba994cd4036cdcc3b84a1e1771ef4b45f61c8ff`。

## 2026-10-18：跨领域 RUL 精读（纠正范围）

用户澄清需超出电池领域。新的正式阅读入口为 `reports/cross_domain_rul_literature_20261018_root/CROSS_DOMAIN_RUL_REVIEW_ZH.md`，覆盖航空发动机、风机轴承、旋转机械、CNC及医疗纵向生存分析十篇。原电池十篇总结仍保留历史，但不作为这次跨领域任务的交付。跨域候选为删失感知、随新纵向观测更新的条件RUL生存分布；尚未检索确认创新性，不授权训练。训练/推理均为0。SHA256：`4e9f9463b676ccdee8b044fbe1626abc95d3cfba0bbfb3098e855e321ce0526a`。
