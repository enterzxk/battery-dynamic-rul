# CS2-35剩余日期文件：部分读取失败与容量计数语义阻塞

- 已完成：独立窄审修复行数预算后fresh exact数据GO执行一次6.981秒；计划24个同35候选train文件，实际读取10个19191767bytes，前9个解析105207条记录、304个连续源循环片段。第10个CS2_35/CS2_35_10_29_10.xlsx触发schema ambiguous/missing并STOP，GO消费，不重试/扩cap/转下一文件。不是完整DataV1或RUL结果。
- 证据：protocol.json、runner.py及原版本、原BLOCK/最终deltaPASS、ROOT_READ_GO.json、summary.json、minimal_validation.json、counter_semantics_diagnostic.json、root_decision.json。canonical_occurrences.csv仅服务器，SHAc66c5c1458167fdf055e46373fa39630c9c56faee2f499a2e653171bf06047ac；原始表不公开。每个已读文件的实测SHA/源Cycle_Index/真实Date_Time边界见summary。
- 最小验证：归档SHA/目标大小CRC、逐行实际row/column预算、锁/owner/create-only claim核验；仅已保存CSV重算304行与105207条源行计数一致，无raw重载。失败前容量计数端点范围1.002043–54.264202Ah，不是单循环容量。294个同文件且源cycle+1的相邻对中，计数差中位数1.025143Ah，部分积分中位数1.015981Ah，二者绝对差中位数0.009167Ah；仅描述累计计数线索，不能静默用差分或部分积分替换参考容量。
- 阻塞/风险：失败回执没有保留第10个文件的各sheet表头，所以缺失/多sheet的具体原因UNVERIFIED，不能猜成某一种；容量counter跨循环累计/重置和step起止语义未闭合，禁止直接按末计数做SOH/EOL。没有拼接跨文件循环或修复时间；首文件到第二文件墙钟间隔未知，首文件payload未重读。其余14文件未读，36dev/37–38locked未读，物理serial/重叠未核。0fit/新模型推理/checkpoint/devtest，CPU20和神经4fit2580steps保持。
- 下一步：只为失败10/29文件冻结一次小范围sheet表头及counter/step边界诊断，fresh数据GO后按最少记录定位结构与counter口径；不重跑24文件、不复用消费GO，不基于未来容量删除启动或改EOL。已完成CPTransformer epoch2预测117540→47894bytes原字节无损归档，原服务器/历史保留，不扩12MiB公开cap。
