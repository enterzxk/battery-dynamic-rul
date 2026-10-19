# NASA B0033：一次真实兼容性读取停止，首段容量测量边界未闭合

2026-10-19。本轮先完成metadata候选选择，再在一次独立pre-GO窄审和fresh exact ROOT_GO后，仅解码原train角色B0033；没有解码B0034或任何locked/dev/test电芯。

## 候选选择及权限
仅据已存官方包README选择24°C/4A的B0033/B0034组；B0033原train、B0034原development，B0036/B0050是已关闭旧读取，不纳入本次。选择未看新曲线或寿命；sourceID不等于已证物理serial，候选组也不是独立确认集。
新的单cell兼容性预算单独记录，不重置旧NASA两cell预算：最多一次、一个MAT、11,057,919字节、嵌套容器<=220,000,000字节、30秒、0fit/推理/checkpoint/下载/locked member。嵌套ZIP容器字节读取与选定MAT解码分别记账，其他MAT成员未打开或解码。
复用既有common2.7V积分函数，不改算法；名义2Ah、阈值1.6Ah来自保存README的1.6Ah/20%fade描述。B0033的作者放电截止是2.0V，共同2.7V为项目另定义端点，不能称官方原任务忠实复现。当前方法主原点>=100；>=20只描述，不用其救援主判据。

## 一次真实结果
- 197条放电记录均通过已有积分函数的数值/形状/截止条件；此处“有效”只是工程可积分，不是完整充电后容量测量资格。
- 24°C，放电活跃电流中位范围约−4.0290至−4.0246A，符合metadata工况。
- 首记录是source operation1/discharge1，共同2.7V容量0.0593417636Ah，原始Capacity0.0684257224Ah；两者都低于1.6Ah。
- 冻结首次阈值计算给出event80=1，>=100可用前缀0，>=20描述性前缀同样0，判定STOP_NO_ORIGIN100_PREFIX_UNDER_FROZEN_ENDPOINT。
- 后续原始Capacity曾达到1.88514017Ah。故首记录低值不能直接解释为正常持续退化EOL，也不能仅将失败归因于共同截止算法。原始字段和项目积分的测量资格都需要进一步来源依据。
- 没有以后续容量最大值归一化、删除前几循环、移动首次事件、换阈值或扩读B0034。冻结结果不变。

## 科学解释和停止边界
这次真实结果阻止将B0033直接当作当前first-crossing动态RUL队列。它不证明NASA整体无效、不证明电池在第1次真实物理报废，也不把软件/测试启动过程当自然删失。
canonical_rows.json没有完整charge操作字段，不能据该保存表证明首个低容量是否在一次规范完全充电后获得。首段启动/部分放电只是待验证解释，不能冒充已确定机制。任何后续测量资格规则必须在预测时可判定，不能通过未来容量反弹来决定删除早期样本。
B0033已因本筛查产生结果暴露，不能今后重新称为未暴露确认电芯；B0034与封存成员保持未解码。

## 最小验证、预算与证据
summary.json记录MAT SHA256=3f6b44d7e123b9e9e4a26c3651acd0b9f38ca4d21aac3930bd9197ccf8b04426。
实际嵌套容器93,662,572字节、MAT11,057,919字节/1cell，耗时约0.323秒；ZIP嵌套SHA、MAT大小/CRC、train角色、owner锁、一次claim、冻结runner/protocol/GO/review哈希均核验。
从保存197行独立重算首次阈值/前缀计数与预算一致，不重新加载MAT。新fit/学习模型推理/checkpoint/下载/dev/test/locked/B0034/旧36和50解码全部0，CPU20和神经4fit2580steps不变。
完整canonical_rows.json仅服务器保留，公开只派生summary、startup_capacity_diagnostic、冻结代码/协议、审查、GO和最小验证/根决策，原始MAT与曲线不上传。
服务器目录：/home/yndx/zxk/rul/reports/nasa_b0033_compatibility_20261019_root。
命令：/home/yndx/miniconda3/envs/a40_env/bin/python reports/nasa_b0033_compatibility_20261019_root/runner.py。该一次GO已经消费，不可直接重跑。

## 下一步
不继续盲扫NASA同组电芯。优先有界查找另一未暴露原始来源的官方元数据，要求明确完整充电/放电容量测量与起始循环定义；先判断数据和独立身份可得性，再准备精确读取预算，不下载、fit或读取locked/test。启动期资格缺证必须先关闭，不能将更多未审样本数量当成修复。
