# MATR v11官方发布来源凭证：有界核查

结论：**STOP_ACTUAL_V11_GENERATOR_PROVENANCE_NOT_CLOSED**。本轮能确认发布身份、文件MD5和官方仓库入口，不能把当前pinned代码绑定为实际MATR.zip生成器。原方向A回顾性NO_GAIN闭合、strict_online资格0、PBT已消费预算和模型/test门不改变。

## 已核官方材料

1. [Zenodo record19688272](https://zenodo.org/records/19688272)，页面Published/version、News、Files的MATR.zip行及Software repository入口：v11，发布日期2026-04-22，MATR.zip MD5为83a1528858b9e1b7b6886757bb561669，与服务器现有VERIFIED_ARCHIVE_ONLY下载回执一致。本轮只比对既有回执，不重新读4.86GB归档。
2. 页面指向的[Version11更新说明](https://github.com/Ruifeng-Tan/BatteryLife/blob/main/assets/Version11_Update_Details.md)，第3项的MATR变更是MATR_b3c0.pkl的seen/unseen类别调整。这是数据分类说明，不是生成该归档的源码commit/配置/执行记录。

在这些已读页面及该更新文件中未找到精确generator绑定。这个结论仅覆盖已读材料；不能扩大成“官方所有metadata都没有凭证”。当前GitHub main更新说明可变，不能自动等同于发布时实际代码。

## 完整API metadata未核

网页工具打开https://zenodo.org/api/records/19688272不可用。服务器一次公开API请求也失败：URLError，Temporary failure in name resolution。未修改DNS、代理或全局环境，未重试；API字段完整性标UNKNOWN，不能把获取失败当字段不存在。没有下载数据集或读取数据二进制。

## 证据、最小验证与停止条件

`acquisition_receipt.json`记录一次API请求错误、官方网页选择性事实和现有归档回执SHA；`web_source_observations.json`明确是从网页选录的事实，不冒充原始HTTP快照或完整API响应；`root_review.json`冻结核查范围、已核/未核边界与STOP。pinned Version11说明文件SHA为3d451b98765d405475de3f2824e5fe6d2bca2bc8a436f82e547ab03ef0d261e1，与实际生成器绑定是不同证据问题。

new_fits=0、optimizer_steps=0、binary_reads=0、test_access=false。无新版本数据切换、不重复下载、不把标签代码重建或MD5一致当strict在线证明。没有新增来源凭证时，不再循环反推该生成过程。

下一步转回P1：只读已有CP开发完成回执、冻结配置及checkpoint文件清单/stat，判断是否存在可以独立预算推进的忠实复现路径；不加载checkpoint、不重跑既有fit、不重置旧600步预算、不凭本报告启动训练。当前完成的元数据核查不是新训练授权。
