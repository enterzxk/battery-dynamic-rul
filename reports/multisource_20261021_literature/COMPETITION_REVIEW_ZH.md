# 多源动态RUL文献竞争审查与数据协议核对

日期：2026-10-21。范围：2024–2026最接近不规则退化轨迹、连续时间模型、在线状态/寿命更新及首达概率的材料；仅使用出版社/作者/机构一手页面和既有项目审查。未下载原始数据，未训练或读取C4。

## 结论

新颖性边界很窄。常规 Neural CDE + spline 插值已经用于不规则/缺失电池退化采样和未来容量轨迹（BatteryCDE，2025）；Wiener/Gamma 随机退化过程的条件首达时间/寿命分布，以及结合真实车辆多年稀疏数据的可靠性评估也有直接先例（Energy，2025；既有两阶段Wiener、Gamma与在线生存评审）。液态连续时间动力学用于电池在线RUL亦有2026 ESWA高重叠先例，但上一轮只取得官方摘要，公式和数据协议仍未核。不可声称“连续时间建模”“概率RUL/首达时间”“在线RUL”本身是创新。

相对可检验的方向为：A. 高频运行多源信号（电流/电压/温度/吞吐量或操作负载）推动电芯隐状态在运行时钟上演化，稀疏到达的RPT/诊断测量仅在到达时提供观测创新校正；显式校正即时可用容量与长期退化状态，且测试到达时间、测量延迟与query time分离。B. 以该校正后的条件退化路径为输入，给出观测时点条件下、定义清楚的事件RUL分布。若estimand是首个源RPT实测容量阈值事件，则T定义为首个满足阈值的源RPT stop时间，是按该定义精确观测的事件时间；没有“检查间区间删失似然”这一创新。若另行研究连续潜在物理阈值首次穿越，才可能在最后一次未越阈与首次越阈测量之间构造区间删失，但这依赖路径连续/单调性与测量误差等假设；容量回弹时，仅凭两端above/below不能约束首次穿越，因为可能先越阈再回弹。不得为引入区间似然而暗中更换estimand。未知停止时点/原因仍保留outcome status unknown；已定义的源观测事件不得被更换为潜在EOL。B单独作为“轨迹分布+FPT”会与现有工作重叠，必须由实际不规则观测到达/as-of更新、测量回弹与明确事件语义的处理能力构成贡献，并实证超过动态HGB强基线。以上是候选机制差异，不是首次性认定。

## 高相关竞争矩阵

| 工作 | 输入许可与目标 | 方法/核心机制（已核范围） | 假设与评估协议 | 与本候选重合 / 尚未回答 |
|---|---|---|---|---|
| Zhang et al., ESWA 2026, [DOI 10.1016/j.eswa.2026.133786](https://doi.org/10.1016/j.eswa.2026.133786) | 官方摘要称电池公开数据；目标可靠实时RUL | Wiener drift/diffusion + liquid recurrent continuous-time network，联合优化及online refinement（摘要信息） | 多个公开电池数据实验；全文公式、前缀输入、到达/查询时刻、EOL/FPT和评估拆分均**unverified** | 与连续状态+随机退化+在线RUL高度重合；必须优先取得全文。本文不能由摘要推断“检查到达更新”或概率校准做法。出处为Elsevier官方摘要，DOI页面/摘要。 |
| Q. et al., **BatteryCDE**, IEEE TTE 11(4), 2025, [DOI 10.1109/TTE.2025.3547740](https://doi.org/10.1109/TTE.2025.3547740) | 电池容量退化序列，强调不规则采样与缺失；目标未来容量估计与跨电池迁移 | cubic-spline 连续数据路径；两级 neural CDE（特征/周期注意力，再建模差分关系） | IEEE官方摘要明确缺失率最高50%、预测跨度100 cycles、跨电池迁移；所查官方IEEE页面受机器人拦截，公式/数据集/拆分为**unverified** | Neural CDE、spline填补、长程容量预测和缺失鲁棒均已覆盖。没证明RUL首达、观测到达语义或诊断/RPT条件更新。方法证据只用官方IEEE元数据/摘要，不能补充未见全文细节。 |
| Li et al., *Energy* 317 (2025) 134663, [DOI 10.1016/j.energy.2025.134663](https://doi.org/10.1016/j.energy.2025.134663) | 25辆公交4年运营数据；BMS稀疏采样、温度/充电率变化、随机充放电；目标容量轨迹、剩余循环、个体/车队可靠性 | available-capacity温度/倍率修正；趋势提取+rainflow重建等效全循环容量轨迹；Gamma过程+Gibbs采样+转折点检测，估计达到指定循环的PDF与车队可靠度 | 论文官方全文检索片段显示§3为数据、容量计算/轨迹/模型/参数估计，§4结果；摘要报告25辆、4年及容量误差。精确观测切分、Gibbs先验与阈值/删失细节需拿全文逐式核验 | 覆盖真实运营稀疏数据、容量轨迹、不确定性和首达寿命。候选A仍可区别为高频运行信号驱动的在线隐状态传播+RPT到达校正；候选B仅凭FPT PDF并无新颖性。出版社ScienceDirect全文页面的正文检索内容、摘要/Conclusion（当前打开受403，精确公式页码待核）。 |
| “An interpretable online prediction method for RUL of lithium-ion batteries,” *Scientific Reports* (2024), [DOI 10.1038/s41598-024-63160-2](https://www.nature.com/articles/s41598-024-63160-2) | NASA B5/B6/B7多种操作模式下健康因子；目标在线RUL并解释容量回弹 | 4项HI + SVR/GPR/UKF + SHAP；容量预测GPR，并把Gaussian non-white noise N加入状态空间表征较高频capacity regeneration；报告lower prediction CI与upper bound | Nature全文/PDF检索文本提及不同B5/B6/B7截止电压2.7/2.5/2.2 V；结论RMSE<4%、最大绝对误差5；精确前缀和split须对照全文方法/表格 | 已有在线SVR/GPR/UKF及再生/区间处理，单纯在线SOH/RUL或容量回弹建模不是新。尚未看到RPT事件间隔/缺测到达/区间删失的事件似然。Nature §§Methods/Results，全文。 |
| Two-phase hybrid deteriorating LIB RUL using Wiener process, IEEE Access (2024), [DOI 10.1109/ACCESS.2024.3374776](https://doi.org/10.1109/ACCESS.2024.3374776) | 单体/异质单元退化与变点不确定性；目标寿命及RUL | 两阶段Wiener退化过程、随机效应、转折点状态不确定性，导出first-passage lifetime/RUL解析解 | IEEE官方摘要明确FPT解析解；数据和在线稀疏检查协议未由摘要核验 | 随机退化FPT已有较早先例，不能把其作为候选B的首创依据。主源只核官方摘要/DOI，不对公式与实验补猜。 |
| EntroLnn, ACM SAC’26 / arXiv:2601.06195 (2026), [官方HTML](https://arxiv.org/html/2601.06195) | MIT-Stanford 124 LFP cells；基于温度和容量健康信息做SoH/CFT refinement | 已读§2.1–2.3式(1)–(12)：温度熵/残差修正热生成；dS/dV健康估计；liquid neural network隐状态ODE；前100 cycles初始化，后期约100-cycle滑窗动态LNN延伸容量轨迹 | §§3–4含电池集和SoH/CFT实验，Bat003 2234 cycles；现有摘要/正文核查材料未显示条件首达RUL分布/删失似然 | 连续液态动态、在线轨迹refinement、温度+SOH的组合重叠明显；其目标偏SoH/CFT轨迹，不等价于到达时间建模的在线条件RUL。全文HTML及公式。 |
| MINE-Graph-Mamba, IEEE TIM 74 (2025), [DOI 10.1109/TIM.2025.3635303](https://doi.org/10.1109/TIM.2025.3635303) | 官方摘要：单循环多变量与全寿命特征；SOH与RUL预测 | MINE相关图、图注意力、Mamba两阶段时序编码（摘要） | 全文公式、dataset、前缀/拆分及动态更新未核（unverified） | 架构替换或多变量编码不是科学机制贡献；用户允许信息、观测到达语义未知。IEEE官方摘要/DOI。 |
| RUL-QMoE (2025), [arXiv:2512.23725](https://arxiv.org/abs/2512.23725v1) | 电池RUL概率输出；项目既有冲突报告已读 | 多专家门控组合分位数（式(3),(7)–(14)）形成概率区间 | 细节见项目既有报告，不在本轮重复读；在线观测到达未由已读片段证明 | 分位数概率RUL已有竞争；本轮不要将校准/分布输出泛称创新。既有项目报告 `reports/post_mixture_methods_conflict_20261019_root/RESULTS_ZH.md` §3–4、§5.2–5.5、§6、附录。 |
| NREL **Physical interpretation of early battery life prediction models** (Gasper et al., 2024), [Zenodo DOI 10.5281/zenodo.14285817](https://doi.org/10.5281/zenodo.14285817), [官方代码](https://github.com/NatLabRockies/interpretable_battery_life) | ISU-ILCC原始充/放电QV曲线与cycling protocol；早期寿命预测和物理解释 | Fused Lasso、PLSR对差分曲线建模；作者README明确输入QV、dQ/dV、ΔV/SOC、dΔV/dSOC；工作流：下载RPT/Cycling JSON，process_data生成HDF5，再提取曲线/协议特征 | 官方repo README §开头/Setup/Modeling（行202–231）明确输入和运行流程；Zenodo记录显示zip 858.1MB；详细拆分、时间前缀与具体模型指标应读论文/仓库模型文件，当前不臆测 | 强早期寿命和可解释特征先例；适合作不同观测特征基线/迁移/外部数据解释，不是在线RUL或不规则RPT到达模型。 |

## 数据源与协议边界

**UConn–ISU–ILCC LFP/Gr原始资源**：[UConn官方数据页](https://digitalcommons.lib.uconn.edu/reil_datasets/1/) §Abstract/Description及文件表确认64颗LithiumWerks APR18650M1B、11种条件；大约每3.5天或约100 cycles（随工况）中断cycling执行RPT，RPT测容量且在3个SoC采100秒CC脉冲；cycling与RPT均1Hz，跨度38周；页面把EOL写作80% remaining capacity；CC BY 4.0。associated paper为Nowacki et al., J Power Sources 628, 235813 (Feb 2025), DOI 10.1016/j.jpowsour.2024.235813。页面挂5kB README文件链接，既有核查报告记为403，故具体RPT日历时钟、基准容量分母、cycling/RPT时长、停测与删失、原始timestamp结构仍待核；勿把厂家当前典型/最小容量替代cell-specific EOL分母。数据体量约15.95 GB，不应为本次文献审查下载。

**ISU-ILCC NMC/Gr原始数据（与上项非同一体系/资源）**：官方README（项目本地核查件：`reports/isu_ilcc_metadata_20261020_root/readme_text.json`, pp.2–8, 10–11）明确251颗502030 NMC/Gr电芯，63条件，250mAh标称容量；RPT按cycling 7天进行，groups 20–64另在最初3.5天执行首个早期RPT；RPT含C/5与C/2 full cycles，C/5 discharge用于capacity fade；每cell cycling/RPT分开JSON，带日期时间与Q/V/I/E序列；组20–29第4周RPT不可恢复缺失，部分G25C1/G26C1–C3的23/24周RPT及24周cycling缺失。该信息支持“日历/周期不等间隔RPT+运行原始信号”的候选A可行性，也暴露非随机数据缺口必须保留。此ISU发布与UConn LFP/Gr数据集不得混称。

## 推荐的最小机制区分与后续审查

1. **候选A（优先）**：将老化/容量退化隐状态在真实operating time或累计throughput上连续传播；允许高频运行量作为控制输入；在RPT/诊断真正到达时，只用当时可见的容量/脉冲观测创新校正，并同时追踪测量误差与可逆容量扰动。必须与“仅RPT动态HGB/回归”“状态传播但无RPT更新”“到达时更新但无运行信号”比较；所有输入截到 arrival time，query time单独定义。BatteryCDE不含已核的稀疏到达校正；ESWA是未决高重叠挑战。
2. **候选B（有条件）**：在A产生的后验轨迹上导出条件RUL分布，并固定为某一明确estimand。若为首个已观察RPT≤阈值，其事件时间就是该RPT的stop时间，不是区间删失；若目标改为潜在物理EOL/连续路径first passage，须显式列出连续性、单调性/回弹、测量误差及随访假设，并说明其与源观测EOL不同，不能把它包装成原estimand的似然改进。仅报告分布CRPS/覆盖/宽度、尾部高估及按cell宏平均；和动态HGB、静态FPT与直接RUL分位数模型同信息集比较。Gamma/Wiener FPT和RUL-QMoE已覆盖宽泛类别，不可包装为新机制。
3. 需优先取得并核读 ESWA 2026全文的公式、数据、在线更新时间和FPT定义；接着逐式读BatteryCDE及Energy §3–4。再读取UConn挂载README的`week/time`, 容量分母与停止/缺测字段，并从NREL仓库readme后的脚本定位早期前缀和split；这一步是候选A/B协议设计的必要前置。

## 证据清单与限制

- BatteryCDE：IEEE官方页面 `https://ieeexplore.ieee.org/document/10909650/` 与官方摘要检索结果；IEEE页面当前robots拦截，未拿到PDF，方法说明仅限摘要。
- EV real-world Gamma：Elsevier ScienceDirect `https://www.sciencedirect.com/science/article/pii/S0360544225003056`，已检索到正文§1–5结构、贡献、结论段和摘要；直接打开返回403，因此不能宣称完成逐式通读。
- Nature online：官方全文/PDF `https://www.nature.com/articles/s41598-024-63160-2`；在线能力、GPR+SVR+UKF、回弹与数据集在正文/Conclusion可查。
- NREL：官方GitHub README `https://github.com/NREL/interpretable_battery_life` 已重定向到NatLabRockies repo并读至lines 202–235；Zenodo官方记录核authors、文件大小、DOI和说明。
- UConn：官方馆藏 `https://digitalcommons.lib.uconn.edu/reil_datasets/1/` lines 20–44；README内容已由先前官方文件核查保存于项目报告 `reports/isu_ilcc_metadata_20261020_root/readme_text.json`（该README其实对应NMC/Gr ISU资源，不能替代UConn LFP/Gr挂载README）。
- 截至本轮，2026 ESWA全文访问、IEEE BatteryCDE全文访问、EV文章精准模型方程/实验拆分、UConn README核验均未完成；报告将这些明示unverified，不以摘要补齐。
# 全文与代码精读补充（2026-10-21）

本补充仅扩展全文确实可读到的机制、变量与实验设计；不把元数据或摘要包装成全文精读。结构化逐项凭据见同目录 `fulltext_evidence.json`。

## A. NREL作者代码的实际预处理和可用运行信号

NREL/NatLabRockies官方仓库 `data/01_process_data.py` 为ISU-ILCC NMC/Gr数据提供可复用参考实现。JSON在`convert_RPT_to_dict`/`convert_cycling_to_dict`读入并将RPT与cycle起止、Q/V时戳字符串转为`np.datetime64`（源码L24–100）。注意此脚本的输入是已解析的RPT/Cycling JSON；不是从原始仪器文件完成物理数据采集或校准。

代码从RPT构造`Time_days`、充/放电容量、C-rate、Voltage_Max/Min、CV_Time及`Label=RPT`，并从常规cycling记录以真实`time_series_charge.start`和容量序列计算同类运行变量，标记`Label=Cycling`（L101–177, 224–279, 290–339）。单次C/5与C/2两个RPT cycles被展开为两个summary观测；RPT容量直接取相应Q序列末端（L119–137）。CC段电流用电压低于峰值95%截取，CV时间依据充电电压差分最小值的索引计算（L139–177）。因此可复用的运行输入具体有：观测的起始时间、charge/discharge Q、I均值、V极值、通过Qcharge+Qdischarge构造吞吐量、C-rate和循环protocol。原始JSON另包含逐点t/Q/V/I/E，可在别处做点级编码；本表只是高度压缩的周期摘要。

这些细节同时暴露了对动态在线任务不应原样沿用的处理：其对缺失RPT时间用下一段cycling的stop+1秒，若不可用则以下段cycling start−1天回填，并假设一个C/5 cycle固定10小时（L203–223）；cycling缺失时间用相邻start线性插值（L280–285）。这种回填适用于整理和排序但会创造测量时间，不能被当作真实measurement-arrival time或到达时的as-of在线证据。`Equivalent_Full_Cycles`采用RPT0 charge+discharge capacity作分母，随后累计每段充放电throughput（L286–345），重构cycle计数不等于原始精确cycle clock。

曲线层：代码把RPT原始Q(V)按V排序，用`splrep`平滑样条对Q(V)插值，同时导数获得dQ/dV和倒数dV/dQ（L347–409）；放电电压网格3.0–4.18V、充电3.1–4.19V，均1000点（L508–533）；异常负Q尾部被截到零并对应导数置零/NaN（L382–401）。DeltaV/SOC把充放电Q归一到各自最大Q，SOC网格1000点，充电/放电V对SOC插值后相减；对DeltaV应用100点、三阶Savitzky-Golay平滑再求导`dDeltaV_dSOC`（L410–469）。这为signals代理提供了实际可跑通的工程参照：每个RPT需分充/放电、多个C-rate曲线，统一V/SOC网格后获得Q(V)、dQ/dV(V)、dV/dQ(Q)或ΔV(SOC)曲线；缺失段必须保留NaN与原来源ID，不能照搬其剪裁/时间补值后误认为源观测。

`data/02_extract_features_raw_curves.py`以每电芯RPT discharge capacity除以RPT0归一，奇偶拆分C/5和C/2，寻找首个SOH≤0.8的行作为C/5、C/2的80%目标，输出time/week/EFC/cycle（L8–74）；随后`get_interpolated_dataset`取指定周与week0曲线差，默认week=3，V网格1000点、3–4.18V（L76–113、116–145）。仓库README所用feature四种为Q-V、dQ/dV、ΔV/SOC、dΔV/dSOC。`03_extract_cycling_protocol.py`取cycling C-rate中位数、用第1周cycling平均放电容量除以RPT0容量估DoD并计算sqrt(C-rate×DoD) stress（L8–53）。这些早期feature定义能作公平baseline或初始化诊断；要在线更新必须换为prefix截至实际到达的流式摘要并避免利用whole-test-derived全寿命target/grid筛选。

## B. 相关但独立的NMC早期寿命论文：核心方法、协议与结果

**更正对应关系**：Li et al. 2024, *Predicting Battery Lifetime under Varying Usage Conditions from Early Aging Data*, Cell Reports Physical Science 5(4), 101891，[arXiv HTML v2](https://arxiv.org/html/2307.08382)，[正式DOI](https://doi.org/10.1016/j.xcrp.2024.101891)，作者为Tingkai Li、Zihao Zhou、Adam Thelen、David Howey、Chao Hu。这与NREL仓库所对应的Gasper、Prakash、Schaeffer, *Physical interpretation of early battery life prediction models*（[Zenodo 10.5281/zenodo.14285817](https://doi.org/10.5281/zenodo.14285817)）是两篇不同论文；两者与ISU-ILCC NMC/Gr资源有关联，但Li et al.不是该NREL仓库的对应论文。实际读到§2–3和supplementary lines 39–446。目标是整电芯早期 total lifetime，不是反复online conditional RUL。建模X来自RPT week0与week3差值和cycling condition，寿命target用log寿命；RPT为周频、C/2与C/5完整循环，EOL为额定250mAh的80%（摘要/§3）。数据225颗NMC/Gr、多个charge/discharge C-rate与DoD，组级划分：DoD≥40%区间内部train/high-DoD test，DoD<40%全部做OOD test（§2.3）。这避免同protocol组内泄漏，但OOD只在DoD一维领域定义。

有价值的对照证据：传统`var(ΔQ(V))`和寿命相关系数−0.686、解释方差不足；在3.60–3.90V窗口平均增量容量差`mean(dQ/dV_week3−dQ/dV_week0)`相关系数−0.848，文中解释为早期活性材料损失proxy（§2.2，HTML约L115–128）。前向选择在反复5-fold CV中比对最多10特征；2-feature（IC特征+ΔCV time）波动较小，加入DoD平均RMSE略降但方差升高（§2.3 L140–147）。Table 2显示3-feature elastic-net高DoD/低DoD MAPE 15.1%/33.0%，2-feature HBM 16.9%/21.8%，而仅cycling条件模型19.0%/23.7%（§2.4）。这明确了“运行条件+早期电芯健康信号”的交互已被研究，且健康特征加法并非总能提高OOD表现。消融/补充分析发现RPT间隔只有一周时两种DoD test误差显著上升，文中提示跨度至少两周才稳健估退化率；测试周4因测试错误排除（supplementary，约L406–412）。

## C. 在线健康动态与首达/删失：机制重叠审查

1. **两阶段hybrid Wiener电池RUL（IEEE Access 2024，DOI 10.1109/ACCESS.2024.3374776）**：本轮读到IEEE Xplore文章方法页与结论，而非仅摘要。式(2)定义首次越过阈值`T=inf{t:X(t)≥w}`，式(3)定义as-of时刻`tk`之后的RUL首达量；分两阶段线性/非线性Wiener，随机个体漂移/变点时间/变点状态；EM+profile likelihood离线估参、新观测可用后Bayes更新（官方全文第II节及结论）。作者数值实验+电池案例，比较两阶段Wiener与两阶段线性、单阶段非线性，报MSE/AE/RE/TMSE。故“连续随机退化 + 条件RUL FPT + 新观测Bayes更新”在电池已经明确存在。它的结论段把观测称perfect measurement，并指出未来实际监测的measurement variability仍待研究。尚未见其更新只由预定RPT实到达触发与否、RPT缺失导致区间删失的细节；不能声称它一定没有。

2. **容量回弹在线RUL（Li et al., Scientific Reports 2024, DOI 10.1038/s41598-024-63160-2）**：Nature全文搜索/开放HTML文本可核第II节和实验。先从CC充、CV充、CC放、电池温度抽四个HI；SVR预测未来HI，GPR映射到容量；SHAP贡献50%阈值把HI分组，将低贡献HI和Gaussian non-white noise构为状态经UKF更新。式(26)之一为`Cap3=Cap2+Nhat`；Cap2用于较可靠CI下界，Cap3用于回弹CI上界。NASA B5–B7，起始prefix T=70/80/90 cycles、EOL按1.4Ah（B7特殊1.5Ah），比较M1与不含回弹/变换的模型；报告在线RUL AE<5、CI宽度最小约2。RUL通过预测capacity达到阈值，主要是路径/点估计和经验区间，并无明确区间删失似然。该路线已覆盖operando HI+滤波+capacity regeneration，但噪声是人为加进HI的回弹模拟而非latent degradation与观测误差可识别分解；并不是严格RPT源事件定义。

3. **联合纵向/生存一般方法：Shabani et al. 2025 landmark-gradient-boosting**（BMC正文[DOI 10.1186/s12911-025-03205-2](https://doi.org/10.1186/s12911-025-03205-2)）：式(1)目标是在landmark s仍存活、给定截至s纵向观测下预测未来w的存活概率；LGBM每个landmark在风险集拟合，梯度提升生存树；simulation 1线性longitudinal-hazard关联下joint model更好，simulation 2非线性且样本更大/删失更多/landmark更晚时LGBM胜；真实肾移植应用558例有完整生存事件字段、五个landmarks，LMM填补优于LOCF（正文§Methods/Simulation/Results）。它证明“新纵向观测后动态更新生存”一般方法不新，但不是电池/FPT的物理退化路径模型。此为预设landmarks上的批量训练而非随单只电池观测即时Bayes滤波。

4. **联合latent纵向和事件风险：Medina-Olivares et al. STJM** [open arXiv HTML](https://arxiv.org/abs/2311.04008)，以年度/月份为离散时标的mortgage event预测。式(1),(2)把纵向过程和离散事件过程连接到共享随机效应；似然式(6)假设给定随机效应后纵向和事件过程条件独立；实证使用57,258个借款人、2,559,056条月数据、16,239 full-prepayment事件，INLA估计并比较加入时空效应的模型，6个forecast evaluation months；结果表明添加spatial main effects稳定改善，而增加时空交互增益较不确定。它为联合SOH/退化潜状态与生存风险提供标准组件，创新必须超越“共享latent state影响event hazard”。关键局限：离散time event而不是battery continuous first passage，不是周期不定RPT观测；案例非电池。

**竞争边界精化**：候选A“状态随时钟连续传播、运行信号驱动、RPT arrival innovation update”会与连续ODE、Wiener模型的Bayesian更新及在线回弹滤波重叠，需证明运行控制输入与稀疏RPT到达校正的结合带来增益。候选B“轨迹分布+首达”亦已有电池Wiener/Gamma先例。当前首个源RPT越阈事件的时间就是该RPT stop，精确观测而非区间删失；只有改为潜在物理首次越阈才需讨论区间观测，并需显式路径/回弹/测量误差/随访假设。不得偷换estimand作为创新。


## 统计语义校正：源观测阈值事件不是区间删失

本报告前文曾把“首个已观察RPT≤阈值”表述成检查间区间删失事件，这是不成立的。当前源事件定义为首个原始RPT满足Q≤0.20Ah，其事件时间T就是该次RPT的stop时间；按定义，T在离散检查记录上精确观测。首次源观测阈值事件的estimand不应使用区间删失似然，也不能将这点作为候选B的机制新颖性。

只有把目标改为连续潜在物理退化路径第一次越阈时，才可能尝试用最后一次阈值上方与第一次阈值下方观测构造区间。但推断需要额外说明连续路径、单调性/回弹、测量误差与检测机制等假设。尤其有容量回弹时，端点一次above、一次below并不能把“首次”越阈限制在两者之间：路径可能先越阈，之后回弹到阈值上方，再于后续测量重新越阈。此时区间端点对潜在首次穿越并无该简单约束。若研究潜在EOL，必须明确标为新的estimand，不能无声替换源观测EOL。

## 修正：竞争边界中的事件时间语义

前文“候选B”及“竞争边界精化”段落把首个源RPT实测阈值事件称作检查间区间删失，并据此提出候选创新；这属于estimand混淆，现明确撤回。当前事件定义是首个原始RPT满足Q≤阈值，其T就是该次RPT的stop时间，按定义精确观测，不是区间删失。当前源观测EOL下不能以区间删失似然作为机制新颖性。

只有另行把estimand改为连续潜在物理路径的首次越阈时间，才可能讨论最后一次未越阈与首次越阈测量之间的区间；这依赖明确的路径连续性、单调性或回弹机制、测量误差和随访假设。若容量会回弹，端点一次above、一次below也不能约束“首次”越阈：路径可能更早越阈，随后回到阈值上方，再在后续样本越阈。因此不得将潜在物理EOL悄然替换为源观测EOL，也不得把端点包络当作无条件的首次穿越区间。
