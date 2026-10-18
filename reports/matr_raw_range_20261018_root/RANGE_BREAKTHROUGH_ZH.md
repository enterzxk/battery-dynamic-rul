## 2026-10-18：主动修复数据阻塞，MATR原始范围读取成功
- **已完成**：NASA两cell空Capacity加载错误修复，累计24,973,571 MAT bytes仍在30MB预算；B0036/B0050首操作均为放电、首容量低而后恢复，不能把未知初始充电状态当退化失效。转向MATR选择字段范围读取，4请求/3,502,419bytes取得两原始summary；未重开整包下载。
- **证据**：reports/nasa_remaining_source_inventory_20261018_root/two_reads_failure.json、two_raw_summary.json、two_raw_read.py；reports/matr_raw_range_20261018_root/range_budget.json、failure.json、completion.json及两raw_summary；automation/bin/matr_selected_range_worker_v1.py/v2.py。项目局部h5py依赖隔离于runtime_deps/h5py_3_11，未修改全局环境。
- **最小验证**：原始actual-cycle单调、容量有限；b2c0/b2c22原始事件300/513，旧处理版299/512；去掉原始第一行后与旧容量逐值差0。描述符MATLAB string不能当char，失败保留后从已缓存块修复，未新增网络读取；barcode内部对象尚未解码为物理serial。
- **阻塞/风险**：full raw SHA UNKNOWN（只读选定块，有各块SHA与ETag绑定）；尚未生成全35cell资产/新预测fit。NASA需明确前置充电完整性，不能以未来恢复删除低值。new_fits=0、steps=0、test=0。
- **下一步**：冻结35颗非test/非12与44的MATR原始summary扩展范围预算，复用缓存；先补两cell原始单周期Qd与summary同循环核验，通过后一次生成全部35cell因果资产。之后独立窄审和scoped GO下真实强基线，不重复旧fit。账号刚查99%used且ordinaryUsageAllowed=true；恢复不解锁训练。GitHub本阶段同步待补，先前已验证26e8c9c45e681f0b54ed8dd3ba9946b2f9bbfc47仍有效。
