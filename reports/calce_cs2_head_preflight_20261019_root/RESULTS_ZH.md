# CALCE CS2-35获取前检查：服务器域名解析失败

2026-10-19。执行已冻结的metadata-only预算一次。首个官方HTML请求返回URLError: Temporary failure in name resolution；HTML返回0bytes，链接未提取，HEAD未发出，原始数据正文0bytes。

STOP_NO_RETRY_NO_GET_FALLBACK。该失败只说明本次服务器名称解析不可用，不证明CALCE源站离线、数据不存在或官方协议无效。此前网页版官方页面成功读取仍是单独的有效元数据证据。

receipt.json记录budget SHA、1次HTML请求/0次HEAD/无重定向、实际错误与0.0074秒耗时。raw下载/解码/fit/推理/checkpoint/devtest均0；没有修改全局或项目DNS/代理、没有切换认证、没有用GET下载作fallback。本次metadata预算已消费，不重复请求。

尚未执行：CS2-35真实链接与Content-Length/类型/完整性元数据，后续下载/解码。35候选train、36候选dev、37/38locked保持；模型门仍闭合。

下一步等待服务器名称解析恢复的外部证据或新的可信官方响应头证据，再为未完成的单文件header检查签独立预算；不是盲目循环相同请求。额度恢复本身不解决网络依赖，不开放raw或模型门。
