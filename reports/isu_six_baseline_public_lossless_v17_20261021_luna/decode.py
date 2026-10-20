#!/usr/bin/env python3
"""Decode the lossless ISU prediction archive into a user-selected directory."""
import argparse,csv,hashlib,io,json,lzma
from pathlib import Path
MAGIC=b"ISUCSVL1\n"
HERE=Path(__file__).resolve().parent

def render(d,names,layout,with_header=True):
 h=d["header"];ki=[h.index(k) for k in d["key_columns"]];mi=h.index(d["model_column"]);xi=[h.index(k) for k in d["metric_columns"]]
 s=io.StringIO(newline="");w=csv.writer(s,lineterminator="\r\n")
 if with_header:w.writerow(h)
 def emit(m,j):
  row=[None]*len(h)
  for i,v in zip(ki,d["keys"][j]):row[i]=v
  row[mi]=m
  for i,v in zip(xi,d["metrics_by_model"][m][j]):row[i]=v
  w.writerow(row)
 if layout=="interleaved":
  for j in range(len(d["keys"])):
   for m in names:emit(m,j)
 elif layout=="model-major":
  for m in names:
   for j in range(len(d["keys"])):emit(m,j)
 else:raise ValueError("invalid archive layout")
 return s.getvalue().encode("utf-8")

def main():
 p=argparse.ArgumentParser();p.add_argument("--target-dir",type=Path,default=HERE/"decoded",help="create-only destination; defaults beside this script")
 a=p.parse_args();blob=(HERE/"archive.bin").read_bytes()
 if not blob.startswith(MAGIC):raise RuntimeError("archive signature mismatch")
 d=json.loads(lzma.decompress(blob[len(MAGIC):]).decode("utf-8"))
 outputs=[(d["sources"][0],render(d,d["cpu_model_names"],"interleaved")+render(d,d["gru_model_names"],"model-major",False)),(d["sources"][1],render(d,d["cpu_model_names"],"interleaved")),(d["sources"][2],render(d,d["gru_model_names"],"model-major"))]
 a.target_dir.mkdir(parents=True,exist_ok=True);done=[]
 for meta,data in outputs:
  digest=hashlib.sha256(data).hexdigest()
  if len(data)!=meta["original_bytes"] or digest!=meta["original_sha256"]:raise RuntimeError("byte-exact check failed: "+meta["output_name"])
  with (a.target_dir/meta["output_name"]).open("xb") as f:f.write(data)
  done.append({"file":meta["output_name"],"bytes":len(data),"sha256":digest})
 print(json.dumps({"status":"DECODED_BYTE_EXACT","target_dir":str(a.target_dir.resolve()),"files":done},ensure_ascii=False))
if __name__=="__main__":main()
