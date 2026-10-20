# V17 Battery RUL 科研接续：完整 ISU DataV2 与首轮真实强基线
交接原因：V16 本聊天第二次实际 compaction=2026-10-20T13:35:48.609Z（第一次12:33:41.492Z）。不是累计token触发。
request_id: V17-second-compaction-20261020T133548Z
predecessor_thread_id: 01a15846-1ade-7623-88ff-98dd7f94f4fd
科研根 /home/yndx/zxk/rul；本地 E:/桌面/rul 仅.control。主协调gpt-6.1-sol/high；必要独立子代理gpt-6-luna/high。新聊以自身compaction为基线，第一次checkpoint第二次fresh。不要再处理前驱压缩。
## 人类目标与门槛
用户最新完整指令 docs/USER_SPARSE_IRREGULAR_RUL_SPRINT_20261020_ZH.md：稀疏、不规则健康观测下单电池在线动态RUL。并行数据、强基线、异步观测创新；不围绕旧MATR10补丁/CS2等待。允许有假设的足规模、多seed/消融与第二体系。保留所有旧数据/训练/test门，独立确认先方法/选择冻结再单独GO。不能只交计划。
## 已完成数据（不再重复读取/解析）
data/processed/ISU_ILCC_DataV2_v1 共188cell资产。先于轨迹曝光冻结C1/C2 train125、C3dev63、C4locked63，63locked payload读取0。
cohort reports/isu_ilcc_capacity_probe_20261020_root/cohort.json SHA4469f7f5b6eb8c26a522fa46c4291ec6d03d98e7ae5c20ce7ae77e835b849ae0。
reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json PASS SHA68f53dc481dfc212896658a9bcb69780b5ed7285d853cc870a4002ae658726e1，map188个文件及角色/SHA。
真实有效RPT train2664+dev1444=4108；missing24+12=36；源实测事件train122/dev62，其余3/1停止原因未知，不自动当独立删失。
每臂相同合法origin：train1606/dev915，共3臂；dev有61cell具共同合法前事件origin（62event中另1不满足起点）。主表不代表全部63dev。
名义容量0.25Ah，端点首次源实际完成RPT Q<=0.20Ah的stop。capacity到stop才可见。原始索引及missing保留，sparse2按原索引而非压缩后有效序号。所有日历时间/周保留；原数据无native cycle/EFC，UNKNOWN；不是实际运行时钟。作者summary Time是on-test周且含未来邻居duration填补，禁止当strictasof输入。
原始/隔次/7天延迟为同源标签、共同origin的回顾性信息隐藏，不声称改变物理实验日程。无新观测不免费获取T>query的存活oracle；RUL分布允许0mass。
官方Figshare22582234v2, CC BY4.0, DOI10.25380/iastate.22582234.v2。有效251ID/63group（G15缺，G61C1缺），网站238/238+12与论文225不强行消解。
RPT_json.zip id43756491 size929406930 MD5/ETag36331bf80f21d00e19a9a45095f542e8；仅选定成员精确range。累计377GET/703332475bodybytes，上限704000000，完整选定压缩703318560/解压5399141926B；完整archiveSHA未知，未整包/10GB循环下载。
full_import_final.json、data_manifest.json、qualify_asset.py为真实证据；qualify一次PASS不重审计。
失败保留：首reader SSH空格错误耗30Bheader，修复独立GO后2样本成功；full G35C1解析9位fractional秒失败，尾3位全0，nsV2只无损去这3位供解析，原字符串保留。full_import_failure及旧GO、G35诊断保留，不重复GET。
## 已完成强基线和真实结果
experiments/isu_irregular_rul_seed42_v1/：7CPU拟合完成=早期HGB3(2cellOOF+full)+动态HGB3+AFT1。group_frozen确定性构造另记，cdf_fusion0fit。
旧ROOT_GO.json SHA11c59b83f3f54a79d56c15bf2f5ba582668b20030a97b3dd41930073f34e07b0 已消费。baseline_run_receipt.json FAILED fits_started8/completed7，GRU第1optimizerstep后保存失败，epoch计数变量被GRU返回值覆盖。GRU消耗1fit/1step，无可用checkpoint。七个CPU权重全部保存，不准重训。
train_eval_pre_gru_epoch_fix.py SHA174d00d8d207627f29aa04297f5acccf421aa09c01cbe05a8f036f503ddefef0保存原失败；fixed train_eval.py SHA793a4682c96d2db48b806ea13c850f878c96cff4ee6b75f636ec75b05c4a2d4e，分开epoch_idx/_gru_out，checkpoint helper mock最小验证通过，没有新增训练。
已通过fresh0fit CPU_PREDICTION_GO.json（SHA927a0d4e56890e5eab13780664fa55b4743e5c084801bc1f89bf54f840a710b7）恢复CPU推理，cpu_prediction_recovery_receipt.json SUCCESS，0newfit/0oldrefit，3已存full模型加载+prior重建1，locked0。
cpu_prediction_recovery/predictions_dev.csv 13725rows=915origin/arm*3arms*5models，SHA01f0b2e5ff973affab97e4ca224911560e0cb6f8383851edd5ad631df53cda82，2491013bytes。原始完整预测保留。
cpu_results_summary/arm_model_summary.csv、cell_metrics.csv、paired_differences.csv、RESULTS_ZH.md是真实主表；root_metric_recompute.json独立statistics重算最大差1.7763568394002505e-15 PASS，0fit/推理。
MAE周(电芯内平均再电芯等权)，原始/隔次/延迟7d：
hgb_dynamic 3.0941830860 /3.2050751877 /3.3777821141；
cdf_fusion 3.2384981386 /3.2981448730 /3.3690562152；
group_frozen 全4.0204429370；
hgb_early_health 全6.1978943428；
aft_dynamic 5.7456365517 /5.9522825413 /5.9509177704。
动态HGB是四simple各臂最强。原始/隔次/延迟的>4week严重高估率9.1478%/10.8705%/11.8623%，IS80 17.2666/17.4656/17.8713，coverage92.3375%/90.2448%/89.2133%。
这些仅pre-event/source-observed开发描述；概率分数不是未知事件状态可靠性证明/物理EOL/独立确认。
## 第一条未执行真实行动
先补本阶段GitHub待同步（若前驱已有新commit以github_sync为准），不能为镜像反复耗尽科研；后续立即完成fresh GRU-only exactGO并执行，不重训7CPU。
finish_gru_only.py SHA852c5254bcef11451b402ab79c3028aaa8872672034b80980420844f96522748 已实现、root已读整份，尚未GO/运行。修复仅GRU1fit100完整epoch=100steps，必须签新预算，旧未用99不复用。双旧CPU/ISU CPU锁、源/manifest/协议/旧失败receipt哈希、唯一claim、owner/time/step/runtime门，per-epochcheckpoint+进度，失败finallyreceipt。
同dir protocol_candidate.json SHA6640ae61ae6e6ae178b2b7c9bb225bcc7a7a6d219505ece3ba8bf4bd1d5c75eb；
baselines.py SHAa8f537e2f2676e9c4a20909c530223bab20521fc7457e544cab092515610187e；
data_adapter.py SHAd5effc7ab9aa946feee717e8490983e6ccbebf890492b456091ac49a942763f3。
GRU-only GO读脚本具体字段后签：statusAPPROVED,allow_fittrue,unique request,owner,issued_utc,max_runtime1..21600,protocol/source_map/canonicalcode_manifest/cohort/data_manifest/prior_failure_receipt SHA,prior_request_id ISU_MAIN_BASELINES_SEED42_20261020_V1,fit_budget hgb0/aft0/gru1,seed42,epochs100,max_inference_calls2745,所有绝对路径绑定。sources5files=finish_gru_only/train_eval/baselines/data_adapter/protocol_candidate。canonicalSHA=json.dumps(source_map,sort_keys=True,separators=(',',':'))。
CLI --cohort --data-root --data-manifest --output --receipt --owner-thread-id --coordinator-json --old-cpu-lock --isu-cpu-lock --claim-dir --prior-failure-receipt --go-json。prior failure receipt应恰为8started/7complete/0epochs。新output目录createonly，不重复CPU load/refit。root记录必要delta review即可，不重复全流程审核。
随后合并GRU与已存CPU预测（0CPU重训），真实汇总，再候选12CPU最大预算比较。
## 候选创新实现与尚未运行的预算
candidate_filter.py SHAba513f55eae38b6bd0bbdb18aa5c7be2bc3387d111f50e492e6f92e7a620a29e：不可逆loss+OU可逆offset、innovation/Josephupdate/显式approx单调投影，sample/arrival/querybarrier和watermark，延迟35d内重放。不是exactGamma滤波，不吸收真实阈值/不凭运行获存活oracle。
filter_representation.py SHA2219151ed12c9fd4cbf71d265bd03c3c7d8296c610c369e46e3cc47b8eeb2896：sample<=arrival<=query、arrival-sample<=35d；不限制无新测量staleness，首已到达Q作reference；O(n)可见prefix重算作为正确性实现，不宣称O(1)部署。train-only cell-balanced Gaussian innovation quasiNLL一次L-BFGS-B固定init/maxiter200，正bounds、logcoords Hessian/cond1e8，任一边界/不可辨识保留STOP不救援。
filter_fit_protocol.json SHA35ed51ca8e98a061fd162bbd2694e7f1e81a63daee956b65fb371d592d7dda12。
filter_comparison.py SHA0ee9cfb6f91e2515329dde151eb4ff1f873671e0078a310d9c3e66c76a330dfe：candidate/scalar各3parameterfits(full+2OOFtrainfold)，修过OOF参数泄漏；HGB各3headfits，最多12新CPUfits，任何必要param非FIT_OK则branch STOP，无退回全train参数。读取已有baselinepred而不重训；82/76维对应raw74+candidate8/scalar2。同原HGB参数150iter15leavesl2=1seed42。
尚无候选GO/fit/真实增益。主协调可在最新授权内经一次必要窄审、完整data合法、额度/预算/锁符合后签fresh12fitGO立即执行，不无理由准备。保留paramfailure不是代码通过即创新成立。
update_probe_candidate.json SHA2bd495ba91e3ec383aa23078a181a71325dab829c0de4b25de6e46b3419e382f，需另0fit/newinferenceGO，完整源查询至recordend含postevent+同query前后arrival，对未知事件概率/更新行为评价，当前未跑。候选设计reports/dora_rul_design_20261020_model/CANDIDATE_REVISION_ZH.md，独立review reports/dora_candidate_review_20261020_luna。
## 创新边界/第二数据体系
竞争报告 reports/irregular_rul_competition_20261020_luna，2026Wiener+liquidrecurrent+online refinement直接重合，正确 DOI10.1016/j.eswa.2026.133786 (131286为无关碳关税论文，纠错证据保留)。官方ScienceDirect S0957417426026941在线2026-07-30，§2/3/4预览已核，全文算法/结果表unverified。EntroLnn arxiv2601.06195官方HTML§2/4已读；GraphMamba10.1109/TIM.2025.3635303全文未核；landmarkLGBM10.1186/s12911-025-03205-2方法已读。撤回2503.13558不作主依据。不能将Gamma+OU/Mamba/GRU/普通门控混合当创新。
LFP/Gr64cell11工况/RPT约100cycles和3.5days/1Hz38weeks仅官方metadata；README403、80%分母未核，15.95millionkB未下载，不强行当第二体系已就绪。
确认方案 docs/ISU_ILCC_CONFIRMATION_PLAN_20261020_ZH.md SHAd7a50e090b15919555f9eeaf2665a5c5e927307992c56e5e7f9e063df91edaf2，在首dev指标前冻结：候选avg3arm cellmacroMAE>=5%改善，任arm严重高估不+>1pct，任armIS80不恶化>5%，逐cell伤害>2w报告/pairedCI；这是开发选择门不是发表证明。GRU若影响选择需13/42/77，C4只在method/code/weights/metrics/selection全冻结后一次确认GO，不因看到指标重调。
## 状态/预算/自动任务
目前没有训练/导入进程，CPU recovery已成功closed。new_fits_allowed=false，无未消费raw/modelGO。
累计旧CPU20+新ISU7=27（旧MATR41另记）；旧神经4fit2580steps+ISU失败1fit1step=5fit2581steps。若新GRU100steps成功为6fit2681steps。旧所有GO/NO_GO、PBT2250966Bentry_cap不可重跑。不要把旧pending字段丢弃当预算reset。
真实现有自动任务ID为 battery-dynamic-rul，原battery-rul API明确不存在且本地TOML缺失，按既有允许只创建1replacement，已验证ACTIVE15min；.control/AUTOMATION_REPLACEMENT_20261020.json。迁移现有ID，别创建第二个，完整prompt保留并追加本次最新快照；旧prompt过时待办以coordinator最新为准。
Windows BatteryRUL-Controller保留不重启。旧CPU锁automation/state/online_survival_cpu.lock，新ISU锁automation/locks/isu_irregular_rul_cpu.lock，共享coordinator.lock。接管需真实flock+无活跃owner冲突、owner==thread_id/cwd/heartbeat/takeover_verified。新聊可自主推进、必要独立子代理，旧agents三项已交付不重复派发。
## GitHub真实边界和待办
最新已验证commit 3f35c34c6c3f5bb8c724fd9f805605a136708659，snapshot ac2f465f7089ccf2c8aa5ea3038dcfc8935ff1b8cd8a3ded590f68bd88cb52c9，12000520B/12MiB余582392。前驱若后续同步，以github_sync.json更晚回执为准。
原CSV2.49MB保留服务器，不强塞单文件2MB/总12MiB；优先公开主表/逐cell/代码/协议/manifest/失败回执，完整预测可后续既有losslesscolumnar或二进制create_blob精确公开，不扩cap不删有效历史。
已有old prediction .bin无损归档候选reports/completed_survival_pilot_public_lossless_v2_20261020_data/archive.bin1905425B SHA2594060db7f8f5b70c5dab8f0e49f40224e8c0a961540aec839fd8832b7f0da4，附decoder+validation总1908161B，旧2json2521660B，可省613499，尚未采用UTF8exporter不支持.bin。不再做无关压缩框架。
严禁发布DataV2原始轨迹/压缩member、full member_ledger控制器原始日志、G35C1_timestamp_diagnostic.json（含容量轨迹）、checkpoint/论文全文/凭据/会话。
科学产物均server权威，白名单同步必须branch正常expectedSHA更新和snapshot/keyentryexact回读后才能claim。新阶段进度应5项更新。
