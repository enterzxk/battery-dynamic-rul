# 已知实验工况输入：语义与统一编码

本任务仅为当前原始DataV1队列核充电工况输入，不宣称部署时未知未来工况可用。P01原文Methods（PDF第7页，已存text630-649）说明0–80%SOC用预设单步/两步C-rate工况；P02原文Fig2caption（PDF第2页/期刊398页，text175-183）说明前四电流步各占20%SOC，第四步由0–80%总10分钟约束。作者policies.py第3–9、18–23、36–45行预先列电流网格并算第四电流。

出处：https://web.mit.edu/braatzgroup/Severson_NatureEnergy_2019.pdf；https://web.mit.edu/braatzgroup/Attia_Nature_2020.pdf；https://github.com/chueh-ermon/battery-fast-charging-optimization/blob/master/policies.py。准确源hash、范围与限定见source_semantics.json；本轮只核相关Methods/Fig2，未重读全部补充材料。Nature登录跳转与MATR metadataAPI网页不可用，未伪称新获取其内容。

项目既有raw worker直接将policy_readable静态字段复制到manifest（batch2worker:70，batch4worker:64），编码器只读该字符串与cell role，不读取寿命、容量未来或标签。作为该实验队列的预测时已知条件，依据预设实验协议及静态字段作有限推断；不等于独立部署/固定未来使用工况的证明，也不闭合物理serial/fullsourceSHA。

不直接拼批次或格式类别，而统一为SOC[0,.2],[.2,.4],[.4,.6],[.6,.8]四个有效C-rate：Ceff=.2/integral_bin dSOC/C(SOC)。它保留每区间充电时长；跨步区间用谐和等效值，不作算术平均。b2c6的3.6C(30%)-6C→[3.6,4.5,6,6]；b4c7的8-6-4.8-3→[8,6,4.8,3]。解析52cell全通过，26两步格式/26四步格式；四步10分钟舍入误差最大.00041004分钟。42fit30个独特字符串，10cal中6个已见/4个未见；不据此称独立新协议泛化。

v0错误拒绝两个4.8C(80%)-4.8C合法单步边界，拟合前停止。旧编码和失败记录保留；v1允许0/80边界。常数解析的严格浮点相等也曾在fit前拒绝，误差1.78e-15；改用解析恒等式1e-12容差，未变公式/数据/标签。两个手算例核对见two_encoding_examples.json。

policy_features.json冻结原字符串/role/四个数值，后续仅用于同42fit/10cal单次matched HGB pointbaseline，经独立窄审与fresh精确GO才可fit。准备、解析通过和工况可用性均不是性能证据。
