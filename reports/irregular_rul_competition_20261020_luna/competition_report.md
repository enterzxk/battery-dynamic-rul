# 不规则健康观测下动态RUL：竞争审查与第二体系可行性
日期：2026-10-20。仅文献竞争与官方数据元数据审查；不含原始数据下载/解码、训练、推理或环境变更。

## 结论
“液态连续动力学+随机退化+在线更新”不能作为创新主张。2026 ESWA官方摘要已描述将Wiener退化过程、liquid recurrent网络与online real-time refinement用于锂电RUL；这是高度重合竞争先例。全文公式和检查到达更新协议未能访问，必须标unverified，不能从摘要推断细节。[Elsevier DOI](https://doi.org/10.1016/j.eswa.2026.133786)

较窄待证问题：操作时钟持续推进、健康测量稀疏不规则到达时，无新测量期间怎样传播条件首达寿命分布，且只在检查真实到达时用创新量更新；容量回弹不能清除已发生首达，检查间失效要保留区间删失语义。此为候选，不是首次性结论。

## 五篇竞争材料

1. **Zhang et al., 2026 ESWA**, “Unified stochastic degradation learning and liquid neural dynamics for reliable real time remaining useful life prediction of lithium-ion batteries,” DOI [10.1016/j.eswa.2026.133786](https://doi.org/10.1016/j.eswa.2026.133786)，官方页称2026-07-30 online / Journal Pre-proof。官方摘要称Wiener drift/diffusion，liquid recurrent连续时间动力学，Transit Search+梯度联合优化和实时在线refinement，多个公开电池数据实验。方法公式、数据集、检查到达协议、首达定义及结果表全文未核；这是最高风险竞争项，需全文优先核验。
2. **EntroLnn 2026**，arXiv:2601.06195，官方HTML列ACM SAC’26 DOI 10.1145/3748522.3779909。[官方HTML](https://arxiv.org/html/2601.06195)。已读§2.1–2.3、§3–4。§2.1式(1)–(6)为温度场熵特征，式(3)用温度残差更新热生成系数；§2.2式(7)–(8)用dS/dV等估SoH；§2.3式(9)–(12)为LNN隐状态连续时间ODE，前100 cycles初始化；后段以约100-cycle滑窗dynamic LNN延伸容量轨迹。MIT-Stanford 124个LFP电芯，Bat003寿命2234 cycles；实验针对SoH/CFT refinement，所读部分未展示条件首达RUL分布/删失似然。在线电池健康更新+液态网络已有先例。
3. **MINE-Graph-Mamba 2025**, IEEE TIM 74, DOI [10.1109/TIM.2025.3635303](https://doi.org/10.1109/TIM.2025.3635303)，IEEE条目日期2025-11-20。官方摘要称MINE相关图+图注意力+Mamba，先编码单循环多变量，再编码全寿命特征预测健康与RUL。全文公式、实验数据、prefix、更新语义未核；不得把改用该架构称核心创新。
4. **Shabani et al. 2025动态生存**, *BMC Medical Informatics and Decision Making* 25:368，[10.1186/s12911-025-03205-2](https://doi.org/10.1186/s12911-025-03205-2)。Methods “Dynamic prediction”式(1)定义landmark后存活概率；boosting式(3)是含事件指示的Cox partial likelihood；按预定landmark风险集拟合，LOCF作纵向基线。模拟30/50/90%删失、五个landmark，另有肾移植数据应用。非电池连续退化模型，但动态生存和按观测时点更新不是新。
5. **RUL-QMoE**：复用项目既有冲突报告（§3–4、§5.2–5.5、§6及附录，式(3),(7)–(14)）；门控凸组合多个分位数构成概率电池RUL先例。项目完整CDF等权混合不是该公式。详见[既有报告](../post_mixture_methods_conflict_20261019_root/RESULTS_ZH.md)，本轮不重读41篇。

arXiv:2503.13558据任务信息已官方withdrawn，排除为主依据。指定Lebesgue DOI 10.1109/JSEN.2026.3723690未核实IEEE主源/全文，unverified，不作方法陈述。

## 候选反证
候选为observation-time-aware条件首达：真实操作时间传播；无测量时不假设获得健康信息；检查到达时才创新更新；输出首达分布；回弹不重置已发生事件；检查间事件按区间删失。先查ESWA全文，不称首次。最小消融：真实不规则时戳vs周期重采样/LOCF；关闭传播vs连续传播；关闭到达创新vs到达更新；回弹重置vs首达吸收；真实vs均匀/延迟时戳。同一事件/信息集下报告条件分布评分/校准、点误差、尾部风险与电芯配对结果。本轮无实验；小样本筛查非显著性或创新证明。

## UConn–ISU–ILCC LFP/Gr元数据
[UConn官方记录](https://digitalcommons.lib.uconn.edu/reil_datasets/1/)列6位作者Benjamin Nowacki、Jayanth Ramamurthy、Adam Thelen、Chad Tischer、Cary L. Pint、Chao Hu；64个LithiumWerks APR18650M1B，11种工况；约每3.5天/约100 cycles（依工况）暂停做RPT，测容量并采三种SOC的100秒CC脉冲；cycling和RPT 1Hz，持续38周；页面说80% remaining capacity时EOL。稀疏RPT适合作外部可行性材料，但精确时间/循环字段、RPT间隔、80%分母及删失/停测语义尚需README。官方5kB README本轮403未读。
该记录未给额定容量。制造商当前产品页列APR18650M1B典型1.2Ah/最小1.15Ah，[LithiumWerks](https://lithiumwerks.com/products/lithium-ion-18650-cells/)；不能代替该批次实测初始容量或EOL分母。关联论文Nowacki et al., *J Power Sources* 628, 235813 (2025-02), DOI [10.1016/j.jpowsour.2024.235813](https://doi.org/10.1016/j.jpowsour.2024.235813)；记录页未显示单独dataset DOI；许可CC BY4.0。
页面列RPT 2,349,987 kB、cycling part1 6,552,148 kB、part2 7,045,687 kB（合计15,947,822 kB）；参数CSV和citation各1kB。本轮未下载任何文件。勿与ISU Figshare DOI 10.25380/iastate.22582234混淆：后者NMC/Gr，251个有效ID/63工况；页面旧描述238与238+12存在差异，未将其当作最终事件数，是不同资源。

可推进候选问题，但先获得ESWA全文核竞争、从README核时间/RPT/EOL字段。当前仅支持竞争风险和元数据可行性，不支持训练、首创、严格在线或跨体系泛化。