# 给网页版 GPT 的 Battery Dynamic RUL 项目入口

本页帮助解释项目，不把规划、程序检查或文献作者数值当作本项目实验成果。请先查看 `public_snapshot.json` 的快照时间与文件哈希，再读 `PROJECT_PROGRESS.md`。这里记录的是发布快照，服务器当前状态可能已推进。

## 项目在研究什么

研究电池随着循环数据逐步到达时，如何合法、准确地更新剩余使用寿命（RUL）。核心问题是：动态更新能否优于“早期预测总寿命 EOL，再减去当前循环数”的固定预测基线？必须先解决标签定义、物理电池拆分、前缀可见性和归一化问题，再比较模型。路线为 P0 数据审计 → P1 BatteryLife 最小可信复现 → P2 PBT checkpoint/适配复现 → P3 动态 RUL → P4 失败模式 → P5 最小创新验证。路线不是完成清单。

## 最近一次已核科学状态：2026-10-17

- HUST 原始文件与标签版本已经做过审计；文件名拆分为 47/15/15。物理身份独立核验、作者 EOL 标签与实际观测循环的关系仍须保留限制，不能直接宣布严格在线动态 RUL 数据协议成立。
- 已完成 CPMLP、CPTransformer 两次 seed=42 的有界开发试验，每次 300 个优化器步骤，共 600 步。完成回执状态均为 `BUDGET_EXHAUSTED_AFTER_PARTIAL_EPOCH`：这是预算内试验结束，完整论文复现尚未完成。没有测试集推理。
- PBT 已完成若干静态检查和一次限定的精确 DKP 键元数据采集，15 个验证电芯的键映射已找到。当前仍缺 15 个 `valid_cycle_number` 证据和 44 项历史实际 Namespace 字段；完整新运行配置尚未闭合。静态通过不等于模型运行、预测性能或训练许可。
- 文献主文接纳记录按独立 paper_id 计为 41 篇。接纳的是带限定的阅读证据，不代表公平复现、动态 RUL 性能或创新成立。原文矛盾和未核实事项保留。
- 当前不开放新增训练；最终 test 保持锁定。本次 GitHub 同步没有新增 fit 或优化器步骤。

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
