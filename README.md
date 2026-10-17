# Battery Dynamic RUL

电池动态剩余寿命研究的代码与证据快照，供人工阅读和 GPT 对话解释。此仓库由服务器项目按白名单同步；原始数据、大 checkpoint、论文全文、运行认证信息及完整内部历史留在服务器。

**从这里开始：**

- [给 GPT 的中文项目说明](docs/CHATGPT_CONTEXT_ZH.md)：研究问题、真实结果、限制和阅读顺序。
- [项目任务进度](PROJECT_PROGRESS.md)：已完成、证据、最小验证、阻塞/风险、下一步。
- [快照清单与时间](public_snapshot.json)：实际同步文件、SHA256 和来源。
- [真实开发结果](results/development_hust_v11_seed42_v1.csv)：CPMLP / CPTransformer / 训练中位数基线。
- [代码](src/)与[配置](configs/)；[公开同步规则](docs/GITHUB_SYNC_ZH.md)。

当前已有两次有界开发试验，各 300 步；它们是 HUST v11 作者总 EOL 估计的 validation 结果。完整论文复现、PBT 运行及严格在线动态 RUL 比较尚未完成。最终 test 锁定，文献接纳和静态检查不代表性能结论。

在网页版 GPT 中贴此仓库链接，并请它按 `docs/CHATGPT_CONTEXT_ZH.md` 的阅读顺序解释。GPT 必须实际获取文件；聊天记录不会因同步仓库而自动互通。若连接器未收录或网页无法访问，可下载该说明与进度文件上传到对话。

该镜像依赖本地应用定时任务及服务器连接；请以快照时间判断新鲜度，不能把页面当成服务器实时监控。现有代码依赖服务器数据及官方第三方项目；公开文件不等同于已打包完整独立运行环境。
