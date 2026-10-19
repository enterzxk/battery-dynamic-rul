# CALCE CS2-35官方归档实际获取完成，尚未解析实验数据

2026-10-19。主结果：官方CS2-35 ZIP已通过一次有界GET直接流入服务器，完整37,056,519字节；传输端与服务器接收端SHA256一致：
84d88cb98a43c02049f16c78806a78ec19084776ea5df8a4b7c2f8f7ba4589e5。

服务器权威文件：/home/yndx/zxk/rul/data/raw/CALCE/cs2_35_official_v1/CS2_35.zip。
官方源：https://web.calce.umd.edu/batteries/data/CS2_35.zip 。

## 已完成与未完成
- 先前服务器HTML请求因DNS失败，原STOP/预算/日志保持，没有重跑该请求或修改DNS/代理。
- 另立本地控制端metadata-only票据：官方HTML成功81,431bytes，唯一CS2-35链接，HEAD200；声明37,056,519bytes、application/zip、ETag及Last-Modified可读。这是新的可信头证据，不意味着服务器DNS已恢复，也不证明文件内容科学合格。
- 在下载前冻结新的单文件获取票据：1GET、正文<=37,056,519bytes、180秒，无重定向/其他电芯/解压/表格读取/模型，保留全部旧预算。
- GET响应的大小/ETag/类型与已取得头相符；本地控制端不落raw文件，HTTPS数据经保留主机验证的SSH stdin直接写远端create-only .partial，只有长度完整才rename。完整传输约59.47秒，接收约57.56秒。
- 两端流式SHA与字节数核对一致。ETag/Content-Length没有被冒充作者发布的SHA；这是接收归档的实测摘要，尚未有额外发布者SHA可比。
- ZIP未解压、未读取任何Excel表格、没有EOL/删失/容量/性能结论，不能把归档获取叫作DataV1或独立确认完成。

## 证据、权限和下一步
ROOT_ACQUISITION_GO.json绑定源URL/大小/ETag/receiver和controller SHA；receive_archive.py、receipt.json和root_decision.json记录实际结果。下载前旧precode票据及完整控制回执仅服务器保留；公开只上传自有接收代码、最终票据和派生科学凭证，不上传原ZIP、Excel或控制器原始日志。
单次获取GO已消费，不可重跑；35原候选train继续，36候选dev、37/38locked未读取。新fit/学习模型推理/checkpoint/解压/表格/devtest读取全部0，CPU20和神经4fit2580steps不变。
归档获取仅关闭“官方文件可得且完整传输”缺口。物理serial/来源重叠、完整充电后容量资格、跨日期cycle编号、自然删失及现有MATRpolicy输入适配未验证。
下一项只对固定SHA的35归档读取中央目录元数据，绑定文件名/大小/CRC/日期顺序与现有候选角色；不解压/读取表格。随后选择一个事前指定的首文件做最小真实schema/完整容量资格检查，须另冻预算/必要窄审与fresh数据读取GO，不触碰36/37/38，不自动训练或重新访问失败源。
