# 独立静态元数据审查：HUST val 15 配对

**结论：PASS_STATIC_METADATA_ONLY**。审查限于既有报告/回执/CSV，小型 JSON 元数据与固定 PBT 源码配置。

## 核验结果

- 固定 split recorder 的 HUST_val_files 与 pairing CSV 顺序、名称逐项一致：15/15。
- stage v11 manifest、CPMLP trainval view manifest 和 CSV 声明的曲线 SHA 三方逐项相等：15/15。这是比对元数据声明；没有读取或重哈希 pickle 内容。
- 原始 v11 标签 JSON 与 trainval label JSON 的 15 个 key 及 EOL 值和 CSV 一致：15/15。stage manifest 中 raw label SHA 与原始 JSON 实际哈希一致；view manifest 将 raw label SHA 和 stage manifest SHA 连到 CPMLP trainval view。该 view 有 62 个 trainval label key，明确省略 15 个 test label key。
- PBT loader 按 basename 去掉 .pkl 得 DKP key，CSV 预期 key 符合规则：15/15。receipt 只有 aggregate 15/15 coverage、missing=0 且省略名称；shape inventory 没有 key-to-array 映射，DKP 逐键映射仍未核实。
- 配置 seq_len=1、early_cycle_threshold=100。15 个 EOL 均大于 100；条件投影 CSV 为 1500 行，每 cell i=1..100，mask 长 100 且前 i 项为 1。默认 eval min=max=10 最多对应 15 行。prefix 仍以 valid_cycle_number 足够为条件，PBT 运行时与 collate 均未证实。

## 边界

- CPMLP manifest/preflight 属于另一个 loader/实验，不是 PBT runtime 或 collate 证据。
- v11 同记录来源链指向 HUST 和 Life labels；既有审计记录 HUST_1-8.pkl 的 time_in_s 与 v9 不同，不得宣称两个 release 全部相同。
- online NO_GO 与 MIX_large exposure STOP 保持；本审查不支持独立泛化或性能结论。
- new_fits=0；optimizer_steps=0；forward=0；metrics=0；test_inference=0。未读取 pickle/joblib/torch payload，未新 decode。

逐文件 SHA 与检查布尔项见 review.json。
