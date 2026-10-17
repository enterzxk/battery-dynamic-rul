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
