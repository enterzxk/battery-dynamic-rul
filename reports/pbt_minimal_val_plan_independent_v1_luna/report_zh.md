# PBT HUSTval15 同算术最小方案独立审查

**Verdict：`PASS_PLAN_SPECIFICITY_WITH_BLOCKING_EVIDENCE_GAPS`。** 该 inactive 方案足够具体，可供 root 按阶段裁决；仅支持“计划边界清楚、未来门控可审”的结论。它不代表执行授权、执行准备完成、科学 GO、模型表现或模型验收。

方案及交付身份已核对：`plan.json` SHA-256 `7095dbeb7df5a1d18838eaabf62af5dae1756087697851b979eb9cd6b74b9155`；`report_zh.md` SHA-256 `4c08da5ea0bd2ca2cb1adcd75f6b2da193b109975c8649f3c1a6f86b59e9870f`。23/23 个 evidence reference 当前 SHA 全部匹配，逐项清单见同目录 `review.json`。

## 支持该判定的事实

- pinned `data_split_recorder.py:5` 与 pairing CSV 的 HUST_val 文件名单及顺序一致，范围为 15 个 validation cell。目标明确限定回顾性 author estimated-total-EOL；不偷换成 online dynamic RUL 或独立泛化。
- 方案指出 Namespace 不能从 parser default 或 finetune shell 推定：checkpoint args 会被 CLI 覆盖；目标 run 的完整有效 args 与 root path 未知。把 HUST 和 10/10 作为未来显式固定值的建议清楚标记为提案。
- `data_loader.py:902-920` 按 `.pkl` 文件名去后缀查 DKP；找不到会填零向量。join receipt 的 15/15 是 aggregate coverage，receipt 不含 key names，CSV逐 cell exact receipt 为空，所以不能称 exact binding。
- `data_loader.py:1052-1053,1114-1177` 显示 row 10 受 valid cycle length、EOL、NaN、数据集mask和eval范围条件约束。prefix projection 是条件推演；实际 eligible rows、masks、collate IDs/shapes 都未观测。
- 同算术约束清楚保留 bf16 输入路径、DKP、模型输出 tuple 第0项 `preds[:B]`，以及既有 scaler 的反变换参数。它只固定算术提议，不证明运行时设备算子支持或数值表现。
- 官方 `evaluate_model.py` 路径构造 test loader、调用 `joblib.load` 读 scaler，并走 checkpoint load/accelerator prepare；方案正确拒绝直接运行。inactive constructor 省略 tokenizer 与 PCA 的对象副作用等价、严格安全加载路径和实际 completion 仍未证明。
- 当前预算为全零；未来各阶段上限明确是未授权的提议上限。阶段执行必须另经 root 决定，不可从本 PASS 推导许可。

## 阻塞项

逐 cell DKP key-to-array 绑定、15 个 valid cycle count、有效 checkpoint Namespace/CLI/root、真实 row/mask/collate receipt、constructor omission 的 RNG/hooks/module registration/global state/metadata 等价、依赖版本与缺失包闭环、patched Llama/tokenizer/model 资产身份、安全 val-only strict loader 与 strict-load 结果，均未完成或未证。缺失项应保持 `unverified`，不能靠已存在文件或旧 source PASS 补足。

因此，root 可把本方案作为分阶段裁决材料；在 G2/G3 补证、G4 单独审查并显式批准前，模型构造、strict load、forward、metrics、fit、test 仍保持关闭。此审查没有更改 root GO/STOP，也没有给任何未来阶段授权。

## 审查边界

只读项目 `AGENTS.md`、`./rul.sh status`、方案列出的23项小型JSON/CSV与固定源码指定行。未读binary/checkpoint/PCA/tokenizer资产；未做普通pickle/joblib/torch.load；未调用newdecode195；未import模型或依赖；未构造、加载、forward、算指标、fit或test。没有重做旧1447/scaler/finite审计。计数：`new_fits=0`，`optimizer_steps=0`，`forward=0`，`metrics=0`，`test=0`。
