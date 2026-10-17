# Batch08 五篇增量综述与科研裁定

本报告仅综合本轮新增P42/P43/P44/P47/P48五篇的最新完整阅读、独立重读及root源附注，不是40篇系统综述。先前35篇未重新通读。作者报告值不是本项目复测，阅读接纳不是模型性能或复现接纳。完整源/最新版本/独审/root附注及SHA在同目录证据矩阵逐行绑定。

## 对动态RUL总任务的实际含义

P44和P47涉及逐循环RUL，但目前都不能成为本项目strict动态GO。P44的百分比误差用总失效年龄作分母，不能替代原始循环数Time-MAE。P47报告MAE(cycles)，仍没有本项目所需的逐origin法律输入、物理ID/预训练暴露及case-equal聚合闭环，其HUST表列最优还是去Chrono变体。P42早期5/10/20循环预测与统一EOL人口时序未闭合；P48只用两片段的效率主张不能变成最初两循环、50倍更早或完整动态轨迹。

因此严格在线动态RUL继续NO_GO。author estimated-total-EOL retrospective lane独立保留，不用其回顾标签冒充观测EOL：既有HUST77没有nominal80% observed crossing，MATR的88 observed与81 estimated人口不能混合宣称完整观测动态证据。此处人口数字继承当前冻结交接/项目状态，本轮没有重读曲线或重算。

## 对机制和创新判断的约束

连续轨迹、浅循环特征、域对齐/平滑、联邦压缩、双CLS/门控/SOH注入/不确定性加权、缺失通道预训练均已有本批原文来源。不能把这些模块的重新堆叠当作新颖性结论。P47的公式尤其要求区分局部detach路径与全局梯度隔离，Gaussian假设与Huber鲁棒替换目标；有界激活和SOH注入不自动带来单调、电化学一致或安全保证。

本批没有建立本项目的负迁移：P43的source-only对照与使用无标签target数据的适配模型信息权限不同；P47表中Stanford单任务CNN优于联合模型是作者设置下的负面观察，未核输入/标签/调参/总预算/复现，不足以独立建立本项目的机制性负迁移。negative_transfer_status=NOT_ESTABLISHED。创新GO与TSC论证GO均未立。

## 下一实证顺序

1. 先冻结每个预测origin的可见输入和观测EOL人口、物理电芯ID、预训练exposure、所有训练/归一化/适配数据权限及独立确认集。当前数据/asof门尚未通过，不据本综述启动训练。
2. 使用相同合法输入和明确预算比较强简单基线、直接剩余时间模型及已有联合/迁移模型。主指标为完整持续区间case-equal原始循环数Time-MAE，并报告逐log/逐cell、早中晚origin和确认不确定性；SOH误差、RMSE、coverage和成本是补充，不能替代核心指标。
3. 只有匹配target/input/adaptation/budget后出现可复现失败，再测试机制。loss scale、detach路径和SOH注入要分别用可否证控制；保留不改善、个体退化和选变体后结果，不用单个子门PASS救结论。
4. 阈值替换策略与误差评价分开；把更高RUL预测称更安全需独立代价/可靠性证据，不能继承P44的方向矛盾。现场部署、量化和隐私也各有独立证据门。

## 本批关键负面与矛盾

- P42：Q0 initial rated/initial value措辞、225/251/222等样本口径、表2LR与表7RF三值相同、完整轨迹特征只作上界。
- P43：0–60%下MMD均值略优完整模型；“10.76%”等对应乘100后的绝对差；score最大降幅、SOH范围、模型名称与SNL人数的文表差异均保留。作者对各比较模型也进行random search，不抹去此公平性安排。
- P44：总EOL分母；NMC532同阈值两组成本/更换次数冲突；高估更安全的作者文字与其触发策略方向张力；48+90>124人口计数差异。
- P47：Stanford并非最优；HUST182.56与full200.57配置不混；资源数值/排序冲突；已MCU profile与未来profile并列；zero-shot及partial robustness未获相应冻结实验闭环。
- P48：MIT1和KIT等逐数据集例外；EV标签积分噪声；预训练与下游实体暴露未知；mask文字/公式差异；补充七循环BatLiNet对照主动尝试公平但仍有通道/预训练差异。

本轮new_fits=0、optimizer_steps=0、PBT_forward=0、metrics=0、test=0。历史2fits/600steps保留，不续训或扩预算。
