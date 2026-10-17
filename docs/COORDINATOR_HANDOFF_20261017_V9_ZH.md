# Battery RUL V9：压缩后的真实执行断点（2026-10-17 UTC）

本地 E:/桌面/rul 仅控制；科研写 SSH lab-server:/home/yndx/zxk/rul；Python=/home/yndx/miniconda3/envs/a40_env/bin/python。按AGENTS主协调请求gpt-6.1-sol/high，独立子代理gpt-6-luna/high；运行时身份未独立内省。此交接不开放任何既有禁门。

- 用户原始交接已原样保存 docs/Battery_RUL_Codex_Handoff_20261017_ZH.md，SHA256=96486eb216e711c1e32808717f94892def2e70da4dcf5b05ad372625e92e729a。要求立即推进真实PBT/信息增量；不重读41篇、不重复DKP/训练/smoke。
- 当前根主控 01a14a34-4ec4-7e91-995f-42318e1322d3 已锁内接管（reports/handoff_execution_20261017_root/takeover_receipt.json）；创建fresh successor前将在锁内改READY_FOR_SUCCESSOR。接续后先核当前coordinator、交接SHA、锁/真实进程及./rul.sh status，再锁内写自己的owner/thread_id/heartbeat/actual_cwd/takeover_verified。不要沿用旧successor字段。
- 上一窗口发生明确压缩（2026-10-17T15:30:40.150Z，compaction_count=1）；不是累计消耗达到475k。应实际迁移既有battery-rul每15分钟任务、核新项目/cwd/active/owner并打开新聊天；不新增重复任务。用户已授权。

## 已完成与不可重跑

1. PBT生产IO由独立代理pbt_io_wrapper实现，root查出v1 worker绕GO问题后v2修复，root只核此修复不重跑旧测试。reports/pbt_valid_cycle_production_io_20261017_luna/production_io_wrapper_v2.py SHA=756e3ff1957a41fff5e3dc26c6ea900a1657d6b69a296f5436eb8038d7987c7e；exact_spec_v2.json SHA=6008c4bb1755c0fdc243ace563577307f3f76b044fbe616c9370d6642a2e01a7；helper SHA=d2ef21d9345fb20953b689eae690028ca414fd0b52b3ba77720ae85d1b438a19。
2. root_review_v2.json及ROOT_GO.json允许且仅允许固定首4文件一次结构读取（不解码数值，不反序列化，不构造模型）。已实际执行一次：shard1.v2.receipt.json=FAILED_STOP_NO_RETRY，Stop entry_cap，实际读2250966字节，invocation_consumed=true。没有成功valid_cycle_number结果。不得重跑/增加entry cap/自动转下个分片；此前DKP预算亦已消费。当前PBT模型构造/strict load/forward/metrics/fit/test均未开放。15个valid-cycle、44个历史Namespace缺证仍保留；新配置可单独显式冻结，不能伪称历史配置已知。
3. MATR独立文本轨道候选表已经实际生成：reports/dynamic_A_eligible_20261017_root/{protocol_candidate.json,eligible_origins.csv,candidate_features.csv,cohort_receipt.json}。544候选时点，530工程候选，99train/34val源ID电池；其中52train/19val observed-event电池。k=50/100/150/200，k0=50，20cycle过去OLS速率；未读test摘要/未新读binary。来源v11既有文本audit，SHA全在cohort_receipt，不重建。
4. 别名b1c0..4与b2c7/8/9/15/16按已有合并关系处理；已知next-cycle remap整电池排除b1c0/b1c18/b2c12/b2c44。实际v11生成器及其余物理serial未核实；strict_online_eligible=0。只可能允许“已处理记录前缀/作者EOL回顾性工程诊断”，绝不能称严格raw-asof在线、独立物理泛化或真实可部署I/V输入。实验容量为已测完整循环放电容量。observed-only结果是条件子群，不能冒充全电池。
5. experiments/dynamic_A_matr_retrospective_seed42_v1/runner.py已写但未运行，无ROOT_GO/claim/fit。A0 k50一次EOL递减；A1 age/soh/累计Ah/batch；A2仅加过去20循环速率；固定同cell/origin、train-only GroupKFold3+4alpha，归一化训练fold拟合，cell-equal权重。计划39个Ridge fit（包含CV），仅A2增益<5%时追加固定GBDT A1/A2两次，上限41；closed-form optimizer_steps=0。primary全34val作者EOL，另19observed子群；test禁用。原动态v3协议DRAFT/false保持，不借诊断打开它。当前本轮new_fits=0；历史CPMLP/CPTransformer=2fits/600steps，不能混记。

## 第一项尚未执行的实质动作

对上述唯一候选protocol+runner做一次窄范围独立审查（可新建gpt-6-luna/high reviewer，唯一产出reports/dynamic_A_matr_retrospective_independent_20261017_luna/review.json；只读必要文本/代码，不训练或再审PBT）。判断在清楚保留物理身份/生成器限制的回顾性工程lane是否可跑，重点核无未来特征、同源cell拆分、train-only归一化、固定cohort/标签、fit预算和主指标。root独立判定后如可接受仅在该实验目录create-only ROOT_GO.json绑定runner/input/protocol SHA，status=GO_RETROSPECTIVE_PROCESSED_RECORD_DIAGNOSTIC_ONLY, strict_online_claim=false,test_access=false，随即执行runner一次，不加smoke。若真实关键泄漏/标签矛盾必须具体STOP，不能为训练改标签。

完成后从validation_predictions.csv独立重算小样本+完整cell-macro Time-MAE、paired改善比例、bias/尾部/年龄层；如已有39/41fit receipt绝不重跑。按用户>=约10%且>=60%电池改善才推进、<5%且固定GBDT无益则NO_GAIN、不确定则INCONCLUSIVE；不是创新成立或最终论文结论。不要一失败换大模型。若独立review阻塞则报告最小缺证，不循环审计或篡改门槛。

## 持久状态与公开同步

更新PROJECT_PROGRESS五项及docs/CHATGPT_CONTEXT_ZH；按automation/bin/export_github_context.py白名单增量同步公开enterzxk/battery-dynamic-rul/main，正常非强推+回读，记录automation/state/github_sync.json。不要上传raw/checkpoints/fulltexts/auth/会话/控制日志。当前已验证旧提交55d361a29d7606c1a4d41a6acae6911b0578ecd2，最新以sync.json为准。详细精读已在reports/literature_discussion_20261017_root_v1，不再重做。
