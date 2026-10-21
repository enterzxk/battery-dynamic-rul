"""Restore byte-exact historical progress into a NEW directory, no overwrite."""
from pathlib import Path
import json,zlib,hashlib,os,argparse
def main():
 p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('target',type=Path);a=p.parse_args()
 d=json.loads(zlib.decompress(a.archive.read_bytes()));a.target.mkdir(parents=True,exist_ok=False)
 for x in d['files']:
  rel=Path(x['path']);assert not rel.is_absolute() and '..' not in rel.parts
  raw=x['text'].encode('utf-8');assert len(raw)==x['bytes'] and hashlib.sha256(raw).hexdigest()==x['sha256']
  out=a.target/rel;out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('xb') as f:f.write(raw)
if __name__=='__main__':main()
