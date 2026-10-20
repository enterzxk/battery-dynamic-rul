# ISU 预测无损归档 v17

Python 3 解码：`python decode.py --target-dir ./decoded`。解码器 create-only 写入；默认目标为本目录下的 `decoded/`，不会写回源路径。

归档按原字符串保存三份开发预测 CSV，保留 CRLF、列序、行序和浮点文本。仅含预测结果，不含原始测量、C4 payload 或 checkpoint；未训练、拟合或推理。校验细节见 `validation.json`。
