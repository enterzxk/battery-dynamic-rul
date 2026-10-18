# 已知充电工况上下文匹配对照：开发门槛PASS

在同42fit22281/10cal4567、相同原age/SOH/robust20、原event标签、等cell权重与HGB参数下，仅加入四个预设充电工况SOCbin等效C-rate。固定seed42、logRUL squared_error、150iter/leaf7/depth3/lr.05/min50/L2=1/noearlystop，真实1CPUfit完成并保存checkpoint，不重训旧模型。

|电池等权指标|旧三状态|加入已知工况|
|---|---:|---:|
|TimeMAE cycles|58.1136980028|36.4008143427|
|bias cycles|11.6762242128|-3.5238951148|
|severeover100|14.160051%|4.258247%|

TimeMAE改善37.36276%，8/10cell改善，pairedcell2000seed42差95%区间[5.583949,41.354502]cycles，严重高估降低9.901805个百分点，冻结四项开发gatePASS。两颗恶化电池也保留：b2c1 MAE增加3.347747、b2c24增加4.962391cycles；不能只报改善case。

原始工况字符串已在fit见过的6cal与未见过的4cal分组在训练前已冻结；具体结果见policy_exposure_subgroups.json。分组仅描述，样本小且cal已多次暴露，不是独立确认/新工况泛化/创新或论文接受证明。已知实验协议作为预测条件与未来真实运行工况未知的部署任务分开。

语义出处与哈希见reports/policy_context_20261018_root/source_semantics.json及ENCODING_ZH.md。P01Methods/PDF第7页与P02Fig2/PDF第2页说明预先设定的C-rate/SOC规则；作者policies.py给出电流网格和10min约束。四个共同SOCbin采用Ceff=.2/integral(dSOC/C)，不用batchID/标签/未来曲线。52条parse/timeidentity通过，6seen/4unseen，编码表SHA91a6bfa3be83b403289133bd13669d36ed7a1f212ec0ca4e692efecfb85be462。

必要独立窄审请求gpt-6-luna/high，实际运行身份不可独立内省。首审cohort SHA转录缺字被主控在GO前拒绝，0claim/fit；原review与拒绝checks保留，修正七项哈希后fresh exactGO才运行。编码v0合法80%单步边界拒绝与浮点严格相等拒绝也均发生在fit前并保留；当前fit账本恰1次，不把控制失败当科学预算重跑。

独立CSV重算最大差7.11e-15；完整预测SHA 796844ff5c863a08ca7f1238c620afee39a3f22b84d68b615ec52135c48b7ea0。Checkpoint SHA 97241e1c5966d179a23902270993c0de5f84c5c3e6de2cb3798ec41728efe541仅服务器保存；公开rawlog+exp输出无损delta复原byteSHA通过。实际耗时0.370s，0optimizer/新尺度估计/checkpointload/dev/test。全球newfits仍false，累计科研CPU14=RUL12+aux2；旧MATR41和神经4fit2580steps另记。

下一步：0fit使用此模型已保存预测，比较origin100固定早期EOL递减与逐时点更新，检验在更强已知工况条件下动态更新是否仍有独立开发价值；不估新sigma/训练/推理/读dev/test。尚未做该对照，不由本gate自动扩大seed/模型。
