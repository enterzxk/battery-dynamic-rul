# GitHub 文件与任务进度同步规则

用户于 2026-10-17 明确授权新建并同步到公开仓库 `enterzxk/battery-dynamic-rul`，默认分支 `main`。这是服务器研究项目的公开阅读镜像，服务器继续是原始科研证据的权威来源。

- 复用当前每小时任务 `battery-rul`。每个实质阶段完成后，更新 PROJECT_PROGRESS.md 和 docs/CHATGPT_CONTEXT_ZH.md，再导出并同步；上轮存在未同步内容时，下一轮先补同步。无内容变化不制造新提交。
- 导出命令：`/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/automation/bin/export_github_context.py`。导出只读取文本和已有预测，不加载数据二进制、不训练、不重算指标。命令返回本地于服务器的 bundle 路径和内容摘要。
- 上传使用已连接的 GitHub 工具：先读取 main 最新提交/树，在其基础上批量 create_tree（bundle 中 tree_elements，按需分批）→ create_commit → update_ref，保留父提交并核对 expected_sha，force=false。初次空仓库需先通过 create_file 建立 README 初始提交。权限缺失、认证失败或分支冲突时保存失败，不覆盖远端变更、不读取凭据、不自动更改仓库授权。
- 同步白名单：项目自有 src/configs/results、选定研究说明、必要数据/as-of/PBT 报告与活动入口引用的静态文本证据、文献接纳记录与综合、已有实验配置和运行回执/指标/validation 预测。完整源数据、checkpoint、论文PDF/全文/逐篇长笔记、第三方 repos、环境与运行目录、认证文件、原始控制器日志和模型会话不上传。
- `public_snapshot.json` 保存快照时间、每文件大小/SHA256及可重现的内容摘要；仅在内容变化时刷新时间。服务器导出 bundle 是控制产物，不上传自身。
- 每次同步成功后，回读仓库的 public_snapshot.json 与关键入口，确认其内容/摘要与导出一致，再将提交SHA、URL、导出摘要和同步时间记录到 `automation/state/github_sync.json`。不能仅凭本地导出或 commit 对象创建成功报告“已上传”；分支必须更新且回读成功。
- 项目状态和网页版 GPT 的回答按发布时刻解读；额度/连接不可用时不保证准点同步。只在实质进展、完成、失败或需要人处理时通知。

公开镜像保留原始科学文件内容与哈希。引用中未上传的二进制和全文仍只在服务器上存在；公开清单明确列出实际内容，不伪称完整公开复现包。
