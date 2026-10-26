# Byte-identical derived evidence

Five per-cell tables and two independent recompute reports are losslessly compressed with standard-library ZIP/LZMA to preserve the 12 MiB snapshot limit. Run `python decode.py NEW_OUTPUT_DIRECTORY` to reconstruct original paths/bytes and verify SHA256. Raw signals, checkpoints, and model sessions are excluded. Full per-query predictions remain authoritative on the server.
