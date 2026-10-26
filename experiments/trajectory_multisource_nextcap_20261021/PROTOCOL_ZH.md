# F1/F2/F3 下一源 RPT 容量扩展（准备态）

问题：在完全相同的 V18 query、到达 arm、下一源 RPT 容量标签及查询到目标的 horizon 下，正式多源缓存的 RPT、Cycling 或二者联合特征，是否改善 F0 强基线的下一容量点预测？

复用已成功的正式 2x2 run2_clocksafe 预拟合特征缓存：F1=686维、F2=98维、F3=710维。正式缓存按 query 行保存；本 runner 只读缓存，不重复提取曲线/循环特征。按缓存行键 (cell_id, arm, query_epoch) 与冻结 B targets.py::build_targets 输出对齐；只保留 next_capacity_ah 非空且 next_query_elapsed_weeks 为正的行。模型输入为对应缓存矩阵加一个显式预测 horizon 特征 next_query_elapsed_weeks，目标容量只作监督。实际未来容量及未来操作/曲线数据不进入特征。

拟合预算严格为 18 次：F1/F2/F3 × HGB/CatBoost；每个组合两次 seed42 电芯隔离 OOF 拟合加一次全 C1/C2 拟合。训练权重每个电芯总质量为一。OOF residual RMS 用作该模型组合的容量尺度。全部 18 次拟合完成后才能开始任何 C3 推断。HGB/CatBoost 参数沿用冻结强基线，不做调参、早停、重新拟合 F0、C3 选择或 C4 读取。CPU 串行，线程上限 4，并在任何 numpy/sklearn/catboost 导入前设置 OMP/MKL/OpenBLAS 线程环境。

GO 必须在执行前由总控精确签发，绑定本代码/协议 SHA、成功的 formal-cache receipt SHA、5 个缓存文件 SHA、V18/DataV2/cohort/target builder SHA、owner、预算、模型参数、运行时上限和全新输出目录。runner 先校验 GO、owner、缓存与数据清单，取得既有 CPU 锁，再读训练/开发 payload 重建冻结目标。该准备目录当前无 GO，不可启动。

主要分数 cell-equal RMSE = sqrt(mean_cell(mean_query(error^2)))、cell-equal MAE 和基于训练 OOF sigma 的描述性 Gaussian NLL；保存逐 query、逐 cell 指标。结果是 C3 development evidence。与已有 F0 strong-baseline run2 在相同键比较；F0 的 6 次拟合不重跑。不得将 next-capacity NLL 与 B 的 teacher-forced trajectory NLL 合并解释。


执行账本：每次拟合先原子落盘 STARTED 记录，再调用 .fit；成功或异常后更新为终态，并在进度与最终 receipt 中分别记录 its_started、its_completed 和成功的 it_count。runner 按 GO 的 max_runtime_seconds 设置进程级定时器并逐次检查单调时钟；超时使任务失败，不再启动新拟合。最终全训练模型写入 inal_models.joblib，训练 OOF 逐行预测/残差及按电芯校准信息写入 oof_calibration.joblib，只在全部 18 次拟合完成后保存模型并启动 C3 推断。每份运行 receipt 绑定 GO 文件 SHA256 与 request_id。GO_TEMPLATE.json 是不可执行模板（TEMPLATE_ONLY / allow_fit=false）；总控需签发新的精确 GO。
