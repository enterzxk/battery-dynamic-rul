#!/usr/bin/env python3
"""Single-seed, zero-fit causal RPT-retention gate; not a fleet or SLO experiment."""
import os
os.environ.setdefault("OMP_NUM_THREADS","4")
os.environ.setdefault("MKL_NUM_THREADS","4")
import argparse,collections,copy,csv,datetime,fcntl,hashlib,json,math,pathlib,sys,time,traceback
import numpy as np
ROOT=pathlib.Path("/home/yndx/zxk/rul")
HERE=ROOT/"experiments/rulaas_value_gate_20261029"
FORMAL=ROOT/"experiments/multisource_factorial_20261021/run2_clocksafe"
SIGNALS=ROOT/"reports/multisource_20261021_signals"
sys.path[:0]=[str(ROOT/"experiments/multisource_factorial_20261021"),str(SIGNALS),str(ROOT/"experiments/isu_irregular_rul_seed42_v1"),str(ROOT/"experiments/dart_rul_v18")]
import features as F
import cycle_asof_features as C
from data_adapter import load_reviewed_cell
from data_protocol import _feature_view,DAY,WEEK
POLICIES=("all0","all7","half_even7","half_odd7","half_hash7","anchor7")
class MemoCycle:
 def __init__(self,index):self.index=index;self.memo={}
 def __getattr__(self,name):return getattr(self.index,name)
 def features_at(self,q,subset="full"):
  key=(float(q),subset)
  if key not in self.memo:self.memo[key]=self.index.features_at(q,subset)
  return self.memo[key]
OWNER="01a17810-6ae6-7cf2-9729-5bfcaa8df5f4"
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def readj(p):return json.loads(pathlib.Path(p).read_text())
def writej(p,x):
 with pathlib.Path(p).open("x",encoding="utf-8") as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(p,rows):
 if not rows:return
 with pathlib.Path(p).open("x",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def progress(out,x):
 tmp=out/"progress.tmp";tmp.write_text(json.dumps(x,ensure_ascii=False));os.replace(tmp,out/"progress.json")
def retained(policy,cid,i):
 if i<3:return True
 k=i-3
 if policy in ("all0","all7"):return True
 if policy=="anchor7":return False
 if policy=="half_even7":return k%2==0
 if policy=="half_odd7":return k%2==1
 bit=int(hashlib.sha256(("42:"+cid+":"+str(k//2)).encode()).hexdigest()[:8],16)%2
 return k%2==bit
def arrived(rows,policy,cid,q):
 lag=0. if policy=="all0" else DAY*7
 return [dict(r,arrival_epoch=float(r["stop_epoch"])+lag) for i,r in enumerate(rows) if float(r["stop_epoch"])+lag<=q and retained(policy,cid,i)]
def vector(cell,vis,q,cache,cycle):
 base=_feature_view(cell,vis,q)
 e={"cell_id":cell["cell_id"],"query_epoch":q,"visible_records":vis,"nominal_capacity_ah":cell["nominal_capacity_ah"]}
 rv=F._rpt_full_vector(e,cache)[1]
 cy=cycle.features_at(q,subset="full")
 x=np.r_[base,rv,cy["values"]].astype(np.float32)
 if x.shape!=(710,) or np.isinf(x).any():raise ValueError("invalid F3 vector")
 return x
def quantile(mu,p,level,res,cum):
 if level<=p:return 0.
 u=(level-p)/(1-p);ix=min(len(res)-1,int(np.searchsorted(cum,u,side="left")))
 return float(math.exp(mu+res[ix]))
def metrics(mu,p,known,res,rw,cum,expresmean):
 if known:return 0.,0.,0.,1.
 point=float((1-p)*math.exp(mu)*expresmean)
 lo=quantile(mu,p,.1,res,cum);hi=quantile(mu,p,.9,res,cum)
 j=int(np.searchsorted(res,math.log(4.)-mu,side="right"))
 b=float(p+(1-p)*(cum[j-1] if j else 0.))
 if not all(math.isfinite(v) for v in [point,lo,hi,b]):raise ValueError("nonfinite prediction; not clipped")
 return point,lo,hi,b
def boot(v):
 a=np.asarray(v,float);rng=np.random.RandomState(42)
 z=a[rng.randint(len(a),size=(5000,len(a)))].mean(axis=1)
 return {"delta":float(a.mean()),"ci_low":float(np.quantile(z,.025)),"ci_high":float(np.quantile(z,.975)),"n_cells":len(a)}
def main(go_path):
 g=readj(go_path);out=ROOT/g["output"]
 rec={"status":"STARTED","request_id":g["request_id"],"started_utc":stamp(),"new_fits":0,"optimizer_steps":0,"C4_payload_reads":0,"prediction_rows":0,"limitations":["C3 development only","fixed pretrained model; no policy tuning","retained observed-RPT information is a cost proxy, not physical intervention","no queue, adaptive scheduler or online label controller in this gate"]}
 locks=[];start=time.time();claimed=False
 try:
  for lp in [ROOT/"automation/state/coordinator.lock",ROOT/"automation/locks/isu_irregular_rul_cpu.lock"]:
   f=lp.open("a+");fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
  coord=readj(ROOT/"automation/state/coordinator.json")
  if coord.get("owner")!=OWNER or coord.get("thread_id")!=OWNER or coord.get("state")!="ACTIVE" or coord.get("takeover_verified") is not True:raise ValueError("owner gate")
  if g.get("owner")!=OWNER or g.get("status")!="APPROVED" or g.get("allow_fits") is not False or g.get("allow_C4") is not False or g.get("allow_inference") is not True:raise ValueError("GO gate")
  hb=datetime.datetime.fromisoformat(coord["heartbeat_utc"].replace("Z","+00:00"))
  if (datetime.datetime.now(datetime.timezone.utc)-hb).total_seconds()>1800:raise ValueError("stale owner heartbeat")
  if set(g["policies"])!=set(POLICIES) or g["max_prediction_rows"]!=30000:raise ValueError("budget/policy drift")
  for rel,h in g["input_sha256"].items():
   if sha(ROOT/rel)!=h:raise ValueError("input hash mismatch "+rel)
  if out.parent!=HERE or out.exists():raise ValueError("output create-only binding")
  writej(HERE/(g["request_id"]+".claim.json"),{"GO_sha256":sha(go_path),"utc":stamp()});claimed=True
  out.mkdir()
  manifest=readj(ROOT/"reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json")
  roles=readj(ROOT/"reports/isu_ilcc_capacity_probe_20261020_root/cohort.json")["roles"]
  if manifest.get("status")!="PASS":raise ValueError("DataV2 not PASS")
  ids=sorted(k for k,v in roles.items() if v=="development")
  if len(ids)!=63 or any(not k.endswith("C3") for k in ids):raise ValueError("C3 role gate")
  ri={x["cell_id"]:x for x in readj(SIGNALS/"all188_rpt_features_v1/manifest.json")["inventory"]}
  ci={x["cell_id"]:x for x in readj(SIGNALS/"cycling_all188_feature_manifest.json")["inventory"]}
  import joblib
  clf=joblib.load(FORMAL/"hgb_F3_event.joblib");reg=joblib.load(FORMAL/"hgb_F3_positive.joblib")
  d=joblib.load(FORMAL/"hgb_F3_distribution.joblib");res=np.asarray(d["residuals"]);rw=np.asarray(d["weights"])
  order=np.argsort(res,kind="mergesort");res=res[order];rw=rw[order]
  if res.ndim!=1 or rw.shape!=res.shape or not np.isfinite(res).all() or not np.isfinite(rw).all() or (rw<0).any() or abs(rw.sum()-1)>1e-8:raise ValueError("invalid frozen residual distribution")
  cum=np.cumsum(rw);cum[-1]=1.;expresmean=float(np.dot(np.exp(res),rw))
  one=np.flatnonzero(np.asarray(clf.classes_)==1)
  if len(one)!=1:raise ValueError("classifier class 1 missing")
  # Exact old-vector identity is checked once before scoring the new grid.
  oldmeta=[]
  with (FORMAL/"development_rows.jsonl").open() as f:
   for ix,line in enumerate(f):
    z=json.loads(line)
    if z["cell_id"]==ids[0] and z["arm"]=="raw":oldmeta.append((ix,z));break
  oldX=np.load(FORMAL/"development_features.npz",allow_pickle=False)["F3"]
  rec["checks"]={};pred=[];cost=[];excluded=[];sources=[];cellstats=collections.defaultdict(list)
  events=[];guard_done=False
  for celln,cid in enumerate(ids,1):
   info=manifest["files"][cid]
   paths=[("DataV2",ROOT/info["path"],info["sha256"]),("RPT",ROOT/ri[cid]["path"],ri[cid]["sha256"]),("Cycling",ROOT/ci[cid]["path"],ci[cid]["sha256"])]
   for typ,p,h in paths:
    if "C4" in p.name or sha(p)!=h:raise ValueError("cell input hash/role "+cid)
    sources.append({"cell_id":cid,"type":typ,"path":str(p.relative_to(ROOT)),"sha256":h})
   cell=load_reviewed_cell(paths[0][1],"development")
   rpt=readj(paths[1][1]);cycle=MemoCycle(C.build_cycle_index(paths[2][1]))
   if cell["cell_id"]!=cid or rpt["cell_id"]!=cid or rpt["role"]!="development" or cycle.role!="development" or cycle.cell_id!=cid:raise ValueError("cell identity/role")
   rows=sorted(cell["records"],key=lambda r:(float(r["stop_epoch"]),int(r["source_rpt_index"])))
   if len(rows)<3:
    excluded.append({"cell_id":cid,"reason":"fewer_than_3_valid_RPTs","n":len(rows)});continue
   cache={cid:{int(r["source_rpt_index"]):r for r in rpt["records"]}}
   if cid==ids[0] and oldmeta:
    ix,z=oldmeta[0];v=vector(cell,arrived(rows,"all0",cid,z["query_epoch"]),z["query_epoch"],cache,cycle)
    if not np.allclose(v,oldX[ix],rtol=1e-6,atol=1e-6,equal_nan=True):raise ValueError("frozen raw F3 feature identity failed")
    rec["checks"]["frozen_raw_F3_vector_identity"]="PASS"
   event=next((float(r["stop_epoch"]) for r in rows if float(r["capacityAh"])<=.20),None)
   end=float(rows[-1]["stop_epoch"]);warm=float(rows[2]["stop_epoch"])
   # Warmup availability is the same for all delayed policies; query support is policy-independent.
   queries=np.arange(warm+7*DAY,end+1e-6,3.5*DAY)
   if not len(queries):
    excluded.append({"cell_id":cid,"reason":"no_post_warmup_query_window","n":len(rows)});continue
   xs=[];items=[]
   for q0 in queries:
    q=float(q0)
    for policy in POLICIES:
     vis=arrived(rows,policy,cid,q)
     if len(vis)<3:raise ValueError("policy-dependent missing warmup")
     x=vector(cell,vis,q,cache,cycle);xs.append(x)
     items.append((q,policy,vis))
     if not guard_done and policy=="all7":
      copied=copy.deepcopy(cache);visible_ids={int(r["source_rpt_index"]) for r in vis}
      for idx,fr in copied[cid].items():
       if idx not in visible_ids:
        vals=fr.get("values")
        if isinstance(vals,list):fr["values"]=[-999999.]*len(vals)
        elif isinstance(vals,dict):fr["values"]={k:-999999. for k in vals}
      # Future/unarrived feature values cannot affect the current vector.
      if not np.allclose(x,vector(cell,vis,q,copied,cycle),rtol=0,atol=0,equal_nan=True):raise ValueError("future/unarrived RPT mutation affected input")
      rec["checks"]["unarrived_RPT_value_mutation_invariance"]="PASS";guard_done=True
   if len(pred)+len(items)>g["max_prediction_rows"]:raise ValueError("prediction budget exceeded")
   X=np.asarray(xs);ps=clf.predict_proba(X)[:,one[0]];mus=reg.predict(X)
   for (q,policy,vis),p,mu in zip(items,ps,mus):
    known=any(float(v["capacityAh"])<=.20 for v in vis)
    point,lo,hi,b4=metrics(float(mu),float(p),known,res,rw,cum,expresmean)
    y=None if event is None else max(0.,(event-q)/WEEK)
    positive=event is not None and event>q
    label4=1 if event is not None and event<=q+4*WEEK else (0 if end>=q+4*WEEK else None)
    err=None if y is None else abs(point-y)
    cover=None if y is None else float(lo<=y<=hi)
    is80=None if y is None else hi-lo+10*max(0.,lo-y)+10*max(0.,y-hi)
    row={"cell_id":cid,"policy":policy,"query_epoch":q,"source_event_epoch":event,"target_rul_weeks":y,"primary_positive_rul":positive,"policy_known_event":known,"visible_RPT_count":len(vis),"last_visible_RPT_stop":float(vis[-1]["stop_epoch"]),"last_arrival_epoch":float(vis[-1]["arrival_epoch"]),"cycle_source_asof_count":int(cycle.features_at(q)["cycle_source_asof_count"]),"mean_RUL":point,"q10":lo,"q90":hi,"p_RUL_le4w":b4,"label4":label4,"abs_error":err,"coverage80":cover,"IS80":is80,"Brier4":None if label4 is None else (b4-label4)**2}
    pred.append(row);cellstats[(cid,policy)].append(row)
   at_risk_end=min(end,event) if event is not None else end
   eligible=[(i,r) for i,r in enumerate(rows) if i>=3 and warm<float(r["stop_epoch"])<=at_risk_end]
   for policy in POLICIES:
    kept=sum(retained(policy,cid,i) for i,r in eligible)
    cost.append({"cell_id":cid,"policy":policy,"bootstrap_RPTs":3,"at_risk_opportunities":len(eligible),"retained_at_risk_RPTs":kept,"retained_all_window_RPTs":sum(retained(policy,cid,i) for i in range(3,len(rows))),"cost_interpretation":"uniform information-access proxy; no queue/physical cost claim"})
    lead=[v for v in cellstats[cid,policy] if v["primary_positive_rul"] and v["target_rul_weeks"]<=4]
    events.append({"cell_id":cid,"policy":policy,"source_event":event is not None,"has_4w_pre_event_query":bool(lead),"episode_missed_alarm_at_fixed_0p5":None if not lead else not any(v["p_RUL_le4w"]>=.5 for v in lead)})
   progress(out,{"status":"RUNNING","cells_complete":celln,"prediction_rows":len(pred),"new_fits":0,"C4_payload_reads":0})
   del cache,rpt,cycle
  per=[]
  for (cid,policy),rs in sorted(cellstats.items()):
   primary=[r for r in rs if r["primary_positive_rul"]]
   scored=[r for r in rs if r["abs_error"] is not None]
   brier=[r for r in rs if r["Brier4"] is not None]
   per.append({"cell_id":cid,"policy":policy,"n_queries":len(rs),"n_positive_queries":len(primary),"n_all_scored":len(scored),"n_Brier4":len(brier),"primary_MAE":float(np.mean([r["abs_error"] for r in primary])) if primary else None,"all_MAE":float(np.mean([r["abs_error"] for r in scored])) if scored else None,"primary_coverage80":float(np.mean([r["coverage80"] for r in primary])) if primary else None,"primary_IS80":float(np.mean([r["IS80"] for r in primary])) if primary else None,"Brier4":float(np.mean([r["Brier4"] for r in brier])) if brier else None})
  summaries=[]
  for policy in POLICIES:
   rr=[r for r in per if r["policy"]==policy];cc=[r for r in cost if r["policy"]==policy];ee=[r for r in events if r["policy"]==policy and r["has_4w_pre_event_query"]]
   s={"policy":policy,"n_cells":len(rr),"n_primary_cells":sum(r["primary_MAE"] is not None for r in rr),"n_queries":sum(r["n_queries"] for r in rr),"retained_at_risk_RPTs":sum(r["retained_at_risk_RPTs"] for r in cc),"at_risk_opportunities":sum(r["at_risk_opportunities"] for r in cc),"n_alarm_eligible_events":len(ee),"missed_events":sum(bool(r["episode_missed_alarm_at_fixed_0p5"]) for r in ee)}
   for k in ["primary_MAE","all_MAE","primary_coverage80","primary_IS80","Brier4"]:
    v=[r[k] for r in rr if r[k] is not None];s[k]=float(np.mean(v)) if v else None
   summaries.append(s)
  by={(r["cell_id"],r["policy"]):r for r in per}
  contrasts=[]
  for a,b in [("anchor7","all7"),("half_even7","all7"),("half_odd7","all7"),("half_hash7","all7"),("all7","all0")]:
   delta=[]
   for cid in ids:
    ra=by.get((cid,a));rb=by.get((cid,b))
    if ra and rb and ra["primary_MAE"] is not None and rb["primary_MAE"] is not None:
     if ra["n_positive_queries"]!=rb["n_positive_queries"]:raise ValueError("query population mismatch")
     delta.append(ra["primary_MAE"]-rb["primary_MAE"])
   if delta:contrasts.append(dict(candidate=a,reference=b,metric="primary_mean_point_MAE",**boot(delta)))
  decision={"status":"COMPLETED_DEVELOPMENT_GATE","screen_noninferiority_margin_weeks":.10,"margin_status":"engineering screening only; not externally justified SLO","no_novelty_claim":True,"no_service_SLO_claim":True}
  anchor=next(x for x in contrasts if x["candidate"]=="anchor7")
  decision["additional_RPT_value"]=("SUPPORTED_IN_THIS_FIXED_MODEL_GATE" if anchor["ci_low"]>0 else "NOT_RELIABLY_ESTABLISHED")
  decision["next_action"]=("Implement a bounded queue-aware observed-opportunity scheduler comparison; frozen model and delayed visibility, no controller using unavailable RUL labels." if anchor["ci_low"]>0 else "Do not scale a scheduler yet; inspect saved per-cell harm and input redundancy before selecting a distinct premise.")
  decision["thinning_screen"]=[dict(candidate=x["candidate"],passes_development_screen=x["ci_high"]<.10) for x in contrasts if x["candidate"].startswith("half_")]
  rec.update(status="SUCCESS",finished_utc=stamp(),elapsed_seconds=time.time()-start,prediction_rows=len(pred),query_cells=len(cellstats)//len(POLICIES),scored_primary_cells=summaries[0]["n_primary_cells"],input_sha256=g["input_sha256"],GO_sha256=sha(go_path),sources=sources)
  for name,data in [("predictions.csv",pred),("per_cell.csv",per),("information_access.csv",cost),("event_episodes.csv",events),("summary.csv",summaries),("paired_bootstrap.csv",contrasts)]:csvout(out/name,data)
  writej(out/"excluded_cells.json",excluded);writej(out/"decision.json",decision);writej(out/"receipt.json",rec)
  report=["# RULaaS fixed-HGB information-value gate", "", "Development-only, zero-fit. Observed RPT information thinning; not fleet queue control or physical inspection savings.", "", "|policy|positive-RUL MAE wk|cov80|IS80 wk|retained at-risk RPTs|", "|---|---:|---:|---:|---:|"]
  for s in summaries:report.append("|{policy}|{primary_MAE:.6f}|{primary_coverage80:.4f}|{primary_IS80:.4f}|{retained_at_risk_RPTs}/{at_risk_opportunities}|".format(**s))
  report+=["","## Paired cell bootstrap (candidate minus reference)"]
  for x in contrasts:report.append("- "+x["candidate"]+" vs "+x["reference"]+": %.6f [%.6f, %.6f] wk, %d cells"%(x["delta"],x["ci_low"],x["ci_high"],x["n_cells"]))
  report+=["","## Decision",json.dumps(decision,ensure_ascii=False,indent=2),"","## Limits","- The 0.10-week margin is a development screen, not a validated noninferiority contract.","- All policies keep the first 3 RPTs free as warmup. Counts exclude warmup and describe retained information during the fixed reference at-risk window.","- Physical diagnostics, degradation interventions, queue interference, policy selection bias and delayed-label feedback have not been validated.","- All cheap cycling features, including capacity proxies, stay visible under identical source-completion assumptions.","- Primary queries have positive reference RUL, with a fixed policy-independent grid. Source-event and censored rows remain in predictions.","- C3 has been used repeatedly; no independent confirmation. No new fits; C4 payload reads zero."]
  (out/"RESULTS.md").write_text("\n".join(report),encoding="utf-8")
  progress(out,{"status":"SUCCESS","prediction_rows":len(pred),"new_fits":0,"C4_payload_reads":0})
  print(json.dumps({"output":str(out),"decision":decision,"summary":summaries,"contrasts":contrasts},ensure_ascii=False))
 except Exception as ex:
  rec.update(status="FAILED",error=repr(ex),traceback=traceback.format_exc(),elapsed_seconds=time.time()-start,finished_utc=stamp(),claim_consumed=claimed)
  if out.is_dir():writej(out/"failure_receipt.json",rec)
  print(json.dumps(rec,ensure_ascii=False));raise
 finally:
  for f in reversed(locks):fcntl.flock(f,fcntl.LOCK_UN);f.close()
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--go",required=True);args=ap.parse_args();main(pathlib.Path(args.go))
