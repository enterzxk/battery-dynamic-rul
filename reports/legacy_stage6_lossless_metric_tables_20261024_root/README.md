# Lossless archival of bulky saved metric tables (stage 6)

23 public JSON/CSV metric tables (1466975 bytes) are stored byte-for-byte in archive.bin (470045 bytes)
to keep the 12MiB snapshot cap after the A3 mechanism results were added. Human-readable
conclusions (RESULTS_ZH.md, all_model_metrics.csv, receipts) stay readable; these per-cell,
paired-bootstrap and summary tables restore byte-exactly via `python decode.py [path]`.
Server originals are unchanged. No source battery signals, weights or model sessions are included.
