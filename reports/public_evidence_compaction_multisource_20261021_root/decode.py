import pathlib,json,zlib,hashlib,sys
p=pathlib.Path(__file__).parent
d=json.loads(zlib.decompress((p/"archive.bin").read_bytes()))
i=json.loads((p/"validation.json").read_text())
assert all(hashlib.sha256(v.encode()).hexdigest()==i["files"][k]["sha256"] for k,v in d.items())
if len(sys.argv)>1: print(d[sys.argv[1]],end="")
else: print("\n".join(d))
