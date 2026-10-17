from pathlib import Path
import json,csv,collections
r=Path('/home/yndx/zxk/rul');o=r/'experiments/dynamic_A_matr_retrospective_seed42_v1';rows=list(csv.DictReader((r/'reports/dynamic_A_eligible_20261017_root/candidate_features.csv').open()));cells={x['cell_id']:x for x in rows};counts=collections.Counter((x['split'],c.split('_b')[1].split('c')[0],x['event_status']) for c,x in cells.items());out={'status':'EXISTING_COHORT_BATCH_OBSERVATION_CROSS_TAB','counts':[{'split':s,'batch':int(b),'event_status':e,'cells':n} for (s,b,e),n in sorted(counts.items())],'interpretation':'Observed versus censored subgroup comparison may be confounded by source batch. This is descriptive association, not an effect of censoring, labels or chemistry. Batch already existed as legal A1/A2 feature; no refit/label change.','new_fits':0,'optimizer_steps':0}
with (o/'batch_observation_cross_tab.json').open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
