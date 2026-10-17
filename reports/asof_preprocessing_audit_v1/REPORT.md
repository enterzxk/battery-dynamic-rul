# MATR/HUST processed 预处理与 as-of 边界源码审计（v1）

日期：2026-10-16（Asia/Shanghai）；实际模型：gpt-6-luna/high。项目：/home/yndx/zxk/rul。源码为 repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9（目录 pin ID；git 不可用，未确认 HEAD）。

## 范围与标签边界

只读 AGENTS.md、两份指定中文标签/交接文档标签段和 pinned BatteryLife 源码；不读旧聊天、不扫描/加载 8GB pickle，不训练、跑性能或修改共享状态。沿用既有记录：MATR v11 169 cells 中 88 个有严格 nominal 80% crossing、81 个无 crossing 但有作者尾段标签；HUST v11 77 个均无 nominal 1.1Ah×0.8 crossing。本次未重算。动态训练 gate 仍关闭。

## 源码发现

1. **MATR 全轨迹处理。** process_scripts/preprocess_MATR.py:19-43,46-113 读取四个完整 MAT batch 和逐 cycle 结构。clean_batches (116-165) 注释称剔除未到80% cell，但实现包含硬编码删除、拼接 batch2 续段并延长 cycle_life/summary/cycles。organize_cell (168-206) 遍历完整轨迹、跳过 cycle 0，对 b1c0/b2c12/b2c44/b1c18 尾段引用下一 cycle 作序号修正；TO_DROP 列于255-262。确证是全轨迹构建和手工删选/对齐；未证现有 v11 文件由本 pinned 代码生成。

2. **HUST 全 cell 导入与时间变换。** process_scripts/preprocess_HUST.py:22-53 解压并逐 cell 读取 pickle，55-70 遍历完整 cycle 并重建容量，72-78 对 HUST_7-5 去前两 cycle 后归一化整条时间序列。time_normalization_utils.py:29-83 顺序累计各 cycle 时间偏移，122-214 在 cycle 内检测重置/大间隔。未见用最终寿命或未来 cycle 容量回写此前时间；但 cycle 内修复使用该 cycle 全部时间点。完整 cycle 后的周期级处理未显示跨后续 cycle 依赖，cycle 内时刻 as-of 安全未证。HUST_7-5 的 CycleData.cycle_number 从3起（preprocess_HUST.py:64,72-75），loader 又按列表索引重标1起（data_loader.py:456-465），需与 row_position/actual_cycle_number 对账。

3. **作者标签依赖全寿命。** process_scripts/Extract_life_labels.py:106-165 读取完整 processed cycle_data：末端 SOH≥0.825 排除；(0.8,0.825) 用末20 cycle 回归外推 0.8 EOL；≤0.8 时全轨迹找首次 crossing。这是离线标签构造，不是 prefix 特征；不能确认 v11 标签由当前代码版本生成。

4. **查询 mask 与未来 EOL 条件化。** data_loader.py:374-477 读取 processed cell 与预存 EOL；530-626 按周期提取/重采样曲线，电压除以当周期最大值，电流/容量除 nominal_capacity。未看到跨 split 输入曲线 scaler；当周期最大电压只有完整周期后才有周期级 as-of 合法性。read_samples_from_one_cell (480-528) 暂存前 early_cycle_threshold 曲线并对每个 i 设置前缀 mask，在 i≥真实 eol 时停止（501-505）。官方 collate (53-80) 将 mask 外曲线置零；因此 collate 后张量有 prefix mask 证据，而 Dataset 中间样本仍保留完整 early-threshold 曲线，绕过 collate 的消费者不自动获得相同保证。loader 排除无标签 cell（340-344）和 eol≤early_cycle_threshold cell（487-489），按真实 EOL 截停 query（501-505）。所以 query population 受未来标签条件化，prefix mask 不足以证明动态 as-of 协议合法。既有决定要求预冻绝对 observation grid，不用真实 EOL 决定查询。

5. **scaler 与实体 split。** data_loader.py:205-210,229-255 按 flag 选文件，训练 label scaler 用训练角色 unique labels 拟合，val/test 复用传入 scaler。data_split_recorder.py:1-8 列 HUST/MATR train/val/test 文件名。只能证实文件名级 split，不能证明物理电芯、continued-cell alias、跨数据集或预训练来源隔离。handoff 记录 MATR 五组已知 alias 跨 split 合并审计，但 raw serial/跨源/pretrain 未全证；本次未重跑。

## 确证与未证

**确证（静态代码层）**：全轨迹导入/构建；MATR 手工删选、续段拼接、特定尾段修正；HUST_7-5 去前两 cycle；标签逻辑读终端/尾20/全轨迹；loader early-threshold 与官方 collate mask；真实 EOL 筛 cell/query；训练角色拟合标签 scaler；split 按文件名。

**未证**：已 stage v11 的 generator commit/config；原始 source ID、完整实体 alias 和预训练重叠；processed cycle 坐标映射；cycle 内 query as-of；所有生产消费者是否执行该 collate；pinned 源码是否精确对应 v11 release。文件存在或 mask 代码不能补足这些证据。

## 最小下一动作

不加载大 pickle，只读对账现有 v11 staged 文件清单/逐文件 SHA/release manifest 与 pinned 源码 SHA；缺 generator commit/config 时保留 unverified。之后仅用已有小型 alias manifest 交叉检查 split 并列未解析实体，交主线程判断冻结协议前置条件。无训练、性能运行或 gate 开启。本报告不替代主线程科学 GO/STOP；动态训练 gate 继续关闭。