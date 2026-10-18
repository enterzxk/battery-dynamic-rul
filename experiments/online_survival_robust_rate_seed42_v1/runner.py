from pathlib import Path
import os,time,json,hashlib,csv,datetime,collections
os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["MKL_NUM_THREADS"]="1"
ROOT=Path("/home/yndx/zxk/rul");OUT=ROOT/"experiments/online_survival_robust_rate_seed42_v1";BASE=ROOT/"experiments/online_survival_observed_pilot_seed42_v1"
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):
 with (OUT/n).open("x",encoding="utf-8") as f:json.dump(v,f,indent=2);f.write("\n")
def main():
 g=json.loads((OUT/"ROOT_GO.json").read_text());p=json.loads((OUT/"protocol.json").read_text())
 assert g["status"]=="GO_ONE_FIXED_ROBUST_RATE_FIT" and g["max_predictive_fits"]==1
 assert g["runner_sha256"]==sha(Path(__file__)) and g["protocol_sha256"]==sha(OUT/"protocol.json")
 for n,h in p["base_bindings"].items():assert sha(BASE/n)==h
 with (OUT/"invocation.claim").open("x") as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
 start=time.monotonic();fits=0
 try:
  import numpy as np
  from scipy.special import ndtr,ndtri
  from sklearn.preprocessing import StandardScaler
  from sklearn.linear_model import Ridge
  ii,jj=np.triu_indices(20,k=1);den=jj-ii
  def rate(w):return np.median((w[:,jj]-w[:,ii])/den,axis=1)
  # One directed check for the only changed feature; no model smoke or tuning.
  linear=.99-.001*np.arange(20)
  assert np.allclose(rate(linear[None,:]),[-.001],rtol=0,atol=1e-14)
  co=json.loads((BASE/"cohort.json").read_text());assert len(co["cells"])==71
  assert not {c["cell_id"]+".pkl" for c in co["cells"]}&set(co["excluded_future_shift_cells"])
  rows=[];hashes={}
  for c in co["cells"]:
   assert c["split"] in ["train","val"]
   f=ROOT/c["cycle_summary_path"];assert sha(f)==c["cycle_summary_sha256"];hashes[c["cycle_summary_path"]]=sha(f)
   q=np.array([r["capacity_Ah"]/c["norm_Ah"] for r in json.loads(f.read_text())])
   T=c["event_cycle"];assert np.flatnonzero(q<=.8)[0]+1==T
   t=np.arange(100,T);w=np.lib.stride_tricks.sliding_window_view(q,20)[t-20]
   rr=rate(w);N=len(t);assert N==c["prefix_count"]
   rows.extend((c["cell_id"],c["split"],int(a),int(T),float(q[a-1]),float(c["batch"]==4),float(b),1/N) for a,b in zip(t,rr))
  tr=[r for r in rows if r[1]=="train"];va=[r for r in rows if r[1]=="val"]
  assert len(tr)==26796 and len(va)==10002
  assert len({r[0] for r in tr})==52 and len({r[0] for r in va})==19 and not {r[0] for r in tr}&{r[0] for r in va}
  X=np.array([[r[2],r[4],r[5],r[6]] for r in tr]);Y=np.log([r[3]-r[2] for r in tr]);W=np.array([r[7] for r in tr])
  V=np.array([[r[2],r[4],r[5],r[6]] for r in va]);truth=np.array([r[3]-r[2] for r in va])
  assert np.isfinite(X).all() and np.isfinite(V).all() and time.monotonic()-start<180
  sc=StandardScaler().fit(X,sample_weight=W)
  fits=1
  with (OUT/"fit_ledger.jsonl").open("x") as f:f.write(json.dumps({"event":"fit_started","fit":1,"arm":"F4_robust_rate"})+"\n");f.flush();os.fsync(f.fileno())
  m=Ridge(alpha=1.).fit(sc.transform(X),Y,sample_weight=W)
  resid=Y-m.predict(sc.transform(X));sig=max(.05,float(np.sqrt(np.average(resid**2,weights=W))));mu=m.predict(sc.transform(V))
  with (OUT/"fit_ledger.jsonl").open("a") as f:f.write(json.dumps({"event":"fit_completed","fit":1,"sigma":sig})+"\n")
  qs=[np.exp(mu+sig*ndtri(a)) for a in [.1,.5,.9]];ps=[ndtr((np.log(h)-mu)/sig) for h in [100,300]]
  assert all(np.isfinite(a).all() for a in qs+ps)
  (OUT/"validation_predictions").mkdir();cells=[];old={}
  for cid in sorted({r[0] for r in va}):
   idx=np.array([i for i,r in enumerate(va) if r[0]==cid]);predpath=OUT/"validation_predictions"/(cid+".csv")
   with predpath.open("x",newline="") as f:
    w=csv.writer(f);w.writerow(["cell_id","origin","observed_event","true_RUL","arm","q10","median_RUL","q90","risk100","risk300"])
    for i in idx:w.writerow([cid,va[i][2],va[i][3],truth[i],"F4_robust_rate",qs[0][i],qs[1][i],qs[2][i],ps[0][i],ps[1][i]])
   e=qs[1][idx]-truth[idx];cells.append({"cell_id":cid,"MAE":float(abs(e).mean()),"bias":float(e.mean()),"severe_over100":float((e>100).mean()),"coverage80":float(((truth[idx]>=qs[0][idx])&(truth[idx]<=qs[2][idx])).mean()),"width80":float((qs[2][idx]-qs[0][idx]).mean()),"Brier100":float(((ps[0][idx]-(truth[idx]<=100))**2).mean()),"Brier300":float(((ps[1][idx]-(truth[idx]<=300))**2).mean())})
   of=BASE/"validation_predictions"/(cid+".csv");assert sha(of)==json.loads((BASE/"completion_receipt.json").read_text())["predictions_sha256"]["validation_predictions/"+cid+".csv"]
   old[cid]=[r for r in csv.DictReader(of.open()) if r["arm"] in ["F2_current_state","F3_state_rate"]]
   for arm in ["F2_current_state","F3_state_rate"]:
    a=[r for r in old[cid] if r["arm"]==arm];assert [int(r["origin"]) for r in a]==[va[i][2] for i in idx]
    assert [float(r["true_RUL"]) for r in a]==truth[idx].tolist()
  keys=[k for k in cells[0] if k!="cell_id"];metrics={k:float(np.mean([r[k] for r in cells])) for k in keys}
  oldm=json.loads((BASE/"metrics.json").read_text());oldc=json.loads((BASE/"per_cell_metrics.json").read_text());boot=np.random.default_rng(42).integers(0,19,size=(2000,19));comp=[]
  for arm in ["F2_current_state","F3_state_rate"]:
   a=np.array([next(r["MAE"] for r in oldc if r["cell_id"]==c["cell_id"] and r["arm"]==arm) for c in cells]);b=np.array([c["MAE"] for c in cells]);ci=np.quantile(1-b[boot].mean(axis=1)/a[boot].mean(axis=1),[.025,.975]);gain=1-b.mean()/a.mean();delta=metrics["severe_over100"]-oldm[arm]["severe_over100"]
   comp.append({"old":arm,"relative_MAE_reduction":float(gain),"paired_bootstrap95CI":ci.tolist(),"improved_cells":int((b<a).sum()),"severe_over100_increase":delta,"exploratory_gate":bool(gain>=.05 and ci[0]>0 and delta<=.02)})
  anchors={}
  for cid,lo,hi in [("MATR_b2c22",256,268),("MATR_b4c28",100,426)]:
   idx=np.array([i for i,r in enumerate(va) if r[0]==cid and lo<=r[2]<=hi]);o={int(r["origin"]):r for r in old[cid] if r["arm"]=="F3_state_rate"}
   anchors[cid]={"origins":[lo,hi],"queries":len(idx),"F3_MAE":float(np.mean([abs(float(o[va[i][2]]["median_RUL"])-truth[i]) for i in idx])),"F4_MAE":float(np.mean(abs(qs[1][idx]-truth[idx]))),"F4_max_prediction":float(qs[1][idx].max())}
  dump("metrics.json",metrics);dump("per_cell_metrics.json",cells);dump("comparisons.json",comp);dump("predeclared_failure_windows.json",anchors)
  dump("model_parameters.json",{"features":["age","soh","batch4","past20_TheilSen_rate"],"scaler_mean":sc.mean_.tolist(),"scaler_scale":sc.scale_.tolist(),"coef":m.coef_.tolist(),"intercept":float(m.intercept_),"sigma":sig,"alpha":1.,"not_a_checkpoint":True})
  dump("completion_receipt.json",{"status":"COMPLETE_OBSERVED_PROCESSED_EVENT_ONLY","new_predictive_fits":fits,"optimizer_steps":0,"train_cells":52,"validation_cells":19,"train_origins":len(tr),"validation_origins":len(va),"test_access":False,"elapsed_seconds":time.monotonic()-start,"bindings":{"runner":sha(Path(__file__)),"protocol":sha(OUT/"protocol.json"),"go":sha(OUT/"ROOT_GO.json")},"source_sha256":hashes,"predictions_sha256":{p.name:sha(p) for p in (OUT/"validation_predictions").glob("*.csv")},"strict_online_claim":False})
  print(json.dumps({"status":"COMPLETE","fits":fits,"metrics":metrics,"comparisons":comp,"failure_windows":anchors}))
 except BaseException as e:
  dump("failure_receipt.json",{"status":"FAILED_STOP_NO_AUTO_RETRY","error":str(e),"type":type(e).__name__,"predictive_fit_attempts":fits});raise
if __name__=="__main__":main()
