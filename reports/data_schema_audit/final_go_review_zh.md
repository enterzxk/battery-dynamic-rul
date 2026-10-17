# CPMLP HUST v11 首次拟合前审阅

审阅结论：**静态审计未发现阻止首次 pilot fit 的 P1**。这不是启动授权或运行结果；主线程仍需检查 GPU、竞争进程和锁状态。本次没有加载数据、运行 runner、创建 optimizer 或执行训练（new_fits=0，optimizer_steps=0）。

runner SHA-256 64b4f517cc9089f8702cc60fb41e9bdd1bc19924dc02e7344bbadbb8a5ff5529；冻结配置 SHA-256 e22102c87e73a0e5dc67a064d082ecf61f4dae65394efe7801374465be1793fa；BatteryLife commit 3b17bb53202e10711deae0448c91f84144bb3dd9。配置状态 FROZEN_PILOT 且 training_authorized=true，语义为官方 total EOL。预算为 300 optimizer steps、10 epochs、600 秒；split 为 47/15/15 个电芯。现有输入视图实际有且仅有 train+validation 的 62 个 HUST 文件，无测试文件。labels 实际 SHA-256 ccb0d9b03f555aacbbd8a2ff9a03d536a5927ff11da99545ef747c4f80ea8cad 与 view manifest 一致；view 指向的 stage manifest SHA-256 656ed7b923ef82e55cb0cd8860afb2ec66d91366d4c1b5ba9f1c62786e337635 与实际文件一致。

runner 静态包含未授权 fit 拒绝、fit/preflight 互斥、逐 pickle 路径与 SHA 限定；恢复时核验 config/stage/view/repository/seed，且无 epoch checkpoint、已完成、哈希不匹配、预算耗尽或 ledger 超过 checkpoint 时拒绝恢复。checkpoint 保存和恢复 Python、NumPy、Torch CPU/CUDA RNG。恢复只覆盖 epoch 边界；不承诺硬崩溃逐 step 精确恢复。

runner 锁定测试集，以全体 validation prefixes 的 MAPE 选择，并同时报告 native cell-macro MAE/MAPE。此 pilot 是 HUST v11 total-EOL 开发实验，不是动态 RUL，也不是完整 MIX 论文复现。GPU 与锁的实时检查不在本次范围。

机器可读证据见 final_go_review.json。
