# CALCE CS2-35 DataV1 字段与测量口径

本资产保留原始循环号与采样时间。原始 ZIP、逐条采样缓存和逐放电表仅在服务器；公开仓库保存解析代码、预算、来源摘要和必要验证。

- `source_file/source_cycle/source_occurrence`：原始文件、原始 Cycle_Index、该文件内连续片段序号；片段序号不代表全寿命循环年龄，不替换原循环号。
- `source_row/step/data_point/time_s/datetime/step_time_s`：源 Excel 行、Step_Index、Data_Point、Test_Time(s)、无时区的源 Date_Time、Step_Time(s)。日期文件名与真实采样时间分别保留；原日期时区未知。
- `charge_counter_Ah/discharge_counter_Ah`：设备记录的累计充放电计数，单位 Ah；不直接当单循环容量。重置由实际记录识别，不推断硬件重启原因。
- `baseline_counter_Ah/end_counter_Ah`：主放电前同一源循环内紧邻休息样本的计数及放电最后样本计数。
- `counter_delta_candidate_Ah`：上述同一步骤边界计数差，无跨循环或未来信息差分。
- `step_time_integral_candidate_Ah`：首个负电流样本的−I×Step_Time/3600，加相邻负电流样本梯形积分。首区间采用同一已验证恒流步骤，不能用于未知电流变化的任意片段。
- `partial_integral_legacy_Ah/legacy_end_counter_Ah`：仅复核旧304摘要的原−0.001A定义，含可能的微小诊断/噪声点；不作为新容量口径。
- `capacity_Ah/soh_nominal`：仅 `VALID_SAMPLED_CC_DISCHARGE` 时给出步骤计数差与其/1.1Ah值。有效表示采样信号与冻结完整性规则相符，不能当独立传感器标定或硬件精确截止证明。
- `status/flags`：缺失完整充电尾段、休息基线、截止样本、步骤起点相邻性、采样间隔、计数单调性、积分一致性等任一条件失败，保留为UNCERTAIN，不删行、不平滑或强制单调。
- `measurement_fingerprint_sha256/duplicate_of`：除源行号外的整片段原始信号精确哈希；完全一致者保留各来源并作为重复别名，不能重复计数。相同末时间/循环号但不同信号保留歧义。

冻结的工程容差见reconstruction_protocol_v2.json；不得据容量趋势调阈值。nominal80%=0.88Ah。逐容量SOH与全局EOL不同：若跨文件漏循环/身份连续性未证，首次观测越阈可以登记，但真实首次EOL、原生循环RUL和末行作为终点均不成立。没有可证事件时保留UNKNOWN或合法右删失；不将未知缺口伪装成右删失。当前文件时区、设备绝对标定和物理serial未核。

Exact duplicate aliases retain their candidate capacity/SOH values only as a source-reference to duplicate_of; consumers must select status=VALID_SAMPLED_CC_DISCHARGE for unique qualified observations. Alias rows are never additional physical samples.
