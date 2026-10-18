from pathlib import Path
import json,re,hashlib,math,itertools,datetime,fcntl
from fractions import Fraction as F
R=Path('/home/yndx/zxk/rul');O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):
 with (O/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def parse(text):
 num=r'(\d+(?:\.\d+)?)';m=re.fullmatch(num+r'C\('+num+r'%\)-'+num+r'C',text)
 if m:
  a,s,b=map(F,m.groups());s/=100;segs=[(F(0),s,a),(s,F(4,5),b)]
 else:
  m=re.fullmatch(num+'-'+num+'-'+num+'-'+num,text);assert m;cs=list(map(F,m.groups()));segs=[(F(i,5),F(i+1,5),c) for i,c in enumerate(cs)]
 merged=[]
 for a,b,c in segs:
  assert c>0 and a<=b
  if a==b:continue
  if merged and merged[-1][2]==c and merged[-1][1]==a:merged[-1]=(merged[-1][0],b,c)
  else:merged.append((a,b,c))
 assert merged[0][0]==0 and merged[-1][1]==F(4,5)
 values=[]
 for i in range(4):
  a,b=F(i,5),F(i+1,5);hours=sum((max(F(0),min(b,y)-max(a,x))/c for x,y,c in merged),F(0));assert hours>0;values.append(F(1,5)/hours)
 return tuple(merged),tuple(values)
def serialized(schedule):return [[str(a),str(b),str(c)] for a,b,c in schedule]
def main():
 p=json.loads((O/'protocol.json').read_text());assert p['cells']==52 and p['abs_effectiveC_tolerance']==1e-12 and p['new_fits']==0
 lock=open(R/'automation/state/online_survival_cpu.lock','a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);control=json.loads((R/'automation/state/coordinator.json').read_text());assert control['owner']==control['thread_id']==p['owner'] and not control['new_fits_allowed']
 with (O/'invocation.claim').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 for rec in p['sources'].values():assert sha(R/rec['path'])==rec['sha256']
 sources=lambda k:R/p['sources'][k]['path'];sem=json.loads(sources('semantics').read_text());assert sem['encoder_sha256']==sha(sources('encoder_v1'))
 rows=json.loads(sources('policy').read_text());assert len(rows)==52 and len({r['cell_id'] for r in rows})==52
 fields=p['columns'];meta={};maximum_error=0.
 for r in rows:
  assert r['role'] in ['fit','calibration'];schedule,vector=parse(r['raw_policy']);stored=tuple(float(r[k]) for k in fields);err=max(abs(a-float(b)) for a,b in zip(stored,vector));maximum_error=max(maximum_error,err);assert err<=1e-12
  meta[r['cell_id']]=dict(row=r,schedule=schedule,exact_vector=vector,stored_vector=stored)
 ids=sorted(meta);pairs=[];tolpairs=[];adj={c:set() for c in ids}
 for a,b in itertools.combinations(ids,2):
  x,y=meta[a],meta[b];delta=max(abs(u-v) for u,v in zip(x['stored_vector'],y['stored_vector']))
  if delta<=1e-12:
   adj[a].add(b);adj[b].add(a);same_schedule=x['schedule']==y['schedule'];exact_equal=x['exact_vector']==y['exact_vector']
   rec=dict(cell_a=a,role_a=x['row']['role'],cell_b=b,role_b=y['row']['role'],raw_policy_a=x['row']['raw_policy'],raw_policy_b=y['row']['raw_policy'],raw_strings_equal=x['row']['raw_policy']==y['row']['raw_policy'],canonical_schedules_equal=same_schedule,exact_rational_effective_vector_equal=exact_equal,max_stored_vector_delta=delta,encoded_vector=list(x['stored_vector']))
   tolpairs.append(rec)
   if not same_schedule:pairs.append(rec)
 groups=[];unseen=set(ids)
 while unseen:
  root=min(unseen);stack=[root];comp=set()
  while stack:
   c=stack.pop()
   if c in comp:continue
   comp.add(c);stack.extend(adj[c]-comp)
  unseen-=comp;members=sorted(comp)
  # Refuse nontransitive tolerance grouping rather than quietly merging chains.
  diameter=max((max(abs(a-b) for a,b in zip(meta[x]['stored_vector'],meta[y]['stored_vector'])) for x,y in itertools.combinations(members,2)),default=0.)
  assert diameter<=1e-12
  raw={meta[c]['row']['raw_policy'] for c in members};canon={meta[c]['schedule'] for c in members}
  groups.append(dict(cells=members,size=len(members),raw_strings=sorted(raw),canonical_schedule_count=len(canon),distinct_schedule_collision=len(canon)>1,fit_cells=sum(meta[c]['row']['role']=='fit' for c in members),cal_cells=sum(meta[c]['row']['role']=='calibration' for c in members),diameter=diameter))
 counts=dict(cells=52,fit_cells=sum(r['role']=='fit' for r in rows),cal_cells=sum(r['role']=='calibration' for r in rows),raw_policy_strings=len({r['raw_policy'] for r in rows}),canonical_schedules=len({x['schedule'] for x in meta.values()}),effectiveC_groups=len(groups),raw_different_same_encoding_pairs=sum(not r['raw_strings_equal'] for r in tolpairs),distinct_schedule_collision_pairs=len(pairs),exact_rational_collision_pairs=sum(r['exact_rational_effective_vector_equal'] for r in pairs),collision_groups=sum(g['distinct_schedule_collision'] for g in groups),collision_involved_cells=len({r[k] for r in pairs for k in ['cell_a','cell_b']}),fit_fit_collision_pairs=sum(r['role_a']==r['role_b']=='fit' for r in pairs),fit_cal_collision_pairs=sum({r['role_a'],r['role_b']}=={'fit','calibration'} for r in pairs),cal_cal_collision_pairs=sum(r['role_a']==r['role_b']=='calibration' for r in pairs),maximum_stored_vs_exact_effectiveC_error=maximum_error)
 # Independent hand arithmetic for the motivating pair, original0to20SOC durations.
 a=F(4,100)/F(1)+F(16,100)/F(6);b=F(10,100)/F(2)+F(10,100)/F(6);assert a==b==F(1,15);assert F(1,5)/a==3
 ex=next(r for r in pairs if {r['cell_a'],r['cell_b']}=={'MATR_b2c0','MATR_b2c1'});assert ex['exact_rational_effective_vector_equal'] and not ex['canonical_schedules_equal']
 example=dict(pair=ex,first20_SOC_hours_A=str(a),first20_SOC_hours_B=str(b),first20_SOC_effectiveC='3',remaining_bins_effectiveC=['6','6','6'],schedule_A=serialized(meta['MATR_b2c0']['schedule']),schedule_B=serialized(meta['MATR_b2c1']['schedule']))
 dump('collision_pairs.json',pairs);dump('encoding_groups.json',groups);dump('summary.json',counts);dump('arithmetic_example.json',example)
 dump('minimal_validation.json',dict(status='PASS_ALL52_EXACT_EXISTING_ENCODING_CHECK_AND_ONE_HAND_CASE',rows=52,pairs_examined=52*51//2,tolerance_group_diameter_verified=True,maximum_stored_vs_exact_error=maximum_error,source_encoder_v1_hash_matches_semantics=True,legacy_encoder_py_hash_differs_and_is_v0=True,no_outcome_labels_read=True,no_new_predictive_encoding=True,new_fits=0,new_model_inference=0,dev_test_reads=0))
 dump('completion.json',dict(status='COMPLETE_EXISTING_POLICY_ENCODING_COLLISION_AUDIT',new_fits=0,new_model_inference=0,new_predictive_encodings=0,raw_battery_reads=0,dev_test_reads=0,outcome_label_reads=0,protocol_sha256=sha(O/'protocol.json'),script_sha256=sha(Path(__file__))))
 print(json.dumps(dict(summary=counts,collision_groups=[g for g in groups if g['distinct_schedule_collision']])))
if __name__=='__main__':main()
