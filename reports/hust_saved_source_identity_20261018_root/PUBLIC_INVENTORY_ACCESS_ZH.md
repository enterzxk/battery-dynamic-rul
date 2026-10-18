# HUST官方公开文件清单：一次有界访问失败

结论：**STOP_PUBLIC_INVENTORY_ACCESS_UNRESOLVED_NO_RETRY**。

[官方v2页面](https://data.mendeley.com/datasets/nsc7hnsg4s/2)当前可由网页工具读取，Version2/DOI/发布日期与保存记录一致。正文提取中Files只有标题，没有文件行；这不是零文件证明，不能据动态列表未提取推出官方没有数据或README。

页面链接的API Docs（https://data.mendeley.com/api/docs）由工具报告fetch timeout；公开清单候选端点https://data.mendeley.com/public-api/datasets/nsc7hnsg4s/files?folder_id=root&version=2 一次查询被工具报告为URL不可访问，未返回可核origin状态/文件清单。不能把旧manifest的400移植为本轮HTTP状态，也没有验证候选路由正确；路由/来源实时内容仍UNKNOWN。

public_inventory_attempt.json只记录工具观察与精确URL，不冒充原始HTTP快照。inventory_attempts=1、retries=0；无raw下载/认证读取/条款或权限更改，无模型/fit/test。原保存来源证据不变，physical serial及跨来源/预训练重叠仍未闭合。

本动作因外部可读来源受限而停止。不得循环重查同一端点/HTML或扩下载；新增可读官方文件清单、README/serial映射凭证或确切访问变化后再恢复该身份门。当前整个研究未宣称完成；现有训练/test/PBT门保持，状态不变时监控保持安静。
