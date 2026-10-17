# BatteryLife / PBT 基线与协议首轮审计

审计日期：2026-10-16（Asia/Shanghai）  
状态：**首轮官方材料核验完成；数据下载、训练、模型运行、性能指标均 NOT_RUN。**

## 核心结论

BatteryLife 的 CPMLP、CPTransformer，以及 PBT（Pretrained Battery Transformer）官方协议都是“用早期循环预测整块电池的总循环寿命/EOL cycle life”，不等于动态 RUL。BatteryLife 论文把输入定义为首 S 个循环（S≤100），输出为标量 y；通常以 SOH 首次不高于额定容量 80% 时的循环数为标签，CALB 使用 90% 并按其规定以 Q1 为基准。[BatteryLife 论文任务定义](https://arxiv.org/html/2502.18807)

若动态 RUL 定义为观测到第 i 个循环时的剩余循环数，目标应是 RUL_i=EOL−i。官方数据加载器在每个前缀样本都追加相同 eol，没有减去当前 i，因此不能把 CP* 或 PBT 结果报告为 dynamic-RUL 结果。

## 简称消歧

- **BatteryLife** 是 Tan 等人在 KDD 2025 的 *BatteryLife: A Comprehensive Dataset and Benchmark for Battery Life Prediction* 和作者[官方仓库](https://github.com/Ruifeng-Tan/BatteryLife)。CPMLP、CPTransformer 是 CyclePatch 家族模型。
- **PBT** 在本次核验范围内指 Tan 等人的 *Pretrained Battery Transformer: A foundation model for battery life prediction*，作者[官方仓库](https://github.com/Ruifeng-Tan/PBT)，论文发表于 EES 2026。README 明确是用首 N≤100 个循环早期预测 cycle life。
- Microsoft 的 [BatteryML](https://github.com/microsoft/BatteryML) 是另一个独立项目，设有单独 RUL benchmark。不要混用 BatteryML 的 RUL、BatteryLife 的 early BLP 和 PBT 的 cycle-life 任务。

## 代码与标签核验

官方 [CPMLP.sh](https://raw.githubusercontent.com/Ruifeng-Tan/BatteryLife/main/train_eval_scripts/CPMLP.sh) 使用 early_cycle_threshold=100、MSE、c_out=1、默认 CALB、双进程；[CPTransformer.sh](https://raw.githubusercontent.com/Ruifeng-Tan/BatteryLife/main/train_eval_scripts/CPTransformer.sh) 使用同一 100 周期阈值、MSE、双进程，默认 MIX_large。task_name=classification 是训练框架参数名；两个模型的输出头都是单一标量，不能据此推断为分类任务。

官方 [data_loader.py](https://raw.githubusercontent.com/Ruifeng-Tan/BatteryLife/main/data_provider/data_loader.py) 从 Life labels JSON 读取 cell 的 eol；为同一 cell 建立不同的早期前缀掩码，并执行 labels.append(eol)。每块电池可产生许多高度重叠的 prefix rows，标签仍然相同。仓库 [split recorder](https://raw.githubusercontent.com/Ruifeng-Tan/BatteryLife/main/data_provider/data_split_recorder.py) 按电池文件列出划分。应按 cell 留出和汇总，不能把同一电池的每个前缀当独立电池。把标签改成 EOL−i 或固定单一预测时点，都属于新的动态 RUL 协议。

论文标签规则也需与代码版本共同固定：通常使用实测 EOL；若最终 SOH 高于阈值 λ+2.5% 则排除；最终 SOH 在 (λ, λ+2.5%] 时线性外推。除 CALB 外 λ=80%，CALB 的 λ=90%，并以 Q1 作为 Q0。[论文实验设置](https://arxiv.org/html/2502.18807)

## MATR / HUST 来源、标签、拆分与许可

| 数据集 | 来源、标签和拆分 | 许可审计 |
|---|---|---|
| HUST | 作者 README 指向 Mendeley。v2 DOI 10.17632/nsc7hnsg4s.2 记录描述 77 个 1.1 Ah LFP/石墨电芯、30°C、同一充电与不同多阶段放电协议。[Mendeley 数据记录](https://data.mendeley.com/datasets/nsc7hnsg4s/2) BatteryLife loader 从 Life labels 取 EOL 标签，HUST cell 文件显式列在 split recorder；服务器实际文件和标签分布未核。 | Mendeley 页面标注 CC BY 4.0。BatteryLife README 要求使用处理后的 HUST 时同时引用 BatteryML 和原始数据论文。 |
| MATR | BatteryLife README 指向 data.matr.io；论文表中列 169 块，而 Severson 较早数据常见 124 块，数据版本和纳入来源须锁定。MATR train/val/test 按 cell 文件清单划分，标签从 Life labels JSON 读取；服务器实际数据未核。[作者数据索引](https://github.com/Ruifeng-Tan/BatteryLife) [MATR 官方门户](https://data.matr.io/) | 官方门户的部分研究数据项列 CC BY 4.0，但当前网页抽取对具体项目只返回 JavaScript 壳。BatteryLife 聚合多个来源/批次，必须在实际下载项逐个确认条款。代码 MIT license 不涵盖数据。 |

BatteryLife README 说明处理后的 MATR/HUST 预处理依赖 BatteryML，并要求引用 BatteryML 与原始实验论文。公开下载不自动等于任意再分发权，应记录数据自己的 license/terms、版本、归档和 SHA256。

## 可执行复现路径（计划，NOT_RUN）

服务器已有作者仓库 ZIP 快照；本次未下载数据。主代理此前提供 a40_env 的 Python 3.9 / PyTorch 2.5.1 / CUDA 12.1 信息；我未安装依赖，也未核验实时 GPU、共享锁或预算。官方脚本默认双进程，运行前由主代理确认 GPU 数量和共享状态。

若复现**官方早期总寿命**基线，先从官方渠道取得处理后的 HUST 或 MATR 与对应 Life labels，核查实际文件和官方 cell split 清单一致；在 run-local 副本中只改 dataset、root_path、checkpoint 目录，保留并记录其余参数，再执行：

~~~bash
cd /home/yndx/zxk/rul/repos/audit/BatteryLife-main/BatteryLife-main
# 前置：在主代理许可的隔离数据目录放置官方数据和 Life labels，并记录 SHA256
# run-local script copy 设置 dataset=HUST（或 MATR）、root_path 和 checkpoint 目录
bash train_eval_scripts/CPMLP.sh
# 或
bash train_eval_scripts/CPTransformer.sh
~~~

这些命令会训练模型，本次没有执行。种子、超参数和双进程设置应按论文 appendix / assets/Selected_hyperparameters.md 固定；脚本默认值不代表每个数据集的最优复现参数。若目标确为动态 RUL，应先建立独立的 EOL_cycle−observed_cycle 标签、cell-level split 和评价方案；这不是 BatteryLife/PBT 原始基线复现。

PBT README 要求其他处理数据用 BatteryLife v9，另用修正版 Zn-coin/CALB 和 cycle-life labels；scripts/PBT.sh 是预训练入口。本次未下载 PBT 数据，不把它列为 HUST/MATR 动态 RUL 的直接复现命令。

## 状态与产物

- 训练、评估、模型指标：NOT_RUN；无性能提升结论。
- 数据下载、解压、存在性及标签文件检查：NOT_RUN / NOT_VERIFIED。
- BatteryLife 快照：/home/yndx/zxk/rul/repos/audit/BatteryLife-main.zip；SHA256 aab91f6e8c02f446203307157d78c89b6ea4187de84b19f410564c03f340fb82。
- PBT 快照：/home/yndx/zxk/rul/repos/audit/PBT-main.zip；SHA256 693e0290caf39c5d70e6ad90b44ce7c96698eae18e66f484bec5c5b23d4f4dd9。
- 机器证据：baseline_audit_evidence.json；协议草案：/home/yndx/zxk/rul/configs/protocols/draft_baseline_audit/draft_baseline_protocol.json。
- ZIP 是 main 分支时点快照，没有 immutable Git commit SHA；后续须锁具体 commit 并复核代码、split 和 label 文件哈希。


### 官方 cell 划分静态核对

我用 Python 3.9 对保存的官方 split recorder 做 AST 字面量解析（未导入/执行训练代码、未读取数据）。HUST 为 train/val/test = 47/15/15，MATR 为 102/34/33；两组各自三个文件名集合两两无交集。可复核脚本在 /home/yndx/zxk/rul/repos/audit/check_batterylife_split_disjointness.py，证据同时写入 baseline_audit_evidence.json。此结果只证明官方清单字符串两两不重叠，未证明服务器数据文件存在、内容正确或不同命名是否指向同一物理电芯。

