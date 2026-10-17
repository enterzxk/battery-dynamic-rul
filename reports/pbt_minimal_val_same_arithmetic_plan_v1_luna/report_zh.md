# PBT HUSTval15 同算术最小方案（inactive）

状态：INACTIVE_FOR_ROOT_DECISION。该文件把可裁决的边界、依赖、输入、输出和未来预算具体化；不授权执行，也不替主控作科学 GO/STOP 决定。当前 active contract 是 v4，执行门全部关闭。

## 固定目标与人口

目标只限回顾性 author estimated-total-EOL lane 的 pinned HUST_val_files 15 个电芯。名单来自 pinned PBT data_split_recorder.py 第5行及现有 pairing CSV；CSV 同时列出 label EOL 元数据，但这些数字不是已经验证的运行时 EOL 或 valid_cycle_number。15 个身份见 plan.json。

现有 evidence 只能支持 aggregate DKP 15/15 covered。receipt 不含 key names，CSV 的每行 exact-per-cell-receipt 为空。Loader 按 data_loader.py:902-907 从文件名去除 .pkl 后查 DKP；:918-920 查不到时静默填零向量。因此必须先证明 15 个具体键与数组逐项绑定，不能把 loader lookup 规则或 aggregate count 当成绑定证据。

## Namespace 与参数冻结原则

PBT 的 config wrapper 在 configuration_BatteryLifeLLM.py:19-29 保存 args 并原样返回 argparse.Namespace；config_output_audit 还指出 evaluator 先读 checkpoint args 再覆盖 CLI model、dataset、batch_size、root_path、num_workers 和 target_dataset 条件字段。当前没有读取或核实该 checkpoint args 内容，不能推定有效 Namespace。

固定源码能提供字段集合和部分声明值，但不能给出该次 HUSTval15 run 的全部实际值。models/PBT.py 的 configs 字段包括 task_name、维度、MoE 专家数、LLM_path、pca_path、topK/use_dff_scale/min_d_ff 等；完整列表及行号在 plan.json。PBT finetune shell 声明 seq_len=1、early_cycle_threshold=100；evaluate_model parser 的 seq_len default 是5，early threshold default是100。checkpoint args 和 CLI 可覆盖它们，故 shell 声明不是有效运行值。evaluate parser 的 dataset/data 默认 HUST/BatteryLifeLLM，eval_cycle_min/max 默认10/10，但示例 evaluate_model.sh 实际显式设 ISU_ILCC 和1..100。active HUST Namespace、args_path、root_path、LLM_path、PCA 路径、batch_size、mask/config字段均未冻。计划建议未来独立 val-only harness 显式冻结 HUST/PBT 与10/10窗口；这只是待根批准的计划值，不声称当前 active 值如此。

## 同算术定义

- 数据生成必须保持 pinned loader 的源逻辑：read_cell_df 用 len(cycle_data) 产生 valid_cycle_number（data_loader.py:1052-1053）；样本逻辑在 :1114-1177 执行 EOL/df筛选、prefix loop、valid-cycle break、EOL break、mask 生成和 eval 范围筛选。若未来把 eval 窗口明确固定为10/10，最多为每个合格电芯取 i=10，15个是上限不是保证值。要证明完整15行仍需逐 cell key/cycle和运行时 row/mask。
- 原 dataloader factory 对非 lookup PBT 静态选择 my_collate_fn_withId（data_factory.py:241-249）；data_loader.py:163-194 静态定义 stack、mask清零和字段顺序。它不证明运行时张量、shape或键对齐。计划必须保留该原实现，不能借用 CPMLP loader。
- 精度保留作者 mixed_precision bf16（evaluate_model.sh:28-38）和 PBT forward 内对 curve/mask/DKP 的 bfloat16 转换（PBT.py:585-588）。不改 FP32，不删 DKP，不做 CPU 算子替代。
- 只取模型返回 tuple 第0项 preds[:B]（PBT.py:637-641），再按固定 scaler 反变换 y_cycles = y_scaled × 765.6855681613043 + 879.4115308151094（evaluate_model.py:655-656,770-771；静态 scaler receipt）。该输出仍是 retrospective total-EOL cycles，不是 dynamic RUL。任何未来指标最多一次、对完整15个合格电芯做 case-equal MAE。

## Constructor / import 风险与禁止路径

inactive proposal 只删三处：AutoTokenizer 创建（PBT.py:487-493）、padding_side赋值（:498）、pickle PCA载入（:519）。虽然静态直接引用审计只在 constructor 看到这些字段，RNG消耗、hooks、module/parameter注册、全局状态、tokenizer/PCA metadata影响和原/候选对象等价仍未证。import closure v2 与 independent review 只证明受限项目源码 AST 闭包和已知模块体effects；不穷尽动态/原生/第三方传递行为。Transformers 的 Llama/GPT lazy exports、patched Llama 实现、trust_remote_code 本地资产和实际 tokenizer/model metadata 均未被检查。requirements 与选定环境版本不同；evaluate、reformer_pytorch、wandb 等直接 import 无法静态定位。不要安装或静默切换环境，环境/patch身份不清即停止。

不要直接跑官方 evaluate_model.py：源码会构建 test_data/test_loader（:658-674），用 joblib.load 读 label_scaler（:655），并调用 load_checkpoint_in_model 和 accelerator.prepare（:706-707）。它不是 val-only 且当前执行权限明确关闭。未来只能另立根审查过的 val-only harness；本轮不创建、不运行。

## 未来阶段与上限

plan.json 把每阶段的数据上限、预算和停止条件写全。简要顺序是先复核现有小 JSON/CSV；再由 root 决定是否单独批准最多15个 key身份/present-missing receipt；之后才可另行决定读取最多15个 valid-cycle 计数，优先已有 hash-bound manifest，若格式必须 ordinary pickle/joblib/torch.load 就停止；随后再申请最多15个 val-only prefix/mask/collate row receipts。只有 G2/G3闭合且 root 单独通过 G4，才可考虑最多15个输入样本的一次 forward pass，并且最多算一次完整15-cell case-equal MAE。所有未来执行、forward和metrics授权当前都为 false；没有 fit、optimizer step、test或其他 split。历史 2 fits / 600 optimizer steps 保持原账，不扩增。

本轮只读已列小型 JSON/CSV 与源码，没有读 checkpoint、PCA、tokenizer assets 或其它二进制，没有 import/构造/strictload/forward/metrics/test/fit。active v4 当前仍报告 G2 partial、G3未闭合；缺项均按未冻/未证处理。