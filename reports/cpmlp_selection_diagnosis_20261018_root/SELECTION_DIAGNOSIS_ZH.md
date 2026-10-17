# CPMLP 冻结MAPE选模点与MAE最小点核查

已完成旧3条与新10条验证事件的定向复算。旧epoch3仅8训练batch，为partial；新10个epoch均146batch完整。这里只读JSON和已存指标，无checkpoint/数据二进制或test。

结论：已记录epoch中不存在MAPE与MAE选模点不一致。旧pilot均在epoch2最小，新recipe均在epoch3最小，MAE选模惩罚均为0循环；NO_GAIN保持，不能用改选checkpoint解释或修复当前回退。

|运行|冻结选择epoch|MAPE最小epoch|MAE最小epoch|所选MAE|MAE惩罚|
|---|---:|---:|---:|---:|---:|
|old_pilot|2|2|2|177.383069|0.000000|
|new_recipe|3|3|3|194.007264|0.000000|

|运行|epoch|累计steps|完整epoch|MAE循环|MAPE|
|---|---:|---:|---|---:|---:|
|old_pilot|1|146|True|269.942611|0.150726242|
|old_pilot|2|292|True|177.383069|0.087462101|
|old_pilot|3|300|False|248.765051|0.134530894|
|new_recipe|1|146|True|252.872104|0.137820400|
|new_recipe|2|292|True|201.023792|0.106479267|
|new_recipe|3|438|True|194.007264|0.101367548|
|new_recipe|4|584|True|215.120621|0.114979542|
|new_recipe|5|730|True|213.263218|0.113452368|
|new_recipe|6|876|True|218.381357|0.117983124|
|new_recipe|7|1022|True|216.472670|0.114231361|
|new_recipe|8|1168|True|217.893785|0.118490524|
|new_recipe|9|1314|True|227.352210|0.124137639|
|new_recipe|10|1460|True|241.778334|0.132909130|

相同292 optimizer steps处：旧MAE 177.383069、新201.023792，差+23.640722（13.3275%）。配方/初始化不同，不能解释为LR单独作用。新epoch10 MAE 241.778334，比已选epoch3差47.771070，额外完成epoch没有带来已记录验证收益；这不证明一般性过拟合机理。

最小验证：13个事件均15电池×100前缀；由per_cell重新求电池等权MAE和MAPE，吻合记录（MAE<1e-8、MAPE<1e-10）；记录的严格最小MAPE epoch吻合completion回执。源epoch JSONL、完成回执、前轮诊断和本脚本SHA见selection_diagnosis.json。未重跑旧独立复算或smoke，new_fits=0、optimizer_steps=0、new_inference=0。

下一步：转回P1忠实复现缺口，只读官方CPMLP CALB脚本及已有数据/标签/拆分凭证、stat，确定最早缺失项；不加载数据、构造模型或训练，不重复HUST开发调参。
