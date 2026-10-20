# CS2-35 DataV1：25日期文件的可信测量资产与端点边界

## 已实际完成

已读取归档中全部25个日期文件，266914条采样记录保存在服务器25份逐条缓存中；生成936个源循环片段，其中854个VALID_SAMPLED_CC_DISCHARGE、32个UNCERTAIN、50个精确重复来源别名。25文件归档覆盖完成，不等于完整无缺口的全寿命循环历史。最终v3运行21.032秒；0模型训练/推理/其他电芯/封存测试。

原始文件、源Cycle_Index、Step_Index、Test_Time、Date_Time、源行和充放电计数保留，不平滑、不强制单调、不按未来反弹删启动。旧304摘要按原−0.001A定义的行数、原循环号、末计数及部分积分全部核对通过；旧结果/失败/预算保留。前次105207仅为已处理源行计数，旧目录实际只保存304行摘要；本次补齐了逐条缓存，不能声称旧逐条数据已被复用。

## 已解决的Excel结构问题

10/29文件新增Statistics_1-008汇总表，与Channel采样表共享旧七字段，导致旧匹配器不唯一。新calce_io.py按Data_Point、Step_Index、Step_Time等采样粒度标识和唯一带单位字段识别，不依赖表名/日期。关键重复列或多采样表语义不唯一则停止，Statistics作为不同粒度保留metadata，不任意选列。

## 容量物理口径

官方CS2协议：nominal1.1Ah、0.5C CC到4.2V再CV至<0.05A、默认放电到2.7V；35为1C组，https://calce.umd.edu/data%20II 第210–235行。官方网页未给出该历史设备counter的具体重置设置。

原记录显示放电counter在休息/充电/循环切换中保留，下一放电继续累加。Q取同一源循环、同一主放电步骤末counter减紧邻放电前休息样本counter；不是相邻循环末值盲差分。独立候选积分补入首个−I×Step_Time/3600，再加负电流样本间梯形积分。三个代表周期1/2/50的差10.19/11.23/16.30μAh；854个有效放电的绝对差中位6.249μAh、最大31.708μAh。旧积分漏首个约30秒区间，约0.00917Ah。

有效性还要求已观察到充电尾段、休息基线、恒流/步骤起点/采样间隔、截止样本和积分一致性。冻结工程容差在reconstruction_protocol_v3.json；这是采样信号一致性判据，不是设备绝对标定或精确终止证明。30片段缺充电尾证据、4无主放电、2截止不明、1积分不符，标志可重叠；32不确定片段全部保留。

## 跨日期与标签

24个边界中21个源Cycle_Index重置。2/4与2/10文件的50个完整循环原始信号精确相同；保留两个来源及duplicate_of，只计一次。无来源依据的间断不拼接，不把记录顺序重新命名为原生循环年龄。

valid容量范围0.303643–1.138460Ah，SOH=validQ/1.1。nominal80%=0.88Ah；首次有效观测越阈为2010-12-16T07:23:52（原始时区未知），12/20文件内Cycle_Index22，Q0.876295332Ah。255个有效观测低于阈值。跨日期缺口不能证明从未漏循环/越阈，故true_first_EOL_event、全局native-cycle RUL和合法末行右删失均保持null/UNKNOWN。禁止把末行当真实寿命终点。

CS2-35仍为原登记candidate_train；原始物理serial/预训练重叠、全局cycle连续性和外部固定模型协议未闭合，independent_confirmation_ready=false。数据资产不开放模型、其他电芯或test。

## 实际失败和版本保留

原批读取的schema失败保持。此次重建v1在4文件后因旧噪声末点与主放电末点定义不同的回归断言STOP；v2复用缓存后在旧无放电片段的空字段对照处STOP。二者均保留原summary/GO/claim/输出；分别修复legacy独立定义与nullable比较。v3只读余19新members，复用5份新缓存及10/29缓存，总新增archive member仍24，无重下载/重复补取。独立窄审原BLOCK与fixed PASS保留，v3空值对照由ROOT定向复核，无物理阈值变化。

## 交付

权威资产：/home/yndx/zxk/rul/data/processed/CALCE_CS2_35_DataV1_v3/，capacity_series.csv、discharge_measurements.jsonl、25份records.jsonl.gz、endpoint_labels.json、DATA_DICTIONARY_ZH.md、manifest.json。CSV SHA8818441b59d405ab34948eaf57824a79780591c13d795a15caca2be2643212ea；JSONL SHA013faaee2994548dbd4f70d8520bdcc2ac266aa7f757ef5ed23930a325d3f85b。原始数据和完整测量表不上传。

本目录公开calce_io.py/capacity_rules.py/reconstruct_v3.py、冻结协议、必要失败回执、final_validation/asset_manifest/public_summary/数据字典。主CSV必须按status筛选VALID；重复别名保留的容量列是同一测量的来源引用，不代表新增独立样本。

下一科研条件：补充测试session/日程记录，证明各重置/长休息边界是否漏循环，才可能建立全局原生cycle年龄与首次EOL。现有证据足够使用分段、带不确定标志的容量测量；不足以开展宣称独立确认的全寿命dynamic-RUL评估。没有新的限定GO不继续原始读取/训练。
