# 稀疏、不规则健康观测下的单电池在线动态RUL创新冲刺
2026-10-20用户最新明确指令，优先于旧CS2-only等待及旧模型小修待办。复用现有项目/coordinator/automation，不重置旧预算，不开放封存确认，不以此覆盖旧数据/模型训练门槛。

研究任务：并行完成ISU-ILCC官方语义及原始时间核验/完整DataV2和冻结train/development/confirmation；评估UConn-ISU-ILCC LFP/Gr第二体系；建立早期条件预测、强HGB动态、统计动态生存、一项时序模型、普通状态融合参考；探索运行与观测时钟不同步的状态估计、innovation更新、连续时间退化、条件寿命分布及观测可靠性。DORA-RUL仅候选，不强制架构。
必须核查2024-2026动态生存、液体神经、Graph-Mamba、随机退化与在线滤波的真实机制重合。Mamba/Wiener/GRU/SOH-RUL联合/普通门控/混合本身不作创新。评价原始/稀疏/延迟观测、容量回弹、工况变化下的精度、分布、高估、逐cell与更新行为；优先击败强简单基线。
在数据合法、预算与freshGO后主动执行足够规模对照；允许必要多seed/消融/数据体系，不为限制次数牺牲科学探索。独立确认在方法及选择冻结后另行开启。用户授权必要子代理并行开发和独立审查，主协调统一科学决策。
本轮交付目标：可运行DataV2协议、强基线主表、候选完整设计/初步实现、真实对照与后续独立确认方案；不能只交研究计划。持续推进，不为普通子任务反复询问。

执行配置：主协调按项目要求gpt-6.1-sol/high，子代理gpt-6-luna/high；请求配置不冒称可独立内省的运行时身份。科研写远端/home/yndx/zxk/rul，本地仅.control控制与日志，认证/环境/其他项目/限额不碰。
当前已完成：251IDs按C1/C2=train125、C3=development63、C4=locked63在容量payload前冻结；官方文档652449bytes；capacity摘要仅G1C1/G20C1两train已读；RPT源精确central range65536bytes已206，两个成员压缩总12403932bytes可恢复原start/stop。作者Time的未来邻居插补禁止直接当strictasof特征。新数据继续按source记录身份，不冒称物理serial已核。
当前门：new_fits_allowed=false/pending_experiment=null，CPU20=RUL18+辅助2、神经4fit/2580steps、旧MATR41均保留；新预算须累计另记。先两RPT成员合法读取/CRC及日期-容量映射验证，再一次生成非locked资产。当前无未消费RPT成员或模型GO。
当前并行分工：isu_datav2负责原始时钟读取与DataV2；baseline_dora负责强基线/候选设计实现但未获准真实fit；coarsening_review负责最新竞争和LFP官方可行性。共享状态/训练放行/进度/公开镜像由root写。未新建自动任务或控制器。

事件信息约束：运行不等于潜在EOL未发生；不把未知缺口冒充合法右删失；首端点明确为原始RPT完成时首次实测Q<=nominal80。无测量时不免费获取T>current的oracle状态；稀疏/延迟的arrival、forecastorigin与event信息权限要冻结且同臂一致，若oracle参考则单列。未来RPT值不进入输入；完整寿命均值DoD等禁止用作初始已知工况。
