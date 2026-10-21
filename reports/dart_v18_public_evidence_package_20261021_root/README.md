# V18静态复现证据（无损）
archive.bin是zlib压缩的UTF8 JSON，包含本轮项目自有源码、冻结协议/GO、原失败与恢复/到达回执、指标表、独立复算脚本/审查和文献竞争记录。每个成员原始字节大小及SHA在index.json。没有原始容量、checkpoint、论文全文或逐query预测。

使用 `python decode.py archive.bin NEW_DIRECTORY` 恢复，目标必须不存在；只在新目录创建文件，不覆盖旧结果。执行实验还需要服务器合法DataV2与既存权重，已消费GO不可重复使用。此包不是完整原始数据复现包。

入口：[实际结果](../../experiments/dart_rul_v18/RESULTS_ZH.md)。新开发CSV三份共54,091,748字节，以及完整arrival_panel.csv、旧预测与全部权重保留服务器。原预测未丢弃或重算替代；公开体积上限仍12MiB。

恢复审查GO后追加了独立文献附录，review_amendment如实保留旧/新审查摘要及无法逐字节重建旧版的限制；实际执行源码/模型哈希与预算绑定不变。数值边界瑕疵和无限logscore不隐藏。
