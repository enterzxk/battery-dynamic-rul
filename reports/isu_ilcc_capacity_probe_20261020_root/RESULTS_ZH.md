# ISU-ILCC文档与两训练电池容量预检（2026-10-20）
- 已完成：三份官方文档652449bytes一次取得，MD5/SHA匹配；README关键页4/5/9/11完成可视核对。有效名单251唯一ID/63组，解决网页旧238描述；在任何容量payload前固定train125/development63/locked63。
- 证据：data/source_audit/isu_ilcc_v2；reports/isu_ilcc_metadata_20261020_root/semantic_decision.json；reports/isu_ilcc_capacity_probe_20261020_root。
- 实际数据：capacity_fade.zip一次140256bytes，SHA2dada0f57db9dbc002abe8ed839a61403003739086cbcc207be479689b5dc7af；只解码预定G1C1与G20C1两train成员。G1C1 52测量，首次观测0.2Ah以下在作者Time49.2451389周；G20C1 9测量，首次观测越阈Time9.08620453周。这里只报告源摘要，不是模型结果。
- 最小验证：sourceID/cohort/源member唯一性、size/MD5/SHA、两CSV Time严格递增与容量有限值通过。原pre-GO阶段BLOCK和澄清后的PASS均保留；不存在的acquisition输出没有冒充已有输入。0fit/推理/开发或封存成员解码/作者代码执行。
- 阻塞/风险：作者process_data.py102-124行可用未来邻居补缺时长，142行dropna；原Time不能直接作strict-as-of特征或精确原生cycle。README明确G20-29第4周、G25C1/G26第23/24周缺失；首次观测阈值不等于潜在物理首次EOL。
- 已推进修复：对RPT_json.zip尾部一次精确65536byte Range，HTTP206/Content-Range匹配、ETag与官方MD5一致，中央目录252entry。没有下载929MB整包、没有读取RPT成员payload。目标两个train原始RPT成员压缩总12403932bytes，可有界恢复直接时间戳而不读取10GB Cycling包。
- 下一步：按next_clock_recovery_scope.json实现/独立窄审并签fresh GO，先2个local header再2个精确压缩成员Range，校CRC/大小后只提取原始RPT开始/结束时间和C/5容量；以RPT完成时间定义可见截止，不插补。先证明两样本时钟，再决定扩成训练/开发资产；locked63保持未解码。当前无新model GO，不把源摘要schema通过当训练许可。
