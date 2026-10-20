import pathlib,json,hashlib,zipfile,io,gzip,time,signal,fcntl,datetime,csv,collections,math
import openpyxl
from calce_io import identify,records
from capacity_rules import derive
R=pathlib.Path('/home/yndx/zxk/rul');D=pathlib.Path(__file__).resolve().parent;OUT=R/'data/processed/CALCE_CS2_35_DataV1_v3';CACHE=R/'data/processed/CALCE_CS2_35_repair_v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
P=json.loads((D/'reconstruction_protocol_v3.json').read_text())
for name,h in P['prior_receipt_sha256'].items():assert sha(D/name)==h
G=json.loads((D/'ROOT_RECONSTRUCTION_GO_v3.json').read_text())
for name,h in G['sha256'].items():assert sha(D/name)==h,name
lock=open(R/'automation/state/online_survival_cpu.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert json.loads((R/'automation/state/coordinator.json').read_text())['owner']==G['owner']
with open(D/'reconstruction_claim_v3.json','x') as f:json.dump({'consumed':True,'go_sha256':sha(D/'ROOT_RECONSTRUCTION_GO_v3.json')},f)
start=time.monotonic();signal.signal(signal.SIGALRM,lambda *a:(_ for _ in ()).throw(TimeoutError('300s budget')));signal.alarm(P['max_seconds']);s={'status':'RUNNING','member_reads':0,'member_bytes':0,'raw_rows':0,'files':[],'new_fits':0,'inference':0,'other_cell_reads':0};allq=[]
try:
 assert sha(R/P['archive'])==P['archive_sha256'];directory=json.loads((R/'reports/calce_cs2_35_firstfile_20261019_root/archive_directory.json').read_text());entries=[e for e in directory['entries'] if not e['directory']];entries.sort(key=lambda e:datetime.datetime.strptime(e['name'].split('CS2_35_')[-1].split('.')[0],'%m_%d_%y'))
 old=list(csv.DictReader((R/'reports/calce_cs2_35_series_20261019_root/canonical_occurrences.csv').open()));oldmap={(x['file'],int(x['occurrence'])):x for x in old};reg=[]
 with zipfile.ZipFile(R/P['archive']) as z:
  for e in entries:
   name=e['name'];filename=pathlib.Path(name).name;cached=CACHE/'CS2_35_10_29_10.records.jsonl.gz'
   prior_cache=pathlib.Path(P['cache_sources'].get(filename+'.records.jsonl.gz','/nonexistent'))
   if prior_cache.name in P['prior_record_caches']:
    binding=P['prior_cache_member_binding'][prior_cache.name];assert binding['archive_sha256']==P['archive_sha256'] and binding['member_name']==name and binding['member_bytes']==e['bytes'] and binding['crc32']==e['crc32']
    assert sha(prior_cache)==P['prior_record_caches'][prior_cache.name];rr=[json.loads(x) for x in gzip.open(prior_cache,'rt')];selected=['Channel_1-008',1];schemas=[];h=binding['original_member_sha256'];s['prior_raw_cache_files_reused']=s.get('prior_raw_cache_files_reused',0)+1
   elif filename=='CS2_35_10_29_10.xlsx':
    assert sha(cached)==P['cached_failed_file_records_sha256'];assert json.loads((D/'schema_receipt_server.json').read_text())['member_sha256']==P['cached_failed_file_member_sha256']
    rr=[json.loads(x) for x in gzip.open(cached,'rt')];selected=['Channel_1-008',1];schemas=json.loads((D/'measurement_probe_server.json').read_text())['schemas'];h='831f59a1087c583330bdb8e4a74ceda2b0cc1af0d4f12c16b750bf53683d45ba';s['failed_cached_rows_reused']=len(rr)
   else:
    assert s['member_reads']<P['max_new_archive_member_reads'];i=z.getinfo(name);assert i.file_size==e['bytes'] and format(i.CRC,'08x')==e['crc32'];assert s['member_bytes']+i.file_size<=P['max_total_member_bytes'];s['member_reads']+=1;b=z.read(i);s['member_bytes']+=len(b);h=hashlib.sha256(b).hexdigest()
    with zipfile.ZipFile(io.BytesIO(b)) as iz:assert sum(x.file_size for x in iz.infolist())<=P['max_internal_xml_bytes_per_workbook']
    w=openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True,keep_links=False);assert len(w.worksheets)<=P['max_sheets'];selected,schemas=identify(w);rr=list(records(w,selected,P['max_rows_per_file']));w.close()
   assert rr;s['raw_rows']+=len(rr);assert s['raw_rows']<=P['max_rows_total'];q=derive(rr,name,P['thresholds']);allq+=q
   cachepath=OUT/(filename+'.records.jsonl.gz')
   with gzip.open(cachepath,'xt') as f:
    for row in rr:f.write(json.dumps(row)+'\n')
   for item in q:
    key=(name,item['source_occurrence'])
    if key in oldmap:
     prev=oldmap[key];assert int(prev['source_cycle'])==item['source_cycle'];assert int(prev['rows'])==item['source_rows'];equal=lambda a,b:(a=='' and b is None) or (a!='' and b is not None and math.isclose(float(a),b,abs_tol=1e-9))
     assert equal(prev['discharge_counter_Ah'],item.get('legacy_end_counter_Ah'));assert equal(prev['partial_integral_Ah'],item.get('partial_integral_legacy_Ah'));reg.append(key)
   s['files'].append({'source_file':name,'member_sha256':h,'member_bytes':e['bytes'],'raw_records_sha256':sha(cachepath),'raw_rows':len(rr),'source_occurrences':len(q),'selected_sheet':selected[0],'schemas':schemas,'first_record':{k:rr[0][k] for k in ['datetime','time_s','cycle','data_point','discharge_counter_Ah']},'last_record':{k:rr[-1][k] for k in ['datetime','time_s','cycle','data_point','discharge_counter_Ah']}})
 assert len(reg)==304;s['legacy_regression_304_exact']=True
 s['boundaries']=[{'previous':a['source_file'],'next':b['source_file'],'wall_gap_s':(datetime.datetime.fromisoformat(b['first_record']['datetime'])-datetime.datetime.fromisoformat(a['last_record']['datetime'])).total_seconds(),'source_cycle_change':b['first_record']['cycle']-a['last_record']['cycle'],'test_time_change_s':b['first_record']['time_s']-a['last_record']['time_s'],'counter_change_Ah':b['first_record']['discharge_counter_Ah']-a['last_record']['discharge_counter_Ah'],'continuity':'UNVERIFIED_NO_ASSUMED_NATIVE_CYCLE_JOIN'} for a,b in zip(s['files'],s['files'][1:])]
 seen={};endkeys={}
 for x in allq:
  fingerprint=x['measurement_fingerprint_sha256']
  if fingerprint in seen:
   x['duplicate_of']=seen[fingerprint];x['status']='EXACT_DUPLICATE_SOURCE_ALIAS';x['flags'].append('exact_duplicate_signal_retained')
  else:seen[fingerprint]=x['source_file']+':'+str(x['source_occurrence'])
  if 'discharge_end_datetime' in x and x['status']!='EXACT_DUPLICATE_SOURCE_ALIAS':
   key=(x['discharge_end_datetime'],x['source_cycle'])
   if key in endkeys:
    for z in [endkeys[key],x]:z['status']='UNCERTAIN';z['flags'].append('same_end_time_different_raw_signal');z['capacity_Ah']=None;z['soh_nominal']=None
   else:endkeys[key]=x
 s['exact_duplicate_aliases']=sum(x['status']=='EXACT_DUPLICATE_SOURCE_ALIAS' for x in allq)
 valid=[x for x in allq if x['status']=='VALID_SAMPLED_CC_DISCHARGE'];cross=[x for x in valid if x['capacity_Ah']<=.88];flags=collections.Counter(f for x in allq for f in x['flags']);first=min(cross,key=lambda x:x['discharge_end_datetime']) if cross else None
 s.update(status='COMPLETE_MEASUREMENT_ASSET_CONTINUITY_QUALIFIED_LIMITS',source_files=len(entries),source_occurrences=len(allq),valid_discharges=len(valid),uncertain_occurrences=sum(x['status']=='UNCERTAIN' for x in allq),flags=dict(flags),capacity_range_Ah=[min(x['capacity_Ah'] for x in valid),max(x['capacity_Ah'] for x in valid)] if valid else None,observed_crossings=len(cross),first_observed_crossing=None if not first else {k:first[k] for k in ['source_file','source_cycle','discharge_end_datetime','capacity_Ah']},true_first_passage_EOLevent=None,global_native_cycle_RUL_labels_allowed=False,independent_model_confirmation_ready=False,right_censoring_status='NOT_SUBSTITUTED_FOR_EVENT; whole-life gap continuity unverified',new_fits_allowed=False)
except Exception as e:s.update(status='FAILED_STOP_PRESERVE_PARTIAL',error=type(e).__name__+': '+str(e))
finally:
 signal.alarm(0)
 with open(OUT/'discharge_measurements.jsonl','x') as f:
  for x in allq:f.write(json.dumps(x)+'\n')
 s['measurement_table_sha256']=sha(OUT/'discharge_measurements.jsonl');s['saved_occurrences']=len(allq);s['elapsed_seconds']=time.monotonic()-start
 with open(D/'reconstruction_summary_v3.json','x') as f:json.dump(s,f,indent=2)
 print(json.dumps({k:v for k,v in s.items() if k not in ['files','boundaries']}))
