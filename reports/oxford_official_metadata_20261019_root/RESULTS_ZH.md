# Oxford Battery Degradation Dataset 1：官方元数据有界核查，协议未闭合

2026-10-19。本轮仅一次候选来源的官方文本核查，不下载MAT、示例曲线或论文，不解码电芯，不训练。

## 实际结果
Oxford Battery Intelligence Lab官方Data and code页面第19行确认：Battery Degradation Dataset1包含8颗Kokam SLPB533459H4、740mAh软包电芯，并链接数据集DOI。
来源：https://battery-intelligence-lab.github.io/data-and-code/ 。

ORA官方记录的搜索索引视图列出作者Howey/Birkl、2017/version1、DOI10.5287/bodleian:KO2kdmYGg、主MAT与Readme文件条目，并显示ODC-ODbL许可。但直接打开该官方记录返回HTTP403；这些记录级字段仅标记SEARCH_INDEX_OBSERVED，不能冒充已成功回读实时官方记录、实际文件或许可全文。
记录：https://ora.ox.ac.uk/objects/uuid%3A03ba4b01-cfed-46d3-9b1a-7d4a7bdf6fac 。
一次限定到同官方域的Readme下载链接搜索无结果，没有重试403、尝试绕过访问限制、访问第三方镜像或下载数据。

## 判定
METADATA_IDENTITY_ONLY_PROTOCOL_UNVERIFIED_NO_RAW_DOWNLOAD。
官方实验室的电芯数/型号/标称容量支持继续把它视作候选，但不能据此签数据导入或确认实验GO。
下列内容本轮均unverified：
- 完全充电/放电与容量测量的具体资格、截止规则；
- 起始记录是否足以支持第一次阈值事件的解释；
- 原始实际循环号、容量测量采样间隔及事件/删失边界；
- 文件实际字节、完整SHA/可读取格式，以及CellID至物理serial/别名映射；
- 本项目现有模型需要的静态工况输入是否可合法构造。
不从数据集简介或相关论文摘要补齐这些方法字段；也不把搜索索引的文件大小和许可标签当已验证下载合同。

## 与现有证据的区别
NASA B0033已经真实读取并因首段容量资格未证/当前冻结无前缀而停止；本Oxford候选尚未读取任何电芯，不产生模型指标，不宣称已经建立独立确认集。
本轮没有核Oxford在旧项目/预训练来源中的逐物理身份重叠，不将“本轮未读取”写成“已证明完全未暴露”。后续若进入候选登记，需先复用已有来源清单核名字/来源重合，身份缺证限制明确保留。

## 交付、预算与下一步
evidence.json明确区分成功读取的官方实验室页面、官方搜索索引记录、403正文访问失败和无结果搜索；保存URL、位置、观测时间与结论边界，不伪造原HTTP快照/Readme SHA。
decision.json将raw_download_allowed=false、execution_allowed=false及待核字段落盘。
实际2次查询、2次页面打开；其中官方实验室页面成功、ORA正文403；MAT下载/解码、新fit/推理、checkpoint、devtest、权限变更全部0。
下一步只有在获得新的可访问官方Readme/等价原始协议证据时，关闭首段容量测量与实际循环定义缺口；相同403不循环重试，不凭当前元数据启动获取或模型。无新增访问证据时本路线保持安静，停止该候选自动派发；这不等于整个科研项目或其他已授权路线完成。
