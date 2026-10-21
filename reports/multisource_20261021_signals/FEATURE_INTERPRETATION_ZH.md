# 多源特征的物理解释与可识别边界

**用途。** 本说明把正式 factorial 中可观察到的信号与可以支持的结论分开。它只依赖 ISU-ILCC V2 官方 README 文本、公开处理代码和当前特征合同/适配代码；没有检查任何原始 payload，也没有拟合模型。

## RPT 与 Cycling 容量代表不同测量

V2 README 第 3 页说明常规循环按各 G 组的充电/放电倍率和 DoD 运行，放电截止电压用于设定 DoD；附录按 G 组给出 mean DoD。第 4 页特意说明，对部分 DoD 老化的电芯需要周期性 RPT 测量 full discharge capacity；RPT 在 C/5 与 C/2 运行完整测试。README 第 5、7、8 页把 `capacity_charge` / `capacity_discharge` 描述为特定循环的总充/放电容量，并把 Cycling 与 RPT 列为独立数据文件。

因此，Cycling 每循环的 charge/discharge capacity 是该常规操作循环下的测量吞吐，受组别的倍率、DoD/截止条件和实际循环影响。它不是同一个电芯在标准全放电 RPT 下的容量，不能互换成 SOH 或 RPT 容量，也不应直接把二者差值叫作不可逆容量损失。README 没有给出每个 cycle 的 SOC 上下界序列；附录给出组别 mean DoD，正文说明以电压 cutoff 决定 DoD，但它们不足以把本资产说成已观测的 SOC-window 标签。mean DoD 也不是 query 时已知的逐循环特征，不能作为 unseen-G 评估的已知输入。精确 SOC 轨迹仍为未知。

若要给观测到的 Cycling 吞吐换算等效全循环量，只能用实际已记录的充、放两腿容量总和：

`observed_EFC = observed_charge_discharge_Ah / (2 × 0.25 Ah)`

这里 0.25 Ah 是 README 所述额定 250 mAh；分子只累加两腿容量都有限的已观测 Cycling 循环。缺腿/缺周期不补值，空档不推算，RPT 测量不加入 Cycling 分子。当前 24 维模型输入保留 `cycle_throughput_cumulative_Ah` 与有效配对计数，**没有**把 EFC 当作已测源字段。若另行报告上述换算，它只是“由已观察吞吐折算的 EFC”，不能称为完整或 native elapsed-cycle 计数；`source_cycle_index` 仅作来源追溯，缺口和完成时间均按源记录处理。

## RPT Q(V)、dQ/dV 的单位与适配

官方 README 第 5、7 页给出容量/Q 的单位 Ah，电压 V；RPT 有 C/5、C/2 的充电及放电 Q-V 记录。当前提取器先按实测电压升序整理有限的 `(V,Q)` 点，对重复电压取容量均值，只在实测电压覆盖范围内线性插值到 3.00–4.20 V 的 0.01 V 网格，不外推；随后对该网格上的 Q(V) 求有限差分。因而原始 Q(V) 为 Ah，原始 dQ/dV 为 Ah/V。提取器的差分遇到空网格会向两侧寻找最近的有限 Q 点，所以跨缺口的差分可能是较宽电压跨度的 secant，不总是紧邻点的局部导数；NaN/缺失仍应视为缺失，不能作精细峰位或局部机理的证据。

正式适配器从 0.01 V 缓存抽取 3.00、3.05、…、4.20 V 共 25 个点。它把四个 C2/C5 充放电容量标量及 Q(V)、dQ/dV 全部除以名义 0.25 Ah，再为每个来源量追加“最新可见值、相对首个实际可见 RPT 的差、按首末 RPT stop 间隔折算的过去斜率/周”。所以特征名虽然保留 `Q` 或 `dQdV`，**模型实际输入**的最新 Q 是无量纲比例，最新 dQ/dV 的量纲为 V⁻¹；其斜率再除以周。delta 与 slope 仅使用 query 时已到达的有效 RPT。delay7d arm 的 measurement stop、protocol arrival 与 query 仍分开；实际网络传输延迟没有被测量。

F1 相对 F0 的效果只说明“加入这些 RPT 标量与 Q-V 派生特征后，当前固定评估设置中的预测结果如何变化”，不能单独证明电化学机制。`control_rpt_scalar_only` 用于检查容量标量这一路；`control_capacity_normalized_shape_only` 把每条曲线再除以其匹配 leg/rate 的 RPT 容量、不输入那四个容量幅度；`control_rpt_scalar_plus_shape` 则把标量与归一化曲线放在一起，容量幅度条件与 F1 接近。若 F1 优于 scalar+shape control，差异可支持原始曲线幅度/归一化方式含有增量预测信号；若 normalized-shape 控制本身优于 F0，只能说明归一化曲线表征有预测信息，不能称其与容量退化完全独立，因为截止范围、缺失模式及曲线端点也可能携带容量信息。

这里未对 charge/discharge Q 轴做统一的 SOC 反向映射，dQ/dV 也不是经过路径配准的迟滞面积。因此，任何预测增益都不能单独称作“物理 hysteresis”“SOC 对齐的材料反应变化”或可解释的机理参数。

## Cycling VI/E/time 与观测可见性

18 维 VI/E/time 控制保留已完成循环的数量、距最近完成时间、两腿时长、端电压的有限样本均值/最小/最大、端电流的有限样本均值/最小/最大和两腿能量末值；它明确去掉直接容量、累计 Ah 吞吐及 Q 末值。它若带来预测改进，可以支持这些**已测操作摘要**在当前训练/开发协议中含有超出 74 维 RPT 历史的增量预测信息，但不证明因果作用，也不能排除它们代理了 G 组操作设定、运行阶段、未观测的温度或缺失过程。F2/F3 全 24 维还加入容量/throughput/Q end；与 18 维对照的差异可定位“加入这些容量类摘要后的预测变化”，仍不证明 EFC 或 SOH 机制。

Cycling 的 `I/V/E/Q/t` 是按有限源样本汇总的均值、极值、首末值及源起止时间，不是完整波形模型。官方实验把 incubator 设为 30°C，不等于当前 JSON 含有逐循环电芯温度测量。官方 README 第 4 页还明确提到 G30–G64 的 RPT 增加了不同 SoC 的 pulse/DCIR 测试；这说明实验确实包含这些测试。当前此处的 Cycling/RPT 特征提取器只输出标准循环统计与四条 RPT Q-V 曲线，没有单独输出 pulse/DCIR 或 rest/relaxation 数值；这是当前 JSON 解析与 predictor 字段范围的限制，不能说实验没有做这些测试。RPT 的 `dQ/dV` 是上述 Q-V 曲线计算得到的特征；Cycling 面板没有计算或声称 Cycling dQ/dV。不得从本面板推断逐循环热响应、静置弛豫、脉冲内阻或原始波形。

Cycle 的 as-of 截点使用 `max(charge.stop, discharge.stop) <= query`。源到达时间未观测，当前 replay 明确假设信号在完成时即可见；因此 no-new-RPT 的变化分析可评估“按此完成即见假设，操作摘要是否更新预测”，不能证明真实在线系统的到达时效。相同 RPT `history_key` 的配对比较能检验 RPT 空档中更新后的预测误差/Brier 是否优于旧预测按时间前移，但观测操作信号与时间同时变化，结果是预测性证据而非因果识别；无增益可以反驳该协议下的更新价值主张，有增益不能证明操作信号导致了寿命变化。

## 主要失效边界

- RPT 对照是周期性参考测量；常规 Cycling capacity 是条件化的操作吞吐。不得混作一个容量序列。
- 源没有完整观测的循环/RPT、缺失电压区间或已知原始资料损失不会用插值补成观测。RPT 的 Q(V) 仅在实测范围内插值；dQ/dV 在网格缺口处可能跨点差分，峰形解释需额外质量门槛。README 报告的 G 组 mean DoD 不可冒充每个 query 可用的 SOC 上下界。
- C1/C2 是训练 replicate，C3 是相同 G 组条件下的开发 replicate，C4 锁定；C3 不是 unseen-G 条件验证。G 组留出需另行协议。
- 分析目标为源记录中首次 RPT capacity <= 0.20 Ah 的观测阈值事件，不是潜在物理 EOL。开发集结果不构成独立确认。

## 可复核依据

- 官方文本摘录：`reports/isu_ilcc_metadata_20261020_root/readme_text.json`，第 2–5、7–8 页及附录 DoD 表。
- 官方转换/曲线处理示例：`data/source_audit/isu_ilcc_v2/process_data.py`。
- 当前 RPT 插值与有限差分：`reports/multisource_20261021_signals/extract_rpt_signal_features.py`。
- RPT 同 query 特征归一化、首个可见 RPT 差和 stop-time slope：`experiments/multisource_factorial_20261021/features.py`。
- Cycling 流式字段摘要、双腿 throughput 与时间字段：`reports/multisource_20261021_signals/extract_cycling_stream_features.py`。
- Cycling 24/18 特征及完成时可见假设：`reports/multisource_20261021_signals/cycle_asof_features.py`、`reports/multisource_20261021_signals/sourcefeature_contract.json`。
