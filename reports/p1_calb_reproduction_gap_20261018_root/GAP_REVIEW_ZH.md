# P1：官方CPMLP CALB忠实复现的首个缺口

结论：STOP_CALB_PROCESSED_DATA_AND_LABEL_STAGE_MISSING。代码与脚本存在，但项目data树没有CALB路径，两个现有HUST stage未含CALB或CALB_labels.json；不能进入模型/训练。此结论只描述已检查项目路径，不声称服务器其他项目不存在数据。

官方固定commit：3b17bb53202e10711deae0448c91f84144bb3dd9。CPMLP.sh第2–31行：CALB、seed2021、100epochs、首100cycle、LR5e-5 constant、2进程×batch16。HUST/seed42/singleGPU配方适配不等于此入口的忠实复现。

data_split_recorder.py第59–61行静态列表：17 train / 5 validation / 5 test；各列表内部唯一且两两无交集。这只证明文件名隔离，物理电池身份仍unverified，未读取任何test样本或标签。

data_loader.py第379、412–413、425行要求root/CALB/*.pkl与root/Life labels/CALB_labels.json。当前未获得/展开CALB。已保存v11 API JSON列CALB.zip大小12,671,967 bytes，MD5 2b1006e96e0ca42765a732060f964687，URL https://zenodo.org/api/records/19688272/files/CALB.zip/content。这是现有官方元数据快照，本轮未在线复核，不把旧快照当当前网络可用性。

标签压缩包data/raw/HUST/Life_labels_v11.zip已存在，stat=12,586 bytes；不重复下载。当前未打开该压缩包，不推断CALB成员、标签覆盖或版本语义已通过。

另一个执行门：run_main.py第211行构造test数据，第370行每epoch评估test。当前test锁定，不能直接执行官方入口；未来若仅做train/val适配，须如实报告偏离。官方双进程runtime本轮未检查，不能把单GPU HUST成功当双GPU忠实复现成功。

最小验证：AST literal_eval只解析三个CALB静态拆分列表；核脚本关键参数/loader路径/test调用具体行，定向stat项目data与已有stage。没有解压、pickle/torch.load、数据读取、模型构造、训练或test访问。new_fits=0、optimizer_steps=0。源SHA和URL/行号见gap_inventory.json。

下一条具体行动：先实时核公开v11 CALB元数据/响应头与当前传输预算，单次有界获取约12.7MB CALB.zip到独立目录并核官方checksum；复用已有标签包，只核归档成员名/CRC及固定17train+5val的覆盖，不打开test内容。数据/标签/asof合法性仍须后续最小检查，不能因获取成功自动训练。
