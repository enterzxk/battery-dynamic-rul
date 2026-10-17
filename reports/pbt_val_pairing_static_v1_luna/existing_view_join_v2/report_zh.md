# HUSTval15 existing-view exact join v2

## 结果

15/15 个 pinned PBT HUST validation 文件名与 v11 stage manifest 的 curve SHA、CPMLP trainval view manifest 中同名文件 SHA 完全一致；15/15 文件名也在现存 trainval labels JSON 精确命中 EOL 值。逐项记录见 hustval15_static_pairing.csv。

DKP 受限回执确认 HUST val key 集合覆盖 15/15、missing 0；receipt 省略 key 名，静态 shape inventory 也不含数组对应的 dictionary key。因此每行列出 loader 规则派生的预期 DKP key（basename 去掉 .pkl）和 aggregate receipt 状态；receipt 中逐 cell key/value 映射仍不可核验。没有新 decode。

## Prefix 与配置的静态投影

Pinned finetune_PBT.sh 设置 seq_len=1、early_cycle_threshold=100。15 个 EOL 值均大于100；如果每个源文件可用 cycle 至少100，源码 loop 投影为每 cell 100个 prefix（i=1..100）、总计1500，mask 长度100且前 i 位为1。Pinned evaluate_model.py 默认 eval_cycle_min=max=10；如使用默认值且第10个 prefix存在，预期每 cell 1行（总15）。finetune_PBT.sh 没有传入 eval_cycle_min/max，因此评估默认值不等于冻结的本次调用配置。prefix_projection.csv 是条件静态投影，不是 PBT 运行时或 collate 证明。

CPMLP 的既存 preflight view 记载同一15个 val cell 每 cell 100 prefix（preflight JSON SHA256 07c2d9bbe13385885d71d4cf726d9c4e9f47cdc5d8b6ad1500c21a3459d677e8）；该证据来自另一个 loader/实验，不能替代 PBT prefix 或 collate 审核。

## 来源和边界

数据来源来自：
- /home/yndx/zxk/rul/repos/pinned/PBT_122077bc5435bb0ba5406f2b112fa96903a08c6a/data_provider/data_split_recorder.py，SHA256 70a14cd0e482f81314fa4c0e86d3233d2ebba59b54cb07df630a7513a5ea9c08，HUST_val_files 行5。
- /home/yndx/zxk/rul/data/source_audit/stage_v11_hust_v11_labels/stage_manifest.json，SHA256 656ed7b923ef82e55cb0cd8860afb2ec66d91366d4c1b5ba9f1c62786e337635。
- /home/yndx/zxk/rul/experiments/cpmlp_hust_pilot_seed42/input_trainval/view_manifest.json，SHA256 5d215aac95ae30f40b01c8fba7c43d5f78a81e15904a979cc4972809be808b47；label view JSON SHA256 ccb0d9b03f555aacbbd8a2ff9a03d536a5927ff11da99545ef747c4f80ea8cad。其 source label SHA256 为 16b001dae3df31871e91998f5e5c1d20440778747bc66a04c89a873614381513。
- /home/yndx/zxk/rul/reports/pbt_validation_loader_candidate_v3/restricted_decode_receipt.json，SHA256 f6f1507589aa9f14ec1506500c150c90e87592288ea3fc215103312bbcd68912。
- /home/yndx/zxk/rul/repos/pinned/PBT_122077bc5435bb0ba5406f2b112fa96903a08c6a/data_provider/data_loader.py，SHA256 86d70a40e33f12c843abf856dcbbc29b823b78928a758c8fee6788118565756a；pair appends 行904-920、prefix/mask/label 行1114-1177、collate 行163-193。
- PBT finetune_PBT.sh 行9-10、evaluate_model.py 行485-497，静态配置如上。

v11 source content audit 报告唯一 v9/v11 变更成员为 HUST_1-8.pkl；本次该 val cell 用 v11 stage manifest hash 5e952df3d8f00e32c8d11591e97fbdf79866f54d196618c88050aa0b407105e2。不能宣称两个 release 全部相同。

本任务只补强来源 hash/label metadata 配对。曲线和 EOL 内部语义、PBT 运行时 prefix、DKP 单键映射、collate 实际形状/值仍未核实。full-EOL筛选仅属于 R_author retrospective；O_strict_online 仍缺 as-of/censoring 设计。MIX_large exposure/物理 ID未闭环，独立泛化 STOP 保持，GO/STOP由root掌握。

本次仅读现存小 JSON/静态源码配置，没有读 pickle/joblib/torch payload，没有新 decode、模型构造/strict-load/forward/metrics/训练/测试推理。new_fits=0；optimizer_steps=0；forward=0；metrics=0；test_inference=0。
