# early EOL 整电芯筛选：实际排除量

结论：固定MATR/HUST train/validation共198颗电芯中，官方eol<=100筛选实际排除0颗、由该筛选移除的origin为0。

| 数据集 | train | validation | 最小作者EOL | 排除cell | 该门槛移除origin |
|---|---:|---:|---:|---:|---:|
| MATR | 102 | 34 | 147 | 0 | 0 |
| HUST | 47 | 15 | 1164 | 0 | 0 |

仅按固定split抽取现有标签小摘要并核全覆盖/唯一性；HUST摘要中train/val标签与现有v11 stage标签文本逐值吻合。不打开数据二进制，不运行模型，不输出或分析test标签。精确输入SHA和各role最小值见filter_realization.json。

[固定源码第487–505行](https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/data_provider/data_loader.py#L487-L505)在eol<=100时整cell返回，但本批全部eol>100。因此不需要重建存活曲线即可断定该特定筛选移除origin数量为0；不能把其他df=None/短记录/曲线缺失/别名排除等归于这个门槛。

这把潜在控制流风险与实际影响分开：源码依赖完整离线结局仍成立，但不能声称这198颗电芯已经被该门槛选择性删除。结果不证明严格在线输入、物理身份、生成器绑定或作者标签真实性，不推广到CALB/test/其它阈值。原NO_GAIN/NO_GO及门控保持。

new_fits=0、optimizer_steps=0、model_loads=0、inference=0、binary_reads=0。下一项只读CALB已存10epoch指标，核官方prefix-MAPE选模与cell-MAE最优是否冲突，不重新选模/预测/训练。
