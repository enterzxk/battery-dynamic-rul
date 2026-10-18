# MATR 原始第二批 DataV1（2026-10-18）
## 实际交付
已完成35颗获准源电芯的原始MAT summary→规范循环表→past-only前缀资产。26train/9development，9445/3586前缀，所有35颗均观测到名义1.1Ah的80%首次实测越阈。原test6颗、续测别名5颗和特殊映射风险b2c12/b2c44未进入本资产。
服务器资产目录：/home/yndx/zxk/rul/data/processed/data_v1_matr_raw_batch2/。manifest SHA256 fcbedb9ee4ea9da83efe3239cda3d56d629678b3dbbd90b675039f6456ad32c1。每颗循环表与特征文件有独立SHA；不上传原始容量曲线。
## 验证与成本
两颗b2c0/b2c22的原始actualcycle100：单循环Qd最大值与summary同循环容量差<1e-6Ah，采样时间不倒退，特征在截断到当前循环后重算相等。全35颗实际循环整数/严格递增，0缺口、0无效容量；原始删首行后与旧处理版容量逐值差0，但循环号不能继续用旧重新编号。
扩展阶段只新增16请求/16777216字节，34.60s；复用此前4个缓存块。所有请求绑定官方原始文件ETag及精确Content-Range，缓存逐块SHA。完整原始文件SHA仍UNKNOWN；不能把部分下载或范围块当成完整文件。
## 边界
身份为原始batch/index；MATLAB string型barcode的内部表示没有当物理serial。已有9development电芯已用于前期开发，非新独立确认集。原始单循环核对和past-only构造不等于BMS仅I/V部署或独立泛化证明；这里假设完整实验室循环容量在循环结束时可用。单batch/event-only无法证明自然删失收益。
## 运行与后续
生成器 automation/bin/matr_raw_batch2_asset_worker_v1.py 通过本地内存HTTP范围桥接运行，协议/两样本核验/完成回执位于本目录；create-only预算已消费，不重复生成。下一实际实验是固定seed42的3CPUfit：稳健20速率线性基线、同输入非线性强基线、相同非线性模型只加稳健100速率。独立关键审查和精确hash ROOT_GO前不fit，全球训练门不开放。
[官方MATR原始入口](https://data.matr.io/1/projects/5c48dd2bc625d700019f3204)，文件URL及ETag、原始索引及split源码hash见protocol/manifest。作者数据字段说明见[原作者README](https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation)Summary和Cycle段。
