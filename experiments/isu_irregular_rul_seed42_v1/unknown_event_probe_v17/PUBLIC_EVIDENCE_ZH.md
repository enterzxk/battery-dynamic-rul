# V17：完整源窗口与迟到观测诊断（开发证据，2026-10-21）

已真实完成0拟合、22590次预测，28.223秒；62电芯/1255共同cell-query，0无效、0 C4读取。61颗有源观测事件；G9C3未观测端点，RUL标签留空，不当独立删失。查询从第二有效RPT+7天至record-end，不按未来T截断；三臂均需至少3条已到达观测。原始、隔次、延迟7天为回顾性信息隐藏。

|正确时间处理|HGB完整窗事件Brier|普通scalar Brier|HGB已知健康闭合后Brier|
|---|---:|---:|---:|
|raw|0.098175|0.102114|0.027902|
|sparse2|0.099509|0.102387|0.035604|
|delay7d|0.101876|0.104279|0.062826|

先cell内平均再cell等权。即时事件Brier与pre-event点RUL/区间是不同估计对象；Brier本身不是校准证明。

延迟7天臂，HGB正确采样时间相对no-latest的MAE差=-0.303870周，cell配对95%区间[-0.387435,-0.227502]；相对故意naive-current差=-1.286758周，[-1.663610,-0.931750]。scalar对应-0.292578/-1.287197周。MAE为61个knownT cell，Brier为62cell；seed42、2000次cell bootstrap，工况组相关及重复开发暴露保留。原始臂correct与naive逐行完全相同。

这支持真实时间戳的重要性，但强HGB已具有同类收益，不能当新滤波结构的增益或新颖性。原Gamma-moment/OU候选STOP、普通scalar未过5%开发门均保留。

原始臂351个at/postT查询（61cell）已看见阈值健康，但原HGB仍给postT MAE2.036117周；只在该变体保留的健康Q<=0.20时置RUL0/pzero1可消除此已知状态不一致，是逻辑闭合，不能当预测创新。延迟臂另有61个query源T已发生但阈值健康尚未到达，HGB pzero均值0.468963/Brier0.327830；该事后条件分层不能单独证明概率失准，闭合规则对此无帮助。

独立重算18项完整窗Brier最大差2.776e-17 PASS；sample<=arrival<=query与raw timing-control identity PASS。没有潜在物理EOL、部署/独立确认或创新已证声明，不开C4、不救候选参数。

服务器权威目录：/home/yndx/zxk/rul/experiments/isu_irregular_rul_seed42_v1/unknown_event_probe_v17/。完整runner/protocol、GO、逐query预测、744逐cell配对差与12组区间在服务器；本镜像只发布紧凑结果和校验哈希。7,086,123-byte新预测未上传，不伪称完整公开复现包。

- runner SHA f5231779d4fb16e67633c950173f5d3fbacf3ecba755be2f3550c173a70e3081
- protocol SHA 7164bee97f70c65614a90a324f762f2f415e6de03ea97612cd1a5595d2c1aa3d
- consumed GO SHA 74432cba801e13208b0edbfa2d67ff643e09db918c6ae0e5213b455a1368cf47
- predictions SHA a505efe9335adfa9c5f7625b5e7713956a9a02851790a2f150ba5e045f8a095f
- root decision SHA 00c682731e1491624c70045ac695f395cb5e56439c909b87ab850752bd1b79d9

下一动作：先核训练侧对“事件已发生但健康尚未到达”状态的目标/暴露覆盖，再冻结可合法学习的目标；不以时间错误对照取代强简单基线，不直接堆模块。
