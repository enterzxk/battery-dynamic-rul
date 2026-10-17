# HUSTval15 keyed DKP / valid-cycle / prefix-mask-collate 静态审计

现有小证据不足以证明15个 pinned HUSTval 各自与 DKP embedding 逐键绑定，也没有每 cell 的 valid_cycle_number 值或 PBT 运行时 prefix/mask/collate 结果。只能保留“aggregate 15/15 covered”，不可写“15/15逐键已匹配”。

受限 decode receipt 记载HUST validation key集合覆盖15/15、missing 0，但省略key names；shape inventory只有195个1x4096、f2数组，无key-to-array映射。join CSV的预期basename key不能代替逐键证据。

固定源码 data_loader.py:1052-1053 从len(cycle_data)取得valid_cycle_number；1114-1177按seq_len..threshold循环，i超过valid_cycle_number或达到EOL时停止，mask[:i]=1。故1500是条件值，只有每cell有效cycle至少100且通过筛选才成立。finetune_PBT.sh:9-10设seq_len=1、threshold=100，未设eval min/max；evaluate_model.py:485-497默认10/10。15行仅为每cell存在第10个prefix时的投影。data_loader.py:163-194显示静态stack操作，无运行时collate证据。CPMLP preflight属另一loader。

源码SHA256：data_loader.py 86d70a40e33f12c843abf856dcbbc29b823b78928a758c8fee6788118565756a；data_split_recorder.py 70a14cd0e482f81314fa4c0e86d3233d2ebba59b54cb07df630a7513a5ea9c08；finetune_PBT.sh 31329043d03a490960ae8c9e99e9a675b0a50c8f817011a2510a8bb0fa93ac83；evaluate_model.py 24a6150f95646fbde0e7eabd048407bdbe5a8722aff656360663a0743c5d301f。行号：data_loader.py 163-194、630-645、902-920、1029-1053、1114-1177、1390-1408；split文件5；finetune脚本9-10；evaluate脚本485-497。

后续方案保持inactive且门全部false，仅限固定hash的pinned HUSTval15：先查已有key-only metadata，缺时须另行授权生成仅15个key身份/present-missing回执，不输出embedding；优先查hash-bound逐cell cycle-count manifest，缺时另行授权受限val-only安全读取，禁普通pickle/joblib/torch.load；按固定源码逐cell列prefix/mask统计，全部符合才报1500；仅root另行授权后留存最小val-only collate row id/mask/shape证据，不构造模型、不strict-load、不forward、不算metrics、不fit、不test。

本次未全盘扫描、未读取或重hash曲线/checkpoint/大binary；未新decode195、import源码或构造对象；new_fits=0、optimizer_steps=0、forward=0、metrics=0、test=0；共享state/index/queue未改。