# CALB 文件名身份链：温度剥离重名核查

结论：**PASS_CALB_FILENAME_BASENAME_DISJOINT_ONLY_PHYSICAL_IDENTITY_UNVERIFIED**。

仅解析 pinned 官方 split 与预处理源码，并复用既有22 train/val电芯审计CSV；没有打开任何数据二进制或test样本。

官方17train/5val/5test共27个文件名互异。去掉CALB与温度字段后，原始文件basename候选仍有27个唯一值，跨角色、跨温度重名0。这关闭了当前命名清单中“仅温度前缀掩盖同basename重复”的窄风险，不排除不同别名属于同一物理电芯。

[preprocess_CALB.py第23–30行](https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/process_scripts/preprocess_CALB.py#L23-L30)明确从0度/25度/35度/45度目录读取xlsx，用温度与文件首个点前basename拼成cell_name；[第263–274行](https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/process_scripts/preprocess_CALB.py#L263-L274)把该name赋给BatteryData.cell_id。[官方split第59–61行](https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/data_provider/data_split_recorder.py#L59-L61)给出固定17/5/5文件名。

因此，既有22条cell_id_matches=True证明输出字段与文件名一致；该字段本就由文件名生成，不能作为独立物理serial证据。27条basename是按pinned源码推得的候选，不是本轮核验了原始xlsx或实际v11生成执行。test只读上述源码中的5个文件名，不读test数据/标签/预测。

既有文件组prior的0/25/35/45在pinned命名语义下对应温度分组，可据此解释其分层含义；其混杂和因果关系未核，不能由组prior误差归因温度因果效应。原预测/组prior/当前5cell扩展NO_GO完全保留。

物理serial、跨数据源alias和预训练重叠仍未闭合，不能宣称独立泛化。本轮new_fits=0、optimizer_steps=0、model_loads=0、inference=0、binary_reads=0。机器记录identity_audit.json保存逐名角色、精确SHA与来源链接。

下一步仅用现有小型标签/周期审计摘要，量化官方eol<=100整cell筛选是否实际排除了早期仍存活origin；不新建strict-online队列、不新fit。
