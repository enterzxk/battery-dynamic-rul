# P1已有CP运行与检查点可接续性

结论：旧CPMLP/CPTransformer两次运行不应自动resume或重置预算。文件存在、源代码声明包含优化器/RNG状态，不等于它们是完整epoch边界或可精确接续第300步。

## 实际阶段与预算

| 模型 | epoch1批次/累计步 | epoch2批次/累计步 | epoch3批次/累计步 | 旧预算剩余 |
|---|---|---|---|---:|
| CPMLP | 146/146 | 146/292 | 8/300（partial） | 0 |
| CPTransformer | 146/146 | 146/292 | 8/300（partial） | 0 |

两次完成回执均BUDGET_EXHAUSTED_AFTER_PARTIAL_EPOCH。checkpoint_epoch_003.pt在预算截断后的第3个epoch保存，不是三个完整epoch。控制台前期按文件名推断“3完整epoch+第4中断”的说法已更正；本报告以epoch_metrics/budget_ledger实际记录为准。每个第3epoch尚有138批未完成，不能无依据跳过或重放。

源码src/experiments/cpmlp_hust_pilot.py与cptransformer_hust_pilot.py:188-227先拒绝已有completion标记，随后校验来源和预算；恢复时设start_epoch=state[epoch]+1。240-275在partial epoch后仍保存同名checkpoint，并在记录后标为partial停止。265行的保存schema含模型、Adam、Python/NumPy/Torch CPU/CUDA RNG，但没有当前epoch采样排列、batch游标或epoch_complete字段。若仅去掉完成/预算门，直接用partial checkpoint开始下一epoch会改变数据消耗轨迹，不能叫精确无损恢复。

本轮只读文本和stat。没有反序列化checkpoint、构造模型、前向或fit；checkpoint实际内部内容/兼容性未验证。机器记录保留文件大小和旧账本SHA（没有重新读取二进制计算SHA），不能把账本SHA冒充本轮checkpoint内容核验。

## 现有pilot与官方配方的区别

官方train_eval_scripts/CPMLP.sh：CALB、seed2021、LR5e-5、per-process batch16、2进程、上限100epochs、patience5、constant LR。CPTransformer.sh：MIX_large、seed2024、LR5e-5、per-process batch32、2进程、100epochs、patience5。现有两次pilot：HUST v11、seed42、LR3e-4、单GPU batch32、300步上限、custom val-only。因此它们是有效有界开发证据，不是完整论文忠实复现。

run_main.py:369-374以validation prefix-MAPE选模；utils/tools.py:103-138的EarlyStopping只在epoch>5后累计变差，平分时重置counter。新候选保留该规则，原生cell-macro Time-MAE和逐电池预测同时报告；不能为降低误差事后更换选模口径。

## 一条最小、独立的新路径（尚未获GO）

next_cpmlp_recipe_candidate.json已经具体列明一个CPMLP候选：复用已核47train/15val视图，fresh seed42，Adam/LR5e-5/constant、patience5且least_epochs5，上限100epoch；单GPU batch32仅匹配官方2x16名义全局batch，不宣称分布式数值等价。拟议独立上限1fit/14600步/1200秒，旧600步保持已消费；这是DRAFT预算，不是已分配或训练授权。

它回答“适配到HUST作者EOL任务的官方训练配方能否在完整有界运行中收敛”，不用于挽救已闭合的MATR方向A。HUST/seed42/singleGPU/val-only与官方任务或执行方式的偏离明示，不称CALB/MIX全论文复现，不访问test，也不称严格在线真实RUL。

下一动作：只创建独立runner/config，复用旧模型/预处理，加入正确早停与complete/partial checkpoint字段，做一次针对停止/保存边界的检查后由root判exact GO；不重复旧smoke、不改旧runner或检查点、不重跑旧fit。目前仍new_fits=0、optimizer_steps=0、checkpoint_contents_read=false。

## 证据

inventory_review.json含两份completion/config/runner/ledger/epoch_metrics和官方shell实际SHA、完整epoch账本摘要及6个checkpoint stat。已核当前runner/config SHA与旧完成回执相符，两个300步账本连续，3个checkpoint事件分别对应146/292/300；这只证明文本记录一致，不证明checkpoint反序列化兼容或新训练性能。
