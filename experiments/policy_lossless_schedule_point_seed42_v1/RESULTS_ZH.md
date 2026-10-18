# 可逆原始schedule点预测对照：平均改善9.27%，联合门槛未通过

## 已执行
相同42fit/10cal、22281/4567前缀、seed42、logRUL目标、电池等权及固定HGB参数，仅将4项积分工况替换为可逆canonical schedule的4电流+3SOC切点，与age/SOH/robust20组成10输入。仅1次新CPUfit与1次cal预测，0旧checkpoint加载/新尺度/OOF/devtest。预GO独立窄审PASS及主控fresh exactGO均已消费。

判定：NO_GO_FOR_LOSSLESS_POLICY_MODEL_OR_SEED_EXPANSION_SINGLEFIT_MEAN_GAIN_ONLY。平均MAE真实改善，但冻结联合gateFAIL；不把正向均值写成稳定确认，也不抹掉实际收益。

| Cell-equal指标 | 原压缩工况点 | 可逆schedule点 |
|---|---:|---:|
| Time-MAE/cycle | 36.400814 | 33.027239 |
| bias/cycle | -3.523895 | -2.554709 |
| severe over100 | 4.2582% | 3.1631% |

MAE相对下降9.2679%，严重高估率下降1.0952个百分点；仅6/10电池MAE改善，低于冻结>=7；pairedcell差95%CI[-0.752789,8.350660]跨0。原>=5%/>=7cells/CIlo>0/over100增量<=.01门槛保持不变，无seed/feature/scale搜索。

## 收益集中与碰撞归因边界
- b4c29 MAE63.792137→41.011106，b4c14 MAE51.409497→40.509934，两cell贡献净MAE增益总和的99.8365%。这是事后算术贡献，不是因果解释。
- 唯一编码碰撞的cal电池b2c1反而MAE8.787635→10.699251，不能把总体改善归因为修复该碰撞。
- b4c7 MAE51.305729→55.713292，severeover10016.0465%→23.7209%；总体风险改善没有消除个别电池风险。
- 旧4effectiveC工况点相对3state的旧开发PASS保留；本次主参考是MAE36.400814的旧工况点，没有偷换到更弱3state。新输入只是强简单表示对照，不是创新确认。

## 编码与最小验证
canonical schedule去零长度并合并相邻相同电流，最多4段；不足4段补最后电流，SOC切点补0.8。全部52行精确Fraction decode回原始schedule，34不同schedule保留34不同向量；不使用format/batch/cellID/结局信息，无归一化拟合。
独立对全部4567记录复算MAE/bias/over100、paired bootstrap及完整gate，最大指标差2.22e-15；原CSV无损归档字节SHA一致。1fit_start/1fit_completed、1calpredict，0optimizer/旧checkpointload/新scale/devtest。累计CPU20=RUL18+辅助2，神经4fit2580steps和旧MATR41另记。新checkpoint仅服务器保存，禁止重复fit。

## 证据与复现
experiments/policy_lossless_schedule_point_seed42_v1/下encode_schedule.py、policy_features.json、minimal_encoding_validation.json、protocol/cohort/runner/ROOT_GO/fit_ledger/completion、metrics/per_cell_metrics/comparison/per_cell_change/gain_concentration、independent_recompute/metrics、predictions_lossless/decoder/lossless_validation/root_decision均保留。独审reports/policy_lossless_schedule_point_review_20261019_luna/review.json。
原调用：/home/yndx/miniconda3/envs/a40_env/bin/python /home/yndx/zxk/rul/experiments/policy_lossless_schedule_point_seed42_v1/runner.py。已有claim与create-only输出防重复；不重用消费GO。代码/配置/源/结果SHA见root_decision，原calCSV和新checkpoint均保留server。

公开空间：两份已完成历史文本证据397695→146658bytes无损归档，原server文件和GitHub历史保留。最初对已压缩预测JSON再次压缩没有释放空间，其packing_no_space_gain回执保留且该原文件继续公开；不把归档当科学验证，不扩大12MiB上限。

限制：10cal反复开发、singlefit/seed、event-only、物理serial/fullsource未知、已知固定labpolicy；来源身份没有因新编码闭环。无独立确认、物理泛化或完整概率可靠性结论。

## 下一条动作
仅用已存新/旧预测做0fit条件存活强对照：新lossless origin100分布随存活解析更新 vs 新动态逐时点预测，并保留旧compressed动态参考。所有arm固定复用已存旧sigmaA，不估新scale/新calforward/checkpoint/devtest。冻结点/over100和既有区间/Brier门槛后一次运行；旧sigma并非新模型独立校准，概率指标只作同尺度参考诊断。当前新点模型扩展NO_GO不变，不用该诊断解锁seed或新训练。
