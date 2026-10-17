# MATR v11 保存 API 完整快照补充核查

结论：**STOP_ACTUAL_V11_GENERATOR_PROVENANCE_NOT_CLOSED**。本次已完整检查早先保存的官方 API 响应，补正旧报告“完整 API 未读”的范围；没有获得实际 MATR.zip 到确切生成器 commit、配置或运行清单的绑定。旧网络失败和旧报告均保留，不覆盖。

来源：[官方记录 API](https://zenodo.org/api/records/19688272)，服务器保存文件 `data/source_audit/zenodo_19688272.json`。原字节 11932，SHA256 `5b79e36abb25fc0721aef484cf92605c7e8d559df7bffba90003b291475238ae`。这是保存快照，不是本轮实时响应；原获取时间未验证，record.created/modified 不是抓取时间，也不确认其当前为最新版本。

已读范围：全部 metadata（含 description、custom、relations）、顶层 links/swh 和文件清单。metadata.description 的 News 明示 Released v11，publication_date=2026-04-22；metadata.version 字段实际不存在，不能要求该键存在才承认发布身份。custom.code:codeRepository 只给官方仓库 URL、语言 Python；related_identifiers/references/notes 在此保存对象中均无键，swh={}。description 链接官方仓库和可变 main 的 Version11 说明，没有精确归档生成绑定。字段不存在的结论仅针对这份已哈希保存对象。

MATR.zip 条目 size=4864920138、MD5=83a1528858b9e1b7b6886757bb561669，与既有 VERIFIED_ARCHIVE_ONLY 回执一致。本轮未重读或重哈希归档，也未重新下载。文件 MD5 匹配只证明保存清单与既有回执一致，不能证明 pinned 代码曾生成该归档。

`root_review.json` 中原“Full API metadata due tool and server access failures”是当时未读范围。本补充把状态分开：保存完整 API 已读；实时 API 当前 UNKNOWN。不能继续笼统称“完整 API 没有核查”，也不能扩大成“官方所有地方都不存在凭证”。本轮最小验证为原始保存 SHA、记录身份/description v11、MATR 条目大小/MD5与既有回执，以及旧四文件 SHA 不变。

证据：`saved_api_metadata.json` 保留完整 metadata 和精确 JSON 字段；`saved_api_addendum.json` 保留来源哈希、字段存在性、旧证据哈希和裁决。方向A NO_GAIN、CALB 当前5电池不扩模型/seed、strict_online_eligible=0及 PBT 已消费失败预算均保持。本轮 new_fits=0、optimizer_steps=0、model_loads=0、new_inference=0、dataset_binary_reads=0、test_access=false、network_requests=0。

下一步：返回 P0 已存审计索引和 pinned split/source 文本，选取一个可用现有证据关闭的物理电芯身份/重叠缺口；缺证保留，不能重复 metadata/HTML 核查、扩 PBT 扫描或启动新模型/训练。
