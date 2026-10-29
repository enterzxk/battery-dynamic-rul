#!/usr/bin/env python3
"""Fixed recorded-window diagnostic admission replay. No deferred-sampling counterfactual."""
import os
os.environ.setdefault("OMP_NUM_THREADS","4");os.environ.setdefault("MKL_NUM_THREADS","4")
import pathlib,sys,json,csv,collections,hashlib,datetime,heapq,time,fcntl,traceback,argparse,math
import numpy as np
ROOT=pathlib.Path("/home/yndx/zxk/rul");HERE=ROOT/"experiments/rulaas_station_admission_20261029"
VALUE=ROOT/"experiments/rulaas_value_gate_20261029";FORMAL=ROOT/"experiments/multisource_factorial_20261021/run2_clocksafe"
SIGNALS=ROOT/"reports/multisource_20261021_signals"
sys.path[:0]=[str(VALUE),str(ROOT/"experiments/multisource_factorial_20261021"),str(SIGNALS),str(ROOT/"experiments/isu_irregular_rul_seed42_v1"),str(ROOT/"experiments/dart_rul_v18")]
from value_gate import vector,metrics,sha,readj,writej,csvout,stamp,MemoCycle
from data_adapter import load_reviewed_cell
import cycle_asof_features as C
DAY=86400.;WEEK=7*DAY
OWNER="01a17810-6ae6-7cf2-9729-5bfcaa8df5f4"
POLICIES=("all","age","width","arrival_risk")
def progress(out,**x):
 t=out/"progress.tmp";t.write_text(json.dumps(dict(utc=stamp(),**x)));os.replace(t,out/"progress.json")
def start_epoch(row):return datetime.datetime.fromisoformat(row["start"]).timestamp()
class Cheap:
 def __init__(self,rows):self.rows=rows
 def features_at(self,q,subset="full"):
  if subset!="full":raise ValueError("only full cheap features")
  return self.rows[float(q)]
class Predictor:
 def __init__(self,clf,reg,res,rw,budget):
  self.clf=clf;self.reg=reg;order=np.argsort(res,kind="mergesort");self.res=res[order];self.rw=rw[order]
  self.cum=np.cumsum(self.rw);self.cum[-1]=1.;self.expmean=float(np.dot(np.exp(self.res),self.rw));self.counter=0;self.budget=budget;self.memo={}
  self.one=int(np.flatnonzero(np.asarray(clf.classes_)==1)[0])
 def batch(self,X):
  if self.counter+len(X)>self.budget:raise ValueError("model-row budget exhausted")
  if len(X)==0:return []
  self.counter+=len(X);X=np.asarray(X)
  if X.ndim!=2 or X.shape[1]!=710 or np.isinf(X).any():raise ValueError("bad F3 batch")
  p=self.clf.predict_proba(X)[:,self.one];mu=self.reg.predict(X)
  if not np.isfinite(p).all() or not np.isfinite(mu).all():raise ValueError("nonfinite model result")
  return [(float(a),float(b)) for a,b in zip(p,mu)]
 def probability(self,p,mu,h):
  i=int(np.searchsorted(self.res,math.log(h)-mu,side="right"))
  return float(p+(1-p)*(self.cum[i-1] if i else 0.))
 def stats(self,p,mu,known=False):return metrics(mu,p,known,self.res,self.rw,self.cum,self.expmean)
 def predict_views(self,cell,q,views):
  # Same (cell, query, visible-record IDs) means exactly the same input across resource worlds.
  missing={};keys=[]
  for vis in views:
   key=(cell["cell_id"],float(q),tuple(int(v["source_rpt_index"]) for v in vis))
   keys.append(key)
   if key not in self.memo and key not in missing:
    if any(float(v["arrival_epoch"])>q or float(v["stop_epoch"])>float(v["arrival_epoch"]) for v in vis):raise ValueError("report visibility")
    if any(float(v["capacityAh"])<=.20 for v in vis):self.memo[key]=(1.,0.,True)
    else:missing[key]=vector(cell,vis,q,cell["_rpt_cache"],cell["_cheap"])
  if missing:
   pm=self.batch(list(missing.values()))
   for key,(p,mu) in zip(missing,pm):self.memo[key]=(p,mu,False)
  return [self.memo[k] for k in keys]
def visible(world,cid,q):return [v for v in world["accepted"][cid] if float(v["arrival_epoch"])<=q]
def main(go_path):
 go=readj(go_path);out=ROOT/go["output"];locks=[];begin=time.time()
 receipt={"request_id":go["request_id"],"status":"STARTED","started_utc":stamp(),"new_fits":0,"optimizer_steps":0,"C4_payload_reads":0,"model_rows":0}
 try:
  for lp in [ROOT/"automation/state/coordinator.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"]:
   lock=lp.open("a+");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(lock)
  coord=readj(ROOT/"automation/state/coordinator.json")
  if coord.get("owner")!=OWNER or coord.get("thread_id")!=OWNER or coord.get("state")!="ACTIVE" or not coord.get("takeover_verified"):raise ValueError("owner gate")
  if go.get("owner")!=OWNER or go.get("status")!="APPROVED" or go.get("allow_fits") is not False or go.get("allow_C4") is not False or go.get("allow_inference") is not True:raise ValueError("GO gate")
  hb=datetime.datetime.fromisoformat(coord["heartbeat_utc"].replace("Z","+00:00"))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError("stale heartbeat")
  if go["max_model_rows"]!=40000 or go["seed"]!=42 or go["stations"]!=[2,4] or go["policies"]!=list(POLICIES):raise ValueError("frozen protocol drift")
  for rel,h in go["input_sha256"].items():
   if sha(ROOT/rel)!=h:raise ValueError("input hash drift "+rel)
  if out.parent!=HERE or out.exists():raise ValueError("create-only output")
  writej(HERE/(go["request_id"]+".claim.json"),{"utc":stamp(),"GO_sha256":sha(go_path)});out.mkdir()
  import joblib
  clf=joblib.load(FORMAL/"hgb_F3_event.joblib");reg=joblib.load(FORMAL/"hgb_F3_positive.joblib");d=joblib.load(FORMAL/"hgb_F3_distribution.joblib")
  predictor=Predictor(clf,reg,np.asarray(d["residuals"]),np.asarray(d["weights"]),go["max_model_rows"])
  if not np.isfinite(predictor.res).all() or not np.isfinite(predictor.rw).all() or (predictor.rw<0).any() or abs(predictor.rw.sum()-1)>1e-8:raise ValueError("residual distribution")
  man=readj(ROOT/"reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json");roles=readj(ROOT/"reports/isu_ilcc_capacity_probe_20261020_root/cohort.json")["roles"]
  train_ids=sorted(k for k,v in roles.items() if v=="train");dev_ids=sorted(k for k,v in roles.items() if v=="development")
  if len(train_ids)!=125 or len(dev_ids)!=63 or any(not c.endswith(("C1","C2")) for c in train_ids) or any(not c.endswith("C3") for c in dev_ids):raise ValueError("frozen source roles")
  train_durations=[];source_files=[]
  def load_cell(cid,role):
   info=man["files"][cid];p=ROOT/info["path"]
   if info["role"]!=role or "C4" in p.name or sha(p)!=info["sha256"]:raise ValueError("source identity "+cid)
   source_files.append({"cell_id":cid,"kind":"DataV2","path":info["path"],"sha256":info["sha256"]})
   return load_reviewed_cell(p,role)
  for cid in train_ids:
   c=load_cell(cid,"train")
   for row in c["records"]:
    duration=float(row["stop_epoch"])-start_epoch(row)
    if duration<=0:raise ValueError("invalid train duration")
    train_durations.append(duration)
  duration_est=float(np.median(train_durations));lead=(duration_est+7*DAY)/WEEK
  Xtrain=np.load(FORMAL/"train_features.npz",allow_pickle=False)["F3"]
  if Xtrain.shape!=(6870,710):raise ValueError("frozen train cache shape")
  pm=predictor.batch(Xtrain);healthy=np.asarray(Xtrain[:,1]>.8)
  widths=[];risks=[]
  for i,(p,mu) in enumerate(pm):
   if healthy[i]:
    pt,lo,hi,b=predictor.stats(p,mu);widths.append(hi-lo);risks.append(predictor.probability(p,mu,lead))
  if not widths:raise ValueError("no train-observable-healthy threshold population")
  thresholds={"age_weeks":float(np.quantile(Xtrain[healthy,6],.95)),"width_weeks":float(np.quantile(widths,.75)),"arrival_risk":float(np.quantile(risks,.75)),"expected_duration_seconds":duration_est,"expected_report_lead_weeks":lead,"healthy_train_rows":int(healthy.sum()),"uses_RUL_labels_for_thresholds":False,"new_predictor_fits":0}
  writej(out/"train_only_thresholds.json",thresholds);del Xtrain,pm
  ri={x["cell_id"]:x for x in readj(SIGNALS/"all188_rpt_features_v1/manifest.json")["inventory"]}
  ci={x["cell_id"]:x for x in readj(SIGNALS/"cycling_all188_feature_manifest.json")["inventory"]}
  cells={};excluded=[];rng=np.random.RandomState(42);offsets={cid:float(rng.uniform(0,14*DAY)) for cid in dev_ids};timeline=[]
  for count,cid in enumerate(dev_ids,1):
   cell=load_cell(cid,"development");rows=sorted(cell["records"],key=lambda z:float(z["stop_epoch"]))
   if len(rows)<3:excluded.append({"cell_id":cid,"reason":"fewer_than_three_RPTs"});continue
   warm=float(rows[2]["stop_epoch"]);end=float(rows[-1]["stop_epoch"]);queries=np.arange(warm+7*DAY,end+1e-6,3.5*DAY)
   if not len(queries):excluded.append({"cell_id":cid,"reason":"no_common_query_support"});continue
   for inv,kind in [(ri,"RPT"),(ci,"Cycling")]:
    item=inv[cid];p=ROOT/item["path"]
    if item["role"]!="development" or "C4" in p.name or sha(p)!=item["sha256"]:raise ValueError("derived input "+cid)
    source_files.append({"cell_id":cid,"kind":kind,"path":item["path"],"sha256":item["sha256"]})
   rpt=readj(ROOT/ri[cid]["path"]);cycle=MemoCycle(C.build_cycle_index(ROOT/ci[cid]["path"]))
   if rpt["cell_id"]!=cid or cycle.cell_id!=cid or cycle.role!="development":raise ValueError("derived role")
   requests=[(i,start_epoch(z)) for i,z in enumerate(rows) if i>=3]
   qset=sorted(set(float(q) for q in queries)|{t for i,t in requests})
   cheap={q:cycle.features_at(q) for q in qset}
   cell.update(_rows=rows,_warm=warm,_end=end,_queries=queries,_event=next((float(z["stop_epoch"]) for z in rows if float(z["capacityAh"])<=.20),None),_offset=offsets[cid],_cheap=Cheap(cheap),_rpt_cache={cid:{int(z["source_rpt_index"]):z for z in rpt["records"]}})
   cells[cid]=cell
   for q in queries:timeline.append((float(q)-warm+offsets[cid],1,cid,float(q),-1))
   for i,t in requests:timeline.append((t-warm+offsets[cid],0,cid,t,i))
   progress(out,status="BUILDING_CAUSAL_INPUTS",cells_complete=count,model_rows=predictor.counter)
   del cycle,rpt
  if len(cells)>63 or not cells:raise ValueError("development cell cap")
  timeline.sort();worlds=[]
  for M in go["stations"]:
   for policy in POLICIES:
    accepted={cid:[dict(z,arrival_epoch=float(z["stop_epoch"])+7*DAY) for z in cell["_rows"][:3]] for cid,cell in cells.items()}
    worlds.append({"name":"M%d_%s"%(M,policy),"M":M,"policy":policy,"accepted":accepted,"busy":[],"free":list(range(M)),"max_concurrent":0,"decisions":[]})
  # One real prediction fixture reproduces the already-saved all7 result.
  fixture=None
  with (VALUE/"run02/predictions.csv").open() as f:
   for z in csv.DictReader(f):
    if z["policy"]=="all7" and z["cell_id"] in cells:fixture=z;break
  c=cells[fixture["cell_id"]];q=float(fixture["query_epoch"])
  vis=[dict(z,arrival_epoch=float(z["stop_epoch"])+7*DAY) for z in c["_rows"] if float(z["stop_epoch"])+7*DAY<=q]
  p,mu,known=predictor.predict_views(c,q,[vis])[0];point,lo,hi,b=predictor.stats(p,mu,known)
  fixture_error=max(abs(point-float(fixture["mean_RUL"])),abs(lo-float(fixture["q10"])),abs(hi-float(fixture["q90"])))
  if fixture_error>1e-8:raise ValueError("frozen model prediction fixture differs")
  predictions=[];next_progress=0
  for evn,(t,kind,cid,q,index) in enumerate(timeline):
   cell=cells[cid];views=[visible(w,cid,q) for w in worlds]
   for w in worlds:
    while w["busy"] and w["busy"][0][0]<=t:
     stop,slot=heapq.heappop(w["busy"]);w["free"].append(slot)
   if kind==0:
    eligible=[];indices=[]
    for wi,(w,vis) in enumerate(zip(worlds,views)):
     known=any(float(z["capacityAh"])<=.20 for z in vis)
     if not known and w["free"] and len(vis)>=3 and w["policy"] in ("width","arrival_risk"):eligible.append(vis);indices.append(wi)
    estimates={wi:pm for wi,pm in zip(indices,predictor.predict_views(cell,q,eligible))}
    for wi,(w,vis) in enumerate(zip(worlds,views)):
     score=None;threshold=None
     if any(float(z["capacityAh"])<=.20 for z in vis):reason="known_event"
     elif not w["free"]:reason="station_busy"
     elif len(vis)<3:reason="admit_warmup_fallback"
     elif w["policy"]=="all":reason="admit"
     elif w["policy"]=="age":
      score=(q-float(vis[-1]["stop_epoch"]))/WEEK;threshold=thresholds["age_weeks"];reason="admit" if score>=threshold else "below_threshold"
     else:
      p,mu,known=estimates[wi]
      if w["policy"]=="width":
       pt,lo,hi,b=predictor.stats(p,mu);score=hi-lo;threshold=thresholds["width_weeks"]
      else:score=predictor.probability(p,mu,lead);threshold=thresholds["arrival_risk"]
      reason="admit" if score>=threshold else "below_threshold"
     row=cell["_rows"][index];admit=reason.startswith("admit")
     actual_hours=None;slot=None
     if admit:
      # The environment reveals the realized completion only through busy/free and eventual report delivery.
      stop=float(row["stop_epoch"]);duration=stop-q
      if duration<=0:raise ValueError("nonpositive physical interval")
      slot=min(w["free"]);w["free"].remove(slot);heapq.heappush(w["busy"],(stop-cell["_warm"]+cell["_offset"],slot))
      w["accepted"][cid].append(dict(row,arrival_epoch=stop+7*DAY));actual_hours=duration/3600.
      w["max_concurrent"]=max(w["max_concurrent"],len(w["busy"]))
      if len(w["busy"])>w["M"] or len(w["free"])+len(w["busy"])!=w["M"]:raise ValueError("resource conservation")
     w["decisions"].append({"world":w["name"],"stations":w["M"],"policy":w["policy"],"cell_id":cid,"source_rpt_index":row["source_rpt_index"],"source_request_epoch":q,"fleet_request_seconds":t,"admitted":admit,"reason":reason,"score":score,"threshold":threshold,"actual_station_hours":actual_hours,"station_slot":slot,"source_stop_epoch_if_admitted":float(row["stop_epoch"]) if admit else None,"arrival_epoch_if_admitted":float(row["stop_epoch"])+7*DAY if admit else None})
   else:
    pm=predictor.predict_views(cell,q,views)
    event=cell["_event"];y=None if event is None else max(0.,(event-q)/WEEK);primary=event is not None and event>q
    label4=1 if event is not None and event<=q+4*WEEK else (0 if cell["_end"]>=q+4*WEEK else None)
    for w,vis,(p,mu,known) in zip(worlds,views,pm):
     point,lo,hi,b4=predictor.stats(p,mu,known)
     err=None if y is None else abs(point-y)
     predictions.append({"world":w["name"],"stations":w["M"],"policy":w["policy"],"cell_id":cid,"query_epoch":q,"fleet_query_seconds":t,"source_event_epoch":event,"target_rul_weeks":y,"primary_positive_rul":primary,"known_event":known,"visible_RPT_count":len(vis),"visible_RPT_indices":json.dumps([int(z["source_rpt_index"]) for z in vis],separators=(",",":")),"last_arrival_epoch":max(float(z["arrival_epoch"]) for z in vis),"cheap_cycle_count":cell["_cheap"].features_at(q)["cycle_source_asof_count"],"mean_RUL":point,"q10":lo,"q90":hi,"p_RUL_le4w":b4,"label4":label4,"abs_error":err,"coverage80":None if y is None else float(lo<=y<=hi),"IS80":None if y is None else hi-lo+10*max(0.,lo-y)+10*max(0.,y-hi),"Brier4":None if label4 is None else (b4-label4)**2})
   if evn>=next_progress:
    progress(out,status="REPLAYING",events_complete=evn+1,total_events=len(timeline),model_rows=predictor.counter,prediction_rows=len(predictions));next_progress=evn+200
  by=collections.defaultdict(list)
  for row in predictions:by[row["world"],row["cell_id"]].append(row)
  per=[];episodes=[]
  for (world,cid),rs in sorted(by.items()):
   primary=[z for z in rs if z["primary_positive_rul"]];allsc=[z for z in rs if z["abs_error"] is not None];bs=[z for z in rs if z["Brier4"] is not None]
   neg=[z for z in rs if z["label4"]==0];leadq=[z for z in primary if z["target_rul_weeks"]<=4]
   v={"world":world,"cell_id":cid,"n_queries":len(rs),"n_primary":len(primary),"primary_MAE":float(np.mean([z["abs_error"] for z in primary])) if primary else None,"all_MAE":float(np.mean([z["abs_error"] for z in allsc])) if allsc else None,"primary_coverage80":float(np.mean([z["coverage80"] for z in primary])) if primary else None,"primary_IS80":float(np.mean([z["IS80"] for z in primary])) if primary else None,"Brier4":float(np.mean([z["Brier4"] for z in bs])) if bs else None,"false_alarm_fraction":float(np.mean([z["p_RUL_le4w"]>=.5 for z in neg])) if neg else None,"alarm_fraction_pre_event":float(np.mean([z["p_RUL_le4w"]>=.5 for z in primary])) if primary else None}
   per.append(v);episodes.append({"world":world,"cell_id":cid,"has_pre_event_4w_query":bool(leadq),"missed_episode":None if not leadq else not any(z["p_RUL_le4w"]>=.5 for z in leadq)})
  summaries=[];jobs=[]
  for w in worlds:
   pp=[z for z in per if z["world"]==w["name"]];ee=[z for z in episodes if z["world"]==w["name"] and z["has_pre_event_4w_query"]]
   dd=w["decisions"];jobs.extend(dd);hour=sum(z["actual_station_hours"] for z in dd if z["admitted"])
   ss={"world":w["name"],"stations":w["M"],"policy":w["policy"],"n_query_cells":len(pp),"n_primary_cells":sum(z["primary_MAE"] is not None for z in pp),"n_queries":sum(z["n_queries"] for z in pp),"offered_opportunities":len(dd),"admitted_tests":sum(z["admitted"] for z in dd),"station_hours":hour,"busy_rejections":sum(z["reason"]=="station_busy" for z in dd),"threshold_rejections":sum(z["reason"]=="below_threshold" for z in dd),"known_event_skips":sum(z["reason"]=="known_event" for z in dd),"max_concurrent":w["max_concurrent"],"alarm_eligible_events":len(ee),"missed_events":sum(bool(z["missed_episode"]) for z in ee)}
   for metric in ["primary_MAE","all_MAE","primary_coverage80","primary_IS80","Brier4","false_alarm_fraction","alarm_fraction_pre_event"]:
    vv=[z[metric] for z in pp if z[metric] is not None];ss[metric]=float(np.mean(vv)) if vv else None
   summaries.append(ss)
  writej(out/"fleet_world.json",{"seed":42,"offset_seconds":offsets,"time_translation_only":True,"sampling_intervals_preserved":True,"queue_waiting_for_physical_sampling":False,"report_lag_days":7,"warmup_RPTs_free":3,"thresholds":thresholds})
  for name,rows in [("predictions.csv",predictions),("decisions.csv",jobs),("per_cell.csv",per),("event_episodes.csv",episodes),("summary.csv",summaries)]:csvout(out/name,rows)
  receipt.update(status="SUCCESS",finished_utc=stamp(),elapsed_seconds=time.time()-begin,model_rows=predictor.counter,training_threshold_model_rows=6870,development_model_rows=predictor.counter-6870,prediction_rows=len(predictions),query_cells=len(cells),timeline_events=len(timeline),fixture_max_error=fixture_error,resource_conservation="PASS",input_sha256=go["input_sha256"],source_files=source_files,GO_sha256=sha(go_path))
  writej(out/"excluded_cells.json",excluded);writej(out/"receipt.json",receipt)
  writej(out/"decision.json",{"status":"RESOURCE_BASELINE_PILOT_COMPLETED","novelty_claim":False,"independent_confirmation":False,"confidence_intervals":"Not estimated from one coupled fleet; no query/cell independence claim.","next":"Inspect exact resource and common-query evidence, compare risk/cost frontier, then freeze a distinct information-value mechanism. No C3 threshold tuning.","limits":["One seed and two predeclared resource capacities","Fixed source-supported test windows: busy means rejection, not deferred sampling","Single pretrained kernel with staleness support limits","Train input/output quantile thresholds are screening baselines, not optimized competitors","Warmup diagnostics free; cheap log arrival assumed at completion"]})
  progress(out,status="SUCCESS",model_rows=predictor.counter,prediction_rows=len(predictions))
  print(json.dumps({"receipt":{k:v for k,v in receipt.items() if k not in ["input_sha256","source_files"]},"thresholds":thresholds,"summary":summaries},ensure_ascii=False))
 except BaseException as ex:
  receipt["model_rows"]=predictor.counter if "predictor" in locals() else 0
  receipt.update(status="FAILED",error=repr(ex),traceback=traceback.format_exc(),elapsed_seconds=time.time()-begin,finished_utc=stamp())
  if out.is_dir() and not (out/"failure_receipt.json").exists():writej(out/"failure_receipt.json",receipt)
  print(json.dumps(receipt));raise
 finally:
  for lock in reversed(locks):fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--go",required=True);main(pathlib.Path(ap.parse_args().go))
