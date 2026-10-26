# Lossless archival of previously published saved-metric tables (stage 5)

7 historical public JSON/CSV files (957956 bytes) are stored byte-for-byte in archive.bin (381676 bytes)
to preserve the existing 12MiB snapshot cap while keeping the 2026-10-23/24 mechanism code, receipts
and comparison tables readable in the snapshot. Their server originals and prior Git history are
unchanged; validation.json pins the source snapshot and every byte hash. Run `python decode.py` to
list paths, or `python decode.py path` to print exact original bytes. Restore a required file to its
original relative path before rerunning a legacy script. No source battery signals, weights or model
sessions are included.
