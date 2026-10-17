# HUST 安全解码与数据结构审计

- Run: `run_20261015T164049_918837Z`
- BatteryLife commit: `3b17bb53202e10711deae0448c91f84144bb3dd9`
- 数据：BatteryLife v9 HUST；标签：BatteryLife v11（跨版本，仅诊断）
- 校验：官方 HUST archive SHA-256 `eb89ae0c384c62934b333009c1bae47d819e9fce55a98f71f3b27d4814b21b08`；标签 archive SHA-256 `45b3adf3f5ea2819244ac206f204defd4eea0ad1eaa4d38534f0543cab4ac033`
- 受限解码：自定义 Unpickler 的 `find_class` 与 `persistent_load` 全部拒绝；未启用 globals 白名单。
- 完成：77/77 cells；停止：0；cycle rows=146120。
- 标签比较定义：每循环 `max(discharge_capacity_in_Ah)` 第一次小于等于 `0.8 * nominal_capacity_in_Ah * SOC_interval宽度` 的 cycle index，与 v11 文件标签逐一比较；按官方 `Extract_life_labels.py` 的字段与阈值形式；只作诊断，不重标、不自动匹配。
- 训练集：未生成；拟合与 optimizer steps：0。

每电芯字段、数组长度、有限值、容量阈值穿越和标签差异见 `per_cell_schema_audit.jsonl`；每循环曲线长度、有限值、时间单调性、容量单调性及 cycle_number 检查见 `data/processed/audit_only` 下 CSV。
