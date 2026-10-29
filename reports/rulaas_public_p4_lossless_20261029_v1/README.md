# P4 历史公开证据无损归档

为维持 12 MiB 公开快照上限，将两份历史 P4 文件打包为无损 ZIP；科研服务器原件不变，旧 Git 提交仍可直接读取。执行 python decode.py 核验，指定 --output-dir 到新目录可恢复；恢复过程不会覆盖文件。归档不含原始电池数据、模型权重或论文全文。

- [experiments/rul_time_recovery_20261026/p4_history.py](https://github.com/enterzxk/battery-dynamic-rul/blob/be1ebc88102ed81c5905faf37934db0786e005fd/experiments/rul_time_recovery_20261026/p4_history.py)；SHA256 13c3a36deae09de9d0168c6c51a25b5ec6b9badb4db3729f62fb56186b2d6a34
- [experiments/rul_time_recovery_20261026/p4_history_run_20261027T1610Z/paired_bootstrap.csv](https://github.com/enterzxk/battery-dynamic-rul/blob/be1ebc88102ed81c5905faf37934db0786e005fd/experiments/rul_time_recovery_20261026/p4_history_run_20261027T1610Z/paired_bootstrap.csv)；SHA256 3711948625f8b7d04c3a65af213dda7f51f8a05d7823ee1ea47302e157359e03
