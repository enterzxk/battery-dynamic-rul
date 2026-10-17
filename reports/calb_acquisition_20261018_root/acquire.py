"""One bounded CALB archive acquisition; no deserialization, model or fitting."""
from pathlib import Path,PurePosixPath
import json,hashlib,datetime,urllib.request,time,zipfile,ast,re,os,zlib,stat
R=Path('/home/yndx/zxk/rul');O=R/'reports/calb_acquisition_20261018_root';D=R/'data/raw/CALB/acquisition_v11_20261018_root'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,obj):
 with (O/name).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n')
url='https://zenodo.org/api/records/19688272/files/CALB.zip/content';expected=12671967;md5_expected='2b1006e96e0ca42765a732060f964687'
start=time.monotonic();state=dict(status='STARTED',at_utc=now(),metadata_requests=0,head_requests=0,artifact_get_requests=0,artifact_bytes_transferred=0,archive_pkl_members_decompressed=0,test_pkl_members_opened=0,test_label_values_decoded=0,new_fits=0,optimizer_steps=0)
try:
 h=json.loads((R/'reports/data_same_version_staging/download_v11_hust_20261015T165557_932008Z_result.json').read_text())
 m=json.loads((R/'data/raw/MATR/download_v11_progress.json').read_text());assert m['status']=='DONE'
 prior=h['combined_estimate_bytes']+m['bytes_transferred'];limit=h['phase_total_budget_bytes'];assert prior+expected+524288<limit
 budget=dict(prior_HUST_phase_combined_estimate=h['combined_estimate_bytes'],MATR_actual_transfer=m['bytes_transferred'],prior_source_phase_transfer_estimate=prior,phase_limit_bytes=limit,CALB_artifact_cap=expected,metadata_cap=524288,total_new_network_cap=expected+524288,prior_PBT_budgets_untouched=True)
 write('budget_and_bounds.json',dict(**budget,max_artifact_get_requests=1,max_member_uncompressed_bytes=64*1024**2,max_selected_total_uncompressed_bytes=256*1024**2,max_wall_seconds=180,retry_allowed=False))
 D.mkdir(parents=True,exist_ok=False)
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':'http://127.0.0.1:29137','https':'http://127.0.0.1:29137'}))
 def req(u,method='GET'):
  if time.monotonic()-start>180:raise RuntimeError('wall deadline')
  return urllib.request.Request(u,method=method,headers={'User-Agent':'Battery-RUL-public-research/0.1'})
 state['metadata_requests']+=1
 with opener.open(req('https://zenodo.org/api/records/19688272'),timeout=30) as response:
  raw=response.read(524289);assert len(raw)<=524288;meta=json.loads(raw);metadata_status=response.status
 entry=next(x for x in meta['files'] if x['key']=='CALB.zip');assert entry['size']==expected and entry['checksum']=='md5:'+md5_expected
 write('live_source_metadata.json',dict(at_utc=now(),record_id=meta['id'],version=meta.get('metadata',{}).get('version'),doi=meta.get('doi'),metadata_http_status=metadata_status,metadata_response_bytes=len(raw),metadata_response_sha256=hashlib.sha256(raw).hexdigest(),entry=entry,official_page_url='https://zenodo.org/records/19688272',metadata_url='https://zenodo.org/api/records/19688272'))
 state['head_requests']+=1
 with opener.open(req(url,'HEAD'),timeout=30) as response:
  headers={k:response.headers.get(k) for k in ['Content-Length','Content-Type','ETag','Last-Modified','Accept-Ranges']};head_status=response.status
 assert head_status==200
 if headers['Content-Length'] is not None:assert int(headers['Content-Length'])==expected
 write('head_receipt.json',dict(url=url,http_status=head_status,headers=headers,at_utc=now()))
 partial=D/'CALB_v11.zip.partial';state['artifact_get_requests']+=1
 md5,sh=hashlib.md5(),hashlib.sha256()
 with opener.open(req(url),timeout=30) as response,partial.open('xb') as f:
  assert response.status==200
  while True:
   if time.monotonic()-start>180:raise RuntimeError('wall deadline')
   buf=response.read(min(1024*1024,expected+1-state['artifact_bytes_transferred']))
   if not buf:break
   state['artifact_bytes_transferred']+=len(buf)
   if state['artifact_bytes_transferred']>expected:raise RuntimeError('artifact cap exceeded')
   f.write(buf);md5.update(buf);sh.update(buf)
  f.flush();os.fsync(f.fileno())
 assert state['artifact_bytes_transferred']==expected and md5.hexdigest()==md5_expected
 final=D/'CALB_v11.zip';os.link(partial,final)
 receipt=dict(status='VERIFIED_OFFICIAL_ARCHIVE_CHECKSUM',url=url,record_id=19688272,bytes=expected,md5=md5.hexdigest(),sha256=sh.hexdigest(),at_utc=now(),archive_path=str(final),artifact_get_requests=1,bytes_transferred=state['artifact_bytes_transferred'])
 write('acquisition_receipt.json',receipt)
 P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
 split={}
 for n in ast.walk(ast.parse((P/'data_provider/data_split_recorder.py').read_text())):
  if isinstance(n,ast.Assign):
   for t in n.targets:
    if isinstance(t,ast.Name) and t.id in ['CALB_train_files','CALB_val_files','CALB_test_files']:split[t.id]=ast.literal_eval(n.value)
 allowed=set(split['CALB_train_files']+split['CALB_val_files']);test=set(split['CALB_test_files']);assert len(allowed)==22 and not allowed&test
 entries=[];selected=[];total=0
 with zipfile.ZipFile(final) as z:
  infos=z.infolist();assert len(infos)<1000 and len({x.filename for x in infos})==len(infos)
  for x in infos:
   p=PurePosixPath(x.filename);assert not p.is_absolute() and '..' not in p.parts and '\\' not in x.filename
   assert not stat.S_ISLNK(x.external_attr>>16) and not x.flag_bits&1
   entries.append(dict(name=x.filename,bytes=x.file_size,crc32='%08x'%x.CRC,compressed_bytes=x.compress_size))
  for name in sorted(allowed):
   choices=[x for x in infos if PurePosixPath(x.filename).name==name];assert len(choices)==1
   x=choices[0];assert x.file_size<=64*1024**2;total+=x.file_size;assert total<=256*1024**2
   count=0;crc=0;hh=hashlib.sha256()
   with z.open(x) as f:
    while True:
     buf=f.read(1024*1024)
     if not buf:break
     count+=len(buf);crc=zlib.crc32(buf,crc);hh.update(buf)
   assert count==x.file_size and crc==x.CRC;state['archive_pkl_members_decompressed']+=1
   selected.append(dict(file_name=name,member=x.filename,bytes=count,crc32='%08x'%crc,sha256=hh.hexdigest(),role='train' if name in split['CALB_train_files'] else 'validation'))
 label_archive=R/'data/raw/HUST/Life_labels_v11.zip';assert sha(label_archive)=='45b3adf3f5ea2819244ac206f204defd4eea0ad1eaa4d38534f0543cab4ac033'
 with zipfile.ZipFile(label_archive) as z:
  labels=[x for x in z.infolist() if PurePosixPath(x.filename).name=='CALB_labels.json'];assert len(labels)==1
  x=labels[0];assert x.file_size<=65536
  # Metadata-only key coverage: never json-decode label values, including test values.
  with z.open(x) as f:raw=f.read(65537)
  assert len(raw)==x.file_size and zlib.crc32(raw)==x.CRC
  keys=re.findall(rb'"(CALB_[^"\\]+\.pkl)"\s*:',raw)
  selected_keys=[k.decode('ascii') for k in keys if k.decode('ascii') in allowed]
  assert len(selected_keys)==22 and set(selected_keys)==allowed
 coverage=dict(status='FIXED22_ARCHIVE_CRC_AND_LABEL_KEY_COVERAGE_PASS',at_utc=now(),train_files=17,validation_files=5,test_filename_count_static=5,all_archive_entries=entries,selected_members=selected,selected_total_uncompressed_bytes=total,labels=dict(archive_path=str(label_archive),archive_sha256=sha(label_archive),member=x.filename,member_bytes=x.file_size,member_crc_pass=True,selected_trainval_keys=sorted(selected_keys),numeric_label_values_decoded=False,mixed_label_member_bytes_read_for_key_only_coverage=True,test_label_values_decoded=0),test_pkl_members_opened=0,semantic_data_audit_passed=False,physical_identity_verified=False,training_allowed=False,new_fits=0,optimizer_steps=0,bindings={str(P/'data_provider/data_split_recorder.py'):sha(P/'data_provider/data_split_recorder.py'),str(final):sha(final),str(Path(__file__)):sha(Path(__file__))})
 write('archive_coverage.json',coverage)
 state.update(status='ACQUISITION_AND_FIXED22_STRUCTURAL_COVERAGE_COMPLETE',completed_at=now(),elapsed_seconds=time.monotonic()-start,artifact_sha256=sh.hexdigest(),selected_uncompressed_bytes=total,phase_source_estimate_after=prior+expected+len(raw),test_samples_opened=False,model_loads=0,new_inference=0)
 write('completion_receipt.json',state);print(json.dumps(state),flush=True)
except BaseException as e:
 state.update(status='FAILED_STOP_NO_RETRY',at_utc=now(),error_type=type(e).__name__,error=str(e),elapsed_seconds=time.monotonic()-start)
 write('failure_receipt.json',state);print(json.dumps(state),flush=True);raise
