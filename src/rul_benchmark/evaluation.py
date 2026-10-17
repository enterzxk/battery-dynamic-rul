"""动态RUL离线评测：原始循环单位，按物理电芯聚合。
不拟合模型，不从最后一次观测构造EOL，不将多前缀视为独立电芯。
"""
import argparse, collections, json, math, pathlib, random, statistics

def _number(value, name):
    if isinstance(value, bool): raise ValueError(name+" must be numeric")
    result=float(value)
    if not math.isfinite(result): raise ValueError(name+" must be finite")
    return result

def validate_predictions(rows):
    if not rows: raise ValueError("no predictions")
    checked=[];seen=set();eols={}
    for original in rows:
        r=dict(original)
        for name in ["physical_cell_id","dataset","role"]:
            if not isinstance(r.get(name),str) or not r[name].strip():raise ValueError(name+" is required")
        if r["role"] not in ["validation","calibration","test"]:raise ValueError("evaluation role must be explicit")
        for name in ["query_cycle","true_rul_cycles","pred_rul_cycles"]:r[name]=_number(r[name],name)
        if r["query_cycle"]<0 or r["true_rul_cycles"]<=0 or r["pred_rul_cycles"]<0:raise ValueError("invalid cycle/RUL range; no silent clipping")
        key=(r["physical_cell_id"],r["query_cycle"])
        if key in seen:raise ValueError("duplicate physical cell/query")
        seen.add(key)
        # 同一电芯在精确未截尾标签下，query+RUL必须对应同一个终寿循环。
        eol=r["query_cycle"]+r["true_rul_cycles"]
        if r["physical_cell_id"] in eols and not math.isclose(eols[r["physical_cell_id"]],eol,rel_tol=0,abs_tol=1e-6):raise ValueError("inconsistent exact EOL labels")
        eols[r["physical_cell_id"]]=eol
        has_interval="lower_rul_cycles" in r or "upper_rul_cycles" in r
        if has_interval:
            if not all(k in r for k in ["lower_rul_cycles","upper_rul_cycles"]):raise ValueError("incomplete interval")
            for name in ["lower_rul_cycles","upper_rul_cycles"]:r[name]=_number(r[name],name)
            if r["lower_rul_cycles"]<0 or r["lower_rul_cycles"]>r["upper_rul_cycles"]:raise ValueError("invalid interval")
        checked.append(r)
    roles=collections.defaultdict(set)
    for r in checked:roles[r["physical_cell_id"]].add(r["role"])
    if any(len(v)>1 for v in roles.values()):raise ValueError("same physical cell appears in multiple evaluation roles")
    if len({r["role"] for r in checked})!=1:raise ValueError("evaluate each role separately")
    if any("lower_rul_cycles" in r for r in checked) and not all("lower_rul_cycles" in r for r in checked):raise ValueError("interval metrics require all rows or a separate predeclared subset")
    return checked

def audit_split_manifest(cells):
    """物理电芯ID必须由已审计manifest提供；不把文件名当作物理身份保证。"""
    if not cells:raise ValueError("empty cell manifest")
    owners={};counts=collections.Counter()
    for c in cells:
        identity=c.get("physical_cell_id");role=c.get("role")
        if not identity or role not in ["train","validation","calibration","test"]:raise ValueError("invalid cell manifest")
        if c.get("identity_audit")!="verified":raise ValueError("physical cell identity unresolved")
        if identity in owners and owners[identity]!=role:raise ValueError("physical-cell leakage")
        owners[identity]=role
    counts.update(owners.values())
    return {"status":"PASS_PHYSICAL_CELL_ROLE_DISJOINT","unique_cells":len(owners),"role_counts":dict(counts),"pretraining_overlap_audited":False}

def evaluate(rows):
    rows=validate_predictions(rows)
    groups=collections.defaultdict(list)
    for row in rows:groups[row["physical_cell_id"]].append(row)
    per_cell=[]
    for cell_id,items in sorted(groups.items()):
        items.sort(key=lambda r:r["query_cycle"])
        errors=[r["pred_rul_cycles"]-r["true_rul_cycles"] for r in items]
        item={"physical_cell_id":cell_id,"n_prefixes":len(items),
              "MAE_cycles":statistics.mean(abs(e) for e in errors),
              "RMSE_cycles":math.sqrt(statistics.mean(e*e for e in errors)),
              "mean_positive_overestimate_cycles":statistics.mean(max(e,0) for e in errors),
              "overestimate_rate":statistics.mean(e>0 for e in errors)}
        # EOL修正量保留为修正诊断，单独变小不代表更准确。
        revisions=[abs((b["query_cycle"]+b["pred_rul_cycles"])-(a["query_cycle"]+a["pred_rul_cycles"])) for a,b in zip(items,items[1:])]
        item["mean_abs_EOL_revision_cycles"]=statistics.mean(revisions) if revisions else None
        if "lower_rul_cycles" in items[0]:
            item["interval_coverage"]=statistics.mean(r["lower_rul_cycles"]<=r["true_rul_cycles"]<=r["upper_rul_cycles"] for r in items)
            item["interval_width_cycles"]=statistics.mean(r["upper_rul_cycles"]-r["lower_rul_cycles"] for r in items)
        per_cell.append(item)
    metric_names=["MAE_cycles","RMSE_cycles","mean_positive_overestimate_cycles","overestimate_rate","mean_abs_EOL_revision_cycles"]
    if "lower_rul_cycles" in rows[0]:metric_names+=["interval_coverage","interval_width_cycles"]
    macro={}
    for key in metric_names:
        values=[x[key] for x in per_cell if x.get(key) is not None]
        macro[key]=statistics.mean(values) if values else None
        if key=="mean_abs_EOL_revision_cycles":macro["n_cells_with_multiple_queries"]=len(values)
    return {"schema_version":1,"status":"COMPUTED_METRICS_ONLY_NOT_A_PERFORMANCE_CLAIM","unit":"cycles","role":rows[0]["role"],
            "n_cells":len(groups),"n_predictions":len(rows),"cell_macro":macro,
            "prefix_micro_MAE_cycles":statistics.mean(abs(r["pred_rul_cycles"]-r["true_rul_cycles"]) for r in rows),
            "per_cell":per_cell}

def paired_cell_bootstrap_mae(rows_a,rows_b,seed=42,n_resamples=2000,confidence=0.95):
    """同电芯、同查询、同标签配对；重采样单位是电芯。返回A-B，负值才是A误差较低。"""
    a=validate_predictions(rows_a);b=validate_predictions(rows_b)
    key=lambda r:(r["physical_cell_id"],r["query_cycle"])
    aa={key(r):r for r in a};bb={key(r):r for r in b}
    if aa.keys()!=bb.keys():raise ValueError("paired comparison needs identical cell/query population")
    for k in aa:
        if any(aa[k][x]!=bb[k][x] for x in ["dataset","role","true_rul_cycles"]):raise ValueError("paired labels/context differ")
    if n_resamples<100 or not 0<confidence<1:raise ValueError("invalid bootstrap configuration")
    ea={x["physical_cell_id"]:x["MAE_cycles"] for x in evaluate(a)["per_cell"]}
    eb={x["physical_cell_id"]:x["MAE_cycles"] for x in evaluate(b)["per_cell"]}
    ids=sorted(ea)
    if len(ids)<2:raise ValueError("uncertainty needs at least two independent cells")
    differences=[ea[i]-eb[i] for i in ids];rng=random.Random(seed)
    samples=sorted(statistics.mean(rng.choice(differences) for _ in ids) for _ in range(n_resamples))
    alpha=(1-confidence)/2
    lo=samples[max(0,int(alpha*n_resamples))];hi=samples[min(n_resamples-1,int((1-alpha)*n_resamples))]
    return {"estimand":"paired_cell_macro_MAE_A_minus_B_cycles","mean":statistics.mean(differences),
            "ci":[lo,hi],"confidence":confidence,"seed":seed,"n_resamples":n_resamples,"n_cells":len(ids),
            "limitation":"cell independence assumed; use experimental-batch bootstrap if batch dependence is material"}

def main():
    from .audited import evaluate_audited
    import hashlib
    root=pathlib.Path('/home/yndx/zxk/rul').resolve()
    ap=argparse.ArgumentParser();ap.add_argument('--predictions',required=True);ap.add_argument('--manifest',required=True);ap.add_argument('--protocol',required=True);ap.add_argument('--output',required=True);ap.add_argument('--seed',type=int,default=42);a=ap.parse_args()
    paths={k:pathlib.Path(getattr(a,k)).resolve() for k in ['predictions','manifest','protocol','output']}
    if any(not p.is_relative_to(root) for p in paths.values()):raise ValueError('all scientific files must stay in project root')
    rows=[json.loads(line) for line in paths['predictions'].read_text().splitlines() if line.strip()]
    result=evaluate_audited(rows,json.loads(paths['manifest'].read_text()),json.loads(paths['protocol'].read_text()),seed=a.seed)
    result['input_sha256']={key:hashlib.sha256(paths[key].read_bytes()).hexdigest() for key in ['predictions','manifest','protocol']}
    paths['output'].parent.mkdir(parents=True,exist_ok=True)
    with paths['output'].open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
