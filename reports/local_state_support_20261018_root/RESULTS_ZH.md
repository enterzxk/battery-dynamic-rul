# 两个相反概率失败病例：局部状态与训练标签支持诊断

先冻结protocol，再读取42fit22281prefix及固定2cal841prefix（b4c7/b2c6）原特征。用fit-only每origin median/IQR缩放age/SOH/robust20，按每颗训练sourcecell的最近prefix取五颗不同电池，避免单颗长轨迹支配邻居。标签仅作事后诊断输出，不进入距离或预测输入；不是新的KNN性能实验。

|诊断|MATR_b4c7|MATR_b2c6|
|---|---:|---:|
|前缀数|430|411|
|超训练逐轴min/max范围|6（仅rate）|0|
|最近IQR-L2距离中位数|.083970|.206143|
|参考距离<=.1的前缀|274|119|
|真RUL在五训练电池标签范围外|297（69.0698%）|302（73.4793%）|
|近距离参考子集中仍在标签范围外|189/274|119/119|
|五训练电池RUL跨度中位数cycles|345.5|74|
|真RUL减最近训练RUL中位数cycles|-152|+48|

逐轴范围内不等于联合支持，IQR距离.1仅冻结的描述参考；五邻居label范围不是校准区间。以上说明这两种失败不能单靠明显逐轴外推解释，也不能据此证明不可约不确定性。

可核算例：b4c7在cycle100的SOH.959574、rate=-5.94508e-6，真RUL430；最近b4c42/cycle102，SOH.958027、rate=-4.26210e-6，RUL673，IQR距离.040121。b2c6/cycle305真RUL206；最近b2c19/cycle320，RUL141，距离.075325。两者有不同偏差方向。

额外核对已有manifest元数据，发现当前三特征遗漏已保存policy字段：b4c7=8-6-4.8-3，而cycle100最近b4c42=5.2-5.2-4.8-4.16；b2c6=3.6C(30%)-6C，而cycle305最近b2c19=4.4C(55%)-6C。42fit有30种字符串。不同字符串只证明记录不同，不能直接称政策导致误差，且作为部署输入的时点/双格式语义尚未独立核实。

已核旧batch2长100rate实验root_decision，仍NO_GAIN_FOR_ADDING_RAW100_RATE，不能把这两例当作重开长窗口或种子扩展的理由。

最小验证：六个固定时点的30个邻居距离，用独立标量算式核对最大差2.22e-16；全部841origin由CSV重算标签范围/参考距离/逐轴外推计数通过。此检查未独立证明全部全局最近邻搜索。0fit/optimizer/新模型推理/checkpoint/dev/test；44个特征CSV读取均hash匹配，预算CPU13与神经4fit2580steps不变。

权威路径/home/yndx/zxk/rul/reports/local_state_support_20261018_root；原逐origin审计CSV和sourcehashes在服务器保留，公开summary/examples/脚本可检视；不公开完整原始曲线。本结论仅对选定已暴露case成立，不作总体性能或独立泛化宣称。

下一步：查已存官方源说明，核policy_readable确为预测时可获得的预设工况及两种格式含义，冻结42fit/10cal解析表/哈希；合法性关闭后才可fresh1CPUfit匹配策略上下文基线（先窄审+exactGO）。不新增网络或把policy解释当收益证据。
