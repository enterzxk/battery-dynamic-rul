from pathlib import Path
import json,csv,hashlib
R=Path('/home/yndx/zxk/rul');E=R/'experiments/capacity_firstpassage_seed42_v1';D=R/'data/processed/capacity20_endpoint_targets_v2';D.mkdir(exist_ok=False)
co=json.loads((E/'cohort.json').read_text());rows=[];cells=[];oldmax=0.
for x in co['manifests']:
 mp=Path(x['path']);assert hashlib.sha256(mp.read_bytes()).hexdigest()==x['sha256']
 for c in json.loads(mp.read_text())['cells']:
  cid=c['cell_id']
  if co['roles'][cid]!='fit':continue
  fp=mp.parent/(cid+'_features.csv');cp=mp.parent/(cid+'_cycles.csv');assert hashlib.sha256(fp.read_bytes()).hexdigest()==c['features_sha256'] and hashlib.sha256(cp.read_bytes()).hexdigest()==c['cycles_sha256'];ft={int(r['origin_cycle']):r for r in csv.DictReader(fp.open())};raw={int(r['actual_cycle']):r for r in csv.DictReader(cp.open())};ev=c['event_cycle'];counts={'before_event':0,'at_event':0,'after_event':0}
  for s,r in sorted(ft.items()):
   t=s+20;assert s<ev and int(r['visible_through_cycle'])==s and r['rate20_missing']=='False'
   if t not in raw or raw[t]['valid']!='True':continue
   phase='before_event' if t<ev else 'at_event' if t==ev else 'after_event';counts[phase]+=1;target=(float(raw[t]['capacity_Ah'])/1.1-float(r['soh']))*1000
   if t in ft:oldmax=max(oldmax,abs(target-(float(ft[t]['soh'])-float(r['soh']))*1000))
   rows.append({'cell_id':cid,'source_origin':s,'target_cycle':t,'features_visible_through':s,'age':s,'SOH':float(r['soh']),'rate20_mSOH_per_cycle':float(r['rate20_per_cycle'])*1000,'target_delta_mSOH':target,'target_phase_audit_only_not_feature':phase})
  assert counts['at_event']==1 and counts['after_event']==19;cells.append({'cell_id':cid,'origins':sum(counts.values()),'target_counts':counts,'features_sha256':c['features_sha256'],'cycles_sha256':c['cycles_sha256']})
assert len(cells)==42 and len(rows)==22281 and oldmax<1e-9
p=D/'fit_pairs.csv'
with p.open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
manifest={'status':'COMPLETE_TRAIN_ONLY_ENDPOINT_TARGET_DATA_V2','fit_cells':42,'fit_pairs':len(rows),'old_pre_event_pairs':21441,'added_at_event_pairs':42,'added_post_event_target_pairs':798,'max_old_target_delta_mSOH':oldmax,'dataset_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'cohort_sha256':hashlib.sha256((E/'cohort.json').read_bytes()).hexdigest(),'input_columns':['age','SOH','rate20_mSOH_per_cycle'],'label':'target_delta_mSOH=(observed Q_(s+20)/1.1-SOH_s)*1000','audit_only_forbidden_feature_columns':['target_cycle','target_phase_audit_only_not_feature'],'input_visible_through':'s only; s+20 capacity used solely supervised target from42fit cells','postevent_labels_not_forced_monotonic':True,'calibration_source':'Reuse existing4367samecal target pairs; no calraw/dev/test reads in builder','per_cell':cells,'new_fits':0,'new_forwards':0}
(D/'manifest.json').open('x').write(json.dumps(manifest,indent=2));print(json.dumps({k:v for k,v in manifest.items() if k!='per_cell'}))
