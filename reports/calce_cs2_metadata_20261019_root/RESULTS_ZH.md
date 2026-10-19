# CALCE CS2：官方协议可读，登记四电芯候选；尚未获取数据

2026-10-19。仅元数据，不是实验结果或独立确认。
官方依据：https://calce.umd.edu/battery-data ，CS2小节第246–263行。

已读事实：标称1100mAh；统一0.5C恒流充电至4.2V，恒压至电流低于0.05A；未另指明时放电截止2.7V。CS2-35/36/37/38列于1C恒流放电组；来源编号为随机编号电芯，数据按测试日期分Excel文件。物理serial/跨来源别名及实际文件完整性仍未核。不能把同页INR低电流OCV小节的启动说明移植到CS2。

决策：METADATA_PASS_FOR_PREFLIGHT_ONLY。相较只有简介的候选，这里有直接实验协议依据，可准备获取前检查；raw_download_allowed=false、fit_allowed=false、confirmation_ready=false。
首次容量是否在所述完整充电后测得、跨日期循环号是否连续、是否实际越阈或删失，必须以后续合法字段验证。不能从页面预判EOL，也不以全寿命最大值归一化。若采用80%nominal，0.88Ah仅为项目预先候选目标，不冒充官方已观测EOL。

prospective_roles.json在任何新数据获取前登记35为candidate_train、36为candidate_development、37/38为locked_candidate；这是读取上限，非科学资格。没有做充分功效计算，不把两locked候选当足够独立确认，也未验证本项目/预训练是否存在来源重叠。
下一步仅从官方HTML解析CS2-35链接并做单次HTTP HEAD：HTML<=262144bytes、15秒、最多1次HTML请求+1次HEAD、数据body=0；未知长度/错误STOP，不转GET、不改权限、不读其他电芯。header_preflight_budget.json不是raw读取GO。
正式下载、解码、模型适配/推理/训练及locked读取仍需各自冻结范围和新exactGO，不能复用旧票据。现有MATR多段schedule输入适配未证，不直接称跨数据独立确认。

本轮1次搜索+1次官方页面读取；新raw文件/电芯解码/fit/推理/checkpoint/devtest均0。服务器目录：reports/calce_cs2_metadata_20261019_root。来源字段/位置与未核边界保存在evidence.json。
