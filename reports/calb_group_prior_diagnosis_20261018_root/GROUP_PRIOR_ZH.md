# CALB更强训练专用组先验：已有预测的有界诊断

结论：NO_GO_FOR_CALB_MODEL_OR_SEED_EXPANSION_FROM_CURRENT5。真实CALB开发fit仍已完成，但当前5验证电池不足以证明超出静态文件组先验的稳定模型优势，不追加模型/seed/fit。未修改原预测、epoch2选模、标签或主指标。

规则在本次计算前冻结，承接上轮root_result_decision.next_action：按CALB文件名第二段分组，只用固定17训练作者EOL取组内中位数；训练无该组时固定回退全局训练中位数1233，不用验证标签估计/调参。这里不把文件组的算术归因当作已证温度因果效应。

训练支持：group35有10cell，中位数1263.5；group0有6cell，中位数142；group45仅1cell，中位数987；group25无训练支持，回退1233。

|对照范围|模型MAE|组条件中位数MAE|全局中位数MAE|
|---|---:|---:|---:|
|全部5cell|61.634746|91.000000|350.400000|
|有训练组支持4cell|54.584443|51.000000|375.250000|
|无支持group25单cell|89.835955|251.000000|251.000000|

全局到模型的288.765254cycle净改善=全局到组先验259.4 + 组先验到模型29.365254；组先验在算术上覆盖原增益89.8308%。CALB_0_B187单cell占全局基线到模型净改善70.4364%。模型相对组先验全部5cell仍改善32.2695%/3of5，但有训练支持4cell模型较prior差7.0283%；全局净余量由group25无支持的fallback情形支撑，不能包装成稳定组内优势。

|验证cell|组训练支持|回退全局|模型MAE|组prior MAE|
|---|---:|---|---:|---:|
|CALB_0_B187.pkl|6|False|27.021404|47.000000|
|CALB_35_B222.pkl|10|False|28.333775|3.500000|
|CALB_25_T25-2.pkl|0|True|89.835955|251.000000|
|CALB_35_B247.pkl|10|False|95.433383|147.500000|
|CALB_45_B253.pkl|1|False|67.549212|6.000000|

最小验证：原497预测SHA一致、5cell固定，全部对照共用精确作者标签；模型MAE61.634745746与原独立精确标签复算吻合，原CSV浮点往返口径61.634743122另保留。全部5cell贡献严格重构总MAE差（<1e-8）；先验参数仅来自train17，无test。new_fits=0、optimizer_steps=0、new_inference=0、model_loads=0。

限制：5开发cell/单seed/同集选模，未做独立显著性或泛化确认；45组仅1train，25组0train，不把fallback结果当独立跨组泛化证明。原singleGPU/val-only与2GPU/test偏离、物理身份/generator/严格在线RUL门保持。

下一步：Close earliest source-provenance gap by reading existing full saved official v11 API JSON(data/source_audit/zenodo_19688272.json) and prior MATR provenance receipt; distinguish saved full-metadata evidence from live unknown and inspect exact generator commit/config binding. No fresh data download, PBT scan retry, model/test/fit or repeat HTML/literature review; preserve missing evidence STOP if absent.
