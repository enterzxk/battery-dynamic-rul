# CALB完整train/val数据集与定向batch检查

结论：完整pinned Dataset_original train/val各初始化一次，实际增强路径运行，读取固定22不同PKL；样本数1689/497、逐cell99/100分布、shared train-only label scaler均在首轮batch断言前通过。首轮最后断言把官方标签batch形状[32,1]误写成[32]而失败，failure_receipt和原脚本/执行回执原样保留，不将首次执行exit1改写为整轮成功。

最小修复只从首个真实训练电池CALB_35_B229前32prefix重建官方getitem/collate输入视图，使用首轮已经拟合的参数进行数值变换；未再调用Dataset_original.__init__、没有全cohort重跑或scaler refit。

|项|实际结果|
|---|---|
|train / val样本|1689 / 497|
|曲线batch|[32,100,3,300]|
|mask|[32,100]|
|标签|[32,1]|
|其他4个返回张量|各[32]|
|batch有限值 / masked未来槽|通过 / 全零|
|标签逆变换|与该电池作者EOL吻合，误差<=1e-4|

归一化：label StandardScaler只拟合17个train unique EOL，mean852.2941176470588、scale532.4366590006279；validation复用同一个scaler对象，初始化前后参数不变。源码另对1689个训练class_labels拟合life_class_scaler，共2次预处理scaler fit，均在train_init；这是预处理统计拟合，predictive_model_fits=0、optimizer_steps=0。定向修复新增scaler fit0。

范围：真实增强helper已运行，未使用identity stub；batch修复是单真实电池的官方getitem/collate视图而非再次初始化全数据集。未建立test Dataset、未读test PKL或数值标签，未构造预测模型/执行推理。物理身份/strict在线标签/generator、官方2GPU/test入口忠实性及新fit授权仍未闭合。

证据：targeted_batch_check.json、check_targeted_batch.py，原目录check_dataset.py/failure_receipt.json/execution_receipt.json；均有stage/decoder/loader/source SHA。单GPU/val-only后续若运行，应明确称CALB作者EOL官方配方适配，不称完整论文复现。

下一步：Prepare independent CALB seed2021 official-recipe singleGPU train/val-only runner/config by minimally adapting reviewed HUST recipe; freeze candidate1fit/5200steps(52batches*100epochs)/1200s, exact source/stage/typed-decoder bindings and failure/stop rules. Root must issue fresh scoped GO only if data/runtime/budget gates satisfied; never reuse consumed HUST GO, no test or full2GPU-fidelity claim.
