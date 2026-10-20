"""Summarize saved predictions_dev.csv only; no raw data, checkpoints, fitting, or inference."""
import argparse,csv,math
from pathlib import Path
import numpy as np
SIMPLE=("group_frozen","hgb_early_health","hgb_dynamic","aft_dynamic")
REQUIRED=("cell_id","arm","model","target_rul_weeks","pred_mean_weeks","q10_weeks","q90_weeks","brier4w","brier12w","model_update_wall_ms")
def num(v):
 try:return float(v)
 except (TypeError,ValueError):return float("nan")
def mkeep(v):
 a=np.asarray(v,float)
 return float(a.mean()) if len(a) and np.isfinite(a).all() else float("nan")
def cell_metrics(rs):
 y=np.asarray([num(r["target_rul_weeks"]) for r in rs]);p=np.asarray([num(r["pred_mean_weeks"]) for r in rs]);lo=np.asarray([num(r["q10_weeks"]) for r in rs]);hi=np.asarray([num(r["q90_weeks"]) for r in rs]);d=p-y;ok=np.isfinite(y)&np.isfinite(p)&np.isfinite(lo)&np.isfinite(hi)
 return {"n_origins":len(rs),"n_invalid_origin_rows":int((~ok).sum()),"mae_weeks":mkeep(abs(d)),
 "severe_overprediction_gt4w_rate":mkeep(np.where(np.isfinite(d),(d>4).astype(float),np.nan)),
 "severe_overprediction_cell_any":float(np.any(d>4)) if ok.all() else float("nan"),
 "is80":mkeep((hi-lo)+10*np.maximum(lo-y,0)+10*np.maximum(y-hi,0)),
 "coverage80":mkeep(np.where(ok,((lo<=y)&(y<=hi)).astype(float),np.nan)),
 "brier4w":mkeep([num(r["brier4w"]) for r in rs]),"brier12w":mkeep([num(r["brier12w"]) for r in rs]),
 "mean_update_wall_ms":mkeep([num(r["model_update_wall_ms"]) for r in rs])}
def write_csv(path,rows):
 with path.open("x",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else []);w.writeheader();w.writerows(rows)
def summarize(src,outdir):
 src=Path(src);out=Path(outdir)
 if not src.is_file():raise FileNotFoundError("saved predictions_dev.csv required; no raw-data fallback")
 if out.exists():raise FileExistsError("summary output must be fresh")
 with src.open(newline="",encoding="utf-8-sig") as f:
  rd=csv.DictReader(f);missing=set(REQUIRED)-set(rd.fieldnames or [])
  if missing:raise ValueError("missing fields: "+",".join(sorted(missing)))
  raw=list(rd)
 if not raw:raise ValueError("empty predictions file")
 arms=sorted({r["arm"] for r in raw});models=sorted({r["model"] for r in raw});groups={}
 for r in raw:groups.setdefault((r["cell_id"],r["arm"],r["model"]),[]).append(r)
 cells=[]
 for (cid,arm,model),rs in sorted(groups.items()):cells.append({"cell_id":cid,"arm":arm,"model":model,**cell_metrics(rs)})
 out.mkdir(parents=False);write_csv(out/"cell_metrics.csv",cells)
 sums=[]
 for arm in arms:
  for model in models:
   rs=[x for x in cells if x["arm"]==arm and x["model"]==model]
   if not rs:continue
   q={"arm":arm,"model":model,"n_cells":len(rs)}
   for k in ("mae_weeks","severe_overprediction_gt4w_rate","is80","coverage80","brier4w","brier12w","mean_update_wall_ms"):
    vals=[num(x[k]) for x in rs];q[k]=mkeep(vals);q[k+"_valid_cells"]=int(np.isfinite(vals).sum());q[k+"_invalid_cells"]=int((~np.isfinite(vals)).sum())
   q["cells_any_severe_overprediction_rate"]=mkeep([num(x["severe_overprediction_cell_any"]) for x in rs]);sums.append(q)
 write_csv(out/"arm_model_summary.csv",sums)
 paired=[];rng=np.random.RandomState(42)
 for arm in arms:
  expected={r["cell_id"] for r in raw if r["arm"]==arm}
  simple=[r for r in sums if r["arm"]==arm and r["model"] in SIMPLE]
  complete=[r for r in simple if r["mae_weeks_invalid_cells"]==0 and r["n_cells"]==len(expected) and math.isfinite(num(r["mae_weeks"]))]
  ref=min(complete,key=lambda r:r["mae_weeks"]) if len(complete)==len(SIMPLE) else None
  for model in models:
   if ref and model==ref["model"]:continue
   aa={x["cell_id"]:num(x["mae_weeks"]) for x in cells if x["arm"]==arm and x["model"]==model}
   bb={x["cell_id"]:num(x["mae_weeks"]) for x in cells if x["arm"]==arm and ref and x["model"]==ref["model"]}
   ids=sorted(set(aa)&set(bb));d=np.asarray([aa[i]-bb[i] for i in ids]);ok=np.isfinite(d)
   status="OK" if ref is not None and len(ids)==len(expected) and ok.all() else ("NO_COMPLETE_REFERENCE" if ref is None else "INVALID_OR_MISSING_PAIRED_CELL")
   ci=[float("nan"),float("nan")]
   if status=="OK":
    z=d[rng.randint(0,len(d),(2000,len(d)))].mean(axis=1);ci=[float(np.quantile(z,.025)),float(np.quantile(z,.975))]
   paired.append({"arm":arm,"model":model,"reference_model":ref["model"] if ref else "UNRESOLVED",
    "reference_rule":"post-hoc lowest cell-macro MAE among four simple baselines","status":status,
    "n_expected_cells":len(expected),"n_paired_cells":len(ids),"n_missing_paired_cells":len(expected-set(ids)),"n_invalid_paired_cells":int((~ok).sum()),
    "mean_cell_paired_delta_mae":mkeep(d),"ci95_seed42":ci,"wins":int((d<0).sum()),"ties":int((d==0).sum()),"losses":int((d>0).sum())})
 write_csv(out/"paired_differences.csv",paired)
 lines=["# ISU 不规则 RUL 开发结果汇总","",
 "仅从保存的预测 CSV 计算；不读取原始曲线、checkpoint，不拟合或推理。端点是 source-observed 首次完成 RPT 的 Q≤0.20 Ah；属于 event-observed 开发描述，不是潜在真实 EOL 或独立确认。锁定队列读取数按 runner 协议为 0；物理电芯串行身份尚未核验。","",
 "先在每电芯内平均预测起点，再对电芯等权平均。NaN/失败不删除不修补；若任一电芯的该指标无效，总体对应均值保留 NaN，同时报告有效/无效电芯数。严重高估是预测均值减目标大于4周。","",
 "参照在每个 arm 内从 group_frozen、hgb_early_health、hgb_dynamic、aft_dynamic 四个简单模型中按最低电芯宏平均 MAE 事后选择；若任一基线含无效 MAE，则不宣称最强参照已确定。配对差为待比较模型减参照的共同电芯 MAE；正值更差。seed42 电芯配对bootstrap 95%区间。","",
 "## 每臂模型主表","","| arm | model | cells | MAE weeks | >4w rate | cells any >4w | IS80 | coverage | Brier4 | Brier12 | update ms |","|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
 def fmt(x):return "NaN" if not math.isfinite(num(x)) else f"{num(x):.4g}"
 for r in sums:lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(r["arm"],r["model"],r["n_cells"],*[fmt(r[k]) for k in ("mae_weeks","severe_overprediction_gt4w_rate","cells_any_severe_overprediction_rate","is80","coverage80","brier4w","brier12w","mean_update_wall_ms")]))
 lines.extend(["","## 配对差异"])
 for r in paired:lines.append(f'- {r["arm"]} / {r["model"]} vs {r["reference_model"]}: delta MAE={r["mean_cell_paired_delta_mae"]}, CI95={r["ci95_seed42"]}, 胜/平/负={r["wins"]}/{r["ties"]}/{r["losses"]}, status={r["status"]}。')
 lines.extend(["","逐电芯结果见 cell_metrics.csv；配对样本和bootstrap见 paired_differences.csv。本汇总不改变训练协议，也不构成模型选择后的独立性能声明。",""])
 (out/"RESULTS_ZH.md").write_text("\n".join(lines),encoding="utf-8")
 return {"rows":len(raw),"cells":len({r["cell_id"] for r in raw}),"arms":arms,"models":models,"output":str(out)}
def main():
 p=argparse.ArgumentParser();p.add_argument("--predictions",required=True);p.add_argument("--output",required=True);a=p.parse_args()
 print(summarize(a.predictions,a.output))
if __name__=="__main__":main()

