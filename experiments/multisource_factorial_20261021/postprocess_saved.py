#!/usr/bin/env python3
"""Saved-cell-metrics paired analysis. No raw data, predictions, models, or C4 access."""
import argparse, csv, hashlib, json, math, os, sys
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yndx/zxk/rul")
EXP = ROOT / "experiments/multisource_factorial_20261021"
RESULTS = EXP / "run2_clocksafe"
RECEIPT = EXP / "MULTISOURCE_FORMAL_2X2_80FITS_CLOCK_VALIDITY_REPAIR_20261021_receipt.json"
FORMAL_GO = EXP / "ROOT_GO_FORMAL80_CLOCKSAFE.json"
CSV_IN = RESULTS / "cell_metrics.csv"
SOURCE_MAP = {
    "formal_receipt": "5eeab340d13c450d028143a6a624e4b0a1431e92b4e2b272e2400c9a285ee8b9",
    "formal_go": "8d8265fc0fdc2603291bb9dd3673e4833310b84bbfb403ff9ebff139c2a11b1f",
    "cell_metrics": None,
}
POSTPROCESS_FILE = Path(__file__).resolve()
PANELS = [
    ("F1_vs_F0", "F1", "F0"),
    ("F2_vs_F0", "F2", "F0"),
    ("F3_vs_F1", "F3", "F1"),
    ("F3_vs_F2", "F3", "F2"),
    ("F3_vs_F0", "F3", "F0"),
    ("RPT_scalar_vs_F0", "control_rpt_scalar_only", "F0"),
    ("normalized_shape_vs_F0", "control_capacity_normalized_shape_only", "F0"),
    ("normalized_shape_vs_scalar", "control_capacity_normalized_shape_only", "control_rpt_scalar_only"),
    ("VI_only_vs_F0", "control_cycle_vi_e_time_only", "F0"),
    ("RPT_VI_vs_F1", "control_rpt_full_vi_e_time", "F1"),
    ("full24_vs_VI_only", "F2", "control_cycle_vi_e_time_only"),
    ("normalized_shape_scalar_cycle_vs_F3", "control_rpt_scalar_plus_shape_cycle", "F3"),
]
BASE_METRICS = [
    "event_brier", "event_logloss", "mean_abs_error", "median_abs_error",
    "severe_gt4w", "IS80", "coverage80", "Brier4", "Brier12", "bin_logscore",
]
LOWER_IS_BETTER = set(BASE_METRICS) - {"coverage80"}

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def fail(msg):
    raise SystemExit("STOP: " + msg)

def check_go(path):
    go = json.load(open(path, encoding="utf-8"))
    if go.get("status") != "APPROVED" or go.get("allow_postprocess") is not True:
        fail("fresh postprocess GO is not approved")
    if any(go.get(k) is not False for k in ("allow_fits", "allow_inference", "allow_raw_data", "allow_c4", "allow_model_weights")):
        fail("GO must explicitly forbid fits, inference, raw, C4, and weight reads")
    if go.get("request_id") != "MULTISOURCE_PAIRED_CELL_ANALYSIS_20261021":
        fail("unexpected request_id")
    if go.get("owner_thread_id") != "01a15c3a-1a06-7d61-8517-27b70b246183":
        fail("owner_thread_id mismatch")
    pins = go.get("source_sha256", {})
    expected = {
        "postprocess_saved.py": sha(POSTPROCESS_FILE),
        "formal_receipt": sha(RECEIPT),
        "formal_go": sha(FORMAL_GO),
        "cell_metrics": sha(CSV_IN),
    }
    if pins != expected:
        fail("GO source_sha256 binding mismatch: expected " + json.dumps(expected, sort_keys=True))
    if go.get("output_dir") != str(EXP / "paired_saved_analysis_20261021"):
        fail("output_dir mismatch")
    return go

def panel_from_model(model):
    if "_" not in model:
        return None
    return model.split("_", 1)[1]

def parse_rows():
    with open(CSV_IN, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 12820:
        fail(f"cell_metrics row count changed: {len(rows)}")
    required = {"seed","model","arm","stratum","cell_id","n_queries",*BASE_METRICS}
    if not rows or not required.issubset(rows[0]):
        fail("cell_metrics schema mismatch")
    out = {}
    for r in rows:
        try:
            key = (r["seed"], r["model"], r["arm"], r["stratum"], r["cell_id"])
            vals = {m: float(r[m]) if r[m] not in ("", "nan", "NaN") else math.nan for m in BASE_METRICS}
            vals["n_queries"] = int(r["n_queries"])
        except Exception as e:
            fail(f"invalid saved metric row: {e}")
        if key in out:
            fail("duplicate saved cell metric key")
        out[key] = vals
    return out

def boot_ci(vals, seed=42, reps=2000):
    vals = np.asarray([x for x in vals if math.isfinite(x)], dtype=float)
    if not len(vals):
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(vals, size=(reps, len(vals)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [.025, .975])
    return float(lo), float(hi)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", required=True)
    args = ap.parse_args()
    go = check_go(args.go)
    if sha(POSTPROCESS_FILE) != go["source_sha256"]["postprocess_saved.py"]:
        fail("source changed after GO validation")
    receipt = json.load(open(RECEIPT, encoding="utf-8"))
    if (receipt.get("status") != "SUCCESS" or receipt.get("CPU_fits_started") != 80
        or receipt.get("CPU_fits_completed") != 80 or receipt.get("C4_payload_reads") != 0
        or receipt.get("old_model_loads") != 0):
        fail("formal receipt does not establish the completed zero-C4 80-fit run")
    rows = parse_rows()
    output = Path(go["output_dir"])
    output.mkdir(parents=True, exist_ok=False)
    # Convert base coverage to distance from the nominal 0.80 target. Higher
    # coverage alone is not better; proper interval score is reported separately.
    keys = sorted(set((k[0], k[2], k[3], k[4]) for k in rows))
    lookup = {}
    for (seed, model, arm, stratum, cell), vals in rows.items():
        family = model.split("_", 1)[0]
        panel = panel_from_model(model)
        lookup[(seed, family, panel, arm, stratum, cell)] = vals
    delta_rows = []
    summaries = []
    for contrast, cand, ref in PANELS:
      for family in ("hgb", "catboost"):
        for arm in ("raw", "sparse2", "delay7d"):
            strata = sorted(set(k[2] for k in keys if k[1] == arm))
            for stratum in strata:
                shared = []
                for seed, a, s, cell in keys:
                    if a != arm or s != stratum:
                        continue
                    c = lookup.get((seed, family, cand, arm, stratum, cell))
                    b = lookup.get((seed, family, ref, arm, stratum, cell))
                    if c is None or b is None:
                        continue
                    shared.append((seed, cell, c, b))
                if not shared:
                    continue
                for metric in BASE_METRICS:
                        metric_name = "coverage80_distance" if metric == "coverage80" else metric
                        deltas = []
                        for seed, cell, c, b in shared:
                            cv, rv = c[metric], b[metric]
                            if metric == "coverage80":
                                cv, rv = abs(cv - .80), abs(rv - .80)
                            delta = cv - rv
                            if not math.isfinite(delta):
                                continue
                            deltas.append(delta)
                            delta_rows.append({
                                "contrast": contrast, "candidate": cand, "reference": ref,
                                "model_family": family,
                                "arm": arm, "stratum": stratum, "seed": seed, "cell_id": cell,
                                "metric": metric_name, "candidate_minus_reference": f"{delta:.12g}",
                                "candidate_value": f"{cv:.12g}", "reference_value": f"{rv:.12g}",
                                "candidate_n_queries": c["n_queries"], "reference_n_queries": b["n_queries"],
                                "harm_gt2w": int(metric == "mean_abs_error" and delta > 2),
                            })
                        if not deltas:
                            continue
                        lo, hi = boot_ci(deltas, seed=42)
                        tol = 1e-12
                        beneficial = sum(x < -tol for x in deltas) / len(deltas)
                        harmful = sum(x > tol for x in deltas) / len(deltas)
                        tied = 1 - beneficial - harmful
                        summaries.append({
                            "contrast": contrast, "candidate": cand, "reference": ref,
                            "model_family": family, "arm": arm, "stratum": stratum, "metric": metric_name,
                            "n_paired_cells": len(deltas), "mean_candidate_minus_reference": sum(deltas)/len(deltas),
                            "median_candidate_minus_reference": float(np.median(deltas)),
                            "physical_cell_bootstrap_95_lo": lo, "physical_cell_bootstrap_95_hi": hi,
                            "benefit_fraction": beneficial, "harm_fraction": harmful, "tie_fraction": tied,
                            "harm_gt2w_fraction": sum(x > 2 for x in deltas)/len(deltas) if metric == "mean_abs_error" else "",
                            "harm_gt2w_cells": sum(x > 2 for x in deltas) if metric == "mean_abs_error" else "",
                            "severe_gt4w_paired_mean_delta": sum(deltas)/len(deltas) if metric == "severe_gt4w" else "",
                        })
    if not summaries:
        fail("no paired summaries generated")
    with open(output/"paired_cell_deltas.csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(delta_rows[0])); w.writeheader(); w.writerows(delta_rows)
    with open(output/"paired_contrast_summary.csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0])); w.writeheader(); w.writerows(summaries)
    # Guard that pairability is genuinely across both model families, without
    # assuming a specific number of rows per contrast/arm/stratum.
    families = sorted(set(key[1].split("_",1)[0] for key in rows))
    manifest = {
        "status":"SUCCESS", "request_id":go["request_id"], "created_utc":datetime.now(timezone.utc).isoformat(),
        "analysis_scope":"saved cell_metrics only; no raw payload, predictions, C4, model weights, fits or inference",
        "input_sha256":{"postprocess_saved.py":sha(POSTPROCESS_FILE),"cell_metrics":sha(CSV_IN),
                        "formal_receipt":sha(RECEIPT),"formal_go":sha(FORMAL_GO)},
        "formal_receipt_status":receipt["status"], "fits_completed":receipt["CPU_fits_completed"],
        "C4_payload_reads":receipt["C4_payload_reads"], "old_model_loads":receipt["old_model_loads"],
        "saved_cell_metric_rows":len(rows), "model_families":families,
        "contrast_count":len(PANELS), "paired_summary_rows":len(summaries), "paired_cell_delta_rows":len(delta_rows),
        "bootstrap":{"unit":"physical cell", "reps":2000, "seed":42, "CI":"percentile 95%"},
        "metric_direction":"lower is better; coverage80 transformed to absolute distance from nominal 0.80; IS80 remains separate",
        "limits":["development-only paired stability analysis","not independent confirmation",
                  "source-observed event may be known from complete arrived RPTs in raw arm",
                  "three invalid-clock source rows are unknown-time whole records; no missing-cycle count is inferred"],
        "outputs":["paired_cell_deltas.csv","paired_contrast_summary.csv","RESULTS_ZH.md"],
    }
    (output/"analysis_receipt.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_report(output, summaries, manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

def write_report(output, summaries, manifest):
    # Compact Chinese tables are computed strictly from the generated paired summary.
    by = {(r["contrast"],r["model_family"],r["arm"],r["stratum"],r["metric"]):r for r in summaries}
    lines = [
      "# 多源电池特征正式开发集配对分析",
      "",
      "本报告只对已保存的逐物理电芯 cell_metrics.csv 做事后配对统计；没有读取原始载荷、逐查询预测、C4、模型权重，也没有拟合或推理。",
      "",
      f"正式 2×2 运行已完成 {manifest['fits_completed']} 次拟合；正式运行回执记录 C4 读取 {manifest['C4_payload_reads']}、旧模型加载 {manifest['old_model_loads']}。以下都是开发集结果，不是独立确认。",
      "",
      "## 方法与解释边界",
      "",
      "每个对比按模型家族、观测臂、事件分层和物理电芯配对；报告候选减参照的逐电芯差值、物理电芯重抽样 95% 区间，以及有利/有害比例。每个电芯等权，区间反映电芯间稳定性，不把查询数当作独立样本。",
      "",
      "误差、Brier、log loss、严重误差比例和 80% 区间分数均按越低越好。覆盖率单独转成 |coverage−0.80|；覆盖率越高并不天然更好。区间分数 IS80 另行报告，不能用覆盖率代替。",
      "",
      "raw 臂的已到达 RPT 历史可以完整显示来源事件是否已发生，因此接近零的当前事件 Brier 不能证明模型具有不确定状态更新机制；仍需关注未来 4/12 周风险与稀疏/延迟臂表现。三条无效时钟记录代表时间未知的整条来源记录，不推断缺失循环数。",
      "",
      "## 关键配对结果",
      "",
      "表中 MAE、IS80、严重 >4 周比例和覆盖率偏差均为候选减参照的平均逐电芯差值；负值有利。范围为物理电芯 bootstrap 95% 区间。配对和异质性细节见 paired_cell_deltas.csv。",
      "",
      "| 对比 | 模型 | 观测臂 | MAE Δ（95% 区间） | MAE有利/有害 | 有害>2周 | 严重>4周比例 Δ | IS80 Δ | 覆盖率偏差 Δ |",
      "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    selections = ["F1_vs_F0","F2_vs_F0","F3_vs_F1","F3_vs_F2","F3_vs_F0",
                  "RPT_scalar_vs_F0","normalized_shape_vs_F0","normalized_shape_vs_scalar",
                  "VI_only_vs_F0","RPT_VI_vs_F1","full24_vs_VI_only",
                  "normalized_shape_scalar_cycle_vs_F3"]
    for contrast in selections:
      for fam in ("hgb","catboost"):
        for arm in ("raw","sparse2","delay7d"):
          mae=by.get((contrast,fam,arm,"all","mean_abs_error"))
          sev=by.get((contrast,fam,arm,"all","severe_gt4w"))
          ins=by.get((contrast,fam,arm,"all","IS80"))
          cov=by.get((contrast,fam,arm,"all","coverage80_distance"))
          if not all((mae,sev,ins,cov)): continue
          def fmt(x): return f"{x:+.3f}" if isinstance(x,(int,float)) and math.isfinite(x) else "NA"
          family_label = "HGB" if fam == "hgb" else "CatBoost"
          lo, hi = mae["physical_cell_bootstrap_95_lo"], mae["physical_cell_bootstrap_95_hi"]
          lines.append(f"| {contrast} | {family_label} | {arm} | {fmt(mae['mean_candidate_minus_reference'])} ({fmt(lo)}, {fmt(hi)}) | {mae['benefit_fraction']:.0%}/{mae['harm_fraction']:.0%} | {mae['harm_gt2w_fraction']:.0%} | {fmt(sev['mean_candidate_minus_reference'])} | {fmt(ins['mean_candidate_minus_reference'])} | {fmt(cov['mean_candidate_minus_reference'])} |")
    lines += [
      "",
      "## 输出与限制",
      "",
      "paired_contrast_summary.csv 给出所有预先指定对比、模型家族、观测臂、分层和指标的汇总；paired_cell_deltas.csv 保留每个配对电芯差值。cell_metrics.csv 中的逐电芯指标本身是查询聚合后的分数，因此本分析不能提供 SOH、阶段或预测时距分层；没有读取预测明细来补做这些分层。",
      "",
      "这些结果量化当前开发集上的配对稳定性，不构成独立确认，也不能单独支持因果机制主张。",
      "",
    ]
    (output/"RESULTS_ZH.md").write_text("\n".join(lines),encoding="utf-8")

if __name__=="__main__":
    main()

