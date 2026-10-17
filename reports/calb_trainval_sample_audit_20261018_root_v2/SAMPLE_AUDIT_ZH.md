# CALB固定train/val隔离与两样本真实字段审计

结论：固定22个训练/验证成员与仅22键的标签已create-only隔离。两固定样本受限载入字段检查通过；不是全部22语义/asof审计或训练授权。

服务器stage：/home/yndx/zxk/rul/data/source_audit/calb_v11_trainval_stage_20261018_root；stage_manifest SHA256 512db20103ecb56e72686577970bf8c7f05f281b10e128068925c358e1637146。没有test PKL或test标签键。

初次primitive-only门发现验证样本NumPy float64标量而停止，restricted_sample_loads=0，failure_receipt及serialization_gate保留。训练样本无构造opcode；验证样本包含STACK_GLOBAL2、REDUCE31391、BUILD1。静态上下文定位numpy.core.multiarray.scalar和numpy.dtype。

独立v2使用固定两符号的本地惰性数值替身，严格只接受dtype(f8,False,True)、state=(3,<,None,None,None,-1,-1,0)和8字节载荷，以struct解析Pythonfloat；不导入NumPy、不调用原构造器，不允许其余global/persistent、普通unpickle。输入8MiB/样本、2M节点、内存768MiB/CPU90秒，样本SHA与旧静态门一致；ROOT_TYPED_LOAD_REVIEW.json记录边界。

|样本|角色|nominal Ah|存储循环|作者EOL|规则可用前缀|每循环采样点范围|
|---|---|---:|---:|---:|---:|---|
|CALB_35_B229.pkl|train|58|99|1171|99|386–388|
|CALB_0_B187.pkl|validation|58|100|189|100|300–1276|

两个样本的current_in_A、voltage_in_V、charge_capacity_in_Ah、discharge_capacity_in_Ah、time_in_s长度对齐，非有限值0、负容量点0、循环内时间下降0；cell_id吻合文件名。99cycle样本对应官方loader:454/507–509的实际可用cycle边界，不能把每cell默认100prefix。

这不是实际loader前向结果：[100,3,300]仅为源码预期张量形状，尚未执行重采样/归一化、拟合train label scaler或验证prefix mask的实际数值。作者EOL/存储早期完整循环不等于严格在线真实RUL；其余20成员序列化和字段未审。物理身份、generator、官方训练test调用冲突和双进程runtime仍未闭合。

证据：sample_audit.json、ROOT_TYPED_LOAD_REVIEW.json、audit_typed_samples.py及原报告目录serialization_gate.json/failure_receipt.json；源SHA绑定。new_fits=0、optimizer_steps=0、new_inference=0、model_loads=0、test_PKL=0、test_label_values_decoded=0。

下一步：Execute pinned curve resampling/normalization and prefix mask checks on the same two fixed CALB samples only, with exact typed decoder and stage/source hashes; verify99-cycle padding versus100-cycle, no dataset-wide reload/scaler fit/model/fit/test. Then decide minimal remaining cohort gate.
