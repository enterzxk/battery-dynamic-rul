# 稀疏容量观测与首次EOL：一次训练源机制诊断
2026-10-20；42fit；固定anchor100/间隔20实际循环；名义80%=0.88Ah。独立窄审后一次运行，0.0676秒，599227bytes/29840行。0fit/模型推理/cal/dev/test/raw archive读取。
本实验只改变已存记录的可见观测日程，不改容量、不平滑、不搜索phase/spacing、不给任何预测器新性能分数；不同于此前lag20预测保留比较。

## 实际结果
42颗均在有限记录内被稀疏观测检测到。检测延迟中位7.5循环、最大228；2颗延迟超过20循环，且普通“最后一次above—首次below”区间没有包含稠密记录首次越阈。2颗共17个稀疏观测点在首次事件之后恢复高于阈值。
|源电池|稠密记录首次T|最后above L|稀疏首次below U|检测延迟|T在(L,U]内|
|---|---:|---:|---:|---:|---|
|MATR_b4c38|1056|1160|1180|124|否|
|MATR_b4c40|872|1080|1100|228|否|
两例均T<L。当前容量above不等于此前从未首次越阈；这不证明噪声校正后潜在真实健康过程也有同样事件。

## 决策
机制计数2/42，未达到读取前冻结的至少3/42研究优先级门。保留NO_GO_COMPLEX_OBSERVATION_MECHANISM_EXPANSION_FROM_THIS_SCREEN，不改门、不据此新增复杂观测模型。这个门不是显著性检验，也不能用来否定机制存在。
两反例可支持论文说明观测/端点假设，不能称新预测方法、真实部署概率或独立确认。稠密“首次实测越阈”是参考事件，不是无噪声物理寿命真值。

## 证据与最小验证
protocol.json/runner.py/ROOT_GO.json/一次invocation.claim/completion.json绑定输入、角色和预算。主结果summary.json/per_cell.json。
独立review及validation在reports/measurement_schedule_firstpassage_review_20261020_luna；独立重算全部逐cell汇总，按sourceID固定选择两个positive源做手工式重算，未运行runner或读其他曲线，验证PASS。
复现命令（已消费票据，禁止重跑覆盖）：/home/yndx/miniconda3/envs/a40_env/bin/python reports/measurement_schedule_firstpassage_20261020_root/runner.py。
下一步按docs/PAPER_ROUTE_20261020_ZH.md建立能支持新方法研究的队列，先限定ISU-ILCC官方README/有效ID/处理口径预检；当前不继续10cal代理调参。
