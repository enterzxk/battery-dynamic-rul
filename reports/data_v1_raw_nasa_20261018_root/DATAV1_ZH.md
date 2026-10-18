# 原始数据 DataV1 有界交付（2026-10-18）
已完成一条 NASA 官方原始 MAT → 因果容量 → 电芯隔离前缀资产链。MATR 完整原始批次下载未完成，不能把本阶段称为 MATR DataV1 或完整论文实验。新增预测 fit=0、optimizer_steps=0、test/封存 MAT 读取=0。

## 真实交付
- 官方 NASA 包 209708670 bytes，SHA256 `82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e`；内层 FY08Q4 SHA256 `f3a4fcd7c3434e06906f4222778445ce6ad42f49c5c78a785bdd676b7c223a2e`。
- 读取前冻结 B0005/B0007 train，B0006 development，B0018 locked_confirmation。3颗各168次放电，共504次；train119/development42共161个前缀。其他 NASA 子包没有解析矩阵。
- 服务器资产：`/home/yndx/zxk/rul/data/processed/data_v1_nasa_fy08q4/`，含每颗 canonical CSV、past-only feature CSV 与独立 manifest。manifest SHA256 `74acf85c1116cb919c5e68fdbdba901770ce3c07e973bb907adb85f3a983002e`。
- `import_nasa.py` 和 `preprocessing_protocol_v2.json`，两真实电芯核验通过后一次生成全部获准3颗资产；没有模型、训练或预测指标。

## 端点不能混用
| source cell | role | 原始 Capacity <=1.6Ah | 项目共同2.7V积分 <=1.6Ah | 原始 Capacity <=1.4Ah | 可用前缀 |
|---|---|---:|---:|---:|---:|
| B0005 | train | 75 | 74 | 125 | 54 |
| B0007 | train | 86 | 85 | 未观测到 | 65 |
| B0006 | development | 63 | 62 | 109 | 42 |

时间单位为累计完成的放电序号，不是包括 charge/EIS 的616条源操作编号。B0007 在原始1.4Ah口径未观测越阈，应在末次168放电右删失；没有把末次记录当精确失效。上述1.6Ah项目端点均观察到事件，不由本阶段产生自然删失收益证据。

README首段说明额定2Ah、原实验30%fade到1.4Ah、各电芯截止2.7/2.5/2.2/2.5V；字段表却统一将 Capacity 描述为“到2.7V”，该语义冲突保留。原始 Capacity 全部保留，另建共同2.7V积分量，不覆盖原值或冒称原版 NASA 复现。共同截止只是操作定义，完整SOCspan/物理健康80%仍未证实。
共同容量由同一次已完成放电的 I/V/Time 计算：负测量电流整流，秒/3600转Ah，负载电流<-0.1A后首次下穿2.7V，末采样区间线性插值。没有跨循环/未来数据插值。记录起始处已在阈下、缺截止、非有限值或时间倒退均标缺失。

## 最小验证及边界
B0005/B0006第1和20次真实放电，独立逐区间梯形求和与向量积分误差<1e-10 Ah；原始80%端点与首次源检查一致；prefix20截断历史重算相等。每次源操作号与原始时间保留；时间区未声明，使用naive源日历坐标，没有假称UTC。固定2Ah归一化，不拟合全寿命极值/缩放；保留63个容量回弹相邻对，没有按未来轨迹删除。共同截止无无效放电记录。电芯身份仅NASA原始编号，serial/跨来源alias仍unverified。
本阶段3颗在项目80%端点前均不满100次历史，past100全部缺失；它们不能支撑100次长窗贡献，不能为让候选生效临时移动窗口。2train/1development不足以支撑论文比较，不开放新fit。下一版实验必须在匹配的工况、足够的训练/开发电芯和冻结端点下定义可用的多尺度窗口。
本报告的元数据与代码公开；原始压缩包、MAT、canonical/feature曲线仅留服务器。

## MATR 传输失败保留
现存 `data/raw/MATR/MATR_v11.zip` 是BatteryLife处理版，不是原始MAT。远端两个下载域名DNS失败，不修改DNS/代理；Windows可访问官方MATR。新冻结第二批2,007,331,155字节/600s/一次下载后内存直传SSH，没有Windows原始数据文件。939524096字节/379.8s观测推算总811.46s，超资源上限而提前停止；最终部分文件1013972992字节保留，未解码或当完整数据。未重试/自动扩大预算。官方源可访问，失败原因是传输速度，不声称来源不存在。NASA一次209708670字节下载在300s预算内成功。
控制证据在 `reports/data_v1_raw_matr_20261018_root/` 的 acquisition_budget、availability_probe、matr_batch2_stream_budget、matr_transfer_stop、nasa_stream_budget。MATR importer只是准备且未执行，不计作交付完成。

## 复现与下一步
已消费的数据生成动作不重复写原目录；复核可读取 manifest 和两电芯核验，不需要重跑。首次生成命令：
`/home/yndx/miniconda3/envs/a40_env/bin/python reports/data_v1_raw_nasa_20261018_root/import_nasa.py`
这是create-only生成器，再次执行会拒绝覆盖已有资产。代码SHA256 `df338e327d53a4b6bf193de2efce64ea0ca3d9da45b2d6e51e7863687502961c`；协议SHA256 `c5377ddda74f2d6f558070d24a18704dd13ac9b49153863b4325107c68ff8f1b`。
最高优先下一动作：只读已下载NASA其它5个子包的目录和README，确认相同源电芯编号的续段/别名及测量协议；在读取其MAT前冻结兼容电芯的训练/开发/封存分组，再有界扩DataV1。若协议不兼容则不拼成一个队列；MATR的下一次源读取另冻结最小必要字节方案，不重跑已消费全文件票。
全球 new_fits_allowed=false、旧1+3CPU/41CPU/神经4fit2580steps/PBT票保持原账；本阶段无新预测fit，尚未设计/授权新预测预算。

## 来源与实际读取范围
- [NASA官方仓库页面，第5项 Batteries](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/)给出Saha/Goebel2007引用与官方镜像下载；本阶段完整下载其链接，但只解析FY08Q4内三颗MAT，B0018及其它子包MAT不读。
- [官方页面所指原始包](https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip)内 `README.txt` 的Data Description首段、Data Structure/discharge字段；完整原文仅服务器 `source_inventory_readme.json`，没有上传原始包。
- MATR下载URL与文件绑定复用 pinned `repos/audit/BatteryML_2861ae3b8c79938c7fc8e6fe9986b799ca71c7dd/batteryml/preprocess/download.py:16-17`；[BatteryML官方数据准备](https://github.com/microsoft/BatteryML/blob/main/dataprepare.md)的MATR段，及[原作者数据载入说明](https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation)Descriptors/Summary/Cycle段。没有把处理版文件或已准备脚本称为原始MAT完成。
