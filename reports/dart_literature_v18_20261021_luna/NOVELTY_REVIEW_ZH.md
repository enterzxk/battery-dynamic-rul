# DART-RUL V18 文献竞争审查与贡献边界

日期：2026-10-21。范围为一手来源竞争核查，不含训练、C4、原始数据访问或下载。完整结构化证据见本目录的 competition_matrix.json 与 sources.json。

## 结论

目前不能把 DART 的宽泛机制组合称为创新。最强电池直接竞争是 Zhang et al. 2026 ESWA：官方摘要已有 Wiener 随机退化、liquid 连续时间循环网络与在线 refinement；此前项目预览又核实了其按循环排序的容量窗口预测协议。预览没有证明它处理不规则报告到达、阈值首达区间删失或发生/报告延迟，相关细节一律保留为 unverified。正确 DOI 是 [10.1016/j.eswa.2026.133786](https://doi.org/10.1016/j.eswa.2026.133786)，不能误用 131286。

关键方法部件分别存在明确先例。Zhu et al. 2020 已在 sparse/irregular 纵向生物标志物下做 landmark 条件事件时间预测；Kim 2026 明确研究纵向标记下区间删失失败时间的动态预测评估，并比较 joint model 与 landmark；Verbelen et al. 2022 将事件发生时间与后续报告时间分开，建模延迟并用 EM 联合估计；Shen et al. 2021 直接以新在线测量更新电池 RUL 分布。它们各自应用不同，不能因此说 DART 的组合已经被完整实现，但足以禁止把这些单个成分分别宣称为新机制。

## 对工作假设的逐项裁定

- R_a 是到达时刻 a 下的剩余寿命分布：条件残余时间/landmark 生存预测已有大量先例。电池一侧的在线 RUL 概率分布也有 Shen et al. 2021。
- R_q=max(R_a-(q-a),0)：若 R_a=T-a，且潜在阈值事件 T 在查询期间吸收，则这是剩余时间坐标的确定性平移和零截断，是分布一致性恒等式，不自动构成新随机过程。当前五篇来源未核到完全相同的代码表达式；这不足以建立首次性。
- p(q)=F_a(q-a)，而 S+ 从同一分布导出：CDF、存活补数和事件概率的关系是分布定义。共享 CDF 可以确保两个预测头一致，属于值得验证的输出约束/工程性质，单独不构成算法创新。
- 只在新报告到达时更新：landmark 方法本来就以当前可用历史为条件，在线电池 RUL 方法也会随新测量更新。需要明确真实信息集和到达时钟，并证明相较于既有 landmark/在线基线有可重复收益。
- 确认阈值闭合后 R=0：符合首达事件吸收后的剩余寿命定义。非平凡问题是“何时越阈”和“何时被观察/报告”是否相同。若定期检查只知道前次检查未越阈、下次检查已越阈，潜在事件时间是区间删失；延迟通知时报告时间更晚。直接把报告时刻当越阈时间会改写标签和风险集。

## 五篇核心比较及证据边界

1. **Zhang et al., ESWA 2026, DOI 10.1016/j.eswa.2026.133786。** 官方摘要明确指出 Wiener 退化、liquid RNN 连续动力学、联合优化及在线 refinement。复用前一轮 Elsevier primary preview：已读问题/随机退化、数据集特征、实验协议部分，preview 记载 XJU/HUST、周期容量排序、lookback=20 的 next-capacity target。当前仍未访问全文方法公式、更新算法、阈值事件/区间观测处理、split 与结果表，因此不可据此断定它覆盖或不覆盖 DART 全部协议。旧 preview：reports/irregular_rul_competition_20261020_root/eswa_primary_preview.json。
2. **Zhu et al., Biometrical Journal 2020, DOI 10.1002/bimj.201900112。** PMC 作者全文的 §2.1 使用 FPCA/MFPCA 拟合稀疏纵向轨迹；§2.2 式 (3) 为 landmark 残余事件时间的线性变换模型；§2.3 式 (7) 由 landmark 健康值和风险集给出条件生存概率，并定义动态 Brier 评分。它证明“稀疏不规则健康历史 + landmark 残余事件时间预测”不是新组合，但不是电池首达传播算法。PMC 页面本次触发验证码；取证使用可检索的 PMC 全文 HTML 节段。未核实配套代码。
3. **Kim, Statistical Methods in Medical Research 2026, DOI 10.1177/09622802251412849。** SAGE 正式页面核实作者、卷期页码和 2026 年 online 日期。摘要称其提出适配区间删失数据结构的 dynamic AUC 与 Brier score；模拟比较 joint model 和 landmarking；示例为重复认知评分预测痴呆。全文受限，具体联合似然和更新算法均 unverified。该论文足以反驳“首次动态预测区间观测事件”的宽泛说法，不能用摘要推断其算法等于 DART。
4. **Verbelen, Antonio, Claeskens & Crevecoeur, Statistical Science 2022, DOI 10.1214/21-STS831。** 机构记录核实作者、年份、37(3):394–410；作者 arXiv 全文 §1–3.1 将主事件时刻 X、报告时刻 S 与延迟 U=S-X 明确分开，说明未报告事件导致发生计数右删失、已报告延迟被右截断，并用 EM 分别建模发生与报告过程。§4 使用保险理赔案例。它确立发生/报告分离已是通用方法；对单体电池 RUL 的似然适配仍需另做。
5. **Shen et al., Energy 2021, DOI 10.1016/j.energy.2020.119490。** Elsevier 官方摘要/索引全文片段核实两阶段 Wiener 模型、Eq. (1) 非线性 Wiener 过程，以及 unscented particle filtering 随在线测量自适应更新模型参数和 RUL 分布；摘要提到变放电电流实验与两个方法对照。正式出版信息由该论文 bibliographic record 交叉核对。ScienceDirect 正文访问本次返回 403；遵守不重试，具体后续公式、数据划分和是否为首达质量分布 unverified。未核实公开代码。

详见两个 JSON 文件，分别保存每篇的主源、读到章节/公式/网页字段、机制及未核边界。

## 与基线的机制关系

- 对 HGB p + future 双头：如果两头分别训练，预测可能不满足 CDF 与未来条件生存的一致性；同一 CDF 导出的输出有清晰一致性动机。但是否降低校准误差或损失，需要同一信息集、cell split 和事件定义下比较，不能从定义本身推出经验优势。
- 对 shared-state 与 separate-state：联合健康/事件模型和共享潜变量早已存在；分开状态可能表达观测到达驱动健康摘要与吸收事件状态的不同语义，但 state 分离不是新颖性证据。需要容量/参数预算受控的消融，证明其降低状态混淆或改善 proper score。
- 对 R_q 传输：当没有新测量时它是已输出条件分布的时钟推进。真正可检验的是在任意查询时刻预测不变性、严格遵循信息截止、遇到迟报时正确修正区间删失状态，而非“平移公式”本身。

## 允许保留的狭窄贡献候选

把主张限定为：在电池稀疏/不规则检查和可能延迟报告下，以真实信息到达时刻维护一个条件首达 RUL 分布；该分布可对检查间任意查询时刻精确传播、只在新报告到达时做信息更新、把潜在越阈区间与报告时间区别处理，并保证越阈闭合为吸收零。当前这只是有待证伪的协议与实现组合，不是已建立首创结论。ESWA 全文仍是优先竞争核查项。

最低决策实验应在同一 cell-level split、输入前缀和事件标签协议下，对比 coherent CDF/传播、现行 HGB p+future、shared state、separate state；再用受控迟报/区间删失情景区分 arrival-time 和 event-time 处理。报告 proper distributional score、校准和电芯级误差。若数据不保存事件区间/报告时刻，就不能声称验证了迟报或区间删失机制；若只有周期容量点，就把结论限定为重采样/间隔敏感性。实验需单独授权，本审查未启动训练。

## 执行与复用记录

- 没有 fit、C4、原始数据访问/下载或模型/数据更改。
- 2021 Energy ScienceDirect 正文访问一次返回 403 后停止；没有重复 publisher PDF 请求。
- 复用既有 irregular competition 报告与 ESWA preview，未重新下载或重读其 PDF。
- 旧 GammaOU 候选保持 STOP，本审查没有提出复活或调参。
- 报告不构成精确模型首创性结论。下一步高价值动作：从合法来源获取 ESWA 全文/作者稿，核其方法公式、事件定义、观测时间处理和实际在线更新协议；若仍不可得则维持 unverified。

## 输入哈希

- reports/irregular_rul_competition_20261020_luna/competition_report.md: dc0dd963848f0ff3aaf4decae19842f98db0f084d5c49e4ae1c1ef6a70c38fc8
- reports/irregular_rul_competition_20261020_luna/evidence.json: c0a272e0e61de2d3066244ca49e9ccfb25fa54739f0e63aef8d273143aa1b202
- reports/irregular_rul_competition_20261020_root/eswa_primary_preview.json: b44d71907826821a194ca39df6120cb931ca129581fa1108a08dfc8fd9f40711
