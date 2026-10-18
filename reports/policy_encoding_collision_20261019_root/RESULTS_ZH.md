# 工况积分编码碰撞审计：确认一对精确信息丢失

## 实际结论
仅审计现有52行训练/校准工况metadata与原编码器，没有读取RUL标签或电池数据。34种raw_policy均对应34种不同的规范化实际schedule，四项20%SOC积分有效C-rate只有33种表示。唯一碰撞是fit电池MATR_b2c0与calibration电池MATR_b2c1，数学上精确相等，不是浮点误差或字符串格式差异。

判定：CONFIRMED_ONE_EXACT_POLICY_ENCODING_COLLISION_NO_PERFORMANCE_CLAIM。确认原4effectiveC表示不保留全部schedule细节；不宣称它导致整体预测失败、解释所有低覆盖电池或证明新输入有收益。此次并未修订旧指标/旧protocol/旧结果。

## 精确例子
| 电池 | 角色 | 原始schedule | 四项有效C |
|---|---|---|---|
| MATR_b2c0 | fit | 1C(4%)-6C | [3,6,6,6] |
| MATR_b2c1 | calibration | 2C(10%)-6C | [3,6,6,6] |

二者0–20%SOC的时间分别为：
- b2c0：0.04/1 + 0.16/6 = 1/15 小时。
- b2c1：0.10/2 + 0.10/6 = 1/15 小时。
因此首段有效倍率均为0.20/(1/15)=3C；20–80%SOC均为6C。但实际电流路径与切换位置不同，编码无法区分。这个推导仅说明输入映射非单射，不说明退化作用相同或不同。

## 全52行范围与最小核验
- fit42/cal10；raw字符串34、去零长度并合并相邻相同电流后的规范schedule34。
- 1326个电池对逐一核验，冻结绝对1e-12C容差；每个连通组另核全组两两最大直径，未用容差链强行合并。
- 不同实际schedule的碰撞共1对、涉及2电池；fit-fit0对、fit-cal1对、cal-cal0对，精确有理数编码相等也是1对。
- Fraction独立重算原积分公式，52行存储值最大差2.6645352591003757e-15。一个手算例精确核对1/15小时及[3,6,6,6]。
- source_semantics.json绑定的当前编码器为encode_policy_v1.py，SHA6a322bc105c6a76be999ecbf4fafd66788449af356ad0d998f6f220fdc4ef7e1。encode_policy.py/encode_policy_v0.py为保留旧版，0<split<80；v1允许0/80边界，与之前合法单段策略修复一致。本次没有修改编码器或重建特征。
- 没有读取结果标签来选分组/容差或评价碰撞影响。0fit/新模型/推理/新预测编码/raw电池/checkpoint/devtest；CPU19=RUL17+辅助2不变。

## 证据与复现
reports/policy_encoding_collision_20261019_root/下protocol.json冻结了范围、1e-12容差、规范schedule定义与边界。audit.py实际执行；summary.json、collision_pairs.json、encoding_groups.json、arithmetic_example.json、minimal_validation.json、completion.json与root_decision.json给出计数、名单、数学例子及SHA。

原调用：
/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/reports/policy_encoding_collision_20261019_root/audit.py
已有invocation.claim和create-only输出防止覆盖；不为确认同一事实反复重跑。原source52行SHA91a6bfa3be83b403289133bd13669d36ed7a1f212ec0ca4e692efecfb85be462。

## 对研究决策的影响
4effectiveC工况基线具有真实点预测收益的旧开发结果继续保留，但其输入只能称为压缩工况表示，不能称保留全部原始schedule。本范围只一对碰撞，没有fit-fit碰撞，不能据此直接扩展复杂网络或归因主要失败。旧全局/固定5局部CDF均保持NO_GAIN，不继续校准参数救援。

下一次仅允许准备一个公平的强简单点对照：用规范分段schedule的4个电流和3个SOC切换位置替换旧4个积分effectiveC。最多4段；不足4段用最后电流和0.8SOC补齐，去零长度/合并相同相邻电流后保证可重构，不使用format/batch/cellID或结局。与原age/SOH/robust20组成10输入，复用相同42fit/10cal、固定HGB/seed42/logRUL/电池等权，最多1新CPUfit和1次cal推理，旧点预测直接复用。以旧policy点MAE36.400814为主要参考，冻结>=5%/至少7cell/pairedCI>0及over100增量<=.01；概率仅按旧sigma不新增尺度的诊断，不冒充完整概率联合PASS。须输入可逆性最小核验、一次窄审+fresh exactGO后才执行，当前没有新GO。失败停止，不搜新特征/seed或返回残差CDF救援。
