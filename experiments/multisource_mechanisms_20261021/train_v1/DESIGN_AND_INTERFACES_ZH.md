# B：条件容量轨迹与源检查首达机制

## 数据和预测信息边界

V18 example提供74维因果 `x_query/x_anchor`、到达历史和 query clock。训练标签端另从冻结的C1/C2 cells中读取完整源RPT轨迹；C3预测features只由arrival<=query的records生成。事件定义是首次源RPT观测容量不高于0.20Ah，不代表连续潜在EOL。

每条训练路径从该query最后一个**可见source stop**（不是arrival time）处的容量出发，形成后续不规则source-RPT间隔 `Δt_j` 和容量目标，直到已记录源窗口末；因此arrival延迟后的隐藏容量区段也进入训练标签。模型用每个实际标签间隔训练条件增量密度，未来实际stop时间和容量均不会拼入74维feature。采样当前事件时，从最后可见source stop推进至query，用训练集经验RPT间隔 schedule 插入source-check surrogate，隐藏检查首个阈值命中给出P(T<=q)。这同时覆盖了report lag造成的“最后可见RPT早于arrival”时间段。

## 机制与训练

B-full为条件GRU路径密度：
`h_j=GRU(h_{j-1},[Δt_j,Q_{j-1}])`
`ΔQ_j~Normal(μ(h_j),σ²(h_j)); Q_j=Q_{j-1}+ΔQ_j`
增量不限制符号，容量可恢复。监督使用真实source间隔的Gaussian增量NLL与train路径支持mask；不插值未来容量，不按事件T筛掉query。每个batch先按cell均匀抽样，再cell内抽query/arm，避免高query cell占优。B-independent为预设机制消融：移除GRU的跨步隐状态，用同输入的独立步MLP预测increment分布；两者输出相同路径和分数接口。

## 评分协议

事件RUL从最后可见source stop的完整隐藏段向query推进，再用训练集唯一确定的128-week重复分位间隔schedule向前模拟，首个source-check surrogate命中阈值时输出RUL；窗口/simulation grid未命中保持未知，不外推。该值是固定模拟检查节律下的source-event RUL，不等于未来真实检查日程。标准4/12-week事件概率只在source记录覆盖至对应horizon时评分，并保留support mask。

下一RPT容量回测使用真实下一源RPT elapsed horizon计算该评估终点下的预测分布与NLL/误差；该horizon只作为明确的评估条件，不进入query的74维特征或事件schedule。标准horizon轨迹分数与模拟schedule首达RUL分数分开报告。HGB/CatBoost同信息对照由总控实现与审查。

## GO合同

`runner.py --go <exact GO>` 预设seed42、B-full与B-independent各不超过500 optimizer steps、串行设备、cell-balanced batch，无C3 checkpoint挑选；GO须锁定source map、DataV2 manifest与C1/C2/C3 cohort SHA、step/runtime/device/batch/lr、新输出目录，以及128-week/16 empirical-quantile schedule规则摘要SHA。runner只有完整校验GO、owner及hash后才load C1/C2/C3；不读取C4。训练后只生成两个checkpoint与step/loss/实际schedule SHA receipt；C3评分由总控统一完成。


## 评估输出

evaluate_v1.py只接受单独的inference-only exact GO并读取已完成train_v1 checkpoint和train-only schedule；仅逐个校验/加载C3 payload。每个query、每个模型/arm在predictions_c3.csv输出4/12周有支持标签、事件概率、128周模拟首达RUL限制均值与分位数、FPT分箱概率和窗口未命中tail mass、下一真实RPT预测摘要及源轨迹Gaussian NLL。已到达source event按可见信息闭合为当前事件。metrics_by_model_arm.csv采用cell-equal macro（cell内query等权），单列4/12周Brier、实际下一RPT容量RMSE、真实不规则轨迹NLL、事件query restricted-RUL MAE及tail质量；这些分别对应不同estimand，不与HGB的普通query MAE合并。下一RPT horizon只作为评估条件。Monte Carlo批次数上限累计两个模型的轨迹/下一RPT采样调用。
