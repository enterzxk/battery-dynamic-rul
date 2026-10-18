## 2026-10-18：真实容量残差未支持RUL修正，累计状态反证保留
- **已完成**：只用既有10cal/4367成对预测检验真实容量预测innovation，0fit/0forward/0dev/test。即时方向balanced43.0284%、rho中位数-0.3698、仅1/10正rho，冻结筛选FAIL。完整保留之前容量预测能力PASS，但不将它转称RUL收益。
- **证据**：reports/learned_capacity_feedback_20261018_root/protocol.json、diagnose.py、diagnostic.json、minimal_validation.json；reports/persistent_capacity_feedback_20261018_root/protocol.json、diagnostic.json。后者独立固定无参数累计均值，作为持久偏差假说的探索性反证，不替换原gate。
- **最小验证**：原容量/RUL预测SHA、目标t=s+20单一配对、signal到t才可见、全部4367对齐、手算-2-(-3)=+1；累计[1,-1,3]→[1,0,1]以及10真实cell截断一致。无未来目标RUL进入反馈状态。
- **阻塞/风险**：累计状态方向准确率49.32%、等cell全局balanced51.62%、cell内balanced39.56%，不优于简单斜率累计控制；只5/10平均状态方向一致。此前8/10全历史平均方向不能替代在线可实现状态。关闭即时和累计容量残差RUL修正，不反号/调窗口/seed救结果，容量MAE能力结果仍有效但不是主任务。
- **下一步**：更换预测机制，不做残差修正：在fresh独立窄审/精确GO后，仅加载已存自训容量checkpoint一次，对10cal已有前缀作固定20cycle分段线性生成轨迹至0.8SOH首次通过；最多100step/2000cycle、180秒、0fit、0dev/test。与同10cal原直接RUL预测比较，完整报告未通过端点/外推/生成斜率假设；这是动态first-passage点预测工程诊断，非条件分布完成或创新证明。

即时模型残差的电池等权global balanced53.47%与within-cell balanced43.03%均保留；累计global51.62%也没有支持。统计口径的变更明确为新between-cell假说，不将它冒充原within-cell gate通过。所有源预测早已公开，可从源CSV重建派生量，原始容量行和本次逐时点派生CSV不上传。
