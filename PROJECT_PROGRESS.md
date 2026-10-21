# Battery Dynamic RUL 当前进度
权威科研根：`/home/yndx/zxk/rul`。更新时间2026-10-21。当前阶段V18 DART-RUL，C4继续封存。

## V18完整窗口真实比较：NO_GAIN
- 已完成：DataV2完整窗口合法目标、HGB事件两头、标准动态风险、共享/分开DART与无平移消融；3seed全部21CPU+12神经fits/3600steps完成，保存79065行开发预测；另0fit50106调用完成1193报告到达前后panel。
- 证据：[完整结果](experiments/dart_rul_v18/RESULTS_ZH.md)、[冻结协议](experiments/dart_rul_v18/protocol.json)、[主决定](experiments/dart_rul_v18/analysis_v2/root_decision.json)。主指标未确认sparse+delay pooled cell-equal Brier：HGB两头0.031653、DART共享0.059571（高88.2%）；delay全窗口MAE2.3587 vs3.0284周。当前候选不进入C4。
- 最小验证：独立原CSV复算重现全部主指标、query/标签/事件闭合一致；C4读取0。473对无报告查询DART平移误差<=2.8e-16。CDF浮点超界与近p1条件S+误差单列，84条无穷logscore原样保留；不宣称逐项严格数值合法。
- 真实风险：T是首次源RPT实测Q<=0.20Ah，不是潜在物理EOL。物理serial未核；noT未来不可评分、未知停测非独立删失。开发多轮暴露，三优化seed不是独立队列。宽泛机制新颖性未建立；当前DART不是完整纵向事件联合生成模型。
- 下一行动：从保存损失/逐cell失败解释神经区间过窄及新增信息价值；提出不同可证伪机制后才另签预算，当前无新fit GO。不要扩大失败候选seed或重启旧滤波参数搜索。[确认方案](docs/DART_V18_CONFIRMATION_PLAN_ZH.md)仅方案，未授权C4读取。

## 保留的旧路线和预算
旧MATR/PBT/CPMLP/CALB/CS2 NO_GO、已消费预算与封存test保持。固定双状态滤波STOP，普通标量滤波相对强HGB平均MAE仅改善0.595%，旧GRU基线NO_GAIN，均不因V18结果重开。累计CPU调用57（旧MATR41另记），神经18fits/6281steps；恢复/到达panel均0fit，原失败receipt保留。

## 历史与公开范围
此前完整进度和ChatGPT上下文已按原始UTF8字节无损归档：
[归档验证](reports/progress_history_public_lossless_v18_binary_20261021_root/validation.json)，[解码器](reports/progress_history_public_lossless_v18_binary_20261021_root/decode.py)；archive.bin SHA `189bfa37833b2c800d24f2ae3c0268a16318375320cd7e09f6e083d4d186f57a`。公开旧提交[1e3a3de](https://github.com/enterzxk/battery-dynamic-rul/tree/1e3a3de4173f68e6ae55ab3ebb485deb17f38dcc)保留。服务器旧文档与原预测未丢失。当前入口为便于阅读的精简索引，不把历史负结果改写成成功。

GitHub只发布白名单代码/协议/报告/压缩静态证据；新54MB预测、panel原表、原始容量、checkpoint、论文全文不公开。12MiB cap不扩。唯一15分钟heartbeat仍为battery-dynamic-rul，Windows BatteryRUL-Controller保留。
