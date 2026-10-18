# HUST 已存原始来源身份凭证核查

结论：**STOP_HUST_PHYSICAL_IDENTITY_NOT_CLOSED_BY_SAVED_SOURCE_METADATA**。

[原始数据集v2](https://data.mendeley.com/datasets/nsc7hnsg4s/2)，[DOI 10.17632/nsc7hnsg4s.2](https://doi.org/10.17632/nsc7hnsg4s.2)。保存公开metadata与历史source manifest的ID/版本/DOI一致，发布字段为2022-05-24T13:06:43.736Z、许可CC BY4.0。描述自述77颗LFP/graphite、1.1Ah、3.3V、30°C；这是发布方metadata说明，不是本项目独立物理身份审计结论。

完整保存对象没有files键，size=0，related_links/articles为空。不能把size=0当原始数据空或零字节：旧manifest已经明确原始文件库存/大小未确认，文件列表端点曾返回400。另一个*_api.json只有no Route matched错误，不能当完整数据集响应。旧manifest中的环境/训练/版本字段是历史快照，本轮不把它们用作当前状态。

[pinned预处理第23–44行](https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/process_scripts/preprocess_HUST.py#L23-L44)预期hust_data.zip/our_data/*.pkl，以原file.stem构造HUST_ID；[第82–84行](https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/process_scripts/preprocess_HUST.py#L82-L84)将其作为cell_id。因此输出ID自洽仍不等于独立physical serial。本文不执行源码中的pickle.load。

未在所查保存材料中找到row/column至物理serial或跨来源alias映射。这个否定范围不扩大到未读原始文件/README或当前实时API，原保存获取时间也不由publish/modified时间替代。源文件SHA及完整字段范围保存在source_identity_review.json。

本轮仅文本：new_fits=0、optimizer_steps=0、model_loads=0、inference=0、binary_reads=0、test_access=false、网络请求0。原训练/test/PBT门与已完成负结果保持。

下一步只进行一次官方公开v2文件清单metadata查询，寻找README/身份映射文件是否存在；不下载raw、不接受新条款/改权限、不碰认证，错误不循环重试，缺证保持STOP。
