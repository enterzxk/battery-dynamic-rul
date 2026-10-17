# HUST v9 安全解码与字段/标签诊断

本报告只记录受限解码与数据质量事实，不构造训练集、不拟合模型。所有 77 个文件先有逐文件 SHA-256 记录；每个文件在解码前再次核对 SHA。自定义 `pickle.Unpickler.find_class` 对任意 module/name 一律抛错，`persistent_load` 一律抛错，没有任何 globals 白名单。77/77 个对象成功解码为纯原语树（dict/list/str/number/None等），未触发类构造。

- 代码来源：BatteryLife commit `3b17bb53202e10711deae0448c91f84144bb3dd9`。数据为 v9 HUST；标签为 v11 Life labels，跨发布版。
- 77 个电芯共 146,120 个周期。所有电芯顶层均为 dict，`cycle_data` 为 list。所有周期具有相同字段集合：`cycle_number`、`current_in_A`、`voltage_in_V`、`charge_capacity_in_Ah`、`discharge_capacity_in_Ah`、`time_in_s`、`temperature_in_C`、`internal_resistance_in_ohm`。前三项测量数组、容量数组和时间数组的长度逐周期一致；必需字段缺失为 0 行。温度与内阻字段存在但 146,120 个周期值均为 null，符合官方说明称这些字段仅在原始数据提供时存在。
- 必需曲线数值中 NaN/Inf 为 0。时间序列非递增点对 4 处，均为相邻重复时间；时间回退和跨周期回退均为 0。放电容量单调下降点对 1 处，位于 `HUST_1-8.pkl`。Cycle number 除 `HUST_7-5.pkl` 外均按 1 起始；HUST_7-5 记录从 3 开始，是官方 `preprocess_HUST.py` 在赋 cycle_number 后删去前两周期导致，符合其固定处理代码。
- 官方 `Extract_life_labels.py` 用周期 `max(discharge_capacity_in_Ah)`、`nominal_capacity_in_Ah` 与 `SOC_interval` 计算 80% SOH 阈值。HUST 元数据给出额定 1.1 Ah、SOC interval [0,1]，故阈值为 0.88 Ah。本审计的容量提取来自已预处理周期的官方 `discharge_capacity_in_Ah` 数组最大值；没有重新积分或归一化。
- 77/77 个 v9 HUST 电芯在已记录周期内均没有观测到容量 ≤0.88 Ah 的周期；末周期最大放电容量范围为约 0.8908–0.9063 Ah。v11 标签 77/77 均超过各自 v9 `cycle_data` 周期数，差值 22–124 周期，中位数 53。因此 EOL 对比 77/77 均不可比。该信号符合跨版本差异或标签由观测末端外推的可能性；不是标签相符证据，不能按文件名自动放行或将 v11 标签当作同版本标签。

## 产物

- 每电芯结构与标签诊断：`per_cell_schema_audit.jsonl`
- 逐周期曲线长度、有限值、时间与容量诊断：`/home/yndx/zxk/rul/data/processed/audit_only/run_20261015T164049_918837Z/hust_v9_cycle_diagnostics.csv`
- 文件 SHA-256：`hust_file_sha256.json`
- 机器可读总计：`aggregate_diagnostics.json`

下一步先寻找并核验与 v9 完全匹配的 Life labels，或取得同版本 processed HUST 覆盖到 EOL 的数据与正式标签规则。完成版本对齐和 EOL 语义核对前，不应将该标签/数据组合用于基线训练或宣称动态 RUL 复现。训练集未生成；fit=0，optimizer steps=0。
