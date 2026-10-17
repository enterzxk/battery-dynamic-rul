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
