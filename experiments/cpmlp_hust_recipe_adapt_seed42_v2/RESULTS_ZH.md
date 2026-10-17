# HUST CPMLP完整配方适配：真实运行结果

结果：**EARLY_STOP_COMPLETED**，10个完整且验证完成的epoch、1460个优化器步骤，按冻结validation prefix-MAPE选择epoch3。cell-macro EOL-MAE=194.0072637533 cycles，MAPE=0.1013675481，bias=-34.9643999837 cycles。15个验证源ID、每电池100个早期prefix，共1500条原始预测。任务是作者总EOL，不是动态真实RUL。

## 科学判定

新结果相比旧CPMLP短pilot的177.3830694173 cycles差9.3719%，仅6/15电池MAE下降；本轮没有性能提升。旧CPTransformer短pilot204.5937与train-median343.6667只作已有开发参考，不是匹配训练预算的新确认对照。新旧学习率、训练时长和初始化RNG消耗顺序不同，不能把差异单独归因于学习率或100epoch上限；同一个15电池validation又用于选模，不能当独立确认。

| 完整epoch | 累计steps | validation EOL-MAE | validation prefix-MAPE | early-stop counter |
|---|---:|---:|---:|---:|
| 1 | 146 | 252.8721 | 0.137820 | 0 |
| 2 | 292 | 201.0238 | 0.106479 | 0 |
| 3 | 438 | 194.0073 | 0.101368 | 0 |
| 4 | 584 | 215.1206 | 0.114980 | 0 |
| 5 | 730 | 213.2632 | 0.113452 | 0 |
| 6 | 876 | 218.3814 | 0.117983 | 1 |
| 7 | 1022 | 216.4727 | 0.114231 | 2 |
| 8 | 1168 | 217.8938 | 0.118491 | 3 |
| 9 | 1314 | 227.3522 | 0.124138 | 4 |
| 10 | 1460 | 241.7783 | 0.132909 | 5 |

官方脚本训练配方的适配：Adam、LR5e-5、constant LR、patience5且epoch>5才累计变差，ties重置counter，上限100epochs；单GPU batch32仅匹配官方CPMLP shell2x16名义全局batch。HUST/seed42/singleGPU/val-only均明示偏离原CALB/seed2021/2GPU执行方式，不称完整论文忠实复现。未加载旧checkpoint，也未重放旧300步。

## 失败保留与实际预算

v1首次启动在导入数据加载器时因a40_env缺batteryml失败，failure_receipt实际fit_attempts=0、optimizer_steps=0、epoch0，原claim/GO/日志完整保留。没有清除旧claim或重跑v1。v2只改输出目录，config字节一致，切换到项目已有BatteryLife Python3.9环境，版本与旧pilot一致且batteryml可用；没有安装包或修改全局环境。root单独绑定最小运行时修复，沿用未消费1fit预算，没有扩大14600步/1200秒上限。

成功子进程实际wall126.79秒（runner126.21秒），受父启动器1200秒timeout保护；实际消费1fit/1460steps。旧CP两fit/600steps保持已消费，当前神经网络训练合计3fits/2060steps；MATR41个CPU拟合/0梯度步另列，PBT消费预算不变。失败启动不能记成成功fit，也不能隐去。

## 最小验证与原始证据

独立review为PASS_SCOPED_HUST_RECIPE_ONLY，root修复了验证阶段deadline边界；只做一次原早停/partial元数据逻辑检查及一次针对新增deadline缺口的检查，没有重跑旧数据smoke。root复核v2仅输出路径改动，独审核心代码和停止检查复用。

independent_metrics.json从已选CSV独立重算15电池/1500prefix MAE、MAPE与bias，全部与receipt吻合；作者整数标签roundtrip误差为0。1460条step账本连续，fit_started1条，10个epoch均146批、epoch_complete及validation_complete=true。未使用测试集。checkpoint没有上传公开镜像。

## 误差上升的位置

| 电池 | 旧pilot MAE | 新配方MAE | 旧减新（正为改善） |
|---|---:|---:|---:|
| HUST_2-8.pkl | 114.622 | 377.596 | -262.974 |
| HUST_10-1.pkl | 82.593 | 223.600 | -141.007 |
| HUST_9-1.pkl | 85.624 | 206.396 | -120.772 |
| HUST_10-8.pkl | 160.902 | 233.078 | -72.176 |
| HUST_7-4.pkl | 35.630 | 90.260 | -54.630 |
| HUST_7-8.pkl | 200.805 | 237.600 | -36.794 |
| HUST_2-3.pkl | 101.264 | 108.962 | -7.698 |
| HUST_3-8.pkl | 87.461 | 94.451 | -6.989 |
| HUST_5-7.pkl | 18.360 | 19.785 | -1.425 |
| HUST_7-6.pkl | 55.351 | 53.382 | 1.969 |
| HUST_8-3.pkl | 414.689 | 410.061 | 4.628 |
| HUST_6-8.pkl | 88.629 | 29.937 | 58.692 |
| HUST_5-2.pkl | 190.574 | 127.718 | 62.856 |
| HUST_5-5.pkl | 135.468 | 30.389 | 105.079 |
| HUST_1-8.pkl | 888.773 | 666.895 | 221.878 |

数据与结论限制保持：HUST作者估计总EOL、文件名split、完整物理serial/实际生成器/as-of例外尚有限制；不称严格在线、真实阈值RUL或物理独立泛化。MATR方向A的CLOSED_NO_GAIN不受本次基线运行影响。

原运行命令（invocation已消费，不得直接重跑）：`OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 CUDA_VISIBLE_DEVICES=0 /home/yndx/zxk/rul/automation/venvs/batterylife/bin/python /home/yndx/zxk/rul/experiments/cpmlp_hust_recipe_adapt_seed42_v2/runner.py --fit`。ROOT_GO绑定代码/配置/数据视图/模型/loader SHA及独审；重算程序independent_metric_recompute.py与原预测CSV可检查指标，不能借其绕过一次性fit门。

下一步仅用既有新旧预测分解电池/早期prefix位置的误差上升，不改seed、模型或训练预算来救结果。
