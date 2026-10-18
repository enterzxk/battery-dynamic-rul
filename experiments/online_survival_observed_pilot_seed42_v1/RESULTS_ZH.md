# 单电池在线条件 RUL：首轮真实对照与方向裁决

2026-10-18 13:07 北京时间。已完成真实3CPUfit、0optimizer_steps。主线按用户新指令转向单目标电池随历史更新RUL；保留旧复现/审计/负结果。

## 科学问题与范围

先回答：存活本身的条件化能提供多少价值？当前健康与过去20循环速率能否在其外提供增益？本轮用已存processed文本的nominal80%首次真实crossing，不用作者尾段外推当真EOL。固定52train/19val source-ID，batch2/4，62个自然删失源ID未用于此event-only探索。每cell从完整cycle100到T−1的全部整数origin；训练26796、验证10002查询。已知四个future-shiftID显式排除，其他物理serial/rawgenerator仍unverified，不能称strict在线、独立物理泛化或部署验证。

## 真实结果

| 方法 | Cell-equal Time-MAE cycles | 偏差 cycles | 高估>100cycles比例 | 80%覆盖 | Brier100 | Brier300 |
|---|---:|---:|---:|---:|---:|---:|
| F0_frozen | 71.499956 | 3.044328 | 0.105263 | 0.789474 | 0.096785 | 0.118510 |
| F1_survival_only | 72.072506 | 14.637496 | 0.109889 | 0.796076 | 0.098050 | 0.118943 |
| F2_current_state | 68.284099 | -1.272201 | 0.111112 | 0.822113 | 0.047239 | 0.121092 |
| F3_state_rate | 58.602646 | -4.350586 | 0.103743 | 0.845636 | 0.030563 | 0.106915 |

F0：t100早期SOH/速率/batch4训练lognormal总EOL，再冻结递减；F1：同一F0分布按T>t条件化，无新增fit；F2：年龄/当前SOH/batch4直接logRUL回归；F3：F2增加过去20cycle速率。均Ridge alpha1、train-only cell等权缩放、train残差确定sigma，未用val校准或调参。它们是简单探索对照，不宣称同一模型仅改变一个模块的全部因果隔离。

| 比较 | Time-MAE相对改善 | 电芯bootstrap探索95%区间 | 改善cell | 冻结探索门 |
|---|---:|---|---:|---|
| F1_survival_only vs F0_frozen | -0.8008% | [-11.5082%, 5.0774%] | 6/19 | False |
| F2_current_state vs F1_survival_only | 5.2564% | [-19.3544%, 23.3926%] | 10/19 | False |
| F3_state_rate vs F2_current_state | 14.1782% | [4.3775%, 21.5915%] | 12/19 | True |

门在运行前冻结：相对MAE改善≥5%、paired cell bootstrap下界>0、高估>100cycles比例增加≤2个百分点；3个比较均为探索，未做确认性多重检验，不把区间跨零与否称最终显著性。F1的偏差从+3.04到+14.64、MAE差0.80%，说明概率条件化不保证点预测更准；不能据此否定正确条件生存建模。F3相对F2在batch2/4分别改善14.32%/14.11%，两组各改善6cell；不是仅某batch。正向改善前三cell仍占59.30%，另7cell受损，最差MATR_b4c28的MAE从26.1110升到41.7239。平均收益不能替代失败诊断。

## 优先级与新颖性边界

1. 优先继续“速率何时帮助、何时伤害”的已有预测失败诊断，不先上深度生存网络或复杂更新控制。
2. 自然删失收益暂不能从本轮建立：62个自然删失电芯被排除，batch与事件观测状态混杂。当前概率覆盖/Brier只针对event-selected开发人口，不是无偏现场风险校准。
3. 条件化公式是标准概率运算。Dynamic-DeepHit已有纵向动态生存；[电池Cox/DeepHit作者仓库](https://github.com/OKIC-CA/RUL)已使用删失电池做生存分析（cycle50表征）；[PEAT预印本](https://www.preprints.org/manuscript/202603.2447)已有在线历史选择与轻量适配/稳健回滚。后者在线RUL标签可得性尚未证。文献代理报告明示仅3篇且部分未读全文，不能称系统新颖性确认。

## 来源整理与历史边界

已按标识核两份十篇与原41篇的关系：电池十篇中3项明确匹配P12/P05/P07；其余不因未匹配而自动算新全文。第1项Severson“Science2019/10.1126/science.aau7705”与已接纳P01“NatureEnergy2019/10.1038/s41560-019-0356-8”冲突；按原P01身份与精读范围使用，不覆盖旧稿。跨领域第9项DynamicDeepHit与本轮来源重复，不再计一篇。完整逐项身份状态见literature_identity_dedup.json。原41篇不重读，两份主题综述及作者值不当本项目实测。

本次目标、标签、人口与覆盖区间不同于旧MATR A0/A1/A2回顾作者EOL诊断。旧2.68%/NO_GAIN保持，不能把本轮14.18%替代或挽救它。CALB扩展NO_GO、PBT一次消费失败、全局new_fits_allowed=false/test锁不变。新scopedGO只消费本轮3CPUfits；历史神经4fits2580steps、旧MATR41CPUfits分别记账。

## 证据、最小验证与下一步

独审先BLOCK缺显式排除清单，补录后限定PASS；原冻结版本/失败回执保留。唯一数值小例核条件分位数CDF=0.5，无重复smoke。真实run一次完成后，从19份每cell原预测CSV独立重算全部四模型7指标及10002连续origin，全部与completion吻合（<1e-9）；fit ledger3开始/3完成。原raw/test/模型checkpoint均未读取。predictions可独立重算指标；源cycle文本和未公开binary仍权威在服务器，公开镜像不冒充完整原始数据包。

复现：本次唯一运行命令为 `/home/yndx/miniconda3/envs/a40_env/bin/python experiments/online_survival_observed_pilot_seed42_v1/runner.py`；invocation.claim已消费，禁止直接重跑，指标请从validation_predictions/*.csv重算。环境numpy1.26.4/scipy1.10.1/sklearn1.6.1，exactGO/protocol/cohort源哈希见回执。

下一项：只用现有F2/F3预测和已存因果前缀核7个受损电芯的错误区间，先判断是否存在可重复、预测时可诊断的噪声/恢复/阶段变化机制；无证据不开发可靠性门控，不加seed/网络或打开test。
