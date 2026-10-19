# CALCE CS2-35：最早文件真实读取与首段容量证据

- 已完成：固定官方ZIP SHA的25个XLSX中央目录按文件名日期排序；只读取最早CS2_35/CS2_35_8_17_10.xlsx（182399bytes，CRC0cae9c26），0.113秒。2sheet，Channel_1-008首行为17字段，1091条数据、源Cycle_Index=1一个连续occurrence。不是全电芯DataV1或RUL实验。
- 证据：本目录protocol.json/read_firstfile.py/独立原BLOCK与fixed PASS/ROOT_READ_GO/public_summary.json/minimal_validation.json/root_decision.json；完整summary.json仅服务器。XLSX实测SHA86cc96deea07eaa9f29007a2260f03cea09332ccebf770af36ebfa443e86ca2d。原ZIP data/raw/CALCE/cs2_35_official_v1/CS2_35.zip保留，未导出原表。
- 最小验证：唯一目标大小CRC/归档SHA/owner/单次claim核验。末次先行充电样本4.199653V、0.049829A，末次放电2.699944V、−1.099749A，容量计数1.138460076Ah；相邻负电流采样区间部分积分1.138450440Ah，差9.6363e−6Ah（计数的0.0008464%），边界样本与官方CC/CV/2.7V协议相容，但不证明精确charger termination。原始字段单位保留，不归一化、不创建EOL。文件名日期2010-08-17而首Date_Time=2010-08-16，二者分别保存，不把文件日期当循环时间。
- 阻塞/风险：仅一个循环，完整生命周期/跨日期cycle与testtime连续性、额定参考容量/事件删失、物理serial与重叠仍未核。积分仅含相邻负电流区间，不是完整参考容量。首段没有NASA式极低容量现象，并不等于全数据合格或独立泛化。36dev与37/38locked未读；0fit/推理/checkpoint/devtest。CPU20/神经4fit2580steps不变。
- 下一步：冻结同一35 candidate_train的剩余24日期文件单次有界解析，按真实时间/源Cycle_Index保留分段与重启，不用未来容量删启动；一次必要窄审+fresh数据GO后形成单电芯因果容量序列，再判断EOL或自然删失。不得扩36/37/38或模型门。完成CPTransformer旧ledger61672→13723bytes原字节无损归档，原件与Git历史保留，不扩12MiBcap。
