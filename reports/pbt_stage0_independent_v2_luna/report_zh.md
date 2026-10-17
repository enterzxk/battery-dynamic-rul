# PBT Stage 0 v2 独立审查

裁定：PASS_BOUNDED_METADATA_STAGE。此结论只支持 root 单独判断是否执行一次固定 metadata collector，不授权 collector 执行，也不放行 G2/G3、数据解码、模型构造/加载、forward、metrics、training 或 test。

冻结源文件 SHA 与委托值一致：spec.json 为 d6d041feb5bc69bffb5cafc796cc21db00e7e3b4f217d4732fd328588aedcae3，collector.py 为 19d08edbd73f1b66ba5ce07b24a4bc75f6eb7e563cf5a7ec790704ec62e518cc。七个白名单输入的当前 SHA 全部匹配，共 40,644 bytes，文件均为普通文件；预算为每文件 65,536 bytes、合计 131,072 bytes，固定 15 cells，10 秒墙钟，输出上限 262,144 bytes。逐项哈希见 review.json。

collector 的路径实现符合冻结范围：从根目录 slash 打开目录描述符，再逐组件相对 dirfd 使用 O_DIRECTORY|O_NOFOLLOW；leaf 以 O_NOFOLLOW|O_NONBLOCK 相对父目录打开，fstat 核实普通文件与大小，有限读取后复核 size/mtime/ctime 并校验固定 SHA。输出父目录同样经 dirfd；临时文件使用排他创建，完整写入、fsync 后通过 no-overwrite hardlink 发布最终文件。路径没有递归搜索或动态输入。

脚本使用默认 SIGALRM 终止，配合读取、解析/校验、序列化和发布前的 deadline 检查。解析与字段校验包括 JSON 根对象、draft.dataset 对象、decode/join aggregate 嵌套结构与精确 15/15/0 类型值，以及固定 cell 次序和 CSV 必需字段。aggregate missing=false 只有通过精确结构检查后才会产生，None 不会被误作已存在值。有效 Namespace 仍全 missing；DKP per-cell presence 和 valid_cycle_number 仍保持缺失；历史 cycle_count 与有效长度分栏。

运行边界需要遵守两点。SIGALRM 默认终止会绕过 Python finally；操作系统会回收进程 fd，但中断时可能留下 pending 临时文件，O_EXCL 会阻止自动重跑。不要自动清理或重试，应留给 root 处理。若超时恰好发生在 final hardlink 发布后，receipt 可能已存在但进程未正常完成；root 必须结合退出码检查 receipt 完整性，不能依据成功输出行是否出现来判断。

AST 语法解析通过。没有执行 collector 或测试；没有读取二进制、archive member 或 payload，也没有进行 pickle/joblib/torch.load、项目导入/AST执行、动态 run object 访问、构造、strict load、forward、metrics、fit 或 test。对应计数均为 0。

若 root 另行授权，review 支持的唯一执行范围是：读取 7 个固定 UTF-8 JSON/CSV/TXT 输入（当前 40,644 bytes；单文件最多 65,536 bytes，总量最多 131,072 bytes），固定 15 cells，硬 10 秒，输出最多 262,144 bytes；无搜索/递归、外部网络/进程、binary/archive/payload、pickle/joblib/torch.load、项目导入/AST执行、模型或动态 run object；唯一输出 reports/pbt_stage0_metadata_freeze_v2_root/metadata_receipt.json，create-only。此审查不替代 root 对是否运行的单独裁定。

请求路由为 gpt-6-luna/high；实际 runtime 模型与推理档位未独立内省。v1 NEEDS_REVISION 审查保留不覆盖。
