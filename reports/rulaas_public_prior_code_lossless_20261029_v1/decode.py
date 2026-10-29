#!/usr/bin/env python3
"""Verify or recover the exact historical public files; never overwrite existing files."""
import argparse,hashlib,json,pathlib,zipfile
h=pathlib.Path(__file__).resolve().parent
m=json.loads((h/"validation.json").read_text())
raw=(h/"archive.bin").read_bytes()
if hashlib.sha256(raw).hexdigest()!=m["archive_sha256"]:raise RuntimeError("archive hash mismatch")
ap=argparse.ArgumentParser();ap.add_argument("--output-dir");args=ap.parse_args()
with zipfile.ZipFile(h/"archive.bin") as z:
 for x in m["members"]:
  data=z.read(x["original_path"])
  if len(data)!=x["original_bytes"] or hashlib.sha256(data).hexdigest()!=x["original_sha256"]:raise RuntimeError("member hash mismatch")
  print("PASS",x["original_path"],x["original_sha256"])
  if args.output_dir:
   base=pathlib.Path(args.output_dir).resolve();target=(base/x["original_path"]).resolve()
   if base not in target.parents:raise RuntimeError("outside output directory")
   target.parent.mkdir(parents=True,exist_ok=True)
   with target.open("xb") as f:f.write(data)
