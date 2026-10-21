# Battery Dynamic RUL 当前进度
2026-10-21：原始信号信息价值研究。权威科研根 `/home/yndx/zxk/rul`；C4封存未读。

## 已完成：真实RPT信号资产与首轮信息证据
- 已完成：188电芯、4108条valid RPT曲线资产；原74维→完整RPT标量→Q-V/dQdV的先导对照，20个新增CPU拟合、22590行开发预测。旧V18结果/权重/失败/预算保留。
- 证据：[先导结果](experiments/multisource_information_20261021/RESULTS_ZH.md)、[独立复算](reports/multisource_20261021_literature/information_independent/INDEPENDENT_RECOMPUTE_ZH.md)。CatBoost加曲线后完整/隔次/迟报MAE从2.1353/2.2156/2.4135降至1.7912/1.8610/1.9398周；HGB也改善，概率/覆盖并非全面改善。
- 最小验证：源RPT索引/stop精确匹配、原始CRC/manifest、cell隔离OOF、所有拟合先于开发预测、22590行独立重算及逐cell bootstrap；C4读取0。
- 风险：仅开发信息证据；未证明容量归一后曲线形状贡献；旧先导F0/F1/F2是嵌套标签，**不是新指令正式2×2的F0/F1/F2/F3**。C3同组新电芯不能叫未见工况。
- 下一步：[正式2×2设计](experiments/multisource_factorial_20261021/design.json)：F0=74，F1=RPT，F2=Cycling，F3=both；提取真实循环特征，优先无新RPT期间的运行信息价值及公平强基线。

## 方法与原始运行信号
B轨迹分布原型和独立增量消融各真实500步已完成，开发评估单独GO进行；当前74输入模型不代表多源创新。A等待有源时间戳的Cycling资产，禁止用日历clock冒充运行推进。Cycling归档按成员/小Range缓存，20个完成+1pilot及失败partial保留，恢复只取缺失成员，原始数据不公开。

## 保全与公开
V18完整窗口DART=NO_GAIN，强HGB双头保留，旧PBT/滤波/GRU等STOP/NO_GO不重开。旧累计57CPU+18神经/6281steps；本轮新增20CPU+2神经/1000steps，MATR41另记。C4、Final/test继续锁定。
GitHub仅白名单代码、协议、主表/逐cell静态证据。旧公开证据通过无损归档保留原UTF8哈希和旧提交，12MiB上限不扩。原始信号/权重/论文全文/认证/模型会话不公开。现有heartbeat不重复创建。
