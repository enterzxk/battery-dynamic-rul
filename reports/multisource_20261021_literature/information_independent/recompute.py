import csv, hashlib, json, random, statistics
from pathlib import Path
from collections import defaultdict
R=Path("/home/yndx/zxk/rul")
OUT=R/"reports/multisource_20261021_literature/information_independent"
go=json.loads((R/"experiments/multisource_information_20261021/SAVED_PREDICTION_REVIEW_GO.json").read_text())
if go.get("status")!="APPROVED" or any(go.get(k)!=v for k,v in [("new_fits",0),("model_loads",0),("raw_payload_reads",0),("C4_reads",0)]): raise RuntimeError("GO scope invalid")
for rel,want in go["allowed_files"].items():
 got=hashlib.sha256((R/rel).read_bytes()).hexdigest()
 if got!=want: raise RuntimeError("GO hash mismatch: "+rel)
pred=R/"experiments/multisource_information_20261021/run1/predictions.csv"
rows=list(csv.DictReader(pred.open(newline="")))
def f(x): return None if x is None or x=="" else float(x)
def mean(xs): return statistics.fmean(xs)
def quantile(xs,p):
 z=sorted(xs); t=(len(z)-1)*p; lo=int(t); hi=min(lo+1,len(z)-1); return z[lo]+(t-lo)*(z[hi]-z[lo])
# Recompute row metrics solely from the GO-approved saved predictions.
for r in rows:
 p=float(r["p_event"]); y=float(r["y_event"]); r["_brier"]=(p-y)**2
 t=f(r["target_rul_weeks"]); mu=float(r["mean_weeks"]); lo=float(r["q10"]); hi=float(r["q90"])
 if t is None: r["_mae"]=r["_cover"]=r["_is80"]=None
 else: r["_mae"]=abs(mu-t);r["_cover"]=float(lo<=t<=hi);r["_is80"]=(hi-lo)+10*max(lo-t,0)+10*max(t-hi,0)
for r in rows:
 if abs(r["_brier"]-float(r["event_brier"]))>1e-9: raise RuntimeError("row Brier mismatch")
 if r["_mae"] is not None and abs(r["_mae"]-float(r["mean_abs_error"]))>1e-8: raise RuntimeError("row MAE mismatch")
 if r["_cover"] is not None and abs(r["_cover"]-float(r["coverage80"]))>1e-9: raise RuntimeError("row coverage mismatch")
 if r["_is80"] is not None and abs(r["_is80"]-float(r["IS80"]))>1e-7: raise RuntimeError("row IS80 mismatch")
cell=defaultdict(lambda:defaultdict(list))
for r in rows:
 k=(r["model"],r["arm"],r["cell_id"]);cell[k]["brier"].append(r["_brier"])
 for metric,col in [("mae","_mae"),("coverage80","_cover"),("IS80","_is80")]:
  if r[col] is not None: cell[k][metric].append(r[col])
macro=defaultdict(dict)
for (model,arm,cid),vals in cell.items(): macro[(model,arm)][cid]={m:mean(v) for m,v in vals.items() if v}
summary=[]
for (model,arm),bycell in sorted(macro.items()):
 for metric in ["mae","brier","coverage80","IS80"]:
  values=[v[metric] for v in bycell.values() if metric in v]
  summary.append({"model":model,"arm":arm,"metric":metric,"cell_macro":mean(values),"cells":len(values),"metric_rows":sum(len(cell[(model,arm,cid)][metric]) for cid in bycell if metric in cell[(model,arm,cid)])})
rng=random.Random(20261021);B=20000
def boot_ci(vals):
 n=len(vals); draws=[]
 for _ in range(B): draws.append(mean([vals[rng.randrange(n)] for _ in range(n)]))
 return [quantile(draws,.025),quantile(draws,.975)]
comparisons=[]
for model in ["hgb","catboost"]:
 for arm in ["raw","sparse2","delay7d"]:
  for base_level in ["F0","F1"]:
   left=macro[(model+"_"+base_level,arm)];right=macro[(model+"_F2",arm)]
   ids=sorted(c for c in set(left)&set(right) if "mae" in left[c] and "mae" in right[c]);imp=[left[c]["mae"]-right[c]["mae"] for c in ids];rel=[(left[c]["mae"]-right[c]["mae"])/left[c]["mae"] for c in ids if left[c]["mae"]>0]
   comparisons.append({"comparison":model+"_F2_minus_"+base_level,"model":model,"arm":arm,"metric":"MAE_weeks","cells":len(ids),"mean_improvement_base_minus_candidate":mean(imp),"relative_improvement_cells_nonzero_baseline":len(rel),"mean_cell_relative_improvement_fraction":mean(rel),"median_cell_relative_improvement_fraction":quantile(rel,.5),"improved_cell_fraction":sum(x>0 for x in imp)/len(imp),"harmed_gt2w_fraction":sum(x < -2 for x in imp)/len(imp),"harmed_gt2w_cells":sum(x < -2 for x in imp),"bootstrap95_ci_improvement":boot_ci(imp)})
head=[]
for arm in ["raw","sparse2","delay7d"]:
 for metric in ["mae","brier","coverage80","IS80"]:
  left=macro[("hgb_F2",arm)];right=macro[("catboost_F2",arm)];ids=sorted(c for c in set(left)&set(right) if metric in left[c] and metric in right[c]);d=[left[c][metric]-right[c][metric] for c in ids]
  head.append({"arm":arm,"metric":metric,"cells":len(ids),"hgb_cell_macro":mean([left[c][metric] for c in ids]),"catboost_cell_macro":mean([right[c][metric] for c in ids]),"hgb_minus_catboost_positive_means_catboost_better":mean(d),"paired_bootstrap95_ci_hgb_minus_catboost":boot_ci(d)})
with (OUT/"row_metrics_recomputed.csv").open("w",newline="") as f:
 fields=["seed","model","cell_id","arm","query_epoch","known_event","y_event","target_rul_weeks","p_event","mean_weeks","q10","q90","recomputed_event_brier","recomputed_mean_abs_error","recomputed_coverage80","recomputed_IS80"]
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in rows:w.writerow({"seed":r["seed"],"model":r["model"],"cell_id":r["cell_id"],"arm":r["arm"],"query_epoch":r["query_epoch"],"known_event":r["known_event"],"y_event":r["y_event"],"target_rul_weeks":r["target_rul_weeks"],"p_event":r["p_event"],"mean_weeks":r["mean_weeks"],"q10":r["q10"],"q90":r["q90"],"recomputed_event_brier":r["_brier"],"recomputed_mean_abs_error":"" if r["_mae"] is None else r["_mae"],"recomputed_coverage80":"" if r["_cover"] is None else r["_cover"],"recomputed_IS80":"" if r["_is80"] is None else r["_is80"]})
result={"GO_request_id":go["request_id"],"input_hashes_verified":go["allowed_files"],"rows":len(rows),"models":sorted({r["model"] for r in rows}),"arms":sorted({r["arm"] for r in rows}),"metric_definitions":"Brier=(p_event-y_event)^2 on current source-event labels; RUL metrics only when target_rul_weeks is present; cell-macro=mean within cell then equal mean across cells; paired bootstrap resamples physical cells with replacement, 20,000 replicates, seed 20261021.","cell_macro_arm_metrics":summary,"paired_F2_incremental_MAE":comparisons,"same_F2_HGB_vs_CatBoost":head}
(OUT/"independent_results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
print(json.dumps({"rows":len(rows),"models":result["models"],"summary_rows":len(summary),"incremental_comparisons":len(comparisons),"head_to_head_rows":len(head)}))
