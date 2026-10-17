from pathlib import Path
import hashlib, json, zipfile, datetime
ROOT=Path("/home/yndx/zxk/rul")
v9=ROOT/"data/raw/HUST/HUST_v9.zip"
v11=ROOT/"data/raw/HUST/HUST_v11.zip"
hashfile=ROOT/"reports/data_schema_audit/run_20261015T164049_918837Z/hust_file_sha256.json"
outdir=ROOT/"reports/data_same_version_staging"
def sha_stream(stream):
    h=hashlib.sha256()
    while True:
        b=stream.read(8*1024*1024)
        if not b: break
        h.update(b)
    return h.hexdigest()
def run():
    if not v11.exists(): raise SystemExit("v11 archive not published yet")
    oldhash={r["file_name"]:r["sha256"] for r in json.loads(hashfile.read_text())["hashes"]}
    with zipfile.ZipFile(v9) as a, zipfile.ZipFile(v11) as b:
        bad9=a.testzip(); bad11=b.testzip()
        na={x.filename:x for x in a.infolist()}
        nb={x.filename:x for x in b.infolist()}
        names=sorted(set(na)|set(nb))
        rows=[]
        for n in names:
            x=na.get(n); y=nb.get(n)
            row={"member":n,"v9_present":x is not None,"v11_present":y is not None}
            if x and y:
                row.update(v9_crc32=f"{x.CRC:08x}",v11_crc32=f"{y.CRC:08x}",
                    v9_uncompressed_bytes=x.file_size,v11_uncompressed_bytes=y.file_size,
                    same_crc_size=(x.CRC==y.CRC and x.file_size==y.file_size),
                    v9_compress_type=x.compress_type,v11_compress_type=y.compress_type,
                    v9_datetime=list(x.date_time),v11_datetime=list(y.date_time))
                if n.lower().endswith(".pkl"):
                    with b.open(y) as f: hs=sha_stream(f)
                    key=Path(n).name
                    expected=oldhash.get(key)
                    row.update(v11_sha256=hs,v9_extracted_sha256=expected,
                        pkl_byte_identical=(hs==expected and expected is not None))
            rows.append(row)
    result={"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "v9_archive":str(v9),"v11_archive":str(v11),"v9_testzip_bad_member":bad9,
        "v11_testzip_bad_member":bad11,"v9_members":len(na),"v11_members":len(nb),
        "member_name_sets_equal":set(na)==set(nb),"all_common_crc_size_equal":all(
            r.get("same_crc_size",False) for r in rows if r["v9_present"] and r["v11_present"]),
        "pkl_count":sum(r["member"].lower().endswith(".pkl") and r["v11_present"] for r in rows),
        "all_pkl_bytes_identical":all(r.get("pkl_byte_identical",False) for r in rows if r["member"].lower().endswith(".pkl") and r["v11_present"]),
        "members":rows}
    outdir.mkdir(parents=True,exist_ok=True)
    p=outdir/"hust_v9_v11_member_compare.json"
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="members"},ensure_ascii=False,indent=2))
    print("result_path="+str(p))
if __name__=="__main__": run()
