import pathlib,zlib,json,hashlib,sys
p=pathlib.Path(__file__).parent
b=zlib.decompress((p/"archive.bin").read_bytes());v=json.loads((p/"validation.json").read_text())
assert hashlib.sha256(b).hexdigest()==v["original_sha256"]
sys.stdout.write(b.decode("utf8"))
