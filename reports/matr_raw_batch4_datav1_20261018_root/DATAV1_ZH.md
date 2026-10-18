# MATR 原始第四批 DataV1 已完成
## 2026-10-18：第四批原始数据格式阻塞已隔离修复，70cell因果资产完成
- **已完成**：官方第四批HEAD锁定2,601,295,745bytes与ETag，21次范围请求/21,798,785bytes；两真实cycle100容量核验后发现b4c31原始cycle833条而QDischarge834条。保留v1失败，整cell隔离；v2完全缓存0新GET完成另外35颗。
- **证据**：reports/matr_raw_batch4_datav1_20261018_root/DATAV1_ZH.md、source_receipt.json、protocol.json、failure.json、repair_v2/protocol.json及completion.json、combined_cohort_summary.json；data/processed/data_v1_matr_raw_batch4/manifest.json SHA862d796f8b1ba2d0d865884de1d77e32f2e7ce00480327299209d966c73bbe8e。
- **最小验证**：b4c1/b4c3 rawcycle100 Qd最大值与summary差0、时间单调与prefix截断相等；保留cell循环无缺口/无效，旧容量去首行后差0。一次关键失败诊断找到长度不匹配，未截断配对/重编号/改标签；无需新增smoke。合并52train/18development、26848/9561origin。
- **阻塞/风险**：train事件范围148–561扩大至148–1056，修复寿命范围不足的数据条件，尚未证明模型收益。两批全为已观测事件、18dev已用于开发，非独立确认/自然删失收益；物理serial未闭合，fullsource SHA未知。隔离b4c31导致不同于旧52/19队列，不直接比较总指标。本轮new_fits=0、steps=0、test=0，旧GO消费不变。
- **下一步**：冻结两批52训练电池的按源ID且分批稳定哈希留出校准组（每批5颗共10，余42fit），实现同一固定HGB的训练残差/独立电池校准残差概率对照；一次关键窄审与精确GO后只跑1CPUfit，评估18dev但不调参、不作独立确认；测试仍锁定。检验coverage/宽度/Brier与逐cell差异，不把校准称新方法或预设收益。

官方source API：https://data.matr.io/1/api/v1/file/5dcef152110002c7215b2c90/download
固定assetstore：https://data.matr.io/assetstore/85/13/851331bb015245eba64586099449fa93
ETag：8aba93a84a5c353645274b231a3707b0-311；这是multipart版本标识，不是MD5。
运行：Windows控制器只作HTTPRange/SSH桥接，科研程序automation/bin/matr_raw_batch4_asset_worker_v1.py → _v2.py；原始块和曲线只在服务器。复现应读取协议/缓存，不能重跑create-only目录覆盖证据。
预处理：名义1.1Ah、first QDischarge<=0.88Ah为观察事件；实际cycle编号、past-only20/100 Theil-Sen、无未来归一化/插值；两batch合并sourceID不重叠仅证明源文件角色分离。
第四批26train/9development、17403/5975prefix；事件范围train443–1056、dev506–914。batch2仍26/9、9445/3586。b4c31未来只有建立原始逐条对应证据才恢复，不能靠删最后一行来通过。
这里没有新的预测、模型构造或测试。原始资产可供下一项受限真实实验，不是正式论文复现完成。
