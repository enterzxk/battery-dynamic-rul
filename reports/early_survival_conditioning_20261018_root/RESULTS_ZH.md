# 固定早期分布显式存活条件化：零训练对照

唯一预测来源为同10cal4567旧directRUL CSV，另读旧fit_parameters.json中fit-only残差sigma A=0.19898311654196568。不用cal sigma B，无新估计/fit/模型推理/checkpoint/dev/test读取。protocol在计算前冻结，源hash见protocol与completion。

令R0为第100cycle时点的剩余寿命，固定R0~Lognormal(mu100,sigma A)，d=t-100。仅知已存活到t时，条件生存S_t(r)=S0(d+r)/S0(d)。条件中位数满足S0(d+r)=.5S0(d)。脚本用log_ndtr与ndtri_exp稳定求解，d=0退化到原中位数；不会把负的固定点预测直接当作存活条件化。

|电池等权指标|固定点递减|固定早期分布存活条件化|既有逐时点动态|
|---|---:|---:|---:|
|TimeMAE cycles|116.4334217342|111.0150987246|58.1136980028|
|bias cycles|-10.2393973862|-1.2836709440|11.6762242128|
|severeover100|20.0000%|21.8110%|14.1601%|

存活条件化相对固定点递减MAE改善4.65358%，仅4/10cell改善；pairedcell2000seed42旧减新MAE差95%区间[-.341363,11.577509]cycles，严重over100增加1.81102个百分点。冻结开发gate FAIL，保留NO_GAIN，不能只引用总体bias趋近零。

既有动态相对存活条件化MAE改善47.65244%，10/10cell改善；95%差区间[25.800289,83.668108]cycles，严重over100降低7.65097个百分点；开发gate PASS。这支持在固定早期lognormal/sigmaA假设下，仅存活条件化不足以解释动态收益，仍不能独立归因给新增健康观测（动态age也改变）。

数值校验覆盖全部4567origin：条件中位数均正/有限，最小15.873275cycle，最低log survival=-5.207935；Scond(median)=.5的最大log误差7.22e-15。独立标准库erfc+70步二分重新计算全部条件中位数与指标，最大指标差1.62e-14。固定点递减756个归零前缀不删除；所有三组使用相同真值和原EOL。

本比较不是新算法，条件概率恒等式不是创新；固定早期lognormal及残差尺度是一种参数假设，尚未证明概率校准。cal已暴露、event-only labcapacity、物理serial/fullsourceSHA未闭合，不能声称独立确认/删失建模/泛化保证。并未估计因果意义的健康信息效应。

权威目录/home/yndx/zxk/rul/reports/early_survival_conditioning_20261018_root；diagnose.py及independent_recompute.py可复算，当前create-only输出不要覆盖。未新增训练或推理，CPU11与神经4fit2580steps账本不变。

下一步：只用当前固定的两个分布（early conditioned与dynamic，同sigmaA），在同10cal4567计算80%区间分数/coverage/width、Brier100/300，判断点预测收益是否也支持概率可靠性；0fit/0校准，不用sigmaB、不调概率参数/阈值、不读dev/test。
