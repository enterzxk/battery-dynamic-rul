# CALB v11 有界获取与固定训练/验证覆盖

已从官方记录19688272实时核API文件信息及HEAD，单次GET获取CALB.zip。官方MD5吻合，固定17训练+5验证成员CRC与SHA留存，标签键覆盖22/22。不是数据语义审计通过或训练就绪。

- 官方记录：https://zenodo.org/records/19688272 （v11；本轮web与服务器API均实时核验）。
- 来源URL：https://zenodo.org/api/records/19688272/files/CALB.zip/content
- 已获取字节：12671967；MD5：2b1006e96e0ca42765a732060f964687；SHA256：153dc6230d445d23b4928ce4dc993f37b331651de8473497f8df01ed9bafe7a3。
- 服务器归档：/home/yndx/zxk/rul/data/raw/CALB/acquisition_v11_20261018_root_v2/CALB_v11.zip。create-only原包及partial均保留，不重复下载。
- 固定22个成员合计解压CRC读取41,987,581字节；未提取到训练目录，未反序列化、构造模型或做推理。
- 复用已有Life_labels_v11.zip（SHA45b3adf3f5ea2819244ac206f204defd4eea0ad1eaa4d38534f0543cab4ac033），CALB_labels.json的train/val文件名键22/22，未json解码数值标签。共享标签成员为键覆盖扫描读取了字节，test标签数值未解码/保留；5个test PKL成员完全未打开，归档中央目录中仅保留其文件名/大小/CRC等metadata。
- 原HUST source阶段估计2,956,681,875字节 + MATR实际4,864,920,138字节；加本轮归档及API响应后7,834,285,913字节，低于原21,474,836,480上限。旧PBT独立预算不重置/不借用。

初次获取在元数据请求前因服务器既有回环代理29137拒绝连接失败，artifact_get_requests=0、bytes=0。reports/calb_acquisition_20261018_root/failure_receipt.json原样保留，不重跑。只读核本地controllerPID27060及tunnelPID25128均退出、原本机7897仍监听后，按既有Start-Rul.ps1原参数恢复同一项目反向隧道，新PID40508；远端29137监听验证。未启动控制器或promoter、未改全局代理/DNS/认证。独立v2目录transport_repair_review.json明确保留原artifact GET上限1，未扩大预算。

最小验证：live_source_metadata.json、head_receipt.json、acquisition_receipt.json、archive_coverage.json与completion_receipt.json可逐项追溯；源码/拆分/归档哈希绑定。新fit=0、optimizer_steps=0、model_loads=0、new_inference=0。归档未对test PKL做CRC解压，不能宣称全包逐成员CRC通过。

仍未完成：实际字段/标签数值/有效前缀形状/归一化与as-of审计、物理身份核验、CALB双进程runtime；官方run_main训练期间test加载/评估与当前test锁冲突仍在。new_fits_allowed=false、旧NO_GAIN和消费预算均保持。

下一步：Create isolated fixed22 CALB train/val stage from verified archive; inspect serialization allowlist and one real train/val sample under bounded restricted loading only if safe, verify label/prefix shapes and train-fitted normalization requirements. Keep test/numeric test labels/model/fit locked; no ordinary unpickle.
