# 41篇已接纳主文：逐篇结论与证据入口

本附录复用已有精读笔记与root限定，不是本轮重读全部PDF。下列结果均为作者报告，不是本项目复测。方法、结果摘要与限制按已有记录转述，完整结果细节与未核实事项保留在 paper_evidence.json。

主文接纳记录有历史性：例如P05主文记录中的SI待修状态属于当时记录；SI须查单独接纳记录，不能把旧状态当当前状态。来源链接取自已有目录，未在本轮逐个联网刷新；具体所读版本以paper_identity、root限定和精读文本路径为准，不能仅从文件名或书目链接推断版本。

## 导航

- [P01 Data-driven prediction of battery cycle life before capacity degradation](#p01)

- [P02 Closed-loop optimization of fast-charging protocols for batteries with machine learning](#p02)

- [P03 Statistical learning for accurate and interpretable battery lifetime prediction](#p03)

- [P04 BatteryML: An Open-source Platform for Machine Learning on Battery Degradation](#p04)

- [P05 Battery lifetime prediction across diverse ageing conditions with inter-cell deep learning](#p05)

- [P06 BatteryLife: A Comprehensive Dataset and Benchmark for Battery Life Prediction](#p06)

- [P07 Pretrained battery transformer (PBT): A foundation model for battery life prediction](#p07)

- [P10 Remaining Useful Life Prediction for Batteries Utilizing an Explainable AI Approach with a Predictive Application for Decision-Making](#p10)

- [P11 IIP-Mixer:Intra-Inter Patch Mixing Architecture for Battery Remaining Useful Life Prediction](#p11)

- [P12 Two-stage Early Prediction Framework of Remaining Useful Life for Lithium-ion Batteries](#p12)

- [P14 Remaining useful life prediction of Lithium-ion batteries using spatio-temporal multimodal attention networks](#p14)

- [P16 Performance Classification and Remaining Useful Life Prediction of Lithium Batteries Using Machine Learning and Early Cycle Electrochemical Impedance Spectroscopy Measurements](#p16)

- [P17 MambaLithium: Selective state space model for remaining-useful-life, state-of-health, and state-of-charge estimation of lithium-ion batteries](#p17)

- [P18 The Case for DeepSOH: Addressing Path Dependency for Remaining Useful Life](#p18)

- [P20 RUL-QMoE: Multiple Non-crossing Quantile Mixture-of-Experts for Probabilistic Remaining Useful Life Predictions of Varying Battery Materials](#p20)

- [P21 Cycle Life Prediction for Lithium-ion Batteries: Machine Learning and More](#p21)

- [P22 HyBattNet: Hybrid Framework for Predicting the Remaining Useful Life of Lithium-Ion Batteries](#p22)

- [P23 Generalization bounds and sample complexity for remaining useful life prediction from complete degradation trajectories](#p23)

- [P24 Improve in-situ life prediction and classification performance by capturing both the present state and evolution rate of battery aging](#p24)

- [P25 Domain knowledge-guided machine learning framework for state of health estimation in Lithium-ion batteries](#p25)

- [P26 SambaMixer: State of Health Prediction of Li-ion Batteries using Mamba State Space Models](#p26)

- [P27 Why we need a standardized state of health definition for electric vehicle battery packs -- a proposal for energy- and capacity-based metrics](#p27)

- [P28 Lithium-ion battery degradation: using degradation mode analysis to validate lifetime prediction modelling](#p28)

- [P29 Systematic Feature Design for Cycle Life Prediction of Lithium-Ion Batteries During Formation](#p29)

- [P31 PiDDM: Physics-Informed Differentiable Degradation Modeling for Lithium-Ion Battery State-of-Health Prediction](#p31)

- [P32 Multiscale Dual-path Feature Aggregation Network for Remaining Useful Life Prediction of Lithium-Ion Batteries](#p32)

- [P33 Towards a BMS2 Design Framework: Adaptive Data-driven State-of-health Estimation for Second-Life Batteries with BIBO Stability Guarantees](#p33)

- [P35 DiffBatt: A Diffusion Model for Battery Degradation Prediction and Synthesis](#p35)

- [P36 Predicting Battery Lifetime Under Varying Usage Conditions from Early Aging Data](#p36)

- [P38 Charging Phase Health Indicators for Battery State-of-Health Estimation: A Systematic Comparison of CC, CV, and Combined Approaches under Cross-Battery Validation](#p38)

- [P39 Knowledge-Aware Modeling with Frequency Adaptive Learning for Battery Health Prognostics](#p39)

- [P40 Conformalized Transfer Learning for Li-ion Battery State of Health Forecasting under Manufacturing and Usage Variability](#p40)

- [P41 Real-Time State-of-Health Estimation and Online Degradation Prognosis from Partial Battery Discharge Using Physics-Informed Neural Networks](#p41)

- [P42 Continuous ageing trajectory representations for knee-aware lifetime prediction of lithium-ion batteries across heterogeneous dataset](#p42)

- [P43 A Self-attention Knowledge Domain Adaptation Network for Commercial Lithium-ion Batteries State-of-health Estimation under Shallow Cycles](#p43)

- [P44 Federated Battery Diagnosis and Prognosis](#p44)

- [P47 Dynamic Loss Balancing for Joint SOH and RUL Prediction of Lithium-Ion Batteries via a Rotary SOH-Injected Prior Battery Transformer](#p47)

- [P48 Multitask Battery Management with Flexible Pretraining](#p48)

- [P49 A Lightweight Transfer Learning-Based State-of-Health Monitoring with Application to Lithium-ion Batteries in Autonomous Air Vehicles](#p49)

- [P51 Physics-informed neural network for lithium-ion battery degradation stable modeling and prognosis](#p51)

- [P52 Early prediction of lithium-ion battery degradation with a generative pre-trained transformer](#p52)



<a id="p01"></a>

## P01｜Data-driven prediction of battery cycle life before capacity degradation



**研究对象与方法：** 作者以早期放电电压曲线构造特征，使用弹性网建立循环寿命回归模型，并另用正则化逻辑回归进行寿命分组分类。



**实验设置：** 实验对象为124个商业LFP/石墨圆柱电芯，在多种快充条件下循环，并以按电芯划分的训练集、主测试集和后续生成的次测试集评估。



**精读结论／作者结果：** 论文报告显示，早期放电电压曲线特征优于仅依赖容量衰减曲线的基线；加入更多特征的收益因测试集而异。作者也报告了前5循环的寿命分类结果。



**关键结果细节（完整条目另见证据JSON）：** 作者报告回归模型使用前100循环数据。 表1中 variance 模型在主测试集的RMSE为138循环、平均百分比误差14.7%，次测试集分别为196循环和11.4%；discharge 模型相应为91循环、13.0%，以及173循环、8.6%；full 模型为118循环、14.1%，以及214循环、10.7%。 排除一个寿命衰减异常的主测试电芯后，表1列出的主测试结果括号值分别为 variance RMSE 138、误差13.2%，discharge RMSE 86、误差10.1%，full RMSE 100、误差7.5%。 作为容量衰减曲线基线，作者报告前100循环最复杂基线在主、次测试集的误差分别为23%和50%；均值预测约为30%和36%。 分类段落报告单特征 variance classifier 测试准确率88.8%，full classifier为95.1%；表2在550循环阈值下则列出 variance classifier 主、次测试准确率78.6%、97.5%，full classifier为92.7%、97.5%。 这些分类数字按正文不同报告处分别记录，具体设定差异无法由本文输入完全核实。 作者还报告对20次随机等分训练与测试的分析显示，在循环索引 i 大于60后，RMSE对索引选择相对不敏感（图5）。



**作者限制：** 作者指出，仅凭高倍率数据识别具体衰退机制有挑战；高倍率放电电压还可能混合动力学影响与非均匀性。



**主控接纳限定：**



- 主文同时报告124个电池、41/43/40划分及排除4个高噪声电池；排除前后口径暂不推断，任何样本数比较须核SI Table 9或原始清单。

- 分类准确率段落与Table 2口径差异保留，不合并为单一数字。

- 本篇是早期总循环寿命预测，不等同任意在线时点的动态RUL。

- 论文报告数值不是本项目复现实测；预印本信息仍未核实。



**精读来源锚点：** 第7页 / Machine-learning model development；第7页 / Cell cycling and data generation；第4页 / Performance of early prediction models；第6页 / Rationalization of predictive performance



**主文接纳记录：** [literature/accepted/P01_maintext_v1.json](../../literature/accepted/P01_maintext_v1.json)。

**精读笔记：** `literature/notes/batch01/P01_full_read_v1.json`；SHA256 `5a156a17e898bfe0c49fa589587b1885f33c3cfe0712a0da52ad965dc19ee7e7`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_year](https://doi.org/10.1038/s41560-019-0356-8)；[venue_doi](https://www.nature.com/articles/s41560-019-0356-8)；[official_code](https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation)。



<a id="p02"></a>

## P02｜Closed-loop optimization of fast-charging protocols for batteries with machine learning



**研究对象与方法：** 研究对象是商业LFP/石墨圆柱电芯的十分钟、0–80% SOC六步快充协议。方法将首100圈数据的弹性网早期寿命预测与高斯过程及上置信界贝叶斯优化结合，以减少每个候选实验的循环数和候选协议试验数。



**实验设置：** 实验以48通道电池测试仪并行评估候选协议，每轮对选定电芯运行100圈后用早期预测更新优化；另对九种协议各测试五个电池至失效作验证，并比较消融基线。



**精读结论／作者结果：** 闭环优化在16天内从224种协议中识别高寿命区域；九协议验证显示排名相关性较高，闭环前三协议平均寿命优于文献启发协议。消融比较显示早期预测显著降低测试时间，贝叶斯优化在资源较紧时贡献更大。



**关键结果细节（完整条目另见证据JSON）：** 四轮后，闭环估计的高寿命区域已在第二轮显现，后续主要提高该区域置信度；224种协议中117种未测试，67%的电池测试资源用于21%的协议。 验证中闭环估计寿命与验证早期预测均值的Pearson相关系数为0.93；验证早期预测与最终寿命的Pearson相关系数为0.86。 正文另报告CLO对充电协议最终寿命排序的Kendall排名相关系数为0.83（主文第2、5页）；该数值不应表述为早期预测与最终寿命之间的相关系数。 作者报告闭环前三协议平均895圈，文献启发协议平均728圈。 验证图示中前三协议最终寿命分别为890、912、884圈。 早期预测存在偏差，作者认为可能与不同储存时间导致的日历老化有关。 消融结果文字报告：达到相近表现时，不用早期预测、随机选择协议的策略约需7700电池小时，而完整闭环约需500电池小时；在该小规模验证中早期预测大幅减少单次实验时间，资源相对参数空间较少时贝叶斯优化相对随机选择的收益最大。 扩展数据模拟比较未纳入早期预测，显示贝叶斯优化在通道数相对于协议数较少时优势最大。 未提供的补充讨论及表格中的其他数值不作补充。



**作者限制：** 作者明确指出早期寿命预测在验证数据上有系统偏差，模型训练需要先获得循环至失效的数据；结果依赖特定充电时间、SOC窗口、温控和电池化学体系，外推至新情境需重新评估。



**主控接纳限定：**



- 所给作者托管主文及内含Extended Data文本；独立SI未提供，不能计SI完成。

- Kendall0.83归于CLO协议寿命排序，Pearson0.86归于验证早期预测与最终寿命，未混用。

- 快速充电闭环优化/早期总寿命预测，不是动态RUL性能或本项目复现。



**精读来源锚点：** 第8页 / Methods：BO hyperparameter optimization；第4页 / Results：闭环实验设置与数据；第5页 / Results：验证实验及早期预测；第9页 / Methods：Early outcome predictor；验证预测偏差



**主文接纳记录：** [literature/accepted/P02_maintext_successor_v2.json](../../literature/accepted/P02_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v2/P02_full_read_v2.json`；SHA256 `aab79e5eacb000534344999b89be528c775934f3a457725f15a22cbfa659e5a1`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_year_venue_doi](https://batterygroup.lbl.gov/publications/closed-loop-optimization-fast)；[publisher_record](https://www.nature.com/articles/s41586-020-1994-5)；[official_code](https://github.com/chueh-ermon/battery-fast-charging-optimization)。



<a id="p03"></a>

## P03｜Statistical learning for accurate and interpretable battery lifetime prediction



**研究对象与方法：** 研究提出容量矩阵表示，并以其基线相减结果提取特征，使用统计学习模型预测电池循环寿命；重点在于用特征工程降低输入维度，同时保持模型可解释性。



**实验设置：** 沿用既有数据集的训练/测试划分及前100圈预测设定，以对数循环寿命为目标、RMSE为主要报告指标；原文数值是作者报告结果，不是本项目实验。



**精读结论／作者结果：** 作者报告的最佳统计学习模型为基于 ΔQ100−10(V) 的 PLSR；IQR 单变量模型略优于既有方差单变量模型。若干降维、变换及模型对照显示，基线相减、log10变换和有针对性的特征表示有助于该数据集表现。



**关键结果细节（完整条目另见证据JSON）：** 采样消融：将曲线电压点从1000点降采样，在4C放电数据中，训练集和主测试集的RMSE绝对变化超过1%要到40 mV（40点）以上，次测试集则到160 mV（10点）以上；作者提示较低倍率放电可能需要更密采样。 单变量统计量对照：log10(IQR(ΔQ100−10(V)))在训练、主测试、次测试上的RMSE为99、124、190圈，分别比log10方差模型低5、14、6圈。 log10特征变换总体误差较低；预测原始循环寿命而非log10寿命时，误差普遍更高。 局部周期平均的结果通常与不平均相近。 训练集确定的31–62百分位差模型误差为82、109、261圈，次测试泛化较差；单点模型在训练误差最优的2.911 V处，两个测试集误差为118、214圈。 多变量对照中，PLSR误差为59、100、176圈，低于IQR单变量模型的测试误差124、190圈；随机森林和MLP测试表现较差。 整个容量矩阵直接展平后训练会过拟合；多变量汇总特征模型与IQR性能相近。 CNN使用基线相减矩阵时误差为17、72、204圈，主测试较好但次测试一般；改用未减去第10圈基线的原始容量后误差升至47、129、313圈。 表II显示 Severson 的 discharge 模型测试误差为86、173圈，低于本文 PLSR 的100、176圈。 以上均为论文所报告实验结果。  CNN残差风险补充：作者进一步报告，次测试集的两只电芯绝对残差超过700 cycles，显著抬高RMSE；因此“次测试表现一般”掩盖了尾部误差集中于少数电芯这一重要解释。 原始容量与基线相减的方向经原文第42页复核为：基线相减输入RMSE为17/72/204 cycles；不减去第10圈基线的原始容量输入为47/129/313 cycles，后者表现下降。 v2数值正确但使用“降至”描述上升错误，本v4将其改为“升至”，旧v2/v3均保留。



**作者限制：** 作者指出结果依赖有限且特定的数据集与放电条件；模型特征对应的具体退化机理尚不能精确解释，且部分尝试未能改善表现。独立补充材料未提供，不能核验正文引用的补充材料细节。



**主控接纳限定：**



- 接纳 compact_v4_root，旧 v3 方向错误记录保留，不作 active 稿。

- 主文51个有文字页面及第52空页；独立 SI 未提供，不能计 SI 完成。

- 早期前100圈的总寿命预测不等于任意时点动态 RUL；作者未用验证集选择 CNN 超参数的限制保留。

- 正文作者提供代码链接不等于项目执行或复现。



**精读来源锚点：** 第1页 / 摘要；第14页 / 特征生成与统计学习方法；第42页 / 总结；第26页 / 单变量百分位模型



**主文接纳记录：** [literature/accepted/P03_maintext_successor_v2.json](../../literature/accepted/P03_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v1/P03_full_read_compact_v4_root.json`；SHA256 `df3ca017a9a5d65115c94b1acad0a4f32d34b4a7afc3665306e7093d39e31272`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_arxiv](https://arxiv.org/abs/2101.01885)；[venue_doi_arxiv](https://arxiv.org/abs/2101.01885)；[official_code](https://github.com/petermattia/revisit-severson-et-al)。



<a id="p04"></a>

## P04｜BatteryML: An Open-source Platform for Machine Learning on Battery Degradation



**研究对象与方法：** 作者提出 BatteryML，一个面向电池退化建模的开源平台，目标是统一电池数据表示并提供从预处理、特征和标签提取到模型训练、预测与可视化的配置化流程。正文介绍平台能力和基准模型；不能据此推定所有模块都用于每项实验。



**实验设置：** 论文评估 RUL、SOH 和 SOC 三类任务，使用 CALCE、HNEI、HUST、MATR、RWTH、SNL、UL PUR 等公开数据源，并构造多个组合数据集。协议按任务和数据集而异；正文未提供所有拆分的电芯名单或统一的随机种子清单。



**精读结论／作者结果：** 以下均为论文报告的基准或消融结果，不是本 RUL 项目的实验或实测结果。论文结果显示方法表现随数据集和任务变化；作者没有报告一个在所有数据集上都占优的方法。



**关键结果细节（完整条目另见证据JSON）：** RUL：表2（页面对象8）报告各模型在八个基准集上的数值，但表格提取文本未清楚标明该表指标名称和单位，故不将数值擅自标为 RMSE 或补单位。 正文称人工特征线性模型在部分单一电池类型数据上表现较好，但在 CRUSH、MIX 等多样数据上会变差；树模型在 CRUSH、MIX 上表现较强，而样本有限的数据集会影响部分统计模型。 正文还报告神经网络结果对初始化敏感，未发现通用最优架构。 附录表3（页面对象20）明确标为 CNN 的 Test RMSE，十个种子数值为76、67、64、74、60、82、65、79、367、78；表中未明确单位。 SOH：表4（页面对象21）报告 Test RMSE。 示例包括 CALCE 上线性回归0.45±0.06、随机森林0.72±0.36；MATR 上线性回归252.75±430.58、随机森林0.53±0.30；RWTH 上随机森林和 LightGBM 均为0.17（标准差分别0.11、0.08）。 作者指出树模型在这些数据上的表现较稳健，深度模型未稳定优于传统模型。 SOC：表5（页面对象22）报告 Test RMSE。 LightGBM 在多数所列任务中误差较低，例如 CALCE 1.714±1.02、HNEI 0.763±0.02、HUST 0.284±0.04、MATR 0.824±0.58；但 RWTH 上为313.757±63.76，显示表现并非各数据集一致。 消融：附录图5（页面对象23）比较 MIX 上不同特征，作者报告 Full 特征在各模型上表现较好；Gaussian Process 和 Random Forest 使用 Discharge 特征也有效；随机森林上 QdLinear 与 Full 特征间存在较大差距。 图6的超参数分析称 PLSR 随主成分增加有过拟合趋势，随机森林树数量呈稳定效果，XGBoost 超过64个 boosting 轮次后趋于收敛。 图7的深度模型分析称 MLP 隐藏维度增加会提高方差而均值变化不明显；CNN 隐藏维度16较有效；LSTM 和 Transformer 增大模型容量时性能改善。 上述图中未在文本给出可逐点核对的完整数值。



**作者限制：** 作者自述的限制集中在跨数据集表现不一致、缺少通用最优模型、神经网络结果波动，以及 SOH/SOC 标签难以准确获得。平台向真实应用的转化和易用性被列为未来工作。



**主控接纳限定：**



- Random forest八格为168±9、233±7、368±7、532±25、192±2、81±1、416±5、197±0；均值与下标std不能粘连。

- MLP/CNN/LSTM/Transformer全部32格与当前v4的mean±std一致；CNN CLO的>1000无std。

- 原Table2仅写error mean、下标standard deviation；不擅补RMSE/MAE指标名或循环单位。

- 神经网络种子波动不是逐时刻动态预测振荡的证据。主文接纳不构成动态RUL公平复现、创新或性能GO。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / 3.3 AUTOMATIC LABEL ANNOTATION；第17页 / A BENCHMARK DATASET CONSTRUCTION；第8页 / 4.2 BATTERY DEGRADATION MODELING；第8页 / Table 2: Benchmark results for remaining useful life prediction；第21页 / C.2 STATE OF HEALTH ESTIMATION；第25页 / Appendix E.2 Unified Data Format for Public and Custom Data



**主文接纳记录：** [literature/accepted/P04_maintext_rootvisual_successor_v3.json](../../literature/accepted/P04_maintext_rootvisual_successor_v3.json)。

**精读笔记：** `literature/revisions/successor_20261016_v1/P04_full_read_v4_rootvisual_complete_table.json`；SHA256 `a4542c8d6daeb79a92bd237d0bb687aceb319bd1647ad208940afbfea0881aee`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_year_arxiv_doi](https://arxiv.org/abs/2310.14714)；[venue](https://arxiv.org/abs/2310.14714)；[official_code](https://github.com/microsoft/BatteryML)。



<a id="p05"></a>

## P05｜Battery lifetime prediction across diverse ageing conditions with inter-cell deep learning



**研究对象与方法：** 研究提出 BatLiNet，用电池单体内学习与单体间学习共同预测电池寿命。研究对象是不同老化条件下的电池单体，目标是在早期循环数据有限时预测寿命，并探索跨电池化学体系迁移。



**实验设置：** 主文汇集多个公开电池数据集，构建五种评估集或设置：MATR-1、MATR-2、HUST、MIX-100和MIX-20。以RMSE和MAPE评价；深度学习模型进行8次不同初始化实验。另设跨化学体系低资源迁移实验。



**精读结论／作者结果：** 作者报告 BatLiNet 在多种老化条件下总体优于所比较的模型，并展示其跨电池化学体系迁移能力。与单体内学习的CNN相比，BatLiNet平均MAPE最高可降低40%；相对各数据集上表现最佳的基线，RMSE分别降低36.5%、6.8%、20.1%、27.4%和40.1%。



**关键结果细节（完整条目另见证据JSON）：** 比较对象包括基于手工特征的线性模型、统计学习模型及MLP、LSTM、CNN等深度学习模型。 主文指出随机森林在部分混合数据设置中相对稳健，但整体表现仍非最优；深度学习基线在随机初始化间变异较大。 BatLiNet降低了这类变异，并在五种数据集上取得有竞争力的结果。 消融比较中，单体内学习CNN是其对照，作者报告BatLiNet平均MAPE最高降低40%。 跨化学体系实验比较直接在目标单体训练、在LFP预训练后微调及BatLiNet；结果显示性能随可用目标训练单体数变化，具体数值见主文图4。  图4亦显示按LCO、NCA、NMC目标化学体系及目标训练电芯数1、2、4、8、16分层的迁移结果；每个设置为8次初始化和数据划分，图中柱为平均误差、误差线为标准差。 此处文字证据仅支持实验设计及结果呈现维度，不对图形中未从文字抽取的具体数值作补写。



**作者限制：** 作者指出，MIX-100和MIX-20上的MAPE明显高于MATR-1和MATR-2；参考单体选择会影响预测误差，增加参考单体批量虽可缓和波动，却会降低推理速度。作者还明确表示，深入的物理理解与建模仍然必要。



**主控接纳限定：**



- 正式发表主文范围接纳；SI是独立read/review路径，当前SI仍NEEDS_REVISION，不合并为SI完成。

- 主文64个参考电芯的推理折中与SI实现说明32个参考电芯分别保留，不推定同一默认配置。

- 主文概述平均输出与方法中α加权组合的差别已披露，不推断α=0.5。

- 作者报告早期阈值寿命/迁移结果，不是项目复现或动态RUL性能。



**精读来源锚点：** 第3页 / Results，BatLiNet框架说明；第6页 / Methods—Unifying intra- and inter-cell learning，式(10)；第5页 / Fig. 4图注；第1页 / 摘要；第4页 / Results，参考单体选择策略



**主文接纳记录：** [literature/accepted/P05_published_main_successor_v2.json](../../literature/accepted/P05_published_main_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v1/P05_published_main_full_read_v2.json`；SHA256 `78f7b9560243d5f80b8c176cbba9e0f0c8826e3808abc2add50efced34c1f7d1`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_year_doi_venue](https://www.nature.com/articles/s42256-024-00972-x)；[arxiv_authors](https://arxiv.org/abs/2310.05052)；[official_code](https://doi.org/10.24433/CO.8904065.v2)。

**状态说明：** 本篇主文和独立SI分别计范围，SI不增加unique主文篇数；旧主文record中“当前SI待修”是历史文字，不覆盖后来的独立SI接纳。



<a id="p06"></a>

## P06｜BatteryLife: A Comprehensive Dataset and Benchmark for Battery Life Prediction



**研究对象与方法：** 论文整合 BatteryLife 数据集并提出 CyclePatch：以前 S 个循环的电压、电流、容量序列预测电池寿命，S≤100；CyclePatch 将循环作为 token，建模循环内与循环间信息。



**实验设置：** 四个数据域分别进行基准、老化条件泛化和跨域迁移评估；训练、验证、测试按6:2:2随机划分，报告三次实验的均值和标准差。



**精读结论／作者结果：** CyclePatch 变体在各域总体有竞争力，但具体最优模型随域和指标变化。消融结果总体支持循环内、循环间编码的作用；未报告统计检验，不能将差异称为统计显著。



**关键结果细节（完整条目另见证据JSON）：** Table 3 中，各域最低 MAPE 的 CyclePatch 模型及数值为：Li-ion CPMLP 0.179±0.003，Zn-ion CPTransformer 0.515±0.067，Na-ion CPTransformer 0.255±0.036，CALB CPMLP 0.140±0.009。 作者在正文叙述中另将 CALB 最佳 MAPE 写为0.141；表中 CPMLP 为0.140，两处源内差异并列保留。 各域最高15%-Acc分别为 Li-ion CPMLP 0.620±0.004、Zn-ion CPMLP 0.297±0.084、Na-ion CPTransformer 0.406±0.084、CALB CPMLP 0.704±0.053。 因此“各域最佳”仅宜理解为作者概括的总体结果，不能说同一个变体在每个域、每项指标都最佳。 举例而言，Na-ion 上 CPMLP 的15%-Acc为0.337±0.038，低于 MLP 的0.364±0.098。 正文称 CyclePatch 融合后模型表现改善，但未提供统计显著性检验。



**作者限制：** 作者明确报告跨域迁移仍有改进空间，并称未见老化条件表现通常较差；论文未设独立局限性章节。需将这些作者陈述与正文未披露的实验细节分开。



**主控接纳限定：**



- 正式12页conference版本未与此13页arxiv版本逐字对齐

- 单独SI未读，文件内附录A/B已读

- CALB表0.140/正文0.141差异保留；随机划分/unknown-condition操作等正文未给完整名单

- 论文原始数据统计与后续v11 release应分开；当前pilot不是正式paper reproduction



**精读来源锚点：** 第5页 / 3.3 CyclePatch；第6页 / 4.1 Experimental Setup；第8页 / Table 5；4.5 Model Performance on Seen and Unseen Aging Conditions (RQ3)；第8页 / 4.6 Cross-domain Transferability (RQ4)



**主文接纳记录：** [literature/accepted/P06_maintext_arxivv7_v1.json](../../literature/accepted/P06_maintext_arxivv7_v1.json)。

**精读笔记：** `literature/notes/batch01_recovery_v3/P06_revision_v3.json`；SHA256 `0eb4d85ef203234feddd7d842fab53f125ad08edff0d803f032da0e88b950e28`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_arxiv](https://arxiv.org/abs/2502.18807)；[venue_doi_official_repo](https://github.com/Ruifeng-Tan/BatteryLife)；[official_code](https://github.com/Ruifeng-Tan/BatteryLife)。



<a id="p07"></a>

## P07｜Pretrained battery transformer (PBT): A foundation model for battery life prediction



**研究对象与方法：** 作者提出由通用PBT及面向具体目标场景的专用PBT组成的框架。通用模型以BatteryMoE组织异质电池循环数据；专用模型从通用模型参数出发，用目标数据进行迁移学习。



**实验设置：** 正文描述了13个锂离子数据集的通用模型预训练评估，以及12个预训练覆盖范围内和3个范围外目标数据集的专用模型评估。主要指标为按老化条件平衡汇总的MAPE。



**精读结论／作者结果：** 论文报告通用PBT在预训练测试数据上优于所比较的神经网络基线；专用PBT在覆盖范围内外的目标数据集均取得较低MAPE。消融结果支持软、硬编码器、文本嵌入、两类老化条件信息及预训练数据规模对结果有贡献。



**关键结果细节（完整条目另见证据JSON）：** 通用PBT：正文报告总体MAPE为0.151，较次优CPMLP低22.7%；seen和unseen条件下分别较次优模型低22.6%和22.8%。 只用第1个循环时，报告的最高改进幅度为30.5%。 这些结果见Fig. 3a–b（正文页6–7）。 13个预训练数据集中的9个取得最佳结果；8个数据集的MAPE较其他方法降低超过15%，见Fig. 3c（正文页6–7）。 

预训练覆盖范围内的12个目标数据集：专用PBT在全部12个数据集上取得最低MAPE，较最佳比较模型平均低23.2%；8个数据集上的降幅超过10%，见Fig. 4a（正文页7–8）。 跨12个数据集聚合后，专用PBT总体MAPE为0.137，较通用PBT降低9.3%，seen与unseen条件分别降低12.8%和6.6%，见Fig. 4b（正文页8–9）。 专用PBT在图示不同可用循环数下持续低于最佳基线，见Fig. 4c（正文页9）。 

覆盖范围外的3个目标数据集：论文报告专用PBT相对最佳比较模型的MAPE降幅分别为工业锂离子42.1%、钠离子19.0%、锌离子31.3%，见Fig. 5a–c（正文页9–10）。 正文称在几乎所有展示的早期预测设定中取得最佳结果，见Fig. 5d–f（正文页9–10）。 工业锂离子数据中27个电池有17个缺少第100循环电压—电流数据，因此该处可评估电池数骤减并可能造成MAPE不连续，见Fig. 5图注（正文页10）。 

消融：移除软编码器或硬编码器都会提高MAPE；以学习得到的查表嵌入替代LLM年龄条件表示时，MAPE增加13.9%。 只保留电池规格，或只保留形成与运行条件，也比使用完整年龄条件信息的MAPE更高。 CPTransformer和DeepSeekMoE均未达到完整PBT表现；加入相同LLM嵌入的CPTransformer-I优于CPTransformer但仍不及PBT。 以上方向性结果及比较见Fig. 6a（正文页10–11）。 

数据规模分析：在25%、50%、75%、100%预训练数据比例下，PBT的MAPE均低于CPTransformer；PBT的MAPE随数据量增加而下降。



**作者限制：** 作者明确指出预测受输入信息量和目标训练数据覆盖的退化模式限制，并提出补充老化条件信息、改进不确定性估计及纳入电压—电流以外测量等后续方向。



**主控接纳限定：**



- 按输入首页EES/Published15September2026/DOI10.1039/d6ee03446b识别为发表版文本；原路径arxiv命名不证明v7身份，未与arxiv逐字对齐。

- 主文17个有文字页面及第18空页；SI未提供，划分/超参数完整细节未核。

- 24.8%/73.9%是摘要作者报告；正文另列12覆盖内与3覆盖外分项，完整聚合和最大值归属未核，不由root重算或替作者解释。

- 已完成静态metadata/validation embedding安全解码不等于PBT模型复现；forward0；代码作者声明不是运行证据。



**精读来源锚点：** 第13页 / Methods；第6页 / Results — The general PBT consolidates comprehensive battery lifetime knowledge from heterogeneous datasets；第10页 / Results — Origins of PBT performance；第12页 / Discussion and conclusions



**主文接纳记录：** [literature/accepted/P07_maintext_successor_v2.json](../../literature/accepted/P07_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v2/P07_full_read_v3_rootchecked.json`；SHA256 `631bc90387b91329d0cb1c9f8771928cf65bddcc51439e22d7e6de6ef81fa124`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [title_authors_year_venue_doi](https://arxiv.org/abs/2512.16334)；[publisher_or_author_record](https://seejhuang.people.ust.hk/publications-2/)；[official_code](https://github.com/Ruifeng-Tan/PBT)。



<a id="p10"></a>

## P10｜Remaining Useful Life Prediction for Batteries Utilizing an Explainable AI Approach with a Predictive Application for Decision-Making



**研究对象与方法：** 研究目标是预测电池剩余寿命（RUL）并将 RUL 分为低、中、高三类；作者提出两级集成回归模型 TLE 和 CNN+MLP 回归模型，并比较若干传统、集成与深度学习基线。分类使用 XGBoost 与 MLP。



**实验设置：** 作者报告采用 80:20 训练/测试划分，深度学习模型从训练集再留出 20% 作验证；回归使用 5 折分层交叉验证，分类使用 10 折嵌套交叉验证。



**精读结论／作者结果：** 作者报告 TLE 回归的表5报告指标（未明确评估集归属）为 R²=0.9999、RMSE=2.8350、MAE=1.4858，并称其优于所列回归基线。分类结果在正文段落、性能表和交叉验证表之间存在数值差异。



**关键结果细节（完整条目另见证据JSON）：** 表 5 报告 TLE 回归 R²=0.9999、RMSE=2.8350、MAE=1.4858；XGBoost 回归为 0.9994、8.0441、4.4955；CatBoost 为 0.9980、14.352、10.607；CNN+MLP 为 0.9985、12.632、8.0108；CNN-BiLSTM 为 0.9963、19.687、6.0099；BiGRU 表中为 0.9980、14.222、9.7447。 表 7 的五折回归均值也显示 TLE RMSE=2.8761、MAE=1.5711、R²=0.9999。 分类方面，表 5 报告 XGBoost 测试准确率 0.9957、MLP 为 0.9877；表 6 的十折分类交叉验证均值均为 0.9969。 正文另称 XGBoost 测试准确率为 0.9973，并给出 MLP 训练准确率 0.9903。 SHAP 解释将 Cycle_Index 列为最重要特征，充放电时间比和 4.15V 时间也被讨论。 比较了模型性能，但未报告移除 TLE 组件、特征或解释模块的消融实验。 正文个别数值与表格不一致：例如 CatBoost 段落开头给出 R²=0.9997、RMSE=5.1060，随后段落及表 5 给出的指标不同；CNN+MLP 的 RMSE 在正文与表格分别为 12.630 和 12.632；BiGRU 的正文指标也与表格不同。 

root核算第32页Table6：根据表列十折准确率等权算术平均，XGBoost为0.99653（四舍五入0.9965），MLP为精确算术均值0.99105（不混用舍入约定；四位Decimal half-up为0.9911、ties-even为0.9910）；原表却给两者相同mean=0.9969及std=0.0016。 两组均值与各自逐折数据不一致。 上述均值是本项目对作者表列数值的算术核查，不是模型复现实测；原作者汇总值按原表保留，不擅定其最终更正结果。



**作者限制：** 作者自述需要通过严格测试获得更可靠、有效的数据，且当前应用系统尚不具备真实世界实施能力。



**主控接纳限定：**



- 只以最新v5及独立v5审查裁定，旧版本和旧失败保留；root本轮实读40/42页限制与愿景，既有20折source/算术回执不重算。

- Table6逐折算术均值XGBoost0.99653、MLP0.99105；MLP四位half-up0.9911/ties-even0.9910。原表两mean0.9969冲突保留，算术不是模型复现。

- RUL是目标非已证输入泄漏；未明确电芯隔离、Table5评估集归属、CV和留出评估对应，不能从高R2宣称独立泛化。

- 第40页明确缺真实部署能力/示例配置，第42页应用愿景仅潜力非部署。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / 2. Methodology；第15页 / 2.7 Cross-validation；第34页 / 3 Results & Discussions；第40页 / 3.3 Limitations and future scopes



**主文接纳记录：** [literature/accepted/P10_maintext_successor_v5.json](../../literature/accepted/P10_maintext_successor_v5.json)。

**精读笔记：** `literature/revisions/successor_20261016_v3_batch04/P10_full_read_v5_root.json`；SHA256 `3a66660f6a6489b832a46960689f4e2a9a5b20d2b3b284ddf1793905ae003c90`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2409.17931v2)；[full_text_candidate](https://arxiv.org/pdf/2409.17931v2)。



<a id="p11"></a>

## P11｜IIP-Mixer:Intra-Inter Patch Mixing Architecture for Battery Remaining Useful Life Prediction



**研究对象与方法：** 研究对象是锂离子电池剩余使用寿命（RUL）预测。作者提出仅由多层感知机组成的 IIP-Mixer，以并行的块内与块间混合提取局部和全局时间模式，并以加权均方误差训练。



**实验设置：** 实验使用 NASA PCoE 电池公开数据集，在 PyTorch 上实施；比较 MLP、Transformer、Informer、DLinear 与 IIP-Mixer。作者报告每项实验使用三个连续随机种子并取指标均值。



**精读结论／作者结果：** 作者报告 IIP-Mixer 在 NASA PCoE 数据集的四项指标上优于所比较的基线；消融结果支持并行双头、加权损失和筛选后的多变量输入。



**关键结果细节（完整条目另见证据JSON）：** 主结果中，IIP-Mixer 的 MAE、RMSE、MAPE、ARE 分别为 0.037 Ah、0.048 Ah、2.480%、1.370%；DLinear 为 0.041 Ah、0.052 Ah、2.732%、3.196%；MLP 为 0.050 Ah、0.066 Ah、3.402%、6.393%；Informer 为 0.049 Ah、0.063 Ah、3.281%、4.110%；Transformer 为 0.055 Ah、0.073 Ah、3.697%、9.589%。 计算复杂度表将 IIP-Mixer 的训练时间和内存记为 O(L)，测试步数为 1。 双头消融中，完整模型优于去掉任一头的配置；去掉块间头时四项指标为 0.081 Ah、0.095 Ah、5.443%、34.703%，去掉块内头时为 0.044 Ah、0.055 Ah、2.940%、5.023%。 并行双头优于两种串行顺序：串行（块间优先）指标为 0.063 Ah、0.076 Ah、4.258%、15.068%；串行（块内优先）为 0.045 Ah、0.056 Ah、3.032%、4.110%；并行为 0.037 Ah、0.048 Ah、2.480%、1.370%。 加权损失相较未加权损失的 MAE、RMSE、MAPE 分别改善 5%、2%、3%；ARE 两者均为 1.370%。 输入特征消融中，单变量、多变量全特征、多变量主特征的四项指标依次为 0.042/0.054/2.822/3.653、0.052/0.064/3.510/7.306、0.037/0.048/2.480/1.370（单位依次为 Ah、Ah、%、%）。 以上均为论文作者报告的实验结果。



**作者限制：** 正文没有单列局限性章节。作者报告小数据集可能使 Transformer 类方法过拟合，并指出使用全部特征可能降低表现；电芯划分和若干复现实验细节未报告。



**主控接纳限定：**



- 第10页Table3是逐层渐进复杂度表：Transformer训练时间/内存O(L²)、测试L步；Informer时间O(L log L)、内存O(L log L)、测试1步；MLP时间/内存O(L²)、测试1步；DLinear与IIP-Mixer时间/内存O(L)、测试1步。IIP-Mixer该推导依赖文中W=H、W×H=L等设定，不是实测运行时。

- 第9页Table2的MAE=0.037 Ah、RMSE=0.048 Ah是作者表中容量序列尺度误差；ARE以阈值RUL比定义。不能当作0.037循环的动态RUL-MAE。

- 电芯划分、预测跨度N、阈值穿越抽取与训练集内特征选择流程未证；主文接纳不是公平复现或独立泛化GO。

- 代码是否公开或与论文关联：无法核实。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / 3.2 The Framework；第8页 / 4.3.1 Parameter Settings；第11页 / 5.3.2 Serial vs Parallel Heads；第11页 / 5.3.4 Effect of Multivariate



**主文接纳记录：** [literature/accepted/P11_maintext_successor_v3.json](../../literature/accepted/P11_maintext_successor_v3.json)。

**精读笔记：** `literature/revisions/successor_20261016_v3_batch04/P11_full_read_v2_root.json`；SHA256 `4380aa27b72728527d1f9246222d858477b57924498eb73391939855dbe1553b`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2403.18379v1)；[full_text_candidate](https://arxiv.org/pdf/2403.18379v1)。



<a id="p12"></a>

## P12｜Two-stage Early Prediction Framework of Remaining Useful Life for Lithium-ion Batteries



**研究对象与方法：** 研究用两阶段框架预测锂离子电池剩余寿命：先识别从健康到不健康的首个预测周期（FPC），再预测FPC至寿命终止（EOL）期间的剩余寿命百分比。



**实验设置：** 作者在MIT数据集上按电芯划分训练集与测试集，并与使用放电容量的常规方法比较，使用三种误差指标评估。



**精读结论／作者结果：** 作者报告提出的方法在三项指标上优于两种常规对照；特征数量实验中4个特征结果最佳，使用7个特征时性能下降。



**关键结果细节（完整条目另见证据JSON）：** 在使用4个特征的比较中，提出方法的MSE、MAE、MAPE分别为0.0035、0.0454、0.0882；Zhou等人方法分别为0.0090、0.0522、0.0944，Li等人方法分别为0.0054、0.0525、0.0902。 特征数消融的MSE/MAE/MAPE为：1个特征0.0133/0.0943/0.2477，2个特征0.0062/0.0653/0.1199，3个特征0.0065/0.0671/0.1154，4个特征0.0035/0.0454/0.0882，7个特征0.0060/0.0606/0.1776。 作者称整体上增加特征有改善趋势，但纳入全部温度特征后性能略有下降，并将其归因于温度作为控制变量对RUL预测贡献有限。 作者还报告测试和训练数据中的FPC平均约出现在总放电容量的95%处。 上述数值均为论文报告结果。



**作者限制：** 作者提出了扩大数据集、验证泛化性与鲁棒性等后续工作方向；正文未报告若干可复现性与评估细节。



**主控接纳限定：**



- 正文以FPC可视化示例及平均约95%放电容量位置说明第一阶段，没有报告针对独立FPC真值的准确率/召回率或检测时延等定量评估；不能把平均位置当检测准确率。

- 监督标签为(EOL_i-j)/(EOL_i-FPC_i)，训练完整电芯寿命监督不自动等于输入泄漏；但百分比输出到绝对循环RUL的尺度未证，不能据作者“无需EOL”宣称已验证绝对在线动态RUL。

- 作者对照从完整寿命40%起点预测容量，其与FPC后百分比预测的起点、特征和输出并不完全匹配；论文报告优越不自动是公平同协议模型优势。

- arXiv元数据的IECON2023接收声明仅是作者/record说明，未读正式会议版本；当前主文接受仅限arXiv v1。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / IV. 方法；第5页 / V. 实验结果；第6页 / V. 实验结果；第6页 / VI. 结论



**主文接纳记录：** [literature/accepted/P12_maintext_successor_v3.json](../../literature/accepted/P12_maintext_successor_v3.json)。

**精读笔记：** `literature/revisions/successor_20261016_v3_batch04/P12_full_read_v2_root.json`；SHA256 `b717e71a540898c2d797f28b0b2e644000543e3515d4d6c763f7399f226f994e`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2308.03664v1)；[full_text_candidate](https://arxiv.org/pdf/2308.03664v1)。



<a id="p14"></a>

## P14｜Remaining useful life prediction of Lithium-ion batteries using spatio-temporal multimodal attention networks



**研究对象与方法：** 研究锂离子电池剩余寿命（RUL）预测，提出先识别健康状态转折点、再预测转折点后剩余寿命百分比的两阶段方案，并设计时空多模态注意力网络 ST-MAN。



**实验设置：** 论文在 MIT 与 HUST 两个公开电池数据集上评估两阶段方案；按电芯进行五折交叉验证，报告 MAE、MSE 和 MAPE，并与 TCN、ADLSTM 及两阶段变体比较。



**精读结论／作者结果：** 作者报告 ST-MAN 在两数据集的 MAE、MSE、MAPE 上优于所列对照；消融结果显示移除卷积、通道交互或时间 LSTM 均使至少部分指标变差。



**关键结果细节（完整条目另见证据JSON）：** 表5中，MIT 上 ST-MAN 的 MAE、MSE、MAPE 分别为0.0275±0.0046、0.0014±0.0005、0.0494±0.0100；HUST 上分别为0.0168±0.0091、0.0005±0.0006、0.0384±0.0193。 作者报告这些指标优于 TCN、ADLSTM、两阶段 TCN 和两阶段 LSTM。 表4报告 FPC 处放电容量占比：MIT 训练/测试为94.70%/94.34%，HUST 为90.771%/86.69%。 消融表8显示，移除初始卷积后性能明显下降；移除通道交互后两数据集指标下降；移除时间 LSTM 后 MIT 三项误差变大；HUST 的 MAE由完整模型0.0168增至0.0176，MSE两者均四舍五入为0.0005，但MAPE由0.0384降至0.0331（该指标反而改善），不能称HUST三指标均变差。 健康状态分类器参数比较后，作者选用一个含三层隐藏层的 LSTM 块。 作者还报告 ST-MAN 参数量为27,861，低于所比较模型，但 FLOPs 为1,200,869，高于 TCN 与 ADLSTM。



**作者限制：** 作者指出 ST-MAN 的 FLOPs 较高，嵌入式部署仍需降低计算量；并提出进一步改进、扩展数据集及真实电池管理系统部署作为后续工作。



**主控接纳限定：**



- 第5页3.1节称分类器两个LSTM模块、每个四层；第6页图2画一个三层LSTM块，第14页4.4及第15页Table7选择一个三层块。正文内部结构描述不一致，不能只凭最优表格推断全部实际运行结构。

- 第7页MCT文字定义为total cycle count百分比，而Algorithm1未列MCT条件，比例与在线来源未明；若使用待预测电芯的真实完整寿命则在线不可用。本文未闭环，不据此断定测试标签确参与训练。

- 第15页Table8去除时间LSTM时HUST MAPE为0.0331，完整模型0.0384，该消融指标改善；MAE变差、MSE四舍五入相同。保留负面消融，不称所有组件在所有指标都受支持。

- FPC后百分比输出及传统40%完整寿命起点对照，与绝对online动态RUL同协议评估分开；另有相同两阶段/特征TCN/LSTM对照，应独立解释。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / 3.2. Remaining Useful Life Prediction；第10页 / 4.2. Implementation Details and Evaluation Metrics；第15页 / 4.4. Ablation Study；第15页 / 5. Conclusion



**主文接纳记录：** [literature/accepted/P14_maintext_successor_v3.json](../../literature/accepted/P14_maintext_successor_v3.json)。

**精读笔记：** `literature/revisions/successor_20261016_v3_batch04/P14_full_read_v2_root.json`；SHA256 `a8eb6386496f3bc65c204cf6ca3e0b0285bd82a74015a50a64542019918b4a45`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2310.18924v2)；[full_text_candidate](https://arxiv.org/pdf/2310.18924v2)。



<a id="p16"></a>

## P16｜Performance Classification and Remaining Useful Life Prediction of Lithium Batteries Using Machine Learning and Early Cycle Electrochemical Impedance Spectroscopy Measurements



**研究对象与方法：** 研究用早期循环的EIS与温度信息，对锂离子电池进行高、低性能分类和剩余寿命预测：分类采用线性SVM，寿命回归采用Lasso。



**实验设置：** 实验使用公开的Zhang锂离子电池EIS-容量数据集；分类与RUL任务采用正文分别说明的数据划分，并以早期循环输入预测性能类别或RUL。



**精读结论／作者结果：** 作者报告20 kHz阻抗可在三种电池状态下正确分类全部60个数据点；RUL模型在三种状态下使用20 kHz、8.8 Hz阻抗及温度时R²均大于0.96，去掉8.8 Hz输入后均大于0.9。



**关键结果细节（完整条目另见证据JSON）：** 分类结果中，作者报告只用20 kHz阻抗、取前20循环数据时，三种状态下的60个数据点均被正确分类。 改用较低的8.8 Hz或32 mHz时，高性能电池点均正确分类，但部分低性能电池被误判为高性能。 决策边界图比较线性SVM、随机森林和决策树。 RUL结果中，前20循环的−Im(Z)（20 kHz、8.8 Hz）与温度模型在V、IX、III三种状态下的R²均大于0.96；只保留20 kHz−Im(Z)与温度时，三种状态下R²均大于0.9。 另报告单用8.8 kHz或32 mHz−Im(Z)及温度时，三种状态下R²大于0.89。 作者称对高性能电池及表现较好的低性能电池预测较准确，对最低性能电池的预测精度下降，但仍能识别其相对表现次序。 作者还称所选频率结果优于原研究中ARD识别的17.80 Hz和2.16 Hz特征。 以上为论文报告的结果，并非本次独立复算。



**作者限制：** 作者指出独立电池数量有限，并提出增加温度条件的后续研究；正文没有单列正式的局限性章节。



**主控接纳限定：**



- 早期20循环预测；第5页图3长线由早期预测外推到失效，不是全寿命逐时更新实验。第8页作者明确区分与原研究动态RUL演化目标的不同。

- 分类60点来自有限独立电芯及循环，不称60独立电芯；25C04分类用线性外推，RUL回归移除该电芯并把25C07移到训练集。

- 主要模型的8.8Hz、部分讨论8Hz与第4页单频段8.8kHz保留原文差异；代码未核，不自行更正作者。

- Lasso SOC V的三个系数在第8页给出，但截距、全部正则和标准化/调参未证；不称已完整复现。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / 4.2 Support Vector Machine；第7页 / 4.1 Data Processing；第4页 / 3.2 Remaining Useful Life Prediction；第8页 / 5 Discussion



**主文接纳记录：** [literature/accepted/P16_maintext_successor_v3.json](../../literature/accepted/P16_maintext_successor_v3.json)。

**精读笔记：** `literature/revisions/successor_20261016_v3_batch04/P16_full_read_v2_root.json`；SHA256 `0e2facf6b29d2daa3fc4e2626580396e85dbedd5e64374fda2695f01e51627ed`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2408.03469v1)；[full_text_candidate](https://arxiv.org/pdf/2408.03469v1)。



<a id="p17"></a>

## P17｜MambaLithium: Selective state space model for remaining-useful-life, state-of-health, and state-of-charge estimation of lithium-ion batteries



**研究对象与方法：** 研究提出MambaLithium，用于锂离子电池剩余寿命（RUL）、健康状态（SOH）和荷电状态（SOC）估计。方法将电池特征经z-score标准化后输入选择性状态空间Mamba模型，并用一维表示进行回归。



**实验设置：** 作者报告了RUL/SOH与SOC估计实验，并以RMSE评估；训练配置为Adam、100个epoch、学习率0.01，在NVIDIA GTX 3060（12GB）上运行。



**精读结论／作者结果：** 作者报告MambaLithium在列出的RUL、SOH和SOC RMSE结果中优于基线（SOC的DST和US06室温结果未列基线）。全文没有报告消融实验。



**关键结果细节（完整条目另见证据JSON）：** RUL RMSE（循环）：CaseA基线45.86、MambaLithium 39.71；CaseB基线56.29、MambaLithium 47.62。 SOH RMSE（表中单位为%）：CaseA基线0.47、MambaLithium 0.40；CaseB基线0.42、MambaLithium 0.38。 FUDS SOC RMSE（%）：0°C时基线2.98、模型2.50；25°C时1.78、1.45；50°C时2.04、1.95。 DST与US06室温SOC结果分别为1.62和0.95%，该表未列基线。 作者称模型优于基线或具有较高准确度；这些是论文报告值，并非本项目实测。 没有消融结果、重复实验或不确定性区间报告；也没有证据据此推断独立电芯泛化能力。



**作者限制：** 全文未见作者明确列出的局限性段落或局限性自述；结论主要重申方法表现与应用前景。



**主控接纳限定：**



- root实际核第2页II-A、3页II-C/D及表I、4页表II-IV。Ii/Vi/Ti的原文归属为RUL/SOH，不能自行改为SOC；具体输入对应仍未证。

- RUL RMSE表I CaseA45.86→39.71、CaseB56.29→47.62均为作者报告；split/origin、窗口及基线公平性未证，不代表全寿命多origin动态或独立泛化。

- 页眉LaTeX Class Files/August2021为模板，不是发表身份；源码地址声明已见但仓库未审。

- 独立v2审查PASS同时提命名遗漏：root已在第4页III-B实际看到MambaStock而TableIV写MambaLithium，作为作者命名不一致补入，不擅改表结果归属。此root addendum与note共同构成接纳读书记录。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第3页 / II. 材料与方法：C. Mamba；第4页 / III. 实验：B. SOC估计；第3页 / III. 实验：A. RUL和SOH估计；第4页 / IV. 结论（该节未见明确的作者自述限制）



**主文接纳记录：** [literature/accepted/P17_maintext_successor_v4.json](../../literature/accepted/P17_maintext_successor_v4.json)。

**精读笔记：** `literature/revisions/successor_20261016_v4_batch05/P17_full_read_v2_root.json`；SHA256 `001c2261bc42e606f2a9affb5061be53fb3f031d4b4afed43ef82197bc35bfbe`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2403.05430v1)；[full_text_candidate](https://arxiv.org/pdf/2403.05430v1)。



<a id="p18"></a>

## P18｜The Case for DeepSOH: Addressing Path Dependency for Remaining Useful Life



**研究对象与方法：** 论文以单粒子模型（SPM）及 SEI 生长、锂析出、机械退化模型描述电池退化，提出 deepSOH 状态向量，用于区分相同 eSOH 和电阻下不同的退化状态及其 RUL。



**实验设置：** 作者通过解析推导和 PyBaMM 数值仿真考察可辨识性；模拟三只 eSOH 与瞬时电阻相同但 SEI、析锂厚度不同的老化电芯，并比较其第二寿命循环轨迹。



**精读结论／作者结果：** 分析与仿真表明，eSOH 加瞬时电阻不能唯一确定 SEI 与析锂状态；具有相同 eSOH 和电阻的模拟电芯仍可出现不同退化轨迹及 RUL。加入不可逆膨胀可增加对 deepSOH 的辨识信息。



**关键结果细节（完整条目另见证据JSON）：** 根据方程分析，eSOH 与瞬时电阻这组输出对 δSEI、δpl 不能唯一辨识：存在多组厚度组合满足相同测量约束。 三只模拟电芯的 eSOH 和电阻在同一寿命时点相同，但第二寿命中容量、电阻发展及 C/20 电压轨迹不同，作者据此论证仅使用 eSOH 与电阻不足以给出唯一退化状态或准确 RUL。 作者从机制上解释，不同 SEI 与析锂初始组合可能因 SEI 自限制及析锂加速等非线性效应产生不同后续轨迹。 将不可逆膨胀作为附加输出与原有方程联合，可使状态方程具有唯一解或无解；三只电芯在第二寿命起点呈现不同的不可逆膨胀，显示该量能够提供额外辨识信息。 结论建议增加不可逆膨胀测量，或记录电池使用数据以确定 deepSOH。 正文没有报告表格数值、量化性能提升、误差统计、RUL 数值或消融实验；结果为解析论证及定性仿真比较，不能据此补写定量精度结论。



**作者限制：** 作者明确指出，分析依赖对电芯动态与退化机制参数的完全了解；后续工作将处理参数化和模型不确定性。文中也指出稀疏测量易受噪声与模型误差影响。



**主控接纳限定：**



- root核第1页传统SOH定义和第5页4.1/4.2仿真及6页结论，pdfinfo确认6物理页、尾空段不算7页。传统SOH不只容量，原文也提电阻/功率。

- deepSOH是SPM退化机制状态，不是已训练神经网络；同eSOH/阻抗但不同机制产生不同轨迹为模型假设内仿真，不是量化真实电芯RUL增益。

- 式38唯一解/无解是作者在已设机制/参数中的陈述，参数可知、噪声/观测性局限保留；不外推普遍可辨识性或已解决strict动态协议。

- 独立补充材料未提供，SI 内容及其是否存在无法核实。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第2页 / 2. Battery degradation model；第5页 / 4.1 Measuring eSOH and resistance；第6页 / 5. 结论



**主文接纳记录：** [literature/accepted/P18_maintext_successor_v4.json](../../literature/accepted/P18_maintext_successor_v4.json)。

**精读笔记：** `literature/revisions/successor_20261016_v4_p18/P18_full_read_v2_root.json`；SHA256 `063cf8f373bb1daf749d5b020d6f8e83debf910ebbd53bbdddc464d23bd70aa0`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2405.12028v1)；[full_text_candidate](https://arxiv.org/pdf/2405.12028v1)。



<a id="p20"></a>

## P20｜RUL-QMoE: Multiple Non-crossing Quantile Mixture-of-Experts for Probabilistic Remaining Useful Life Predictions of Varying Battery Materials



**研究对象与方法：** 研究目标是对不同锂离子电池正极材料及混合化学体系进行概率剩余寿命预测。方法以五个材料专属专家网络和输入依赖的门控网络构成混合专家模型，通过多个不交叉分位数估计寿命条件分布，并据此构造密度、累积分布、生存概率和预测区间。



**实验设置：** 实验汇集七个公开电池数据集，按70%训练、30%测试划分训练专家，并报告混合训练阶段、循环100输入的模型比较以及若干回归指标。



**精读结论／作者结果：** 作者报告模型在不同化学体系和数据集上取得不同程度的预测表现，并展示了一个电池的概率预测示例及与既有机器学习基线的RMSE比较。未报告消融实验。



**关键结果细节（完整条目另见证据JSON）：** 按电池类型的表2中，ALL行报告MAE 55、MAPE 7.82%、RMSE 98、R² 98.34%；NMC-LCO行的MAE为10、MAPE为5.20%，而LCO行R²最低，为33.22%。 循环100的表3中，MIX行报告MAE 65、MAPE 9.59%、RMSE 100、R² 96.84%；HUST行MAE最低，为47，MATR2行误差较高，MAE 98、RMSE 136、R² 80.13%。 与基线比较时，作者报告HUST的RMSE为60，对照模型为322；第6页比较文字写CRUSH为100、对照XGBoost为330，但第5页表3的CRUSH RMSE为68；CLO在第6页文字为70、对照模型138，而第5页表3的CLO RMSE为93。 两处内部冲突均保留，未裁定哪个正确，不能将正文100/70作为唯一确定结果。 MIX为100，对照随机森林为197；SNL为93，对照PCR为200。 CRUH上PLSR的RMSE 60优于本文模型的70。 图4示例给出中位RUL预测1632循环、90%预测区间1565至1681循环，覆盖真实值1599循环；文中还给出循环100时生存概率示例。 没有找到消融实验结果。 不同表格/摘要所列总体指标对应的分组或设置并不完全相同，不应合并为同一评价结果。



**作者限制：** 作者提出LCO样本量小、特征表示不足可能解释其弱表现；附录SNL数据集段称实验仍在进行，未分析这对已报告结果的影响。正文未提供专门局限性章节，未报告指标不确定性置信区间或独立外部验证。文中有单电芯预测区间，不能误写为完全无区间输出。



**主控接纳限定：**



- root核第3至6页5.2-5.6及表2/3、附录SNL。CRUSH RMSE表3=68/第6页文字=100；CLO表3=93/文字=70，均保留，不裁定更正值。

- 10至100循环曲线序列、每曲线1000点而1010维及cycle100-only比较之间，如何聚合未证。实际label是否减origin、全寿命更新/拆分/基线预算未证。

- 专家正间隔及共享非负门控权重的非交叉构造不是校准保证；1632和[1565,1681]覆盖1599只是单例。SNL仍在实验为源文状态，不替代独立验证。

- 图像未抽取；除正文可读取的图注及文字描述外，无法核实图中全部曲线、标注和视觉细节。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / 附录：RUL-MoE架构；第4页 / 第5.3节模型训练的实现；第5页 / 第5.6节与其他模型的比较；第4页 / 第5.5节模型性能



**主文接纳记录：** [literature/accepted/P20_maintext_successor_v4.json](../../literature/accepted/P20_maintext_successor_v4.json)。

**精读笔记：** `literature/revisions/successor_20261016_v4_batch05/P20_full_read_v2_root.json`；SHA256 `6edca1c4c7f1e80cf0be0447a91f11e28567ecba9b88892c54a00608c5d2e584`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2512.23725v1)；[full_text_candidate](https://arxiv.org/pdf/2512.23725v1)。



<a id="p21"></a>

## P21｜Cycle Life Prediction for Lithium-ion Batteries: Machine Learning and More



**研究对象与方法：** 这是一篇关于锂离子电池循环寿命预测的教程论文，介绍第一性原理、机器学习与混合模型，并以早期实验室循环数据预测寿命为例，说明可解释数据驱动建模流程。案例采用放电容量差分特征与弹性网回归；论文也讨论融合机理信息的混合建模方向。



**实验设置：** 本文是教程与案例说明，没有报告作者新开展的电池实验。其讲解的案例数据来自既有研究：124 个同批次圆柱形 LFP 电池，电池间改变快充方案，放电条件为恒定 4C、恒温且均为完整循环；图示将样本分为训练集、主测试集和次测试集。



**精读结论／作者结果：** 正文转述的弹性网案例中，训练集、主测试集、次测试集的 RMSE 分别为 76、91、173 个循环；次测试集预测较差，尤其对寿命较长的电芯。融合 LASSO 对寿命低于 1200 次循环的电芯取得与放电特征模型相近的预测表现。没有报告本文新实验或系统消融。



**关键结果细节（完整条目另见证据JSON）：** 图 3 展示基于放电特征的弹性网模型预测：训练集 41 个电芯 RMSE 为 76，主测试集 43 个 RMSE 为 91，次测试集 40 个 RMSE 为 173。 作者指出模型难以准确预测次测试集中寿命更长的电芯；次测试电芯约晚十个月循环，因而经历了更高日历老化，且训练数据中寿命超过 1200 次循环的电芯较少。 正文还转述 Schaeffer 等人的融合 LASSO 方法：它直接从 ΔQ 学习，系数呈分段常数，具有较强可解释性；对循环寿命低于 1200 次的电芯，其预测表现与放电模型相近。 上述均为论文引用并展示的既有工作结果，不是本次独立实测；正文没有报告针对本文方法组件的新消融实验。



**作者限制：** 作者指出数据泄漏、对特定实验条件过拟合、日历老化缺失及跨应用泛化不足等限制；预测相关性本身不能证明因果关系。作者主张需要更丰富且互补的诊断数据以加强退化机理理解。



**主控接纳限定：**



- 仅接纳 arXiv:2404.04049 v1 主文；没有与正式会议版逐字比对，独立 SI 未提供。

- 这是教程及既有研究案例，不是新模型实验或本项目复现。

- 笔记 method 引文的跨栏连续字符串不是优良语义锚点；实质方法据页3–4的特征和弹性网说明核定。limitations 引文所在具体小节为 III.D 的续段，IV 的日历老化限制另在同页核定；本接纳记录修正定位。



**精读来源锚点：** 第4页 / III. TUTORIAL: INTERPRETABLE & ACCURATE DATA-DRIVEN CYCLE LIFE PREDICTION；C. Feature Selection with Regularized Regress；第3页 / III. TUTORIAL: INTERPRETABLE & ACCURATE DATA-DRIVEN CYCLE LIFE PREDICTION；A. Data Generation；第5页 / III. TUTORIAL: INTERPRETABLE & ACCURATE DATA-DRIVEN CYCLE LIFE PREDICTION；E. Battery Cycle Life Prediction Case Studies；第5页 / IV. DISCUSSION ON GENERALIZATION AND CONCLUSION



**主文接纳记录：** [literature/accepted/P21_maintext_successor_v2.json](../../literature/accepted/P21_maintext_successor_v2.json)。

**精读笔记：** `literature/notes/batch03_v4/P21/P21_arxiv_v1_full_read_v4.json`；SHA256 `50070178cc8bcc5056f2748c31153271a206cd29e3af7c14e3471f94fbe69dc7`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2404.04049v1)；[full_text_candidate](https://arxiv.org/pdf/2404.04049v1)。



<a id="p22"></a>

## P22｜HyBattNet: Hybrid Framework for Predicting the Remaining Useful Life of Lithium-Ion Batteries



**研究对象与方法：** 研究目标是根据近期充放电循环信息，预测锂离子电池到达寿命终止点前的剩余循环数。方法将信号预处理与CNN、注意力LSTM和ODE-LSTM组成的混合预测网络结合。



**实验设置：** 作者在两个公开LFP/石墨电池数据集上评估RUL预测，并报告数据划分、训练设置、基线比较、消融和跨数据集迁移实验。



**精读结论／作者结果：** 作者报告混合模型在两个数据集的基线比较中取得较低误差，并通过特征与模块消融报告派生容量特征及混合架构的作用；迁移结果随目标域数据量和冻结策略而变。



**关键结果细节（完整条目另见证据JSON）：** 基线比较表报告：第一数据集上所提模型RMSE 101.59、R² 0.82、MAPE 8.29%；第二数据集上RMSE 158.09、R² 0.89、MAPE 6.95%。 第二数据集模型消融表中，带派生容量特征的CNN+A-LSTM+ODE-LSTM为RMSE 158.09、R² 0.89、MAPE 6.95%；不带该特征时对应为163.31、0.85、7.54%。 文中还报告特征组合搜索中[I,V,Q,派生容量]优于只用派生特征，δ=9表现最佳；ODE-LSTM对比标准LSTM的图示结论为预测较稳定。 迁移实验中，第二数据集Case 8报告RMSE 157.92、R² 0.88、MAPE 6.88%，冻结A-LSTM模块的结果优于表列的其他冻结方案；不迁移而跨数据集测试的Case 2和6误差较高且R²为负。 作者报告早期寿命预测的平均RMSE为181.11循环，低于其引用基线的214循环。 结果均为论文报告值，不是本项目实测。 需注意，正文第11页对跨电芯RMSE分布的文字将两数据集的均值写为第一数据集158.09、第二数据集101.59，与基线表及前文的对应关系相反，来源内部存在不一致，无法据此消解。  作者称前30循环的早期寿命RMSE181.11与引用前100循环的214比较；这里输入预算不同，不作为本项目统一公平基准优势证据。



**作者限制：** 作者指出现有评估受控于恒定环境温度和特定电池化学体系，并提出真实驾驶数据、更多化学体系、不确定性建模及设备端部署等后续方向。



**主控接纳限定：**



- root核第4页delta和窗口构造、9至11页基线和early设置、12页讨论。delta=9，i-29>9意味着整数锚点至少39；前30循环early实验如何满足条件未证。派生特征原始历史可能早于名义30cycle窗口，仍不能因此断言未来泄漏。

- 传统ML用本文预处理，引用[16]/[36]保留自身设置；early基线前100cycle与本文前30不同，不是统一预算公平比较。90%/10%验证是否物理电芯隔离未证。

- 容量/派生容量输入与讨论只用I/V矛盾，数据集RMSE均值叙述与表归属相反保留。正文80%阈值未与本项目HUSTv11 observed/estimated语义对齐，不升级onlineGO。

- ODE-LSTM更平稳是作者图示解释，不是本项目逐origin震荡度量；source-only跨域差不自动证明适配负迁移。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / II-A. Signal Preprocessing—Feature Fusion；第7页 / IV-A. Experimental Setup；第8页 / IV-B. Evaluation of Signal Preprocessing；第13页 / IV-F. Discussion / V. Conclusion



**主文接纳记录：** [literature/accepted/P22_maintext_successor_v4.json](../../literature/accepted/P22_maintext_successor_v4.json)。

**精读笔记：** `literature/revisions/successor_20261016_v4_batch05/P22_full_read_v2_root.json`；SHA256 `adbd4be970253ba5db00adf06081bb25b9e5cf7f590d4f836084aad4b1c4a01b`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2505.16664v3)；[full_text_candidate](https://arxiv.org/pdf/2505.16664v3)。



<a id="p23"></a>

## P23｜Generalization bounds and sample complexity for remaining useful life prediction from complete degradation trajectories



**研究对象与方法：** 研究对象是从完整退化轨迹预测设备剩余寿命（RUL）所需的样本量及其泛化误差。作者把一台设备的一条完整轨迹视为一个样本，建立分布无关的泛化界、极小极大下界，并分析物理先验、机群差异、右删失和模型错设的影响。



**实验设置：** 本文以既有公开数据集及已发表结果对理论预测作数值核验，没有开展新的实验室或现场实验。唯一新增计算是对公开电池数据训练集作子样本分析以估计收敛率。



**精读结论／作者结果：** 理论上，泛化偏差界随模型复杂度增加、随完整失效轨迹数增加而收紧；物理先验在模型正确设定时可显著降低样本需求，低噪声条件下可达到快速收敛率。公开基准核验显示效果因领域、指标和条件而异，且并非受控消融。



**关键结果细节（完整条目另见证据JSON）：** 定理1给出标准率界，样本复杂度约为 B⁴p/ε²（忽略对数项）；定理5给出不可改进的复杂度下界，定理6在 Bernstein 条件 κ=1 时达到 O(p/n) 超额风险率。 定理2推导物理约束带来的复杂度比例；表1的代表性预测中，LSTM、CNN、Transformer 的样本需求分别降低约93%、96%、99%。 定理3将风险拆为名义风险、机群方差和随样本增多而下降的估计误差。 定理4指出删失效率依赖退化类型：β=3 的幂律退化只观察一半寿命时，状态估计效率约0.031，约需32倍轨迹匹配完整数据；作者同时指出该量可能高估凹型退化对 RUL 外推有用的信息。 定理7显示错设引入偏差地板，表2报告了不同退化类别假设组合的惩罚。 数值验证中，FD001 的预测与观测 RMSE 界约为28/13，电池约572/73，轴承约14.7千/3千；表5给出的跨比较平均一致性比率为2.5，而泛化界本身的比率为5.0，说明界较保守。 电池子样本误差约从 n=20 时19%降至 n=100 时9.8%；原始拟合指数为0.41，扣除估计机群误差地板后为1.2。 作者称快速率和删失理论的经验核验依赖间接推断；数据中多种效应重叠，缺少能隔离单一效应的受控实验。



**作者限制：** 作者明确指出：独立同分布机群假设限制部署外推；高斯噪声、独立删失及单一退化模式限制部分结果；删失效率不等于 RUL 外推效率；经验验证多为间接比较，无法干净分离各因素。



**主控接纳限定：**



- root核第3至6页模型/完整轨迹等权损失与定理1证明、9至10页定理5/6，并结合独立theory spot audit。主文接纳仅认可读书笔记与源文一致，不是定理独立重证。

- 定理1 Step3直接以Pdim(H)控制trajectory-integrated squared loss class，复杂度传递论证未展开；定理5 Fano packing对任意Pdim类/退化族适用性未展开。保留为证明缺口待核，不据此声称已证错误或反例。

- 标准uniform deviation率与Bernstein条件fast excess-risk率分开。Theta(p/n)需packing/fast-rate等条件；经验alpha单点校准/文献指标换算不是独立定理证成。

- t/T归一化及完整轨迹风险不是已实现prefix-only在线系统，也不自动证明训练标签泄漏。删失SNR效率不等同RUL外推效率。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第6页 / 第4.1节 RUL预测的样本复杂度；第12页 / 第5节 数值验证；第16页 / 第5.5节 定量总结；第19页 / 第6.5节 局限与扩展



**主文接纳记录：** [literature/accepted/P23_maintext_successor_v4.json](../../literature/accepted/P23_maintext_successor_v4.json)。

**精读笔记：** `literature/notes/batch05_v1/P23/P23_full_read_v1.json`；SHA256 `7f20048acd3bf026c2cdfa9e8bb1d4f1ac3209f7e9fa352243df34e7f0e1a95b`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2607.23454v1)；[full_text_candidate](https://arxiv.org/pdf/2607.23454v1)。



<a id="p24"></a>

## P24｜Improve in-situ life prediction and classification performance by capturing both the present state and evolution rate of battery aging



**研究对象与方法：** 研究旨在改善锂离子电池原位剩余寿命预测和退役电池寿命分类，将电池当前老化状态与近期老化速率同时作为信息来源。方法以二阶等效电路模型特征表示状态，以电压松弛曲线差或相邻循环容量—电压曲线差表示速率，并分别用高斯过程回归和高斯过程分类建模。



**实验设置：** 作者在既有循环老化数据上评估方法，涉及74个、三种类型的电池；寿命预测与分类采用不同输入采集和评估设置。



**精读结论／作者结果：** 作者报告，状态与速率联合特征通常改善NCA、NCM寿命预测，并在多项分类条件下优于仅用状态或速率特征；效果因电池类型和工况而异。



**关键结果细节（完整条目另见证据JSON）：** 寿命预测消融比较ECM、统计速率特征STATS、ECM加累计Ah和累计时间的基准、以及ECM加新提出的电压松弛曲线差特征。 NCA和NCM上，联合新特征通常得到更低RMSE，作者报告相对基准的最高精度改善为67.09%；个别条件下新特征不如基准。 NCM的STATS单独模型在一个条件下RMSE达到317.6循环。 NCM+NCA的多种特征结果相近，作者将其归因于不同工况下特征变化较一致。 改变起始循环后，作者报告新方法对NCA、NCM通常仍表现较好；减少松弛时间时预测总体稳定，但仅用六个采样点会有轻微误差增加。 分类结果中，作者报告总体准确率约95%，并称不同窗口大小下结果变化有限；表III显示，各条件表现并非处处优于基准。 NCA 25℃条件下，ECM准确率为71.60%，联合特征为82.72%；NCA 35℃时联合分类器准确率低于ECM。 作者还报告NCA新电芯分类准确率从SOH 100%时的61.90%升至SOH 95%时的90.48%，接近寿命终点时仅一例误分类。 上述均为论文作者报告值，不是本项目实测。



**作者限制：** 作者明确指出，部分条件样本很少，联合特征需要更多数据才能建立可靠关系；现有结果不能证明在未测试数据或真实现场条件下具有独立泛化能力。



**主控接纳限定：**



- root核第3页TableI、5至7页III-A/B及式13、第10页TableII与13页TableIII。74cells按表分配是作者报告，非本项目数据审计。

- 式13的MAPE分母是文中bar_y（作者称observed cycle of battery EOL），不是逐样本remaining-RUL y_i；不能将其数值直接与通常逐样本RUL-MAPE比较。

- 67.09%来自NCA35C相对benchmark RMSE59.53→19.59；不是所有条件平均增益。NCA35C分类联合特征劣于ECM且仅1train/1test必须保留。

- 窗口起点/松弛采样需可得性定义；全文未提供完整阈值/label生成链，不直接等同严格online合法验证。PDF无版本戳，v1由精确下载URL/SHA和对应primary record限定，不宣称PDF内有戳。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第5页 / III.A. 原位电池寿命预测方法：特征工程；第3页 / II. 数据生成；第10页 / IV.B. 原位电池RUL预测性能，表II；第13页 / IV.C. 车载电池寿命分类性能



**主文接纳记录：** [literature/accepted/P24_maintext_successor_v4.json](../../literature/accepted/P24_maintext_successor_v4.json)。

**精读笔记：** `literature/notes/batch05_v1/P24/P24_full_read_v1.json`；SHA256 `6731de2ccc943f74410f7f8b42e6d20056cde0e175f83d0e092fd1101d92e991`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2308.13996v1)；[full_text_candidate](https://arxiv.org/pdf/2308.13996v1)。



<a id="p25"></a>

## P25｜Domain knowledge-guided machine learning framework for state of health estimation in Lithium-ion batteries



**研究对象与方法：** 研究对象是用于电动汽车工况老化实验的锂离子电芯，目标是依据可从充放电信号提取的领域知识健康指标估计SOH所用的容量衰减。方法构造五类指标并以增量特征训练线性回归模型；这是经验性建模工作，未报告形式化定理或证明。



**实验设置：** 作者使用公开实验数据中五只INR21700-M50T电芯，进行跨电芯训练与测试；协议包含UDDS放电、分段充电和周期性参考性能测试。



**精读结论／作者结果：** 功率自相关单特征及充放电能量特征均能较准确地估计容量衰减；在能量特征上增加内阻或充电阻抗没有改善结果。



**关键结果细节（完整条目另见证据JSON）：** 作者报告功率自相关模型APE低于1.5%；但该特征依赖放电电流剖面的周期性，因此作者认为不能直接作为真实道路驾驶中的SOH指标，可考虑用于静置时施加周期电流的诊断工具。 充电和放电能量特征在仅用W8训练时，跨其他四只电芯测试APE低于2.5%；使用四只电芯训练、留一只测试时APE低于1.6%。 作者报告这些特征在部分数据缺失的电芯上仍有表现。 消融比较中，在充放电能量之外加入充电阻抗和/或内阻后，模型表现变差，作者将其解释为短时指标可能引入更多噪声。 对比模型的补充表给出各模型RMSE：FNN为0.66、1.21、0.90、0.87；RNN为0.50、1.04、1.11、0.78；线性回归为0.40、1.27、0.94、0.91；ARMAX为0.39、1.23、0.93、0.91（对应V4、W5、W7、W9）。 补充材料称没有一种模型在准确度上全面胜出，作者选择线性回归主要基于计算效率。 上述数值均为作者报告结果，不是独立复现实测；跨电芯测试结果不单独证明更广泛的独立泛化能力。



**作者限制：** 作者指出数据集未覆盖温度变化和典型真实使用中的实际放电事件，且信号噪声水平较低；未来工作包括使用现场数据及探索更大数据集上的RUL预测。



**主控接纳限定：**



- 正文表1 W9=341、补充表S2=340并列，原文未解释；不自行更正。

- 五电芯受控23C/UDDS容量SOH估计，非动态RUL；RPT插值监督不自动等于输入泄漏。

- LR与复杂模型没有全面赢家；功率自相关依赖周期放电，能量指标现实工况适用性及跨温度/化学体系未验证。

- 独立v2 PASS仍建议补作者化学体系无关主张；root实际读第4页明确：作者称指标agnostic to specific battery chemistries且不依赖累计周期/Ah，这只是指标设计/适用性主张，本研究五只NMC实验不验证跨化学泛化。独立审建议和此root补充一并保留，未改旧note/review。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第20页 / Methods—Estimation model；第30页 / Methods—Cell cycling and experimental dataset；第12页 / Results—SOH estimation；第15页 / Conclusions



**主文接纳记录：** [literature/accepted/P25_maintext_successor_v5.json](../../literature/accepted/P25_maintext_successor_v5.json)。

**精读笔记：** `literature/revisions/successor_20261016_v5_batch06/P25_full_read_v2_root.json`；SHA256 `5854a0724d87492ca4284c8425b2af22f316653b39daf8401df7421cb1c06d80`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2409.14575v1)；[full_text_candidate](https://arxiv.org/pdf/2409.14575v1)。



<a id="p26"></a>

## P26｜SambaMixer: State of Health Prediction of Li-ion Batteries using Mamba State Space Models



**研究对象与方法：** 研究目标是从单个锂离子电池放电循环的多变量测量序列预测该循环的SOH。作者提出SambaMixer，以MambaMixer式结构处理时间与通道维度，并加入锚点重采样及基于采样时间和相邻循环时间差的位置编码。



**实验设置：** 作者在NASA Ames PCoE锂离子电池放电数据集上评估，设置NASA-S、NASA-M、NASA-L三种训练与评估划分，主要实验以NASA-L训练的SambaMixer-L为基线，并报告SOH及EOL相关指标。



**精读结论／作者结果：** 作者报告SambaMixer在NASA评估设置中取得较低的SOH误差；消融结果支持所提出的混合骨干、锚点重采样和联合位置编码在该数据设置中的效果。



**关键结果细节（完整条目另见证据JSON）：** NASA-L上的SambaMixer-L报告MAE 1.072、RMSE 1.592、MAPE 1.346。 与Mazzi等方法逐电芯比较时，SambaMixer在电芯#6的MAE/RMSE/MAPE为1.173/2.068/1.406，对照为2.448/3.177/1.579；#7为1.197/1.285/1.498，对照为1.861/2.252/1.114；#47为0.512/0.645/0.822，对照为2.549/3.094/1.969，因此该表并非每项指标均优于对照。 模型规模与数据规模实验显示总体误差随规模变化，但XL在NASA-L上的表现略逊于L，作者认为可能过拟合。 消融中，SambaMixer骨干优于vanilla Mamba（MAE/RMSE/MAPE为1.072/1.592/1.346，对照1.709/2.386/2.161）；锚点、线性、随机重采样分别为1.072/1.592/1.346、1.272/1.862/1.631、3.315/4.368/4.302；无位置编码、仅采样时间编码、采样时间加循环间隔编码分别为3.097/3.966/4.257、1.160/1.721/1.450、1.072/1.592/1.346。 无CLS的均值池化结果优于所测CLS位置。 预老化起点实验中，作者报告多数所列指标优于Mazzi等方法，但#07的MAPE例外；#47各起点的AEOLE为0。 以上均为论文报告结果，并非本项目独立复算或实测。



**作者限制：** 作者称仅一个NASA数据集、同一化学体系和所选恒流放电循环；其中“仅恒流”与表II/III中NASA-S训练包含PWM电芯#25冲突。跨数据集、化学体系和放电配置的泛化尚未验证。



**主控接纳限定：**



- active只用v3，v2式24抽取误疑已移除；root PDF第8页实核式24含绝对值，文本缺竖线不是原文错误。

- 表II #25为PWM 0.05Hz/4A、表III #25 NASA-S train，与VI.A仅恒流冲突保留；不猜实际实现。

- 任务是单放电循环SOH，EOL指示绝对误差非严格动态RUL；first/last crossing操作仍待代码核实，绝对误差不当signed bias。

- NASA同化学体系有限划分，#7 MAPE未胜Mazzi；缺前序循环的时间编码实现未证。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / IV. Proposed Method—Problem Formulation；第7页 / V. Experiments and Ablations；第9页 / V.C1. SOH Estimation for Entire Battery Lifetime；第11页 / VI.A. Limitations



**主文接纳记录：** [literature/accepted/P26_maintext_successor_v5.json](../../literature/accepted/P26_maintext_successor_v5.json)。

**精读笔记：** `literature/revisions/successor_20261016_v5_batch06/P26_full_read_v3_root.json`；SHA256 `193b55f33af04b5e0baae7a3c2f7329266f9d491ab915d105351d3f6f37ee6a6`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2411.00233v1)；[full_text_candidate](https://arxiv.org/pdf/2411.00233v1)。



<a id="p27"></a>

## P27｜Why we need a standardized state of health definition for electric vehicle battery packs -- a proposal for energy- and capacity-based metrics



**研究对象与方法：** 提出通过车载充电测量容量和能量型电池包健康状态，并可用差分电压分析进一步辨析老化特征。



**实验设置：** 实际测试涵盖多种量产电动汽车；车辆先放电、静置，再以低功率充电并采集车载信号。



**精读结论／作者结果：** 作者报告多个车型可用该程序测量，并观察到锂库存损失是所测电池包的主要老化模式；固定电压窗口有助于测量间比较。



**关键结果细节（完整条目另见证据JSON）：** 论文在大众 ID.3、保时捷 Taycan、Tesla Model 3 和 Model Y 等车辆上展示了应用。 作者报告所测车辆中锂库存损失是主要退化模式，并主要导致容量或能量损失；不同化学体系及电压曲线特征会影响能否识别电极活性物质损失。 五辆 Cupra 的比较显示，固定 SOC 窗口下充入能量存在差异，而采用适配全部样本的370–445 V窗口时，所列充入能量为52.7–54.0 kWh；同一辆车三次测量为53.8、53.9、54.0 kWh。 作者据此认为固定电压边界更利于可比性和重复性。 正文提到定量容量、能量及退化模式汇总在补充表1；该补充材料未提供，因此此处无法核对其完整结果。



**作者限制：** 作者指出测量耗时、车型及电池包差异、BMS行为和电芯缺陷会限制测量或老化诊断。



**主控接纳限定：**



- 本篇研究车辆电池SOH标准测量/诊断，不是寿命预测性能。

- 主文第5页pristine voltage-capacity curves/OEM访问限制已修窄，不泛称全部原始数据难取得。

- SI未提供；作者代码/数据声明的当前可访问性和运行未核。



**精读来源锚点：** 第7页 / Methods—Data acquisition；第3页 / Results—A standard charging measurement proposal；第4页 / Results—Application of the proposed method；第6页 / Discussion—EV-specific peculiarities



**主文接纳记录：** [literature/accepted/P27_maintext_successor_v2.json](../../literature/accepted/P27_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v2/P27_full_read_v2.json`；SHA256 `d93458736a05f6dc3ebb9136ce7530db7cdf9b1ca71dbe21634f2b3061da7381`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2508.15517v1)；[full_text_candidate](https://arxiv.org/pdf/2508.15517v1)。



<a id="p28"></a>

## P28｜Lithium-ion battery degradation: using degradation mode analysis to validate lifetime prediction modelling



**研究对象与方法：** 研究比较三种复杂度不同的锂离子电池物理退化模型，检验将退化模式纳入参数化和验证是否有助于模型区分与预测。



**实验设置：** 使用既有商用圆柱电芯老化数据，以一组实验进行参数化，另一组实验进行验证，并在多个温度和荷电状态范围下比较模型。



**精读结论／作者结果：** 三种模型都能较好拟合部分常用性能指标，但退化模式误差使模型差异更明显；五机制耦合模型在实验2的综合退化模式拟合较好，验证表现则随温度而变。



**关键结果细节（完整条目另见证据JSON）：** 在实验2中，三种模型对电压的平均百分比误差均低于0.8%，正文第3页文字称状态健康度最大MPE低于0.88%，但第4页表2的5 coupled、25 °C行列出0.88%；原文两处数值边界表述存在冲突，故不将 低于0.88%作为一致结论；电阻拟合误差较高，单凭电压、状态健康度和电阻难以选出优胜模型。 退化模式比较显示，SEI 单机制模型因不预测活性材料损失而在两极活性材料损失上出现100%误差。 五机制耦合模型在三种温度下的综合加权误差分别为11.99%、10.41%和12.05%，低于 SEI 与干涸模型对应的16.91%、13.78%和14.45%。 实验3验证中，五机制模型在40 °C拟合五项指标较好，综合误差为10.58%；25 °C表现较差，10 °C未能拟合。 作者还报告该模型在实验3高 SOC 条件下较能捕捉退化，而三个模型均不能重现10 °C和25 °C下实验2与实验3间复杂的 SOC 依赖性。 三种模型的比较构成模型复杂度对照；正文未报告单独的正式消融实验。



**作者限制：** 作者指出参数搜索未使用优化方法，模型仍无法解释若干 SOC 依赖和实验数据；低 SOC 下可能需要加入硅退化机制。



**主控接纳限定：**



- 物理退化模型比较与验证，不自动构成动态RUL预测。

- 保留原文文字与表格0.88%的边界差异。

- SI中的方程/参数/补图未提供，代码与模型实现对应和项目复现未核。



**精读来源锚点：** 第8页 / 方法：参数化；第6页 / 方法：老化数据集；第5页 / 结果：退化模式模拟误差；第6页 / 讨论：研究限制与未来工作



**主文接纳记录：** [literature/accepted/P28_maintext_successor_v2.json](../../literature/accepted/P28_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v2/P28_full_read_v2.json`；SHA256 `dac75ed92e7731811b64f48c77a166dcfb89c76b0a2740232345364475064541`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2311.05482v2)；[full_text_candidate](https://arxiv.org/pdf/2311.05482v2)。



<a id="p29"></a>

## P29｜Systematic Feature Design for Cycle Life Prediction of Lithium-Ion Batteries During Formation



**研究对象与方法：** 研究目标是仅利用电池制造形成阶段的数据，对锂离子电池循环寿命进行极早期预测，并设计少量、可解释且能比较不同形成条件的特征。作者提出系统化特征设计流程：筛选输入数据类型，以融合套索回归得到分段系数曲线，再据其分段构造并筛选特征。该研究还用反应粒子集合模型探讨特征可能的物理来源；这属于机制解释假设，不是形式化证明。



**实验设置：** 作者使用按形成方案划分的嵌套交叉验证评估预测性能，并与方案参数基线、自动特征提取模型及设计特征模型比较。预测输入来自形成过程，不需额外诊断循环；标签为循环寿命。来源没有报告独立电芯级外部测试。



**精读结论／作者结果：** 作者报告，步骤B的两个设计Q(V)特征在非线性模型下达到9.20%的中位MAPE，低于最佳autoML模型的9.72%；但最大MAPE为11.93%，高于autoML的10.85%。结果支持该数据集和划分下少量设计特征具有竞争力，不足以单凭高预测表现证明独立泛化。



**关键结果细节（完整条目另见证据JSON）：** 步骤B的Q(V)候选优于其他候选输入类型。 表中最佳非线性设计模型只用2个特征，RMSE中位数/最大值为97.33/108.54，MAPE中位数/最大值为9.20/11.93；非线性autoML使用155个特征，对应86.17/136.92及9.72/10.85；非线性agnostic模型使用4个特征，对应107.10/124.81及11.06/11.35。 线性设计模型的中位MAPE为11.30%，线性autoML为9.87%，线性agnostic为14.84%。 因此设计模型并非在所有指标上胜出，作者报告其与autoML各自在两项指标上更优。 作者还报告五个外层划分得到的设计特征较一致，并称设计特征在62种方案间变化约12%。 物理分析将所选电压区间与平均容量曲线二阶导数的局部极值联系起来，并通过极慢形成子集及粒子集合模拟提出温度效应和微观电阻异质性可能参与解释预测表现；该解释是作者的机制假设。



**作者限制：** 作者明确指出，反应粒子集合模型假设所有粒子在初始时具有相同SoC；由于数据无法量化或验证粒子SoC分布，这一假设可能较差，相关研究留待后续。作者也指出简化的电极利用率模型未能完美拟合微分电容曲线，可能因为忽略反应与传输限制的假设不成立。



**主控接纳限定：**



- 正文inner10 subsets与附录S3 inner5 groups冲突保留，实际实现未核。

- RLS需准确SoC/额外低倍率循环且只适合同形成温度；agnostic模板/个体诊断限制显式保留。

- 形成期cycle-life预测非全origin动态RUL；仅纳入达到EOL178/186的回顾筛选不当strict online资格。

- 设计2特征中位MAPE9.20优于autoML9.72但最大11.93差于10.85；机制微观异质性仍作者假设，非独立实测。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / 2.2.3 从输入数据确定线性回归系数β；第4页 / 2.1 数据集描述；第12页 / 3.1 设计特征的评估；第40页 / 附录S7.3 反应粒子集合模型



**主文接纳记录：** [literature/accepted/P29_maintext_successor_v5.json](../../literature/accepted/P29_maintext_successor_v5.json)。

**精读笔记：** `literature/revisions/successor_20261016_v5_batch06/P29_full_read_v2_root.json`；SHA256 `99b422a1d7bac0fffe5141b68212f52e0edf0784b8271d36f5503e1e20fbc6bf`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2410.07458v1)；[full_text_candidate](https://arxiv.org/pdf/2410.07458v1)。



<a id="p31"></a>

## P31｜PiDDM: Physics-Informed Differentiable Degradation Modeling for Lithium-Ion Battery State-of-Health Prediction



**研究对象与方法：** 研究对象是锂离子电池SOH衰退预测。PiDDM将充电特征输入神经网络，以可微的Arrhenius—幂律衰退率先验约束容量轨迹；文中给出模型设计与经验依据，未报告定理证明。



**实验设置：** 使用公开的55个NCM电池数据，覆盖六种充放电协议；采用按电池划分的43个训练、12个独立测试电池，并另做前90%轨迹训练、末10%时间外推。



**精读结论／作者结果：** 标准预测和时间外推均与MLP、基线PINN比较。PiDDM总体平均误差最低，但外推R3上MLP在四项误差指标均更优；文中未报告单独的组件消融实验。



**关键结果细节（完整条目另见证据JSON）：** 标准预测中，PiDDM平均MSE为6.6271×10⁻⁵，低于基线PINN的1.7702×10⁻⁴和MLP的2.4187×10⁻⁴；作者称其在大多数协议和指标上较优。 R2.5是例外之一：PINN的MAPE和MAE略低于PiDDM，作者将其与测量噪声或暂时性容量回升样波动及PiDDM的非增约束联系起来；但PiDDM在该协议的RMSE和MSE较低。 时间外推中，PiDDM平均MSE为1.1067×10⁻⁴，低于PINN的2.4381×10⁻⁴和MLP的8.2631×10⁻⁴；PiDDM在六种协议中的五种误差最低。 R3则由MLP在四项指标上获胜，其MSE为1.5786×10⁻⁴，PiDDM为3.4648×10⁻⁴。 作者同时报告轨迹层面的定性观察：PiDDM通常更平滑且更符合长期衰退方向，但点误差并非在所有协议上最低。 实验是不同模型间比较；未见逐项移除PiDDM损失或组件的消融结果。



**作者限制：** 作者承认经验衰退式不是完整或唯一的老化描述，物理约束也可能降低对局部上升波动的拟合；后续计划扩展变量、化学体系与使用条件。



**主控接纳限定：**



- PiDDM/MLP与PINN epochs500/200、batch10000/256、baseLR0.001/0.01，且PINN双网络不同；共同输入/拆分不等相同预算。

- 55cells报告43train/12test及90/10外推；SOH轨迹估计非严格全origin绝对RUL，label/asof实现与独立验证集划分未核。

- 负衰退先验可牺牲局部恢复拟合；R2.5部分指标、外推R3 MLP四误差更好，保留负面。

- 经验Arrhenius/幂律是学习先验，非完整唯一机理；无定理或内部组件消融。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第8页 / 2.3. PiDDM Framework；第15页 / 2.4.6. Evaluation protocol；第16页 / 3.1. PiDDM performance；第23页 / 4. Conclusion and Discussion



**主文接纳记录：** [literature/accepted/P31_maintext_successor_v5.json](../../literature/accepted/P31_maintext_successor_v5.json)。

**精读笔记：** `literature/revisions/successor_20261016_v5_batch06/P31_full_read_v2_root.json`；SHA256 `fd741ddcc0cc40349c06abff95650b07706ce29b959801c44813a1d763fefc7a`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2607.29095v1)；[full_text_candidate](https://arxiv.org/pdf/2607.29095v1)。



<a id="p32"></a>

## P32｜Multiscale Dual-path Feature Aggregation Network for Remaining Useful Life Prediction of Lithium-Ion Batteries



**研究对象与方法：** 研究对象是锂离子电池剩余寿命预测。作者提出MDFA-Net，以并行的多尺度特征路径MF-Net和编码路径EC-Net提取并融合浅层与深层特征。



**实验设置：** 作者在NASA和CALCE两个公开锂离子电池循环测试容量数据集上评估模型，采用留一电芯测试协议，并与多类RUL预测基线比较。



**精读结论／作者结果：** 作者报告MDFA-Net在NASA与CALCE数据集上取得较强的整体结果；消融显示去除MF-Net造成的性能下降尤其明显，作者认为MF-Net解释了多数方差。



**关键结果细节（完整条目另见证据JSON）：** NASA表格的平均结果为R² 0.9571、MAE 0.0259、RMSE 0.0333；CALCE结果为R² 0.9828、MAE 0.0216、RMSE 0.0277。 作者报告NASA B0006的MAE相对降低8.68%，B0018的R²提升7.30%、RMSE降低26.86%；CALCE相对当时最佳对照的三项指标提升分别报告为0.47%、5.67%、9.47%。 NASA窗口分析中，多数测试电芯以窗口16表现较好，B0005以24较好，32会过度平滑短期变化。 消融表中，去除MF-Net后NASA R²由0.9571降至0.9133、CALCE由0.9828降至0.9448；去除EC-Net后分别为0.9537和0.9811。 去除位置编码、同时去除位置编码与自注意力、改为串行结构也有表列结果。 作者指出EC-Net带来一致但有限的平均增益，并提供互补线索。 数值均为论文报告，非本次独立复测。  第6页作者对Fig.4的定性文字称所选NASA各子集示例曲线倾向低估而非高估RUL，并称其在实践中更安全；这里只转述作者定性观察，不是root读图逐点或本项目signed-bias统计，也不构成安全保证。 第5页Table1同时显示NASA平均MAE：AUKF-GASVR=0.0253，MDFA-Net=0.0259；因此不能将正文“所有指标胜出”升级为整个表格所有baseline/所有指标均优，作者强调部分神经基线不代表全表最优。



**作者限制：** 作者明确提到精度与效率之间存在权衡，并指出训练数据有限；其未来工作计划采用迁移学习应对数据有限问题。



**主控接纳限定：**



- NASA avgMAE AUKF0.0253优于MDFA0.0259，不能说全表所有指标胜出；可复现均10次与文献最佳值混用公平性未证。

- 第6页作者称示例曲线倾向低估且更安全，仅作者定性叙述非root像素/统计或真实安全证明。

- B0006训练243.18/154.64/491.35秒及测试0.7812/0.2343/1.2656秒只在作者设置内；无实际BMS部署验证。

- 70% nominal EOL、留一电芯是作者协议；实际RUL单位/标签/输入完整特征与origin未明，Lie-Trotter类比不是证明。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第2页 / 2. Methodology；2.1 MDFA-Net Overview；第4页 / 3.1 Datasets；第9页 / 3.5.2 Ablation study；Table 4；第6页 / 3.3 Results on NASA



**主文接纳记录：** [literature/accepted/P32_maintext_successor_v5.json](../../literature/accepted/P32_maintext_successor_v5.json)。

**精读笔记：** `literature/revisions/successor_20261016_v5_batch06/P32_full_read_v2_root.json`；SHA256 `1cdd52df0df3d71f3502e4ff84f6383cf20ed693b1663147a5c35e5e4459ce7e`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2512.19719v1)；[full_text_candidate](https://arxiv.org/pdf/2512.19719v1)。



<a id="p33"></a>

## P33｜Towards a BMS2 Design Framework: Adaptive Data-driven State-of-health Estimation for Second-Life Batteries with BIBO Stability Guarantees



**研究对象与方法：** 研究目标是为缺少历史使用记录、特性各异的退役电动车电池设计在线SOH估计方法，并给出BIBO稳定性保证。方法将基于轨迹聚类的自适应估计与离线弹性网络回归结合。



**实验设置：** 作者在八个实验室老化的退役日产Leaf电池软包电芯上验证方法，并报告留一电芯测试。



**精读结论／作者结果：** 八个留一电芯案例的平均RMSPE从ENR的3.40%降至自适应估计的3.27%；单电芯案例中，组合方法也降低了报告的容量估计误差。



**关键结果细节（完整条目另见证据JSON）：** 表I逐电芯结果显示，自适应方法在部分电芯上优于ENR、部分电芯上略差。 Cell 1.4案例中，ENR最大逐点绝对百分比误差为3%，RMSPE为1.8166%；自适应方法对应为2%和0.8610%。 Cell 1.2案例中，报告的点对点容量百分比RMSE从ENR的1.4686%降至1.2182%。 α敏感性分析显示最佳值随电芯而异：Cell 1.2当前α在所测范围内给出最低RMSE；Cell 1.4最低值出现在α=6×10⁻⁶；Cell 2.3最低值出现在α≥2.8×10⁻⁴的一段范围。 作者展示的消融/对照主要是组合自适应方法对比单独ENR，并未报告其他模型或组件的系统性消融。 平均RMSPE改善幅度有限，不能据此推出独立泛化能力。



**作者限制：** 作者指出，观测数据有限时聚类可能出现较大分类误差；来源未报告对更广泛电池类型、真实部署场景或独立数据集的验证。



**主控接纳限定：**



- 容量峰值高于初始与温度背景、测试一年容量不低于初值与电压降额解释分开，均作者观察非项目因果实测。

- Fig6电流/电压/表温及前一时刻特征；回归当前Xn、聚类累计Ah与charge轨迹；w2=min(alphaAh,0.5)，alpha训练集验证选择未独立核嵌套预算。

- BIBO限有界输入/轨迹下误差有界，非独立泛化；8同来源退役电芯平均RMSPE3.40→3.27有个体负面，SOH非动态RUL。

- 未提供独立补充材料。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第7页 / V.B. 结合聚类与回归的自适应估计；第2页 / III. 退役电池数据集；第10页 / VI. 结果与讨论



**主文接纳记录：** [literature/accepted/P33_maintext_successor_v6.json](../../literature/accepted/P33_maintext_successor_v6.json)。

**精读笔记：** `literature/revisions/successor_20261017_v6_batch07/P33_full_read_v4_root.json`；SHA256 `c7280fbcae6e583886ea21e6d740a3e74eefcd7b7c3463ac623b3b4238ba76cc`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2401.04734v2)；[full_text_candidate](https://arxiv.org/pdf/2401.04734v2)。



<a id="p35"></a>

## P35｜DiffBatt: A Diffusion Model for Battery Degradation Prediction and Synthesis



**研究对象与方法：** 研究对象是锂离子电池的容量退化曲线，目标包括SOH估计、RUL预测和SOH曲线合成。DiffBatt将扩散模型、分类器自由引导与Transformer条件编码结合，用概率生成方式表示退化行为。



**实验设置：** 作者使用BatteryML所列公开电池数据及其数据划分进行基准比较，并分别评估RUL预测、SOH估计和SOH合成。



**精读结论／作者结果：** 作者报告DiffBatt在多个数据集的RUL和SOH任务中取得较低RMSE；MATR1合成实验显示，引导强度会影响合成相似度、多样性与随机森林预测误差。



**关键结果细节（完整条目另见证据JSON）：** RUL任务中，作者报告MATR1、SNL和CRUSH上的RMSE分别为88±4、125±11和294±18，均为所比较结果中的最低值；跨数据集平均RMSE为196。 MIX上的RMSE为202±6，略高于最佳报告值197；MATR2为235±16，未取得该数据集最低值。 SOH任务在EOL为80%时，作者报告跨数据集平均RMSE为2.05；EOL为90%、70%、60%时的平均RMSE分别为1.19、2.59、3.16。 MATR1合成实验中，w=0的FID最低（0.405），w=6时Recall降至0.398；随机森林测试RMSE在w=2时最低，为104±6，而使用真实数据训练的BatteryML随机森林对照报告值为168±9。 原PDF表3使用mean下标std记法，纯文本抽取粘连为1046/1689；必须按均值和标准差分开读取。 文中没有报告针对网络组件或训练目标的系统消融；合成部分对引导强度进行了比较。 文中数值为作者报告的结果，不是本次独立复测。



**作者限制：** 作者指出，若要深入理解退化机制并据此制定电池设计、生产或化成对策，数据驱动的DiffBatt需要与物理模型连接，或扩展以纳入电池设计和工艺参数变化。



**主控接纳限定：**



- 仅接受arxiv2410.23893v3完整主文+内含附录阅读审查；独立子代理显式Luna/high，运行时模型未独立内省，非controller自动回执。

- root与独立review均实际查看PDF7/9页，RF对照168±9、w2=104±6，旧1046/1689为文本粘连错误，旧PASS和旧note保留inactive。

- SOH RMSE必要时reference补零匹配预测长度；不静默替换为公共长度指标。

- 前100循环条件生成完整SOH曲线并由阈值推寿命；非逐origin动态RUL或已证as-of/ID合法。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / 第2.2节 架构；第6页 / 第3.1节 RUL预测；第10页 / 第5节 结论与展望



**主文接纳记录：** [literature/accepted/P35_maintext_successor_v6.json](../../literature/accepted/P35_maintext_successor_v6.json)。

**精读笔记：** `literature/revisions/successor_20261017_v6_batch07/P35_full_read_v3_root.json`；SHA256 `5de495ae36a7dbb40d44f045e7c9f5b067226a81db1afc11bb28a47618392e39`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2410.23893v3)；[full_text_candidate](https://arxiv.org/pdf/2410.23893v3)。



<a id="p36"></a>

## P36｜Predicting Battery Lifetime Under Varying Usage Conditions from Early Aging Data



**研究对象与方法：** 研究提出面向不同充放电倍率和放电深度条件的早期电池寿命预测方法。方法从周期性参考性能测试中提取降解相关特征，结合弹性网回归或分层贝叶斯模型预测寿命。



**实验设置：** 作者在恒温实验室条件下对商业 NMC/石墨软包电池进行循环老化，以每周参考性能测试获得容量和电压数据，并按测试条件组划分训练集与测试集。



**精读结论／作者结果：** 论文报告的测试结果显示，分层贝叶斯模型在低 DoD 外推测试集上优于相同特征数的弹性网模型。加入第三个特征 DoD 可改善训练及高 DoD 测试结果，但使低 DoD 测试误差上升。



**关键结果细节（完整条目另见证据JSON）：** 两特征退化信息弹性网模型在高 DoD 测试集的 RMSE 为 3.0 周、MAPE 为 16.0%；低 DoD 测试集分别为 7.8 周和 24.4%。 两特征分层贝叶斯模型对应为 3.1 周、16.9%，以及 7.3 周、21.8%。 加入第三个特征后，弹性网模型低 DoD 测试 MAPE 上升至 33.0%，分层贝叶斯模型上升至 24.1%；分层贝叶斯模型仍较能抵抗过拟合。 上述是论文报告的结果，不是本项目独立实测。 作者还指出，常用的放电容量差特征未能充分解释该数据集中电芯寿命差异。  正文引言还报告：仅使用前5%老化数据时寿命预测MAPE为22%；最多使用全寿命数据的15%时，同分布测试集平均MAPE为15.1%、RMSE为2.8周（主文第4页）。



**作者限制：** 作者自述的主要限制是数据来自受控实验室中的恒定循环条件；真实应用中的电池数据可能更复杂、噪声更大，增加特征提取和寿命预测难度。



**主控接纳限定：**



- 使用部分早期寿命数据预测总寿命，不能自动称动态RUL。

- 低DoD外推/加入DoD误差恶化是作者报告，不是本项目实测；是否严格负迁移需独立设定。

- SI未提供；代码DOI原文存在不等于代码内容、实现对应或复现已核。



**精读来源锚点：** 第5页 / 结果与讨论：早期使用数据的预测特征提取与寿命预测方法；第16页 / 实验程序：电芯与测试仪规格、老化测试设计；第12页 / 结果与讨论：选定模型在高、低 DoD 测试集上的预测误差（表 2）；第16页 / 结果与讨论：研究限制及未来动态循环数据



**主文接纳记录：** [literature/accepted/P36_maintext_successor_v2.json](../../literature/accepted/P36_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v2/P36_full_read_v2.json`；SHA256 `8d557a908030fe819650a6d2de4c781c8eb33e4fc77db692a6c00304f73e070a`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2307.08382v2)；[full_text_candidate](https://arxiv.org/pdf/2307.08382v2)。



<a id="p38"></a>

## P38｜Charging Phase Health Indicators for Battery State-of-Health Estimation: A Systematic Comparison of CC, CV, and Combined Approaches under Cross-Battery Validation



**研究对象与方法：** 研究以NASA老化数据集中的四个LiCoO₂体系18650电芯为对象，比较CC阶段时长、四种CV阶段健康指标及其组合对SOH估计的作用。采用LightGBM建模，并用SHAP分析指标贡献。



**实验设置：** 研究使用四个电芯的逐循环充放电数据，主要以留一电池交叉验证评估跨电池泛化，并报告随机打乱的五折交叉验证作比较。



**精读结论／作者结果：** 作者报告CV与CC时长组合的LOBO RMSE/R2最好，但MAE并非最优；标准随机五折的误差低于LOBO。



**关键结果细节（完整条目另见证据JSON）：** 指标集比较中，CV-only为RMSE 4.69%、MAE 3.69%、R² 0.796；仅CV/CC比为5.55%、4.14%、0.715；仅CC时长为4.09%、2.72%、0.845；CV加CC组合为3.68%、2.87%、0.874。 跨模型比较中，LightGBM的LOBO RMSE为4.63%、R² 0.801；XGBoost为4.65%、0.799；CatBoost为5.07%、0.761；随机森林为5.08%、0.760。 正文另报告LightGBM按四个LOBO测试电池汇总RMSE为4.69±1.26%、MAE为3.69±1.03%、R²为0.769±0.110；该汇总与跨模型表中的LightGBM结果及指标集表中的CV-only结果不同，来源未进一步解释这些汇总口径差异。 标准五折中LightGBM RMSE为2.30%，而表9跨模型平均RMSE由2.22%升至4.86%，作者报告增加119%。 SHAP分析将CV/CC时长比列为最重要指标。 阈值敏感性分析中五种电压阈值均识别出623个有效循环，LOBO RMSE为4.121%至4.300%，R²为0.793至0.817。 以上为来源报告值，并非本次独立复算或实测。  表7具体显示，仅CC时长的MAE2.72%优于组合2.87%；组合只在该表RMSE/R2上最好，不能称全指标胜出。



**作者限制：** 作者指出数据和协议范围有限，跨电池泛化存在挑战；跨数据集和真实运行环境验证仍待开展。



**主控接纳限定：**



- 1.86Ah为作者observedmax定义非厂家额定2.0；统计人口/训练折/asof未证。

- 第4页>100%归属B0006/7与表1 B0018上限104.6%矛盾；第5页tau拟合636/637与提取623/630口径差异均保留。

- 组合指标只RMSE/R2最佳，CC-only MAE2.72优于combined2.87；各表LOBO汇总口径差异未解决。

- early-to-late负R2与仅单化学/单NASA同协议范围保留；5%维护工程判断与作者计时非真实安全/BMS部署。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第5页 / 3.3 健康指标提取；第5页 / 3.4 机器学习模型与验证；第7页 / 4.4 指标集比较；第11页 / 5.5 局限性



**主文接纳记录：** [literature/accepted/P38_maintext_successor_v6.json](../../literature/accepted/P38_maintext_successor_v6.json)。

**精读笔记：** `literature/revisions/successor_20261017_v6_batch07/P38_full_read_v4_root.json`；SHA256 `9572b04b8a7d9896de8899ff77a1c92253f52da42f6f9681c45e5ef3e2b4ad6e`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2607.23482v1)；[full_text_candidate](https://arxiv.org/pdf/2607.23482v1)。



<a id="p39"></a>

## P39｜Knowledge-Aware Modeling with Frequency Adaptive Learning for Battery Health Prognostics



**研究对象与方法：** 研究对象是锂离子电池容量估计与剩余使用寿命（RUL）预测。K ARMA将变分模态分解、频率自适应双流网络和基于经验退化函数的粒子滤波结合，用数据驱动预测校准知识模型。



**实验设置：** 作者在NASA与CALCE锂离子电池数据上报告单周期容量预测、RUL相关评估、不确定性分析和预测跨度敏感性分析。



**精读结论／作者结果：** 作者报告K ARMA在所测NASA和CALCE电芯上整体优于比较方法；移除知识模块的DUAL STR表现略有下降，较长预测跨度的误差增加。



**关键结果细节（完整条目另见证据JSON）：** 单周期容量预测中，作者报告NASA平均MAPE为0.284%，CALCE平均MAPE为0.756%；并在摘要和结论报告，相对比较算法的平均误差降幅分别为50.6%和32.6%。 这些是论文报告值，并非本项目复算。 消融比较显示，DUAL STR在NASA的部分电芯上误差高于K ARMA；作者报告其余三节电芯的MAE增加4.1%、5.1%、0.4%，RMSE增加8.1%、3.7%、13.3%。 RUL相关表格中，NASA上K ARMA平均MAE为0.0040，CALCE在不同SP设置下报告的平均MAE由SP=100时0.0067降至SP=300时0.0044。 DUAL STR预测跨度结果显示平均MAPE随跨度增大：NASA从1周期的0.284%升至15周期的1.497%，CALCE从0.756%升至2.473%。 作者还报告95%区间及电芯间表现差异；这些结果限于所述数据与协议，不能单凭拟合指标推断独立泛化能力。  表II表头明确MAE/RMSE为EOL周期处容量误差、乘10^-2尺度，NASA均MAE0.0040不能当循环数Time-MAE。 表III才列剩余循环Actual/Pred/AE及95%CI；NASA的SP为50/70/90，CALCE为100/200/300。 表III举CS35 SP100 actual540/pred541；相应图4(b)写SP100、EOL641、RUL591，EOL-SP应为541而非591；CS36/37/38图内EOL639/713/759与RUL589/663/709也相差50（若SP100分别应为539/613/659），后者与表III对应pred一致。 图表差异保留，未自行更正作者结果。 第9页DUALSTR平均MAE0.0055等叙述还与表II的MAE/RMSE列需区分：表II平均MAE0.0041、RMSE0.0055；不把列混用升级为本项目测量。



**作者限制：** 作者指出电芯间表现有显著差异，噪声较大或退化模式复杂时误差会增大；并将适配不同化学体系、实际部署和轻量化列为后续工作。



**主控接纳限定：**



- 只接受arxiv2510.02839v1完整12页主文阅读审查；独审v3 NEEDS保留，v4仅对唯一PSO方法补句增量核验，全文与视觉阅读在同审查任务已实际完成。

- NASA目标电芯SP前容量也训练，非zero-shot；VMD/PSO归一化窗口asof与调参边界未证。

- 表II为EOL-cycle容量误差×1e-2非cycles TimeMAE；表III给cycle RUL。

- 图4(b)CALCE SP100标EOL641/639/713/759及RUL591/589/663/709；EOL-SP及表III pred为541/539/613/659，图标签多50，源矛盾保留。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / II. K ARMA: Methodology；C. A Dual-Stream Frequency-Aware Model；第6页 / III. Experimental Study；A. Experiment Setup；第9页 / III. Experimental Study；B. Comparison Study；2) RUL Prediction；第11页 / III. Experimental Study；D. Forecast Horizon Sensitivity Analysis



**主文接纳记录：** [literature/accepted/P39_maintext_successor_v6.json](../../literature/accepted/P39_maintext_successor_v6.json)。

**精读笔记：** `literature/revisions/successor_20261017_v6_batch07/P39_full_read_v4_root.json`；SHA256 `ddb3406c931121679b58e80f837af4206818212740b9b1d24b620c648aa892b4`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2510.02839v1)；[full_text_candidate](https://arxiv.org/pdf/2510.02839v1)。



<a id="p40"></a>

## P40｜Conformalized Transfer Learning for Li-ion Battery State of Health Forecasting under Manufacturing and Usage Variability



**研究对象与方法：** 研究对象是具有制造差异和使用条件差异的锂离子电池健康状态（SOH）预测。作者提出将LSTM时序预测、基于最大均值差异（MMD）的迁移域适配和保形预测（CP）不确定性量化结合起来的框架。



**实验设置：** 实验使用PyBaMM生成的合成NMC石墨电池老化数据；评估模型在源域和目标域的SOH预测表现，并在目标域考察CP区间覆盖率。



**精读结论／作者结果：** 作者报告，MMD迁移适配改善了目标域预测表现；经源域校准的CP区间在目标域达到高于设定值的经验覆盖率。正文还比较了微调迁移与不迁移基线。



**关键结果细节（完整条目另见证据JSON）：** 源域LSTM的RMSE为0.083%、R²为0.999；直接用于目标域时RMSE为1.637%、R²为0.833。 微调方法在目标域的RMSE为1.591%、R²为0.843，作者报告误差相对不适配基线减少2.81%。 所提迁移方法在目标域的RMSE为0.781%、R²为0.962；作者报告相较基线预测误差降低超过50%。 仅用源域留一批次交叉验证选出的λ为0.236；使用目标标签网格搜索得到的理想比较值为0.192，前者表现仅略逊于后者。 CP目标域经验平均覆盖率为98.8%，平均区间宽度为4.08%，非符合性分数为2.04%。 这些均为论文报告的数值，不是本项目实测。 正文未报告独立组件消融实验；表中提供的是不同迁移设置之间的比较。



**作者限制：** 作者指出，当前证据来自合成模拟，尚待实验老化数据验证；测量噪声和现实世界变异尚未被充分覆盖。



**主控接纳限定：**



- 方法为单步SOH预测，非动态RUL数值结果；数据是30Ah NMC合成老化，A123校准是模型既有背景。

- 第6页式6使用历史SOH与倍率，第5页截断后可用信息论述仅明确倍率一直可测。截断后SOH输入由真实值或递归预测得到的实施未证，不可自动称严格online/as-of合法长期预测。

- 第8页CP校准为每源域批次10电芯，与源域同分布及工况模拟生成。第10页98.8%是本合成目标域经验覆盖，不证任意域移位的分布无关保证。

- 表3确认0.083/1.637/1.591/0.781%等RMSE；第9页明确常规fine-tuning为dense-layer重训。本项目未运行或复现本模型。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第6页 / 方法：迁移学习框架与联合优化（3.2.2）；第4页 / 方法：合成老化数据生成与预处理（3.1）；第9页 / 结果与讨论：目标域迁移适配效果（第4节）；第11页 / 结论与未来工作（第5节）



**主文接纳记录：** [literature/accepted/P40_maintext_successor_v3.json](../../literature/accepted/P40_maintext_successor_v3.json)。

**精读笔记：** `literature/revisions/successor_20261016_v2/P40_full_read_v2_root.json`；SHA256 `c06dba50b8cbf8e4b7b3bb1cba6483893c92b3b3080764bfbfd9d996a3cab846`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2603.24475v1)；[full_text_candidate](https://arxiv.org/pdf/2603.24475v1)。



<a id="p41"></a>

## P41｜Real-Time State-of-Health Estimation and Online Degradation Prognosis from Partial Battery Discharge Using Physics-Informed Neural Networks



**研究对象与方法：** 研究用部分放电曲线估计锂离子电池健康状态（SOH），并据此在线拟合退化趋势、识别膝点及估计寿命终止（EoL）。方法将分段特征驱动的神经网络与广义 Verhulst 退化动力学约束结合。



**实验设置：** 实验使用122只电芯的数据，按电芯留出10只作验证，其余用于训练和分析；比较充电与放电信息，并在8个放电电压段上评估PINN与FNN。



**精读结论／作者结果：** 放电数据在膝点和EoL预测的比较中均优于充电数据；8个放电段的PINN均优于FNN，验证集SOH预测MAPE均低于4%。验证集上选择连续34次预测落在置信区间外作为膝点报警阈值。



**关键结果细节（完整条目另见证据JSON）：** 充放电比较中，三类模型对膝点和EoL预测的放电MAPE均低于充电MAPE，因此后续实验采用放电数据。 XGBoost电压段分类器在验证集准确率为0.99。 各放电段的PINN在MAPE、RMSE和R²三项指标上均优于FNN；第6段表现最好，表格报告MAPE 1.543%、RMSE 0.016、R² 0.952，且只保留VQ曲线斜率这一特征。 正文另将该段MAPE写为1.52%，数值存在报告差异。 第2、3段相对较弱，但MAPE仍低于4%。 膝点阈值敏感性分析取γ=1至70，验证数据上平均KPPE最低时γ=34。 第二退化阶段的预测受电芯寿命差异影响，作者称此阶段预测不如第一阶段准确。 以上结果来自同一数据集的留出验证电芯，不构成独立外部泛化证据。



**作者限制：** 作者指出仍需研究分段数量与长度、异质数据和不同电流工况下的表现、跨电芯类型参数优化、增加物理变量，以及跨电压段输入时的多模型组合。



**主控接纳限定：**



- SOH监督为Kneedle放电弯折点容量，作者说明非通常SOH；Verhulst经验近似/同cell参数假设不当异质泛化。

- 第8页u先定义1-SOH容量loss随后称网络输出u代表SOH，实际代码符号未核；u0通常10%、K20%-100%为作者范围。

- 同10电芯前称validation、结论称testing，gamma34在该集选择，不构成未调参独立finaltest。

- 表4segment6 MAPE1.543%与相邻正文1.52%差异保留；root实际看PDF8/13页。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第8页 / 2.2. SOH estimation；第4页 / 2. Materials and Methods；第13页 / 3. Results；第17页 / Future work



**主文接纳记录：** [literature/accepted/P41_maintext_successor_v6.json](../../literature/accepted/P41_maintext_successor_v6.json)。

**精读笔记：** `literature/revisions/successor_20261017_v6_batch07/P41_full_read_v4_root.json`；SHA256 `5af2e55ddbf3302dc7c0e8872e1f9fe13fa82ca465a808886cdd17dd15396f5a`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2608.14764v1)；[full_text_candidate](https://arxiv.org/pdf/2608.14764v1)。



<a id="p42"></a>

## P42｜Continuous ageing trajectory representations for knee-aware lifetime prediction of lithium-ion batteries across heterogeneous dataset



**研究对象与方法：** 研究以隐式神经表示（INR）将电压-容量和容量-循环轨迹表示为连续函数，再提取轨迹形状及拐点相关特征，用于电池老化分析和寿命预测。



**实验设置：** 将电流、电压、温度记录切分并统一为循环级数据，容量低于Q0的80%（第15物理页称initial rated capacity）时定义为寿命终点；预测实验按电芯划分训练与评估数据，并以最初5、10或20个循环作为早期输入窗口。



**精读结论／作者结果：** 作者报告早期RUL预测随输入循环数增加而改善，INR在所列窗口下略优于线性回归和随机森林；拐点循环与寿命终点呈较强正相关。完整轨迹特征消融的近乎完美表现被作者解释为包含终点信息的上界结果。



**关键结果细节（完整条目另见证据JSON）：** 表列INR在5、10、20循环输入下的RMSE分别为1.68、1.47、1.25，R²分别为0.87、0.90、0.93；随机森林对应RMSE为1.72、1.51、1.28，线性回归为2.05、1.89、1.62。 ISU-ILCC统计中，EOL与拐点循环的Pearson相关为0.836、Spearman相关为0.745；与初始容量的Pearson相关为0.658。 跨数据集表格显示，随机森林在训练/测试数据类型不匹配时误差增大，而Fourier-INR表列误差相对均匀。 各INR架构的容量重建验证误差相近。 消融中，随机森林仅用早期容量特征的RMSE/MAE/R²为2.05/1.54/0.81，加入完整轨迹描述量后为0.15/0.08/0.99；作者指出完整轨迹拐点等特征隐含编码EOL信息，不能视作现实早期预测结果。 表格结果与正文所述样本及循环定义存在需谨慎解读之处，见未核实项。  第18物理页表2邻文称大多数EOL在统一索引8至20，且非完整物理充放电事件；5/10/20输入窗口与该EOL人口的先后、仍存活纳入规则及绝对RUL目标单位未充分交代，不能视作合法逐origin动态RUL证据。  表2 linear regression/5输入的RMSE2.05、MAE1.54、R2.81，恰与表7标为Random Forest early-only的同三值一致，而表2 RF/5为1.72/1.31/.86；两表模型/窗口/人口对应未说明，保留原值，不自行更正或宣称同一实验。  第27物理页表6行列为Recommissioned/Regular/Second-life数据类型，不自动等同NASA/CALCE/ISU三个数据集留一；类型到原始数据及物理ID映射未核。



**作者限制：** 作者自述研究受限于实验室规模公开电芯数据、容量阈值EOL定义、未显式施加电化学约束及不确定性方法缺少完整概率保证；性能也可能受网络架构和优化设置影响。



**主控接纳限定：**



- 文中对ISU-ILCC数据规模的描述不一致：输入数据段称约225个电芯，前文称251个，统计表列251个；可靠性拟合附表又列222个。不同分析的样本筛选和口径未充分解释，无法核实其对应关系。

- 摘要称分析超过250个电芯，但各结果表的纳入样本数不一；各数据集合并分析的具体样本构成无法从现有文字完整核实。

- “harmonised evaluation protocol”及时间交叉验证、按电芯留出和跨数据集训练/测试的具体拆分如何对应，原文未充分交代。

- 摘要和附录对早期5至20循环预测的表述与部分寿命统计及统一循环定义并列后，具体样本和预测目标的对应关系无法仅凭文字核实。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第6页 / 2.1. Implicit Neural Representations；第9页 / 3.2. Implementation details and training setup；第18页 / 7. Results；第32页 / 9. Limitations



**主文接纳记录：** [literature/accepted/P42_maintext_successor_v7.json](../../literature/accepted/P42_maintext_successor_v7.json)。

**精读笔记：** `literature/revisions/successor_20261017_v7_batch08/P42_full_read_v5_root.json`；SHA256 `1d1a10d72820555cc4e3cdfc2c6c75279c9206e25196ed619979eaf761202d84`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2604.16580v1)；[full_text_candidate](https://arxiv.org/pdf/2604.16580v1)。



<a id="p43"></a>

## P43｜A Self-attention Knowledge Domain Adaptation Network for Commercial Lithium-ion Batteries State-of-health Estimation under Shallow Cycles



**研究对象与方法：** 研究对象是商业锂离子电池在浅循环、部分SOC范围且目标域没有SOH标签时的SOH估计。作者提出无监督深度迁移学习网络SKDAN，将有标签全循环源域知识迁移到无标签浅循环目标域。



**实验设置：** 实验使用CALCE与SNL电池数据，构造同数据集不同SOC范围迁移、SNL不同工作条件迁移，以及CALCE与SNL跨数据集迁移。



**精读结论／作者结果：** 作者报告SKDAN在多个浅循环迁移设置中改善估计误差；CALCE消融结果显示多头自注意力对应的变体性能下降最大。



**关键结果细节（完整条目另见证据JSON）：** CALCE全循环到浅循环的单域迁移中，作者报告20%–80%及40%–100% SOC目标相较非迁移模型的RMSE分别按原文记为降低10.76%和12.89%，MAE分别按原文记为降低10.34%和12.41%（表3实际是乘100数值的绝对差，不当相对降幅）；0%–60%因SOH维持较高且域差异较小，改进较小。 表3中RMSE与MAE乘以100。 SNL多工作条件实验报告加入域适配后，各工作条件下估计性能改善。 跨CALCE/SNL实验表4中，SKDAN在所列八种迁移设置下的RMSE均低于Nonad-SKDAN。 消融在CALCE的20%–80%与40%–100% SOC范围进行，各模型测试10次；去除多头自注意力的Model-1表现最差，作者报告相较完整SKDAN，最大RMSE、MAE及score降幅分别为49.6%、48.6%和47.6%。 去除蒸馏或平滑约束的变体也逊于完整模型。 结论称单域迁移RMSE在2%以内、MAE为1.7%、score为0.45；这些是论文报告值，不是本项目实测。  第17页表3 0%-60%目标下SKDAN-MMD的RMSE1.00/MAE.82略优Ours1.01/.83，score同.15，故正文MK-MMD更优不是每格都成立；只作者均值无显著检验。  第20页作者称score最大降幅47.6%，表5 40%-100% Model1 .81到SKDAN .34算术约58.0%，而20%-80% .82到.43约47.6%；保留文表差异不改作者值。



**作者限制：** 作者将更复杂充放电协议及基于灵活SOC范围充电数据的浅循环SOH估计列为未来工作。



**主控接纳限定：**



- 正文文本未给出逐个物理电芯的训练/测试分配名单，无法核实各迁移实验具体的电芯级划分及是否在所有实验中一致。

- 文中图表和公式的文本抽取存在格式丢失；无法仅据抽取文本完整核实图中全部细节或所有公式符号。

- 正文未报告独立外部现场部署验证、推理延迟或在线系统运行结果。

- 出版版本与该固定arXiv版本是否等同，未报告/无法核实。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第6页 / 2.2. Self-attention knowledge domain adaptation network；第14页 / 3.1.3. Training procedure；第20页 / 4.1. Ablation study；第22页 / 5. Conclusion



**主文接纳记录：** [literature/accepted/P43_maintext_successor_v7.json](../../literature/accepted/P43_maintext_successor_v7.json)。

**精读笔记：** `literature/revisions/successor_20261017_v7_batch08/P43_full_read_v5_root.json`；SHA256 `8f297969672b5b52185aa2382677fe0a4fae4fa3320d90ff9e52409e599a82e1`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2304.05084v1)；[full_text_candidate](https://arxiv.org/pdf/2304.05084v1)。



<a id="p44"></a>

## P44｜Federated Battery Diagnosis and Prognosis



**研究对象与方法：** 研究提出HOPE-FED，用联邦自编码器压缩电池特征，再用联邦深度神经网络预测锂离子电池剩余使用寿命（RUL）；训练时客户端本地处理数据、中心端以FedAvg聚合模型参数。



**实验设置：** 作者在Nature Energy与Argonne两套电池数据上进行计算实验，并比较预测误差、长期平均成本率及多种基准方案。



**精读结论／作者结果：** HOPE-FED的绝对平均预测误差在Nature Energy、Argonne HE5050和Argonne NMC532测试集分别为11.3%、13.0%和6.9%；相对年龄周期更换方案，长期平均成本率分别改善38%、21%和22%。



**关键结果细节（完整条目另见证据JSON）：** Nature Energy上的绝对平均预测误差随退化百分位上升而下降；Argonne上未见明确趋势，较高退化百分位的误差为正，作者据此描述为临近失效时略微高估RUL。 相较年龄周期更换，HOPE-FED在三组数据的成本率分别为12.6对20.3、25.7对32.5、20.6对26.5。 NMC532的灾难性失效次数比周期更换多1次，作者同时报告未使用寿命改善。 消融比较中，加入联邦自编码器后，成本率相较无自编码器模型改善24%、19%、14%（Nature Energy、HE5050、NMC532）。 完全集中模型的成本率略优于完全联邦模型；部分联邦与完全联邦的成本率相近。 仅NMC532报告的批次联邦结果显示，5簇和20簇成本率介于集中与联邦方案之间，30簇的成本率略优于二者；附录D称簇数增加、模型趋近完全联邦时预测误差一般上升。 上述均为论文报告的计算实验结果，不是独立复测。  第15-16页称临失效正误差/高估RUL有助防灾难并减少成本；与第11页高估可能unexpected failure、算法2预测RUL降至阈值才触发存在方向张力。 保留作者措辞，不作为高估更安全的证据。  NMC532第17页表1和第30页C3 threshold50成本20.6/预防17/纠正8；第20页表4和5 fully-federated同threshold50为19.1/19/6，unused95.8与unavailable2.2却相同，未解释population/运行差异。 原笔记只述前一组，现并列保留，不选数消解。  第17页无AE改善24/19/14%：Nature16.5到12.6、HE31.9到25.7可对应约24/19%，NMC22.3到19.1约14%；NMC若用表1的20.6则不同，再次显示表口径未闭合。



**作者限制：** 作者提出的后续方向是尝试其他联邦神经网络架构，并在其他类型电池系统上评估；结论没有明确列出局限性清单。



**主控接纳限定：**



- 是否存在独立于所给全文的补充材料文件：未提供，无法核实；给定全文含附录。

- 所有实验随机种子、每个阶段的完整超参数与联邦收敛判据：未报告完整信息，无法核实。

- Argonne数据的RUL失效标签具体定义、实际电芯在训练集和测试集间的划分实施细节及防止同一电芯信息泄漏的流程：未报告到足以核实。

- 长期平均成本计算所用更换成本、灾难性失效成本、服务人员等待时间等具体参数取值：未报告完整信息，无法核实。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第22页 / 7.2 Main Algorithm；第15页 / 5.2 Datasets；第18页 / 5.5 Comparative Analysis: HOPE-FED Approach vs. Major Benchmarks；第21页 / 6 Conclusion



**主文接纳记录：** [literature/accepted/P44_maintext_successor_v7.json](../../literature/accepted/P44_maintext_successor_v7.json)。

**精读笔记：** `literature/revisions/successor_20261017_v7_batch08/P44_full_read_v4_root.json`；SHA256 `c163f03ab5bfaa0d196e46b9a86de6881ff1f7a037399edd3a1a01264eb5ac34`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2310.09628v1)；[full_text_candidate](https://arxiv.org/pdf/2310.09628v1)。



<a id="p47"></a>

## P47｜Dynamic Loss Balancing for Joint SOH and RUL Prediction of Lithium-Ion Batteries via a Rotary SOH-Injected Prior Battery Transformer



**研究对象与方法：** 研究对象是锂离子电池的健康状态（SOH）与剩余使用寿命（RUL）联合预测。RoSIP-Batt使用共享Transformer、旋转位置嵌入、双任务CLS token、逐维门控融合和梯度分离，并将预测SOH作为先验输入RUL回归头；训练时以同方差不确定性加权联合损失平衡任务。



**实验设置：** 实验使用NASA PCoE、MIT-Stanford和HUST三个公开数据集，比较单任务模型与多任务基线，并报告SOH及RUL的MAE；文中还开展组件消融和Huber阈值敏感性分析。



**精读结论／作者结果：** 表中RoSIP-Batt在NASA取得1.994% SOH MAE和19.79循环RUL MAE；在HUST为0.893%和182.56循环。Stanford结果为0.440%和62.85循环，但多项表列基线在该数据集的SOH或RUL指标更低，因此正文所称三个数据集均持续优于基线与表格数值不完全一致。



**关键结果细节（完整条目另见证据JSON）：** NASA上，RoSIP-Batt表列SOH及RUL误差均低于各列基线；相较PLE，正文报告RUL误差降低10.0%。 Stanford上，RoSIP-Batt的RUL MAE为62.85循环，优于Vanilla Transformer的80.19，但高于CNN-1D的41.20、MMoE的49.89和PLE的48.25；其SOH MAE 0.440%也高于CNN-1D、MMoE、PLE和MTAN的表列值。 HUST上，RoSIP-Batt的RUL MAE为182.56循环，略低于MTAN的186.37；SOH MAE为0.893%，与PLE的0.887%接近但更高。 消融结果显示，去掉SOH注入后NASA RUL MAE从19.79升至30.24；去掉梯度分离后NASA SOH MAE升至2.246%、RUL MAE升至27.94；用简单相加替代门控时Stanford和HUST的RUL MAE分别升至83.59和258.06。 作者还报告去掉时间特征在HUST达到0.893% SOH MAE和182.56循环RUL MAE，即该消融配置在HUST反而优于完整模型以外的表列基准陈述。 关于模型大小和计算量，正文叙述与表3数值不一致，具体见无法核实项。  第9页Stanford完整模型RUL62.85不只差于CNN41.20/MMoE49.89/PLE48.25，也差于MTAN59.32；SOH.440亦高于这些模型；HUST SOH.893高于PLE.887，故全数据全指标SOTA主张不获表2支持。 作者值不等于本项目复测或负迁移证明。  第12页称HUST去Chrono最优.893/182.56，恰被表2当Ours；第13页敏感性full config delta10为200.57±32.98，不与表2 182.56±17.81混称同一完整模型。 各数据集选变体和delta的验证/测试隔离未知。  第16页正文模型432.7k/277.1M FLOPs/3.93ms，MTAN59.8k、MMoE143k、CNN比作者多22.2%参数；第17页表3作者320k/14.5M、MTAN1250k、MMoE380k、CNN180k，与文字大小排序和数值均冲突，不能据此确定实际资源或等预算。



**作者限制：** 作者指出，当前方法依赖固定起始SOC、预重采样的256点充电序列，部分充电可能带来序列对齐问题；温度变化也可能造成分布外偏移。作者提出未来研究将纳入等效电路物理约束。



**主控接纳限定：**



- 没有提供独立补充材料；本文之外的补充实验无法核实。

- 正文未明确给出各数据集SOH和RUL标签的完整构造步骤、具体EOL阈值及样本按as-of时点截取的规则。

- 尽管说明按电芯划分，未报告各随机种子对应的电芯名单或完整划分索引。

- 未完整报告基线模型各自的超参数搜索范围、调参预算以及是否采用完全一致的预处理与调参协议。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / 2.1 Probabilistic Formulation and Data Alignment；第7页 / 3.1 Datasets and Technical Parameters；第10页 / 3.4 Benchmark Performance Comparison；第17页 / 4.2 Limitations and Future Physics-Guided Integration



**主文接纳记录：** [literature/accepted/P47_maintext_successor_v7.json](../../literature/accepted/P47_maintext_successor_v7.json)。

**精读笔记：** `literature/revisions/successor_20261017_v7_batch08/P47_full_read_v6_root.json`；SHA256 `d4b6d92397bed6d0fdba79274aaccb1fd993be2e83da3f0ece777bf6eca6f8d2`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2607.18329v1)；[full_text_candidate](https://arxiv.org/pdf/2607.18329v1)。



<a id="p48"></a>

## P48｜Multitask Battery Management with Flexible Pretraining



**研究对象与方法：** 研究面向异构锂离子电池数据的多任务管理，提出柔性掩码自编码器（FMAE），以缺失通道建模和跨片段关联学习支持多种下游任务。



**实验设置：** 实验覆盖电芯级容量与内阻估计、系统级容量估计、电动汽车异常检测和剩余寿命预测；各任务和数据集分别微调、推理，并采用五折交叉验证。



**精读结论／作者结果：** 作者报告FMAE在多项任务上整体表现有竞争力；去除预训练、减少输入通道及RUL输入循环数等比较显示其预训练和缺失通道设计有益，但不同正文表述与具体表格数值应分别看待。



**关键结果细节（完整条目另见证据JSON）：** 电芯级容量估计中，FMAE的平均绝对SOH误差为0.63%，正文报告相较基线降低39.4%至76.8%；内阻估计RMSE为0.53 mΩ。 系统级容量估计平均绝对SOH误差为1.50%；异常检测平均AUROC为0.945。 RUL正文称仅用2个循环的数据时，相较使用100个循环信息的BatLiNet和Discharge模型，RMSE分别提升6.8%和31.0%。 补充表2报告容量RMSE平均值FMAE为1.43%、LSTM为1.68%、RF为2.64%、XGBoost为2.69%；异常检测AUROC平均值分别为94.46%、88.57%、88.47%、59.38%；RUL平均RMSE中FMAE（2 cycles）为69、BatLiNet为74、Discharge为100个循环；内阻估计RMSE为0.53 mΩ，LSTM为0.69 mΩ，CNN为0.81 mΩ。 无预训练对照中，正文报告容量、内阻、异常检测和RUL任务的相对性能增幅分别为15.43%、11.02%、2.83%和16.30%。 缺失数据实验中，FMAE仅用电压通道时与电压松弛特征方法表现相当；人为移除部分系统统计通道后，FMAE仍优于使用全部通道的LSTM。 补充材料也指出特征方法在个别任务可能取得最佳结果。  第19页补充表2 RUL RMSE：MIT1 FMAE2=129，高于BatLiNet117与Discharge116；MIT2=49优于74/98；KIT FMAE2=30而FMAE1=28更优。 平均69/74/100支持作者平均改善6.8%/31.0%，不支持每数据集/每输入配置全胜。 该指标是RMSE非本项目case-equal TimeMAE。  补充表2其他例外：EV6 anomaly DyAD94.05优FMAE85.19；EV6 capacity LSTM1.90优FMAE1.99，MIT2 capacity RF.27/XGB.41优FMAE.47。 表2总Avg1.43来自跨数据集指标平均，正文cell .63和system1.50为平均绝对误差，不能把MAE和RMSE混同。



**作者限制：** 作者没有单列系统性局限章节。文中披露部分数据集元数据因行业隐私原因未知，并排除了不适合相应任务的数据集；更多局限或外部验证范围未报告。



**主控接纳限定：**



- 数据集标签的完整生成规则、标注质量及其在训练/验证/测试间的具体可见性未报告或无法核实。

- 除文中描述的五折划分外，无法核实所有数据集是否按物理电芯、车辆或电池包身份实现无泄漏划分，也无法核实同一实体片段跨折隔离的细节。

- 所有基线与FMAE的输入信息、调参预算及计算资源是否完全公平一致，未报告或无法核实。

- 未报告统计显著性检验；图表中误差或波动的统计含义仅按原文所述呈现。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第4页 / 2 Flexible Pretraining for Heterogeneous Battery Data；第23页 / Supplementary Note 1: Experiment Setup；第19页 / Supplementary Table 2: Overall results of FMAE compared with baselines across different datasets；第18页 / Supplementary Table 1: LiB systems datasets description and metadata



**主文接纳记录：** [literature/accepted/P48_maintext_successor_v7.json](../../literature/accepted/P48_maintext_successor_v7.json)。

**精读笔记：** `literature/revisions/successor_20261017_v7_batch08/P48_full_read_v4_root.json`；SHA256 `59dd66c83ed4c803d71793ca93c12dd68ec66df013506ce4a7c22e1cc5e9f9b4`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2509.01323v1)；[full_text_candidate](https://arxiv.org/pdf/2509.01323v1)。



<a id="p49"></a>

## P49｜A Lightweight Transfer Learning-Based State-of-Health Monitoring with Application to Lithium-ion Batteries in Autonomous Air Vehicles



**研究对象与方法：** 研究对象是自主飞行器（AAV）锂离子电池的健康状态（SOH）估计。论文将SOH定义为特定循环的最大可用容量与标称容量之比，并提出构造式增量迁移学习方法CITL，利用源工况的有标签放电电压数据、目标工况少量有标签数据及目标工况无标签数据建立轻量目标估计器。任务是SOH估计，不是剩余寿命（RUL）预测。



**实验设置：** 实验使用现实飞行任务中采集的AAV电池数据，以不同电池/工况之间的迁移任务评估SOH估计，并报告模型训练、测试表现及嵌入式部署指标。



**精读结论／作者结果：** 作者报告SOH迁移结果和消融数值；其总体胜出主张、统计口径与消融比较对象存在下列原文冲突，均不构成本项目验证或性能验收。



**关键结果细节（完整条目另见证据JSON）：** 作者表III平均CITL SOH RMSE.61%、training4.80s/testing.57ms/L40.39；以下17/20和改善为作者主张，存在明确比较例外及数值串问题。  第11页正文实际列6个百分比83.73/61.15/28.24/57.34/87.70/57.34，却列5个baseline；摘要列5值83.73/61.15/28.24/87.70/57.34。 保留原串，不把六值自行压缩映射成五值；表III均值0.61对4.96的算术改善约87.7%，不是项目测量。  作者称17/20任务准确度和速度同时优于所有方法；第10页表III至少4个RMSE例外：B2→B5 DDAN.72<CITL.92，B5→B2 MMD.95<CITL1.40，B5→B7 AS³ LSTM RMSE 0.69<CITL 1.05，B7→B5 AS³ LSTM RMSE 0.44<CITL 0.75。 原文17/20保留为作者主张，不当核实全表胜数。  第11页节点图6：first10 TLtasks、CITL每task取10次重复中最低error试次，而MMD-LSTM不同hidden sizes另训再报average；这是被选择的机制曲线，不是公平重复均值/确认generalization。 其文字还提B3→B1，不在表III前10任务清单；第12页称B2→B5与B5→B3达到Lmax200，而表III平均L101.65/92.70，不能混成相同run。  表IV基线61.22/onlystructural7.07/withoutmanifold1.12/full.70。  第14页消融文字称对Baseline和without manifold改善98.86%与90.10%，但表IV .70对7.07（only structural risk）才约90.10%，.70对1.12（without manifold）为37.50%，同页后文也写37.50%。 明确比较对象冲突，不能把90.10当已核实无manifold增益。



**作者限制：** 正文未见作者明确列出的自述局限或未来工作清单。实验结论限于论文所述数据、迁移任务及设置；若干复现和拆分细节未报告，不能据此推断其处理方式。



**主控接纳限定：**



- 目标测试样本涵盖全部目标循环的具体样本索引、与训练样本的重叠情况及其评估实现无法核实。

- 物理电池ID级拆分、as-of归一化及任何潜在跨循环数据泄漏控制方式未报告。

- 数据样本总数及各迁移任务训练、半监督训练、测试样本的完整数量明细未报告。

- 不同基线的调参搜索空间、各自预算分配及是否完全一致的调参公平性无法核实；文本只报告100次贝叶斯优化及相同20次随机试验。

- 其余限定及未核实事项见结构化证据，未因篇幅省略而视为已解决。



**精读来源锚点：** 第6页 / III.B Target Estimator with CITL；第10页 / IV.A Experimental Setup；第13页 / IV.F Ablation Analysis；第15页 / V. Conclusion



**主文接纳记录：** [literature/accepted/P49_maintext_successor_v7.json](../../literature/accepted/P49_maintext_successor_v7.json)。

**精读笔记：** `literature/revisions/successor_20261017_v7_batch09/P49_full_read_v3_root.json`；SHA256 `da69567141890de2f665c8ee5f772ad5d00e441fe0758387daa5c3434da699cd`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。

**原始目录的来源入口（版本限定见上）：** [metadata](https://arxiv.org/abs/2512.08512v2)；[full_text_candidate](https://arxiv.org/pdf/2512.08512v2)。



<a id="p51"></a>

## P51｜Physics-informed neural network for lithium-ion battery degradation stable modeling and prognosis



**研究对象与方法：** 研究对象为锂离子电池健康状态（SOH）估计。作者提出物理信息神经网络，将统计特征到 SOH 的映射与电池退化动态方程结合，以经验退化和状态空间方程表达退化规律。



**实验设置：** 作者使用四个数据集、387节电池和310,705个样本评估常规估计、小样本学习及跨数据集迁移；常规实验比较PINN、MLP和CNN。



**精读结论／作者结果：** 作者报告PINN在常规估计、小样本及多数迁移比较中表现较好；论文给出与MLP、CNN的模型比较及训练电池数量变化实验，未报告单独移除损失项的消融。



**关键结果细节（完整条目另见证据JSON）：** 常规实验表2显示，PINN在XJTU六个批次的MAPE为0.0070、0.0113、0.0086、0.0071、0.0105、0.0063，RMSE为0.0094、0.0122、0.0100、0.0105、0.0135、0.0097；TJU三个批次MAPE为0.0164、0.0119、0.0080，RMSE为0.0158、0.0132、0.0079；MIT为0.0065/0.0074，HUST为0.0078/0.0087（分别为MAPE/RMSE）。 正文报告四个数据集的平均MAPE依次为0.85%、1.21%、0.65%、0.78%；摘要报告总体MAPE为0.87%。 图4报告各模型重复实验的误差分布，作者称PINN整体误差较小且稳定。 小样本表3中，随训练电池数量由1增至4，三种模型误差总体下降；作者称PINN在各任务和设置下结果最好，并指出PINN仅用1节电池训练的表现可与MLP、CNN用3至4节训练相当。 跨域表4显示微调优于源域直接测试；作者称仅有1节有标签目标域电池时，预训练后微调优于直接用目标域少量电池训练。 论文还比较了不同训练样本量、网络类型与迁移方案，但未提供逐项移除数据损失、PDE损失或单调性损失的消融结果。 以上均为论文作者报告的实验结果，不是本项目实验。



**作者限制：** 作者自述，现有电池物理模型参数众多且内部参数难以获取，物理模型与神经网络的无缝整合尚缺满意方法；本文方案属于经验退化与状态空间视角的探索，未来可纳入更复杂电化学模型。



**主控接纳限定：**



- 本篇是SOH估计，不能作为动态RUL或剩余寿命性能证据。

- SI未提供；预印本身份未核实；代码来源声明不等于实际运行/复现。

- 本root接纳含明确上述页9补充，不将review PASS当无遗漏。



**精读来源锚点：** 第10页 / Methods—Physics-informed neural network；第7页 / 常规实验协议；第6页 / 结果—SOH估计结果图注；第9页 / Discussion



**主文接纳记录：** [literature/accepted/P51_maintext_with_addendum_successor_v2.json](../../literature/accepted/P51_maintext_with_addendum_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v1/P51_full_read_v2.json`；SHA256 `34a5003ae80b52b42a4b7337c9955239cd78b4eb19df4cd7d94135861f21a581`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。



<a id="p52"></a>

## P52｜Early prediction of lithium-ion battery degradation with a generative pre-trained transformer



**研究对象与方法：** BatteryGPT先用GPT-Small自回归预测电池全生命周期充电运行轨迹，再用监督式SOH估计器将预测轨迹映射为全生命周期SOH，据此识别膝点和寿命终止点（EOL）。



**实验设置：** 作者在MIT数据集上按电芯划分训练、验证和测试，并以不同EPSO设置衡量仅使用早期充电数据的预测。论文还称使用交叉验证、早停和正则化；未提供独立补充材料中的具体基线超参数。



**精读结论／作者结果：** 作者报告BatteryGPT在EPSO=30%时总体优于列出的基线；EPSO=5%时也给出早期预测结果。增加早期数据与性能改善相关，但正文没有提供可核验的组件消融实验。



**关键结果细节（完整条目另见证据JSON）：** 表1在EPSO=30%时报告BatteryGPT的SOH RMSE为0.21%、MAPE为0.14%，膝点误差13个循环、膝点MAPE为2.30%，EOL误差10个循环、EOL MAPE为1.18%。 表中回归基线CNN、LSTM、CNN-LSTM的SOH RMSE分别为6.33%、2.61%、2.63%，MAPE分别为5.88%、2.04%、1.90%；自回归LSTM和Transformer的SOH RMSE分别为6.56%、6.49%，MAPE为5.93%、5.73%，且表中膝点/EOL预测较差或EOL超出范围。 EPSO=5%的BatteryGPT在表1中SOH RMSE为2.56%、MAPE为1.90%，膝点误差−177个循环、MAPE为31.33%，EOL误差−21个循环、MAPE为2.49%。 摘要报告EPSO=30%时SOH变化RMSE为0.213%、膝点和EOL MAPE分别为2.30%和1.18%。 正文还报告EPSO从5%增至30%时性能改善，但不同段落给出的改善百分比不一致：第3页为SOH 91.80%、膝点92.6%、EOL 54.61%；第8页为SOH 91.80%、膝点92.02%、EOL 52.61%。 这些是论文报告的结果，不是本项目实验。 图4、图5的定性比较称GPT-Small预测误差整体更集中、趋势跟踪较好，但后期各方法误差范围均增大，电流预测改善较不明显。 正文没有报告去除GPT-Small或SOH估计器等组件的消融对照。



**作者限制：** 作者自述的主要限制是可用LIB退化数据规模有限、计算能力受限，因此无法充分探索更多电池状态数据及更大模型带来的潜在性能提升。



**主控接纳限定：**



- 独立SI未提供，训练/验证/测试拆分措辞及不同段落百分比差异保留。

- 0.001到0.0001与rising方向矛盾不代替作者推断schedule。

- Zenodo17420674/17420675正文与参考文献冲突未核；当前部分源码可获取，未执行或复现。

- 发表版主文接纳不等于创新、完整复现或动态RUL合法评测。



**精读来源锚点：** 第3页 / Results—Overview of the methodology；第10页 / Methods—Training Setting of BatteryGPT；第7页 / Results—Table 1 and performance comparison；第8页 / Discussion



**主文接纳记录：** [literature/accepted/P52_maintext_successor_v2.json](../../literature/accepted/P52_maintext_successor_v2.json)。

**精读笔记：** `literature/revisions/successor_20261016_v1/P52_full_read_v3_root.json`；SHA256 `aebf6ddea5239521ff50fe97c43e5c8fbb804ff827ebdccd435337c112c3912f`。原笔记保留服务器，本次公开其结构化摘要和锚点，不公开论文全文。
