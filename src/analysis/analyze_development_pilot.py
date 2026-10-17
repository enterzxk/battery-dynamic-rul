#!/usr/bin/env python3
"""只读已有验证预测；不训练、不接触测试集。作者EOL标签诊断不能充当真实动态RUL证据。"""
import argparse,csv,datetime,hashlib,json,math,pathlib,statistics
ROOT=pathlib.Path("/home/yndx/zxk/rul")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load_csv(p):
 with p.open() as f: rows=list(csv.DictReader(f))
 for r in rows:
  r["prefix_index"]=int(r["prefix_index"])
  for k in ["label_total_life_cycles","prediction_total_life_cycles","absolute_error_cycles","absolute_percentage_error"]:r[k]=float(r[k])
 return rows
def metrics(rows):
 cells={}
 for r in rows:
  cells.setdefault(r["file_name"],[]).append(r)
 per=[]
 for n,rs in sorted(cells.items()):
  per.append({"cell":n,"prefixes":len(rs),"mae_cycles":statistics.mean(abs(r["prediction_total_life_cycles"]-r["label_total_life_cycles"]) for r in rs),"mape":statistics.mean(abs(r["prediction_total_life_cycles"]-r["label_total_life_cycles"])/r["label_total_life_cycles"] for r in rs)})
 return {"cells":len(per),"prefixes":len(rows),"cell_macro_mae_cycles":statistics.mean(r["mae_cycles"] for r in per),"cell_macro_mape":statistics.mean(r["mape"] for r in per),"per_cell":per}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--run-dir",type=pathlib.Path,required=True);args=ap.parse_args()
 p=args.run_dir.resolve();assert p.is_relative_to(ROOT/"experiments")
 completion=json.loads((p/"completion_receipt.json").read_text())
 records=[json.loads(x) for x in (p/"epoch_metrics.jsonl").read_text().splitlines()]
 best=min(records,key=lambda r:r["validation_prefix_mean_mape"])["epoch"]
 assert best==completion["best_epoch_selected_by_validation_prefix_mape"]
 cfg=ROOT/"configs/experiments/cpmlp_hust_pilot_seed42_v3.json";config=json.loads(cfg.read_text())
 expected=set(config["split_files"]["val"]);test=set(config["split_files"]["test"])
 paths=[p/("val_predictions_epoch_%03d.csv"%best),p/("train_median_val_predictions_epoch_%03d.csv"%best)]
 rows,base=map(load_csv,paths)
 assert len(rows)==1500 and len(base)==1500
 assert set(r["file_name"] for r in rows)==expected and not (set(r["file_name"] for r in rows)&test)
 assert len({(r["file_name"],r["prefix_index"]) for r in rows})==1500
 for name in expected:
  rs=[r for r in rows if r["file_name"]==name];assert set(r["prefix_index"] for r in rs)==set(range(1,101));assert len(set(r["label_total_life_cycles"] for r in rs))==1
 for r in rows+base:
  assert all(math.isfinite(v) for v in r.values() if isinstance(v,float))
  assert abs(r["absolute_error_cycles"]-abs(r["prediction_total_life_cycles"]-r["label_total_life_cycles"]))<1e-6
 a,b=metrics(rows),metrics(base)
 bins=[]
 for lo,hi in [(1,10),(11,25),(26,50),(51,100)]:
  bins.append({"prefix_start":lo,"prefix_end":hi,"cpmlp":metrics([r for r in rows if lo<=r["prefix_index"]<=hi]),"median":metrics([r for r in base if lo<=r["prefix_index"]<=hi])})
 revision=[]
 for name in sorted(expected):
  rs=sorted((r for r in rows if r["file_name"]==name),key=lambda r:r["prefix_index"])
  changes=[abs(y["prediction_total_life_cycles"]-x["prediction_total_life_cycles"]) for x,y in zip(rs,rs[1:])]
  revision.append({"cell":name,"mean_adjacent_eol_revision_cycles":statistics.mean(changes),"max_adjacent_eol_revision_cycles":max(changes)})
 signed=[r["prediction_total_life_cycles"]-r["label_total_life_cycles"] for r in rows]
 report={"created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"run_dir":str(p),"selection":"Best epoch by same validation prefix-MAPE, development result only","selected_epoch":best,"selected_optimizer_steps":next(r["optimizer_steps_total"] for r in records if r["epoch"]==best),"completed_optimizer_steps":completion["optimizer_steps"],"cpmlp":a,"train_only_median":b,"prefix_bins_exploratory":bins,"adjacent_revision_exploratory":revision,"overestimation_exploratory":{"threshold_cycles":100,"threshold_is_exploratory_not_risk_calibrated":True,"prefix_fraction_above_100":statistics.mean(e>100 for e in signed),"max_overestimate_cycles":max(signed),"mean_signed_error_cycles":statistics.mean(signed)},"source_hashes":{str(x.relative_to(ROOT)):sha(x) for x in paths+[p/"completion_receipt.json",p/"run_manifest.json",p/"epoch_metrics.jsonl",p/"budget_ledger.jsonl",cfg]},"limits":["One seed and one development validation split; selected-on-validation numbers are optimistic and unconfirmed","Official author total-EOL labels; HUST nominal-80-percent observed crossings absent","Only cycles 1..100, no late-life dynamic inference or unknown-condition experiment","No physical-serial or pretraining overlap proof","No hypothesis test, SOTA or novel method claim"]}
 out=ROOT/"reports/development_pilot/cpmlp_hust_seed42_v3";out.mkdir(parents=True,exist_ok=False)
 (out/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 text="# CPMLP HUST 开发试验：已有预测的诊断\n\n"
 text+="300次更新已完成，最佳验证MAPE出现在第%d个epoch（%d次更新）。作者总EOL是本次目标；这不是已验证的动态RUL标签。\n\n"%(best,report["selected_optimizer_steps"])
 text+="|方法|验证电芯宏平均MAE（cycle）|验证MAPE|\n|---|---:|---:|\n"
 text+="|CPMLP|%.4f|%.4f%%|\n|训练集EOL中位数|%.4f|%.4f%%|\n\n"%(a["cell_macro_mae_cycles"],100*a["cell_macro_mape"],b["cell_macro_mae_cycles"],100*b["cell_macro_mape"])
 text+="同一验证集用于选epoch并报告指标，不能据此宣称泛化提升或完成论文复现。\n\n|观测前缀周期|CPMLP MAE|CPMLP MAPE|\n|---|---:|---:|\n"
 for x in bins:text+="|%d–%d|%.4f|%.4f%%|\n"%(x["prefix_start"],x["prefix_end"],x["cpmlp"]["cell_macro_mae_cycles"],100*x["cpmlp"]["cell_macro_mape"])
 text+="\n相邻预测修订和高估仅为对作者标签的探索诊断，阈值100周期未作风险校准。详见analysis.json，后续须在冻结动态协议及独立确认集上验证。\n"
 text+="\n所有负结果、最后partial epoch和原始逐prefix预测均保留；未因验证更好而增预算。\n"
 (out/"report_zh.md").write_text(text,encoding="utf-8")
 print(json.dumps({"analysis":str(out/"analysis.json"),"report":str(out/"report_zh.md"),"cpmlp_mae":a["cell_macro_mae_cycles"],"cpmlp_mape":a["cell_macro_mape"],"median_mae":b["cell_macro_mae_cycles"],"median_mape":b["cell_macro_mape"],"prefix_bins":[{"from":x["prefix_start"],"to":x["prefix_end"],"mae":x["cpmlp"]["cell_macro_mae_cycles"],"mape":x["cpmlp"]["cell_macro_mape"]} for x in bins]},indent=2))
if __name__=="__main__":main()
