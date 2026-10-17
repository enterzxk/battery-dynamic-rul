# 索引空间与 80% 容量分母澄清

本校正附录用于进一步澄清 `final_findings_zh.md` 中周期数比较的口径。它不覆盖先前产物；报告原因与直接观测分开。

## EOL 标签的索引空间

Pinned BatteryLife v9 的 `process_scripts/Extract_life_labels.py` 在观测到 SOH ≤0.8 时把标签设为 `correct_cycle_index + 1`（行 152–153），即 `cycle_data` 中的 1-based 行位置；当末端 SOH 位于 (0.8, 0.825) 时，末 20 周期回归目标也通过 `i + 1` 构造（行 129–145）。因此该代码将 EOL label 定义在行位置空间，而非 `cycle_number` 字段空间。

77/77 个标签都大于周期行数；也在 77/77 个文件中大于实际 `max(cycle_number)`。标签减周期行数范围 22–124（中位数 53）；标签减 `max(cycle_number)` 也范围 22–124（中位数 53）。76 个文件的 cycle_number 与行位置一致；`HUST_7-5.pkl` 是已知例外：官方 `preprocess_HUST.py` 第 64 行先给周期编号，第 75 行再删除最初两周期，所以行位置 1..1873 对应实际 cycle_number 3..1875。该例外已在逐周期表单独审计。

## 80% 容量的两个分母诊断

Pinned v9 的标签提取逻辑读取 `nominal_capacity_in_Ah` 与 `SOC_interval`（`Extract_life_labels.py` 第 116–121 行）。HUST 文件中额定容量为 1.1 Ah、SOC interval=[0,1]，于是 `0.8 × Q_nominal × SOC宽度 = 0.88 Ah`。在现存 v9 周期数据中，77/77 电芯都没有观测到最大放电容量 ≤0.88 Ah 的周期。末周期按该额定容量计算的 SOH 为 0.80979–0.82394，全部位于 pinned 提取代码的 `(0.8,0.825)` 末端分支；该分支会基于末 20 周期外推标签。这与观察到 EOL label 超过已观测行位置相一致，但 v11 标签发布的生成版本/代码尚未独立核实，因此它只是与 pinned 代码相符的解释假说。

另一个独立诊断以每电芯第一周期最大放电容量为分母，阈值为 `0.8 × Q_first_cycle`；77/77 电芯在已观测数据内均穿越此阈值，首次 crossing 的行位置为 969–2323（中位数 1702）。此分母与 pinned v9 标签代码的额定容量分母不同，本报告不将它替换为标签定义，也不据此修改标签。

## 结论边界与下一步

直接事实是索引空间比较结果与两个不同容量分母下的 crossing 结果如上。原因假说是 pinned 提取代码对末端 SOH >0.8 的电芯采用回归外推。当前下载组合仍是 v9 HUST 数据与 v11 标签；未核实 v11 的发布生成链，不能宣称标签已与 v9 观测或 v9 生成代码一致。下一步应核验 v11/v9 标签 artifact 的生成版本/源输入，并获取可对应的同版标签与 processed 数据；不自动接受现标签或重标。

完整逐电芯指标见 `index_capacity_clarification.json`；逐周期曲线和 cycle_number 原始值见 `/home/yndx/zxk/rul/data/processed/audit_only/run_20261015T164049_918837Z/hust_v9_cycle_diagnostics.csv`。训练数据未生成，未 fit、未调用 optimizer。
