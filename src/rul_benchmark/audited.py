"""将身份manifest、聚类不确定性与分层诊断接入正式离线评测入口。"""
import collections,hashlib,json,math,pathlib,random,statistics
from .evaluation import evaluate,validate_predictions

def validate_against_manifest(rows,manifest):
    cells=manifest.get("cells",[])
    if not cells:raise ValueError("cell identity/split manifest is required")
    aliases={};roles=collections.defaultdict(set)
    for c in cells:
        required=["dataset","source_cell_id","physical_cell_id","role","identity_audit"]
        if any(not c.get(k) for k in required):raise ValueError("incomplete manifest cell")
        if c["identity_audit"]!="verified":raise ValueError("unresolved physical identity")
        if c["role"] not in ["train","validation","calibration","test"]:raise ValueError("invalid manifest role")
        alias=(c["dataset"],c["source_cell_id"])
        identity=(c["physical_cell_id"],c["role"])
        if alias in aliases and aliases[alias]!=identity:raise ValueError("alias maps to conflicting canonical identity/role")
        aliases[alias]=identity;roles[c["physical_cell_id"]].add(c["role"])
    if any(len(v)>1 for v in roles.values()):raise ValueError("physical-cell role leakage in manifest")
    rows=validate_predictions(rows)
    for r in rows:
        alias=(r["dataset"],r.get("source_cell_id"))
        if alias not in aliases:raise ValueError("prediction source cell is absent from manifest")
        if aliases[alias]!=(r["physical_cell_id"],r["role"]):raise ValueError("prediction canonical identity/role conflicts with manifest")
    counts=collections.Counter(next(iter(role)) for role in roles.values())
    return {"status":"PASS_IDENTITY_AND_ROLE_CONTRACT","unique_manifest_cells":len(roles),"role_counts":dict(counts),
            "identity_evidence_limit":"manifest attestations require external data audit; bytes alone cannot prove physical identity",
            "pretraining_overlap_audit":manifest.get("pretraining_overlap_audit",{"status":"UNRESOLVED"})}

def cell_bootstrap_mae(rows,seed=42,n_resamples=2000,confidence=0.95):
    if n_resamples<100 or not 0<confidence<1:raise ValueError("invalid bootstrap configuration")
    values=[x["MAE_cycles"] for x in evaluate(rows)["per_cell"]]
    if len(values)<2:return {"status":"INSUFFICIENT_INDEPENDENT_CELLS","n_cells":len(values),"ci":None}
    rng=random.Random(seed)
    samples=sorted(statistics.mean(rng.choice(values) for _ in values) for _ in range(n_resamples))
    alpha=(1-confidence)/2
    return {"status":"COMPUTED","estimand":"cell_macro_MAE_cycles","point":statistics.mean(values),
            "ci":[samples[int(alpha*n_resamples)],samples[min(n_resamples-1,int((1-alpha)*n_resamples))]],
            "confidence":confidence,"seed":seed,"n_resamples":n_resamples,"n_cells":len(values),
            "assumption":"independent cells; correlated experimental batches need batch-level resampling"}

def overestimate_exceedance(rows,threshold):
    if isinstance(threshold,bool) or not math.isfinite(float(threshold)) or threshold<0:raise ValueError("invalid prespecified overestimate threshold")
    grouped=collections.defaultdict(list)
    for r in rows:grouped[r["physical_cell_id"]].append(r["pred_rul_cycles"]-r["true_rul_cycles"]>threshold)
    return {"threshold_cycles":threshold,"definition":"predicted_RUL - true_RUL > threshold","cell_macro_rate":statistics.mean(statistics.mean(v) for v in grouped.values())}

def evaluate_audited(rows,manifest,protocol,seed=42,n_resamples=2000):
    rows=validate_predictions(rows);label_audit=validate_exact_label_contract(rows,protocol);audit=validate_against_manifest(rows,manifest);report=evaluate(rows)
    report["label_contract_audit"]=label_audit
    report["data_identity_audit"]=audit
    report["single_model_MAE_CI"]=cell_bootstrap_mae(rows,seed,n_resamples)
    if protocol.get("overestimate_threshold_cycles") is not None:
        if not protocol.get("threshold_frozen_before_test",False):raise ValueError("danger threshold must be frozen before test")
        report["overestimate_exceedance"]=overestimate_exceedance(rows,float(protocol["overestimate_threshold_cycles"]))
    else:report["overestimate_exceedance"]={"status":"UNCONFIGURED_NO_DANGER_THRESHOLD_CLAIM"}
    strata={}
    for name in ["dataset","aging_condition"]:
        if all(r.get(name) is not None for r in rows):
            groups=collections.defaultdict(list)
            for r in rows:groups[str(r[name])].append(r)
            strata[name]={key:evaluate(value) for key,value in sorted(groups.items())}
        else:strata[name]={"status":"FIELD_NOT_AVAILABLE"}
    edges=protocol.get("query_cycle_bin_edges")
    if edges is not None:
        if not protocol.get("query_grid_frozen_before_test",False):raise ValueError("query bins must be frozen before test")
        if len(edges)<2 or any(not math.isfinite(float(x)) for x in edges) or any(b<=a for a,b in zip(edges,edges[1:])):raise ValueError("invalid observed-cycle bins")
        groups=collections.defaultdict(list)
        for row in rows:
            match=None
            for left,right in zip(edges,edges[1:]):
                if left<=row["query_cycle"]<right:match="[%s,%s)"%(left,right);break
            groups[match or "outside_prespecified_grid"].append(row)
        strata["observed_query_cycle"]={key:evaluate(value) for key,value in sorted(groups.items())}
    else:strata["observed_query_cycle"]={"status":"UNCONFIGURED"}
    report["stratified"]=strata
    report["protocol"]=protocol
    return report

def validate_exact_label_contract(rows, protocol):
    """数学MAE计算之前强制核验端点种类、循环坐标和预先声明查询。"""
    from .queries import SPACES
    if protocol.get('evaluation_target') != 'exact_observed_rul':
        raise ValueError('Exact observed-RUL evaluation target must be explicit')
    required = ['eol_definition_id', 'cycle_index_space', 'future_policy_id']
    if any(not protocol.get(k) for k in required) or protocol['cycle_index_space'] not in SPACES:
        raise ValueError('Explicit EOL definition, coordinate and policy are required')
    grid = protocol.get('query_grid')
    if (not protocol.get('query_grid_frozen_before_test') or not isinstance(grid, list)
            or not grid or any(isinstance(q, bool) or not isinstance(q, int) or q <= 0 for q in grid)
            or grid != sorted(set(grid))):
        raise ValueError('A prespecified absolute observed-cycle query grid is required')
    sources = protocol.get('label_source_sha256_allowlist', [])
    if not sources or any(not isinstance(s,str) or len(s)!=64 or any(c not in '0123456789abcdef' for c in s) for s in sources):
        raise ValueError('Audited label-source SHA256 allowlist is required')
    for row in rows:
        if row.get('label_status') != 'observed_crossing':
            raise ValueError('Only observed crossing labels enter exact RUL MAE; extrapolated/censored are excluded')
        if any(row.get(k) != protocol[k] for k in required):
            raise ValueError('Prediction EOL definition, coordinate or policy conflicts with protocol')
        if row.get('query_cycle') not in grid:
            raise ValueError('Prediction query is outside the prespecified absolute grid')
        if row.get('label_source_sha256') not in sources:
            raise ValueError('Prediction label source is not in audited source allowlist')
    return {'status':'PASS_EXACT_OBSERVED_LABEL_CONTRACT',
            'eol_definition_id':protocol['eol_definition_id'],
            'cycle_index_space':protocol['cycle_index_space'],
            'endpoint_status':'observed_crossing',
            'evidence_limit':'Metadata must be backed by external source/feature audit; this function does not re-read trajectories.'}
