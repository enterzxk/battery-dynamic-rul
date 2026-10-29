"""Export an allowlisted text snapshot; no model/data execution or network IO."""
import datetime
import base64
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('/home/yndx/zxk/rul')
OUT = ROOT / 'automation/github_export'
EXT = {'.py', '.md', '.json', '.jsonl', '.csv', '.yaml', '.yml', '.sha256', '.svg'}
BINARY_PREDICTION_ARCHIVES = {

    'reports/isu_six_baseline_public_lossless_v17_20261021_luna/archive.bin',
    'reports/progress_history_public_lossless_v18_binary_20261021_root/archive.bin',
    'reports/dart_v18_public_evidence_package_20261021_root/archive.bin',
    'reports/completed_matr_longtrend_binary_lossless_v18_root/archive.bin',
}
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|https?://[^\s/:]+:[^\s/@]+@)')


def main():
    chosen = {'AGENTS.md', 'PROJECT_PROGRESS.md', 'automation/bin/export_github_context.py'}
    chosen.add('docs/COORDINATOR_HANDOFF_20261019_V15_ZH.md')
    for directory in ['src', 'configs', 'results', 'literature/accepted']:
        chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob('*') if p.is_file())
    chosen.update('docs/' + name for name in [
        'CHATGPT_CONTEXT_ZH.md', 'GITHUB_SYNC_ZH.md', 'CONTINUATION_POLICY.md', 'RESEARCH_PLAN_ZH.md', 'Battery_RUL_Codex_Handoff_20261017_ZH.md', 'COORDINATOR_HANDOFF_20261017_V9_ZH.md',
        'BATTERY_CONCEPTS_ZH_v0.md', 'DYNAMIC_RUL_PROTOCOL_ZH.md',
        'DYNAMIC_RUL_LABEL_DECISIONS_v1.md', 'DYNAMIC_RUL_ASOF_FREEZE_CANDIDATE_v3_ZH.md'])
    for directory in ['data_schema_audit', 'baseline_audit', 'development_pilot', 'asof_preprocessing_audit_v1', 'literature_discussion_20261017_root_v1', 'dynamic_A_eligible_20261017_root', 'pbt_valid_cycle_production_io_20261017_luna', 'matr_v11_release_provenance_20261018_root', 'p1_cp_checkpoint_inventory_20261018_root']:
        chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports' / directory).rglob('*') if p.is_file())
    for directory in sorted((ROOT / 'reports').glob('literature_synthesis_increment*')):
        chosen.update(str(p.relative_to(ROOT)) for p in directory.rglob('*') if p.is_file())
    index_path = 'reports/pbt_author_eol_val_contract_v2_root/active_preparation_index.json'
    chosen.add(index_path)
    index = json.loads((ROOT / index_path).read_text())
    chosen.add(index['active_contract'])
    for item in index.get('active_static_evidence', []):
        path = item['path'].removeprefix(str(ROOT) + '/')
        chosen.add(path)
    chosen.add('automation/github_export/build_dynamic_A_eligible_20261017.py')
    chosen.add('reports/dynamic_A_matr_retrospective_independent_20261017_luna/review.json')
    for name in ['runner.py', 'ROOT_GO.json', 'fit_ledger.jsonl', 'validation_predictions.csv', 'per_cell_paired_deltas.json', 'selection.json', 'completion_receipt.json', 'launch_receipt.json', 'independent_metrics.json', 'root_decision.json', 'RESULTS_ZH.md', 'independent_metric_recompute.py', 'censored_failure_diagnosis.json', 'CENSORED_FAILURE_ZH.md', 'LABEL_BOUNDARY_SUPPORT_ZH.md', 'label_boundary_feature_support.json', 'label_boundary_support_diagnosis.py', 'ERROR_CONTRIBUTION_ZH.md', 'error_contribution.json', 'batch_observation_cross_tab.json', 'error_contribution_diagnosis.py', 'batch_observation_diagnosis.py', 'TERMINAL_BOUNDARY_ZH.md', 'terminal_boundary_diagnosis.json', 'terminal_boundary_diagnosis.py', 'diagnostic_closure.json']:
        chosen.add('experiments/dynamic_A_matr_retrospective_seed42_v1/' + name)
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/cpmlp_recipe_error_diagnosis_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/cpmlp_selection_diagnosis_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/p1_calb_reproduction_gap_20261018_root').rglob('*') if p.is_file())
    for directory in ['calb_acquisition_20261018_root', 'calb_acquisition_20261018_root_v2']:
        chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports' / directory).rglob('*') if p.is_file())
    for directory in ['calb_trainval_sample_audit_20261018_root', 'calb_trainval_sample_audit_20261018_root_v2']:
        chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports' / directory).rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/calb_two_sample_preprocessing_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/calb_remaining20_audit_20261018_root').rglob('*') if p.is_file())
    for directory in ['calb_dataset_trainval_20261018_root', 'calb_dataset_trainval_20261018_root_v2']:
        chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports' / directory).rglob('*') if p.is_file())
    for name in ['runner.py', 'config.json', 'ROOT_GO.json', 'root_adaptation_review.json', 'run_manifest.json', 'launch_receipt.json', 'budget_ledger.jsonl', 'epoch_metrics.jsonl', 'completion_receipt.json', 'validation_predictions_epoch_002.csv', 'independent_metric_recompute.py', 'independent_metrics.json', 'root_result_decision.json', 'RESULTS_ZH.md']:
        chosen.add('experiments/cpmlp_calb_recipe_adapt_seed2021_v1/' + name)
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/calb_group_prior_diagnosis_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/calb_identity_text_audit_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/early_eol_filter_realization_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/calb_selection_diagnosis_20261018_root').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/hust_saved_source_identity_20261018_root').rglob('*') if p.is_file())
    chosen.add('docs/USER_SINGLE_BATTERY_ONLINE_RUL_20261018_ZH.md')
    for directory in ['online_survival_competition_20261018_luna', 'online_survival_pilot_review_20261018_luna']:
        chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports' / directory).rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'experiments/online_survival_observed_pilot_seed42_v1').rglob('*') if p.is_file())
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT / 'reports/online_rate_harm_diagnosis_20261018_root').rglob('*') if p.is_file())
    chosen.add('reports/p1_cpmlp_recipe_review_20261018_luna/review.json')
    for name in ['runner.py', 'config.json', 'ROOT_GO.json', 'stopping_check.json', 'deadline_boundary_check.json', 'failure_receipt.json', 'launch_receipt.json']:
        chosen.add('experiments/cpmlp_hust_recipe_adapt_seed42_v1/' + name)
    for name in ['runner.py', 'config.json', 'ROOT_GO.json', 'runtime_repair_review.json', 'completion_receipt.json', 'launch_receipt.json', 'run_manifest.json', 'epoch_metrics.jsonl', 'budget_ledger.jsonl', 'independent_metrics.json', 'root_result_decision.json', 'RESULTS_ZH.md', 'independent_metric_recompute.py', 'validation_predictions_epoch_003.csv']:
        chosen.add('experiments/cpmlp_hust_recipe_adapt_seed42_v2/' + name)
    for run in (ROOT / 'experiments').glob('*/fit_runs/*'):
        chosen.update(str(p.relative_to(ROOT)) for p in run.iterdir() if p.is_file())

    chosen.add("docs/PAPER_FAST_PATH_20261018_ZH.md")
    for name in ["runner.py","protocol.json","ROOT_GO.json","root_delta_review.json","fit_ledger.jsonl","launch_receipt.json","completion_receipt.json","metrics.json","per_cell_metrics.json","comparisons.json","predeclared_failure_windows.json","independent_metrics.json","root_decision.json","RESULTS_ZH.md","published_predictions_columnar.json","decode_public_predictions.py"]:
        chosen.add("experiments/online_survival_robust_rate_seed42_v1/" + name)

    # Raw NASA DataV1 pilot: code and small derived audit only; no raw MAT/CSV/source README.
    for name in ['DATAV1_ZH.md','import_nasa.py','preprocessing_protocol.json','preprocessing_protocol_v2.json','two_cell_check.json','data_v1_summary.json']:
        chosen.add('reports/data_v1_raw_nasa_20261018_root/' + name)
    for name in ['acquisition_budget.json','availability_probe.json','matr_batch2_stream_budget.json','matr_transfer_stop.json','nasa_stream_budget.json']:
        chosen.add('reports/data_v1_raw_matr_20261018_root/' + name)

    for name in ['SOURCE_INVENTORY_ZH.md','inventory_summary.json','prospective_split.json','budget.json']:
        chosen.add('reports/nasa_remaining_source_inventory_20261018_root/' + name)

    for name in ['RANGE_BREAKTHROUGH_ZH.md','range_budget.json','completion.json','failure.json']:
        chosen.add('reports/matr_raw_range_20261018_root/' + name)
    for name in ['two_reads_failure.json','two_raw_summary.json','two_raw_read.py']:
        chosen.add('reports/nasa_remaining_source_inventory_20261018_root/' + name)
    chosen.update(['automation/bin/matr_selected_range_worker_v1.py','automation/bin/matr_selected_range_worker_v2.py'])

    # Preserve original server predictions and historical commit; publish exact lossless CSV archive.
    chosen.discard('experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_lossless.json')
    chosen.difference_update(str(p.relative_to(ROOT)) for p in (ROOT/'experiments/online_survival_observed_pilot_seed42_v1/validation_predictions').glob('*.csv'))
    chosen.update(['experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_part1.json','experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_part2.json','experiments/online_survival_observed_pilot_seed42_v1/decode_public_prediction_csvs.py','docs/PUBLIC_PREDICTION_STORAGE_V1.json'])

    chosen.add('automation/bin/matr_raw_batch2_asset_worker_v1.py')
    for name in ['protocol.json','two_raw_cycle_check.json','completion.json','DATAV1_ZH.md']:
        chosen.add('reports/matr_raw_batch2_datav1_20261018_root/' + name)
    chosen.add('reports/matr_raw_longtrend_review_20261018_luna/review.json')
    chosen.update(str(p.relative_to(ROOT)) for p in (ROOT/'experiments/matr_raw_batch2_longtrend_seed42_v1').iterdir() if p.is_file())

    chosen.update(['automation/bin/matr_raw_batch4_asset_worker_v1.py','automation/bin/matr_raw_batch4_asset_worker_v2.py'])
    for name in ['DATAV1_ZH.md','source_receipt.json','quarantine_report.json','protocol.json','failure.json','two_raw_cycle_check.json','combined_cohort_summary.json','repair_v2/protocol.json','repair_v2/two_raw_cycle_check.json','repair_v2/completion.json']:
        chosen.add('reports/matr_raw_batch4_datav1_20261018_root/' + name)

    chosen.discard('experiments/matr_raw_batch2_longtrend_seed42_v1/previous_github_sync.json')

    chosen.add('reports/matr_heldout_scale_review_20261018_luna/review.json')
    for name in ['runner.py', 'protocol.json', 'cohort.json', 'ROOT_GO.json', 'fit_ledger.jsonl', 'completion.json', 'fit_parameters.json', 'residual_cell_statistics.json', 'metrics.json', 'per_cell_metrics.json', 'comparison.json', 'independent_metric_recompute.py', 'independent_metrics.json', 'scale_failure_diagnosis.json', 'root_decision.json', 'RESULTS_ZH.md', 'minimal_metric_check.json', 'published_predictions.json', 'decode_public_predictions.py']:
        chosen.add('experiments/matr_raw_heldout_calibration_seed42_v1/' + name)

    for name in ['protocol.json','diagnose.py','diagnostic.json','minimal_validation.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/causal_capacity_feedback_20261018_root/' + name)

    chosen.add('reports/capacity20_forecast_review_20261018_luna/review.json')
    for name in ['runner.py', 'protocol.json', 'cohort.json', 'ROOT_GO.json', 'fit_ledger.jsonl', 'completion.json', 'metrics.json', 'per_cell_metrics.json', 'comparison.json', 'independent_metric_recompute.py', 'independent_metrics.json', 'published_predictions.json', 'decode_public_predictions.py', 'two_pair_check.json', 'root_decision.json', 'RESULTS_ZH.md']:
        chosen.add('experiments/capacity20_forecast_seed42_v1/' + name)

    for directory in ['learned_capacity_feedback_20261018_root','persistent_capacity_feedback_20261018_root']:
        for name in ['protocol.json','diagnose.py','diagnostic.json','minimal_validation.json','root_decision.json','RESULTS_ZH.md']:
            chosen.add('reports/' + directory + '/' + name)

    chosen.update(['reports/capacity_firstpassage_review_20261018_luna/review.json','automation/bin/build_capacity20_endpoint_targets_v2.py'])
    for name in ['runner.py', 'protocol.json', 'cohort.json', 'ROOT_GO.json', 'completion.json', 'metrics.json', 'per_cell_metrics.json', 'comparison.json', 'independent_metric_recompute.py', 'independent_metrics.json', 'published_predictions.json', 'decode_public_predictions.py', 'training_endpoint_coverage.json', 'endpoint_data_manifest.json', 'root_decision.json', 'RESULTS_ZH.md']:
        chosen.add('experiments/capacity_firstpassage_seed42_v1/' + name)

    chosen.add('reports/capacity_endpoint_v2_review_20261018_luna/review.json')
    for name in ['runner.py', 'protocol.json', 'cohort.json', 'ROOT_GO.json', 'fit_ledger.jsonl', 'completion.json', 'capacity_comparison.json', 'metrics.json', 'per_cell_metrics.json', 'comparison.json', 'independent_metric_recompute.py', 'independent_metrics.json', 'published_predictions.json', 'decode_public_predictions.py', 'capacity_prediction_delta.json', 'decode_capacity_delta.py', 'preGO_control_failure.json', 'preGO_control_resolution.json', 'root_decision.json', 'RESULTS_ZH.md']:
        chosen.add('experiments/capacity_endpoint_firstpassage_seed42_v2/' + name)

    chosen.add('reports/native_rul_mae_review_20261018_luna/review.json')
    for name in ['runner.py','protocol.json','cohort.json','ROOT_GO.json','fit_ledger.jsonl','completion.json','metrics.json','per_cell_metrics.json','comparison.json','independent_metric_recompute.py','independent_metrics.json','prediction_delta.json','decode_prediction_delta.py','failure_diagnosis.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('experiments/native_rul_mae_seed42_v1/' + name)

    for name in ['protocol.json','diagnose.py','metrics.json','per_cell_metrics.json','comparison.json','transition_audit.json','phase_metrics.json','arithmetic_examples.json','completion.json','independent_metrics.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/fixedearly_dynamic_20261018_root/' + name)

    for name in ['protocol.json','diagnose.py','metrics.json','per_cell_metrics.json','comparison.json','numeric_validation.json','arithmetic_examples.json','completion.json','independent_recompute.py','independent_metrics.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/early_survival_conditioning_20261018_root/' + name)

    for name in ['protocol.json','diagnose.py','results.json','completion.json','independent_recompute.py','independent_metrics.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/frozen_probability_audit_20261018_root/' + name)

    # Lossless archive replaces duplicated example JSONs in current snapshot; originals retained.
    chosen.difference_update(['reports/fixedearly_dynamic_20261018_root/arithmetic_examples.json', 'reports/early_survival_conditioning_20261018_root/arithmetic_examples.json'])
    chosen.update(['reports/saved_examples_lossless_20261018_root/examples_lossless.json','reports/saved_examples_lossless_20261018_root/decode.py','reports/frozen_probability_audit_20261018_root/export_cap_failure.json'])

    chosen.add('reports/conditional_quantiles_review_20261018_luna/review.json')
    for name in ['runner.py', 'protocol.json', 'cohort.json', 'ROOT_GO.json', 'fit_ledger.jsonl', 'completion.json', 'metrics.json', 'per_cell_metrics.json', 'comparison.json', 'independent_recompute.py', 'independent_metrics.json', 'prediction_delta.json', 'decode_prediction_delta.py', 'root_decision.json', 'RESULTS_ZH.md']:
        chosen.add('experiments/conditional_quantiles_seed42_v1/' + name)
    chosen.difference_update(['experiments/native_rul_mae_seed42_v1/ROOT_GO.json', 'experiments/native_rul_mae_seed42_v1/cohort.json', 'experiments/native_rul_mae_seed42_v1/comparison.json', 'experiments/native_rul_mae_seed42_v1/completion.json', 'experiments/native_rul_mae_seed42_v1/failure_diagnosis.json', 'experiments/native_rul_mae_seed42_v1/fit_ledger.jsonl', 'experiments/native_rul_mae_seed42_v1/independent_metric_recompute.py', 'experiments/native_rul_mae_seed42_v1/independent_metrics.json', 'experiments/native_rul_mae_seed42_v1/metrics.json', 'experiments/native_rul_mae_seed42_v1/per_cell_metrics.json', 'experiments/native_rul_mae_seed42_v1/protocol.json', 'experiments/native_rul_mae_seed42_v1/runner.py', 'reports/early_survival_conditioning_20261018_root/comparison.json', 'reports/early_survival_conditioning_20261018_root/completion.json', 'reports/early_survival_conditioning_20261018_root/diagnose.py', 'reports/early_survival_conditioning_20261018_root/independent_metrics.json', 'reports/early_survival_conditioning_20261018_root/independent_recompute.py', 'reports/early_survival_conditioning_20261018_root/metrics.json', 'reports/early_survival_conditioning_20261018_root/numeric_validation.json', 'reports/early_survival_conditioning_20261018_root/per_cell_metrics.json', 'reports/early_survival_conditioning_20261018_root/protocol.json', 'reports/fixedearly_dynamic_20261018_root/comparison.json', 'reports/fixedearly_dynamic_20261018_root/completion.json', 'reports/fixedearly_dynamic_20261018_root/diagnose.py', 'reports/fixedearly_dynamic_20261018_root/independent_metrics.json', 'reports/fixedearly_dynamic_20261018_root/metrics.json', 'reports/fixedearly_dynamic_20261018_root/per_cell_metrics.json', 'reports/fixedearly_dynamic_20261018_root/phase_metrics.json', 'reports/fixedearly_dynamic_20261018_root/protocol.json', 'reports/fixedearly_dynamic_20261018_root/transition_audit.json', 'reports/frozen_probability_audit_20261018_root/completion.json', 'reports/frozen_probability_audit_20261018_root/diagnose.py', 'reports/frozen_probability_audit_20261018_root/export_cap_failure.json', 'reports/frozen_probability_audit_20261018_root/independent_metrics.json', 'reports/frozen_probability_audit_20261018_root/independent_recompute.py', 'reports/frozen_probability_audit_20261018_root/protocol.json', 'reports/frozen_probability_audit_20261018_root/results.json', 'reports/pbt_import_closure_static_v2_luna/audit.json'])
    chosen.update(['reports/saved_examples_lossless_20261018_root/completed_details_lossless.json','reports/saved_examples_lossless_20261018_root/decode_completed_details.py'])

    for name in ['protocol.json','diagnose.py','summary.json','examples.json','source_hashes.json','completion.json','minimal_validation.json','policy_context_observation.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/local_state_support_20261018_root/' + name)

    for name in ['encode_policy.py','encode_policy_v0.py','encode_policy_v1.py','encoder_v0_failure.json','constant_check_float_resolution.json','policy_features.json','encoding_summary.json','source_semantics.json','two_encoding_examples.json','ENCODING_ZH.md']:
        chosen.add('reports/policy_context_20261018_root/' + name)
    chosen.update(['reports/policy_context_point_seed42_v1_luna/review.json','reports/policy_context_point_seed42_v1_luna/review_v0_hash_transcription_error.json'])
    for name in ['runner.py','protocol.json','cohort.json','ROOT_GO.json','fit_ledger.jsonl','completion.json','metrics.json','per_cell_metrics.json','comparison.json','independent_recompute.py','independent_metrics.json','prediction_delta.json','decode_prediction_delta.py','policy_exposure_subgroups.json','preGO_review_schema_rejection.json','preGO_hash_resolution.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('experiments/policy_context_point_seed42_v1/' + name)

    for name in ['protocol.json','diagnose.py','metrics.json','per_cell_metrics.json','comparison.json','transition_audit.json','phase_metrics.json','arithmetic_examples.json','completion.json','independent_recompute.py','independent_metrics.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/policy_fixedearly_dynamic_20261018_root/' + name)

    for name in ['protocol.json','diagnose.py','metrics.json','per_cell_metrics.json','comparisons.json','arithmetic_examples.json','completion.json','independent_recompute.py','independent_metrics.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/policy_survival_probability_20261019_root/' + name)

    chosen.add('reports/policy_fit_scale_review_20261019_luna/review.json')
    for name in ['protocol.json','cohort.json','point_model_protocol.json','runner.py','ROOT_GO.json','minimal_static_validation.json','inference_ledger.jsonl','fit_input_receipt.json','fit_scale.json','metrics.json','per_cell_metrics.json','comparison.json','completion.json','independent_recompute.py','independent_metrics.json','fit_residual_predictions_lossless.json','decode_fit_residual_predictions.py','lossless_validation.json','review_timestamp_annotation.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('experiments/policy_fit_scale_seed42_v1/' + name)

    for name in ['protocol.json','diagnose.py','diagnose_v1.py','failure_v0.json','metrics.json','per_cell_metrics.json','comparison.json','transition_audit.json','arithmetic_examples.json','completion.json','independent_recompute.py','independent_metrics.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/policy_causal_ema20_20261019_root/' + name)

    for name in ['protocol.json','diagnose.py','train_cutoff.json','summary.json','paired_calibration.json','examples.json','completion.json','independent_recompute.py','independent_validation.json','independent_public_recompute.py','public_independent_validation.json','per_cell_metrics_lossless.json','decode_per_cell_metrics.py','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/policy_revision_reliability_20261019_root/' + name)

    chosen.add('reports/policy_conditional_quantiles_review_20261019_luna/review.json')
    for name in ['runner.py','protocol.json','cohort.json','ROOT_GO.json','fit_ledger.jsonl','metrics.json','per_cell_metrics.json','comparison.json','completion.json','independent_recompute.py','independent_metrics.json','prediction_delta.json','decode_prediction_delta.py','lossless_validation.json','crossing_localization.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('experiments/policy_conditional_quantiles_seed42_v1/' + name)

    # Completed static evidence lossless archive; original server files/history retained.
    chosen.difference_update(['reports/literature_discussion_20261017_root_v1/paper_evidence.json', 'reports/data_schema_audit/run_20261015T164049_918837Z/per_cell_schema_audit.jsonl', 'reports/pbt_val_pairing_static_v1_luna/existing_view_join_v2/prefix_projection.csv', 'reports/pbt_stage0_metadata_freeze_v2_root/metadata_receipt.json'])
    chosen.update(['reports/completed_static_lossless_20261019_root/archive.json', 'reports/completed_static_lossless_20261019_root/decode.py', 'reports/completed_static_lossless_20261019_root/validation.json'])

    chosen.update(['experiments/policy_oof_cdf_seed42_v1/runner.py', 'experiments/policy_oof_cdf_seed42_v1/protocol.json', 'experiments/policy_oof_cdf_seed42_v1/cohort.json', 'experiments/policy_oof_cdf_seed42_v1/ROOT_GO.json', 'experiments/policy_oof_cdf_seed42_v1/launch_receipt.json', 'experiments/policy_oof_cdf_seed42_v1/fit_ledger.jsonl', 'experiments/policy_oof_cdf_seed42_v1/completion.json', 'experiments/policy_oof_cdf_seed42_v1/metrics.json', 'experiments/policy_oof_cdf_seed42_v1/per_cell_metrics.json', 'experiments/policy_oof_cdf_seed42_v1/comparison.json', 'experiments/policy_oof_cdf_seed42_v1/failure_description.json', 'experiments/policy_oof_cdf_seed42_v1/independent_recompute.py', 'experiments/policy_oof_cdf_seed42_v1/independent_metrics.json', 'experiments/policy_oof_cdf_seed42_v1/predictions_lossless.json', 'experiments/policy_oof_cdf_seed42_v1/decode_predictions.py', 'experiments/policy_oof_cdf_seed42_v1/lossless_validation.json', 'experiments/policy_oof_cdf_seed42_v1/root_decision.json', 'experiments/policy_oof_cdf_seed42_v1/RESULTS_ZH.md', 'reports/policy_oof_cdf_review_20261019_luna/review.json', 'reports/policy_oof_cdf_review_20261019_luna/review_stage_resolution.json'])

    chosen.update(['reports/policy_oof_age_residual_20261019_root/protocol.json', 'reports/policy_oof_age_residual_20261019_root/diagnose.py', 'reports/policy_oof_age_residual_20261019_root/summary.json', 'reports/policy_oof_age_residual_20261019_root/per_cell_age_metrics.json', 'reports/policy_oof_age_residual_20261019_root/population_contribution.json', 'reports/policy_oof_age_residual_20261019_root/common_cell_comparison.json', 'reports/policy_oof_age_residual_20261019_root/paired_concentration.json', 'reports/policy_oof_age_residual_20261019_root/minimal_validation.json', 'reports/policy_oof_age_residual_20261019_root/completion.json', 'reports/policy_oof_age_residual_20261019_root/root_decision.json', 'reports/policy_oof_age_residual_20261019_root/RESULTS_ZH.md'])

    chosen.discard('experiments/cpmlp_hust_recipe_adapt_seed42_v2/budget_ledger.jsonl')
    chosen.update(['reports/completed_ledger_lossless_20261019_root/archive.json', 'reports/completed_ledger_lossless_20261019_root/decode.py', 'reports/completed_ledger_lossless_20261019_root/validation.json'])

    chosen.update(['experiments/policy_local_oof_cdf_fixed5_v1/protocol.json', 'experiments/policy_local_oof_cdf_fixed5_v1/runner.py', 'experiments/policy_local_oof_cdf_fixed5_v1/ROOT_GO.json', 'experiments/policy_local_oof_cdf_fixed5_v1/estimate_ledger.jsonl', 'experiments/policy_local_oof_cdf_fixed5_v1/train_transform.json', 'experiments/policy_local_oof_cdf_fixed5_v1/local_CDF_parameters.json', 'experiments/policy_local_oof_cdf_fixed5_v1/metrics.json', 'experiments/policy_local_oof_cdf_fixed5_v1/per_cell_metrics.json', 'experiments/policy_local_oof_cdf_fixed5_v1/comparisons.json', 'experiments/policy_local_oof_cdf_fixed5_v1/completion.json', 'experiments/policy_local_oof_cdf_fixed5_v1/independent_recompute.py', 'experiments/policy_local_oof_cdf_fixed5_v1/independent_metrics.json', 'experiments/policy_local_oof_cdf_fixed5_v1/predictions_lossless.json', 'experiments/policy_local_oof_cdf_fixed5_v1/decode_predictions.py', 'experiments/policy_local_oof_cdf_fixed5_v1/lossless_validation.json', 'experiments/policy_local_oof_cdf_fixed5_v1/root_decision.json', 'experiments/policy_local_oof_cdf_fixed5_v1/RESULTS_ZH.md', 'reports/policy_local_oof_cdf_fixed5_review_20261019_luna/review.json'])

    chosen.update(['reports/policy_encoding_collision_20261019_root/protocol.json', 'reports/policy_encoding_collision_20261019_root/audit.py', 'reports/policy_encoding_collision_20261019_root/summary.json', 'reports/policy_encoding_collision_20261019_root/collision_pairs.json', 'reports/policy_encoding_collision_20261019_root/encoding_groups.json', 'reports/policy_encoding_collision_20261019_root/arithmetic_example.json', 'reports/policy_encoding_collision_20261019_root/minimal_validation.json', 'reports/policy_encoding_collision_20261019_root/completion.json', 'reports/policy_encoding_collision_20261019_root/root_decision.json', 'reports/policy_encoding_collision_20261019_root/RESULTS_ZH.md'])


    chosen.difference_update(['reports/cpmlp_recipe_error_diagnosis_20261018_root/paired_prediction_deltas.csv', 'reports/literature_discussion_20261017_root_v1/PAPER_BY_PAPER_ZH.md'])
    chosen.update(['reports/completed_plaintext_lossless_20261019_root/archive.json', 'reports/completed_plaintext_lossless_20261019_root/decode.py', 'reports/completed_plaintext_lossless_20261019_root/validation.json', 'reports/completed_robust_evidence_lossless_20261019_root/packing_no_space_gain.json'])

    chosen.update(['experiments/policy_lossless_schedule_point_seed42_v1/encode_schedule.py', 'experiments/policy_lossless_schedule_point_seed42_v1/policy_features.json', 'experiments/policy_lossless_schedule_point_seed42_v1/minimal_encoding_validation.json', 'experiments/policy_lossless_schedule_point_seed42_v1/protocol.json', 'experiments/policy_lossless_schedule_point_seed42_v1/cohort.json', 'experiments/policy_lossless_schedule_point_seed42_v1/runner.py', 'experiments/policy_lossless_schedule_point_seed42_v1/ROOT_GO.json', 'experiments/policy_lossless_schedule_point_seed42_v1/fit_ledger.jsonl', 'experiments/policy_lossless_schedule_point_seed42_v1/completion.json', 'experiments/policy_lossless_schedule_point_seed42_v1/metrics.json', 'experiments/policy_lossless_schedule_point_seed42_v1/per_cell_metrics.json', 'experiments/policy_lossless_schedule_point_seed42_v1/comparison.json', 'experiments/policy_lossless_schedule_point_seed42_v1/per_cell_change.json', 'experiments/policy_lossless_schedule_point_seed42_v1/gain_concentration.json', 'experiments/policy_lossless_schedule_point_seed42_v1/independent_recompute.py', 'experiments/policy_lossless_schedule_point_seed42_v1/independent_metrics.json', 'experiments/policy_lossless_schedule_point_seed42_v1/predictions_lossless.json', 'experiments/policy_lossless_schedule_point_seed42_v1/decode_predictions.py', 'experiments/policy_lossless_schedule_point_seed42_v1/lossless_validation.json', 'experiments/policy_lossless_schedule_point_seed42_v1/root_decision.json', 'experiments/policy_lossless_schedule_point_seed42_v1/RESULTS_ZH.md', 'reports/policy_lossless_schedule_point_review_20261019_luna/review.json'])

    chosen.update(['reports/lossless_survival_probability_20261019_root/protocol.json', 'reports/lossless_survival_probability_20261019_root/diagnose.py', 'reports/lossless_survival_probability_20261019_root/metrics.json', 'reports/lossless_survival_probability_20261019_root/per_cell_metrics.json', 'reports/lossless_survival_probability_20261019_root/comparisons.json', 'reports/lossless_survival_probability_20261019_root/arithmetic_examples.json', 'reports/lossless_survival_probability_20261019_root/risk_change.json', 'reports/lossless_survival_probability_20261019_root/completion.json', 'reports/lossless_survival_probability_20261019_root/independent_recompute.py', 'reports/lossless_survival_probability_20261019_root/independent_metrics.json', 'reports/lossless_survival_probability_20261019_root/root_decision.json', 'reports/lossless_survival_probability_20261019_root/RESULTS_ZH.md'])

    chosen.difference_update(['reports/dynamic_A_eligible_20261017_root/eligible_origins.csv', 'reports/dynamic_A_eligible_20261017_root/cohort_receipt.json', 'reports/data_schema_audit/run_20261015T164049_918837Z/index_capacity_clarification.json'])
    chosen.update(['reports/completed_eligibility_lossless_20261019_root/archive.json', 'reports/completed_eligibility_lossless_20261019_root/decode.py', 'reports/completed_eligibility_lossless_20261019_root/validation.json'])

    chosen.update(['experiments/lossless_equal_CDF_mixture_v2/protocol.json', 'experiments/lossless_equal_CDF_mixture_v2/runner.py', 'experiments/lossless_equal_CDF_mixture_v2/ROOT_GO.json', 'experiments/lossless_equal_CDF_mixture_v2/key_alignment_validation.json', 'experiments/lossless_equal_CDF_mixture_v2/metrics.json', 'experiments/lossless_equal_CDF_mixture_v2/per_cell_metrics.json', 'experiments/lossless_equal_CDF_mixture_v2/comparisons.json', 'experiments/lossless_equal_CDF_mixture_v2/numeric_validation.json', 'experiments/lossless_equal_CDF_mixture_v2/completion.json', 'experiments/lossless_equal_CDF_mixture_v2/independent_recompute.py', 'experiments/lossless_equal_CDF_mixture_v2/independent_metrics.json', 'experiments/lossless_equal_CDF_mixture_v2/public_quantiles_lossless.json', 'experiments/lossless_equal_CDF_mixture_v2/decode_public_quantiles.py', 'experiments/lossless_equal_CDF_mixture_v2/public_quantiles_validation.json', 'experiments/lossless_equal_CDF_mixture_v2/root_decision.json', 'experiments/lossless_equal_CDF_mixture_v2/RESULTS_ZH.md', 'experiments/lossless_equal_CDF_mixture_v1/runner.py', 'experiments/lossless_equal_CDF_mixture_v1/protocol.json', 'experiments/lossless_equal_CDF_mixture_v1/ROOT_GO.json', 'experiments/lossless_equal_CDF_mixture_v1/failure.json', 'experiments/lossless_equal_CDF_mixture_v1/independent_check_not_run.json', 'reports/lossless_equal_CDF_mixture_review_20261019_luna/review.json', 'reports/lossless_equal_CDF_mixture_review_20261019_luna/review_v2_alignment.json'])

    chosen.update(['reports/post_mixture_methods_conflict_20261019_root/RESULTS_ZH.md','reports/post_mixture_methods_conflict_20261019_root/evidence.json','reports/post_mixture_methods_conflict_20261019_root/validation.json'])

    chosen.update(['reports/delayed_capacity_reliability_20261019_root/RESULTS_ZH.md', 'reports/delayed_capacity_reliability_20261019_root/protocol.json', 'reports/delayed_capacity_reliability_20261019_root/diagnose.py', 'reports/delayed_capacity_reliability_20261019_root/ROOT_GO.json', 'reports/delayed_capacity_reliability_20261019_root/metrics.json', 'reports/delayed_capacity_reliability_20261019_root/per_cell_metrics.json', 'reports/delayed_capacity_reliability_20261019_root/root_decision.json', 'reports/delayed_capacity_reliability_20261019_root/validation.json', 'reports/delayed_capacity_reliability_20261019_root/completion.json'])

    chosen.discard('reports/pbt_validation_finite_static_v1/finite_static_receipt.json')
    chosen.update(['paper/EMPIRICAL_RESULTS_DRAFT_ZH.md', 'paper/evidence_table.json', 'paper/validation.json', 'reports/completed_finite_receipt_lossless_20261019_root/archive.json', 'reports/completed_finite_receipt_lossless_20261019_root/decode.py', 'reports/completed_finite_receipt_lossless_20261019_root/validation.json'])

    chosen.difference_update(['experiments/cptransformer_hust_pilot_seed42/fit_runs/fit_20261016T040414_680559Z/val_predictions_epoch_001.csv', 'experiments/cptransformer_hust_pilot_seed42/fit_runs/fit_20261016T040414_680559Z/val_predictions_epoch_003.csv'])
    chosen.update(['experiments/causal_linear_threshold_fixed20_v1/RESULTS_ZH.md', 'experiments/causal_linear_threshold_fixed20_v1/runner.py', 'experiments/causal_linear_threshold_fixed20_v1/runner_pre_missingfix.py', 'experiments/causal_linear_threshold_fixed20_v1/protocol.json', 'experiments/causal_linear_threshold_fixed20_v1/feature_manifest.json', 'experiments/causal_linear_threshold_fixed20_v1/dedup_static_receipt.json', 'experiments/causal_linear_threshold_fixed20_v1/missing_input_fix_validation.json', 'experiments/causal_linear_threshold_fixed20_v1/ROOT_GO.json', 'experiments/causal_linear_threshold_fixed20_v1/metrics.json', 'experiments/causal_linear_threshold_fixed20_v1/per_cell_metrics.json', 'experiments/causal_linear_threshold_fixed20_v1/independent_validation.json', 'experiments/causal_linear_threshold_fixed20_v1/completion.json', 'experiments/causal_linear_threshold_fixed20_v1/root_decision.json', 'experiments/causal_linear_threshold_fixed20_v1/public_predictions_lossless.json', 'experiments/causal_linear_threshold_fixed20_v1/decode_public_predictions.py', 'experiments/causal_linear_threshold_fixed20_v1/public_predictions_validation.json', 'reports/causal_linear_threshold_review_20261019_luna/review.json', 'reports/causal_linear_threshold_review_20261019_luna/review_v2_missing.json', 'reports/completed_cptransformer_predictions_lossless_20261019_root/archive.json', 'reports/completed_cptransformer_predictions_lossless_20261019_root/decode.py', 'reports/completed_cptransformer_predictions_lossless_20261019_root/validation.json'])

    chosen.difference_update(['experiments/cpmlp_hust_pilot_seed42/fit_runs/fit_20261016T034610_311103Z/val_predictions_epoch_001.csv', 'experiments/cpmlp_hust_pilot_seed42/fit_runs/fit_20261016T034610_311103Z/val_predictions_epoch_002.csv', 'experiments/cpmlp_hust_pilot_seed42/fit_runs/fit_20261016T034610_311103Z/val_predictions_epoch_003.csv'])
    chosen.update(['paper/figures/empirical_reliability_v1/figure.svg', 'paper/figures/empirical_reliability_v1/plot_figure.py', 'paper/figures/empirical_reliability_v1/figure_contract.json', 'paper/figures/empirical_reliability_v1/CAPTION.md', 'paper/figures/empirical_reliability_v1/README.md', 'paper/figures/empirical_reliability_v1/source_cell_metrics.csv', 'paper/figures/empirical_reliability_v1/source_trajectories.csv', 'paper/figures/empirical_reliability_v1/data_validation.json', 'paper/figures/empirical_reliability_v1/figure.alignment.json', 'paper/figures/empirical_reliability_v1/figure.preflight.json', 'paper/figures/empirical_reliability_v1/figure.text-audit.json', 'paper/figures/empirical_reliability_v1/figure.collision-audit.json', 'paper/figures/empirical_reliability_v1/visual_qa.json', 'reports/completed_cpmlp_predictions_lossless_20261019_root/archive.json', 'reports/completed_cpmlp_predictions_lossless_20261019_root/decode.py', 'reports/completed_cpmlp_predictions_lossless_20261019_root/validation.json'])

    # Fixed20 reporting-delay: saved predictions on server; publish reproducible code and full cell metrics.
    for name in ['runner.py','protocol.json','preflight.json','ROOT_GO.json','metrics.json','per_cell_metrics.json','comparisons.json','numeric_validation.json','independent_recompute.py','independent_validation.json','completion.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('experiments/reporting_delay_fixed20_v1/' + name)
    chosen.update(['reports/reporting_delay_fixed20_review_20261019_luna/review.json', 'reports/reporting_delay_fixed20_review_20261019_luna/review_preGO_resolution.json'])
    chosen.discard('experiments/cpmlp_calb_recipe_adapt_seed2021_v1/budget_ledger.jsonl')
    for name in ['archive.json','decode.py','validation.json']:
        chosen.add('reports/completed_calb_ledger_lossless_20261019_root/' + name)

    for name in ['RESULTS_ZH.md','protocol_candidate.json','evidence.json','readiness.json']:
        chosen.add('reports/independent_confirmation_readiness_20261019_root/' + name)

    for name in ['runner.py','protocol.json','ROOT_GO.json','summary.json','failure.json','minimal_validation.json','startup_capacity_diagnostic.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/nasa_b0033_compatibility_20261019_root/' + name)
    chosen.add('reports/nasa_b0033_compatibility_review_20261019_luna/review.json')
    chosen.discard('experiments/cpmlp_hust_pilot_seed42/fit_runs/fit_20261016T034610_311103Z/budget_ledger.jsonl')
    for name in ['archive.json','decode.py','validation.json']:
        chosen.add('reports/completed_hust_pilot_ledger_lossless_20261019_root/' + name)

    for name in ['RESULTS_ZH.md','evidence.json','decision.json']:
        chosen.add('reports/oxford_official_metadata_20261019_root/' + name)

    for name in ['RESULTS_ZH.md','evidence.json','decision.json','prospective_roles.json','header_preflight_budget.json']:
        chosen.add('reports/calce_cs2_metadata_20261019_root/' + name)

    for name in ['receipt.json','RESULTS_ZH.md']:
        chosen.add('reports/calce_cs2_head_preflight_20261019_root/' + name)

    for name in ['ROOT_METADATA_GO.json','receipt.json']:
        chosen.add('reports/calce_cs2_local_head_20261019_root/' + name)
    for name in ['ROOT_ACQUISITION_GO.json','receive_archive.py','receipt.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/calce_cs2_35_acquisition_20261019_root/' + name)

    chosen.discard('experiments/cptransformer_hust_pilot_seed42/fit_runs/fit_20261016T040414_680559Z/budget_ledger.jsonl')
    for name in ['archive.json','decode.py','validation.json']:
        chosen.add('reports/completed_cptransformer_ledger_lossless_20261019_root/' + name)
    for name in ['archive_directory.json','protocol.json','read_firstfile.py','independent_review.json','independent_review_fixed.json','read_firstfile_pre_review.py','ROOT_READ_GO.json','public_summary.json','minimal_validation.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/calce_cs2_35_firstfile_20261019_root/' + name)

    chosen.discard('experiments/cptransformer_hust_pilot_seed42/fit_runs/fit_20261016T040414_680559Z/val_predictions_epoch_002.csv')
    for name in ['archive.json','decode.py','validation.json']:
        chosen.add('reports/completed_cptransformer_epoch2_lossless_20261019_root/' + name)
    for name in ['protocol.json','runner.py','runner_pre_review.py','independent_review.json','independent_review_final.json','ROOT_READ_GO.json','counter_semantics_diagnostic.json','summary.json','minimal_validation.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/calce_cs2_35_series_20261019_root/' + name)

    for name in ['RESULTS_ZH.md', 'schema_diagnosis.json', 'source_evidence.json', 'calce_io.py', 'capacity_rules.py', 'capacity_rules_before_legacyfix.py', 'capacity_rules_before_nullablefix.py', 'reconstruct.py', 'reconstruct_v2.py', 'reconstruct_v3.py', 'schema_protocol.json', 'ROOT_SCHEMA_GO.json', 'measurement_probe_protocol.json', 'ROOT_MEASUREMENT_PROBE_GO.json', 'reconstruction_protocol.json', 'reconstruction_protocol_v2.json', 'reconstruction_protocol_v3.json', 'ROOT_RECONSTRUCTION_GO.json', 'ROOT_RECONSTRUCTION_GO_v2.json', 'ROOT_RECONSTRUCTION_GO_v3.json', 'reconstruction_summary.json', 'reconstruction_summary_v2.json', 'independent_reconstruction_review.json', 'independent_reconstruction_review_fixed.json', 'independent_reconstruction_review_v2.json', 'independent_reconstruction_review_v2_fixed.json', 'regression_failure_diagnostic.json', 'representative_capacity_validation.json', 'final_validation.json', 'public_summary.json', 'asset_manifest.json', 'endpoint_labels.json', 'DATA_DICTIONARY_ZH.md', 'root_decision.json']:
        chosen.add('reports/calce_cs2_35_repair_20261020_root/' + name)
    chosen.discard('experiments/cpmlp_hust_recipe_adapt_seed42_v2/validation_predictions_epoch_003.csv')
    for name in ['archive.json','decode.py','validation.json']:
        chosen.add('reports/completed_hust_recipe_epoch3_lossless_20261020_root/' + name)

    chosen.discard('experiments/matr_raw_batch2_longtrend_seed42_v1/development_predictions.csv')
    for name in ['archive.json','decode.py','validation.json']:
        chosen.add('reports/completed_matr_longtrend_predictions_lossless_20261020_root/' + name)

    chosen.add('docs/COORDINATOR_HANDOFF_20261020_V16_ZH.md')
    for name in ['receipt.json','RESULTS_ZH.md']:
        chosen.add('reports/calce_cs2_35_session_evidence_20261020_v16/' + name)

    chosen.add('docs/PAPER_ROUTE_20261020_ZH.md')
    for name in ['protocol.json','runner.py','ROOT_GO.json','summary.json','per_cell.json','semantic_validation.json','completion.json','root_decision.json','RESULTS_ZH.md']:
        chosen.add('reports/measurement_schedule_firstpassage_20261020_root/' + name)
    for name in ['review.json','validation.json']:
        chosen.add('reports/measurement_schedule_firstpassage_review_20261020_luna/' + name)
    for name in ['receipt.json','next_semantic_preflight_scope.json','RESULTS_ZH.md']:
        chosen.add('reports/isu_ilcc_metadata_20261020_root/' + name)

    for name in ['semantic_decision.json','Valid_cells.csv.receipt.json','process_data.py.receipt.json','README_V2.0.pdf.receipt.json']:
        chosen.add('reports/isu_ilcc_metadata_20261020_root/' + name)
    for name in ['cohort.json','protocol.json','runner.py','receive_archive.py','ROOT_GO.json','acquisition_receipt.json','stage_resolution.json','probe_results.json','completion.json','RESULTS_ZH.md','root_decision.json']:
        chosen.add('reports/isu_ilcc_capacity_probe_20261020_root/' + name)
    for name in ['review.json','review_fixed.json']:
        chosen.add('reports/isu_ilcc_capacity_probe_review_20261020_luna/' + name)
    for name in ['central_directory_scope.json','central_directory_receipt.json','next_clock_recovery_scope.json']:
        chosen.add('reports/isu_ilcc_clock_source_20261020_root/' + name)

    chosen.add('docs/USER_SPARSE_IRREGULAR_RUL_SPRINT_20261020_ZH.md')
    for name in ['competition_report.md','evidence.json','lfp_feasibility.json']:
        chosen.add('reports/irregular_rul_competition_20261020_luna/' + name)

    for name in ['prepare_datav2.py','receive_datav2.py','protocol.md','two_train_once.claim.json','two_sample_result.json','minimal_validation.json','root_decision.json']:
        chosen.add('reports/isu_ilcc_datav2_two_sample_repair_20261020_root/' + name)
    for name in ['review_v1.json','delta_review.json','ROOT_GO.json','delta_review_repair.json','ROOT_GO_REPAIR.json']:
        chosen.add('reports/isu_ilcc_datav2_20261020_root_review/' + name)
    chosen.add('reports/isu_ilcc_datav2_20261020_data/two_sample_failure.json')
    chosen.add('reports/isu_ilcc_datav2_full_20261020_root/scope_candidate.json')
    chosen.add('reports/irregular_rul_competition_20261020_root/eswa_primary_preview.json')

    # V17: actual ISU baseline evidence; trajectories, checkpoints and member logs remain private.
    chosen.add('docs/COORDINATOR_HANDOFF_20261020_V17_ZH.md')
    chosen.add('docs/ISU_ILCC_CONFIRMATION_PLAN_20261020_ZH.md')
    for name in ['data_manifest.json','full_import_final.json','full_import_failure.json','delta_review.json','ROOT_GO.json','full188_protocol.md','parser_ns_v2.py','qualify_asset.py']:
        chosen.add('reports/isu_ilcc_datav2_full_20261020_root/' + name)
    for name in ['train_eval.py','train_eval_pre_gru_epoch_fix.py','baselines.py','data_adapter.py','protocol_candidate.json','ROOT_GO.json','CPU_PREDICTION_GO.json','baseline_run_receipt.json','cpu_prediction_recovery_receipt.json','recover_cpu_predictions_once.py','summarize_results.py','finish_gru_only.py','candidate_filter.py','filter_representation.py','filter_fit_protocol.json','filter_comparison.py','update_probe_candidate.json']:
        chosen.add('experiments/isu_irregular_rul_seed42_v1/' + name)
    for name in ['RESULTS_ZH.md','arm_model_summary.csv','cell_metrics.csv','paired_differences.csv','root_metric_recompute.json']:
        chosen.add('experiments/isu_irregular_rul_seed42_v1/cpu_results_summary/' + name)

    chosen.add('reports/isu_gru_delta_review_20261020_v17_luna/review.json')
    for name in ['GRU_ONLY_V17_GO.json','gru_only_v17_seed42_receipt.json','six_baseline_seed42_v17/merge_validation.json','six_baseline_seed42_v17/summary/RESULTS_ZH.md','six_baseline_seed42_v17/summary/arm_model_summary.csv','six_baseline_seed42_v17/summary/paired_differences.csv','six_baseline_seed42_v17/summary/root_metric_recompute.json']:
        chosen.add('experiments/isu_irregular_rul_seed42_v1/' + name)

    for name in ['review.json','delta_owner_guard.json']:
        chosen.add('reports/isu_filter_comparison_review_20261020_v17_luna/' + name)
    for name in ['filter_comparison_pre_v17_owner_guard.py','FILTER_COMPARISON_V17_GO.json','filter_comparison_v17_receipt.json','filter_comparison_v17_run1/filter_parameter_status.json','filter_comparison_v17_run1/candidate_full_parameter_fit.json','filter_comparison_v17_run1/candidate_oof_fold_1_parameter_fit.json','filter_comparison_v17_run1/candidate_oof_fold_2_parameter_fit.json','filter_comparison_v17_run1/scalar_full_parameter_fit.json','filter_comparison_v17_run1/scalar_oof_fold_1_parameter_fit.json','filter_comparison_v17_run1/scalar_oof_fold_2_parameter_fit.json','filter_comparison_v17_run1/feature_contract.json']:
        chosen.add('experiments/isu_irregular_rul_seed42_v1/' + name)

    # Replace two published prediction wrappers with byte-exact archives; Git keeps prior history.
    chosen.difference_update(['experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_part1.json','experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_part2.json'])
    chosen.update(BINARY_PREDICTION_ARCHIVES)
    for name in ['decode.py','validation.json']:
        pass  # pilot stage moved out of snapshot HEAD (2026-10-24, receipt V7)
    for name in ['decode.py','validation.json','README.md']:
        chosen.add('reports/isu_six_baseline_public_lossless_v17_20261021_luna/' + name)

    for name in ['RESULTS_ZH.md','root_decision.json','summary/RESULTS_ZH.md','summary/arm_model_summary.csv','summary/scalar_cell_metrics.csv','summary/paired_differences.csv','summary/root_metric_recompute.json']:
        chosen.add('experiments/isu_irregular_rul_seed42_v1/filter_comparison_v17_run1/' + name)

    for name in ['PUBLIC_EVIDENCE_ZH.md','run1/root_recompute.json','run1/root_invariants.json']:
        chosen.add('experiments/isu_irregular_rul_seed42_v1/unknown_event_probe_v17/' + name)


    # V18 create-only lossless archives retain full prior history/predictions under 12MiB.
    chosen.discard('reports/completed_matr_longtrend_predictions_lossless_20261020_root/archive.json')
    for d, names in [
        ('reports/progress_history_public_lossless_v18_binary_20261021_root',['decode.py','validation.json']),
        ('reports/completed_matr_longtrend_binary_lossless_v18_root',['decode.py','validation.json']),
        ('reports/dart_v18_public_evidence_package_20261021_root',['decode.py','README.md','index.json'])]:
        chosen.update(d+'/'+n for n in names)
    chosen.update('docs/'+n for n in ['DART_V18_CONFIRMATION_PLAN_ZH.md','USER_DART_RUL_V18_20261021_ZH.md'])
    chosen.update('experiments/dart_rul_v18/'+n for n in ['RESULTS_ZH.md','protocol.json','data_protocol.py','hgb_models.py','neural_models.py','distributions.py','evaluate.py','benchmark.py','recover_evaluation.py','arrival_panel.py','analyze_saved_v2.py','analysis_v2/root_decision.json','analysis_v2/three_seed_arm_summary.csv','analysis_v2/arrival_summary.csv','analysis_v2/hidden_and_negative_probability.csv'])
    chosen.add('reports/dart_literature_v18_20261021_luna/NOVELTY_REVIEW_ZH.md')

    # Multisource pilot: reviewed reports/code only; raw curve/cycling caches excluded.
    compact = ROOT/'reports/public_evidence_compaction_multisource_20261021_root'
    chosen.difference_update(json.loads((compact/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/public_evidence_compaction_multisource_20261021_root/archive.bin')
    chosen.update('reports/public_evidence_compaction_multisource_20261021_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    chosen.update('experiments/multisource_information_20261021/'+n for n in ['runner.py','protocol.json','ROOT_GO.json','RESULTS_ZH.md','MULTISOURCE_F0F1F2_HGB_CATBOOST_SEED42_20261021_receipt.json','run1/arm_summary.csv','run1/cell_metrics.csv','run1/reliability_bins.csv','review.json','review_addendum.md'])
    chosen.add('experiments/multisource_factorial_20261021/design.json')
    chosen.update('reports/multisource_20261021_signals/'+n for n in ['extract_rpt_signal_features_all188.py','extract_cycling_stream_features.py','ROOT_GO_ALL188.json'])
    chosen.update('reports/multisource_20261021_literature/'+n for n in ['COMPETITION_REVIEW_ZH.md','fulltext_evidence.json','information_independent/INDEPENDENT_RECOMPUTE_ZH.md','information_independent/recompute.py','information_independent/independent_results.json'])
    chosen.update('reports/multisource_20261021_literature/information_figure/'+n for n in ['plot.py','figure_contract.json','figure_source_summary.csv','figure_source_paired.csv','rpt_information_pilot.svg','alignment.json','collision.json','VISUAL_QA.md'])
    chosen.update('experiments/multisource_mechanisms_20261021/train_v1/'+n for n in ['runner.py','targets.py','mechanisms.py','DESIGN_AND_INTERFACES_ZH.md','ROOT_GO.json','runs/run1/receipt.json'])
    chosen.add('experiments/multisource_mechanisms_20261021/evaluate_v1.py')

    chosen.discard('experiments/multisource_information_20261021/run1/cell_metrics.csv')
    BINARY_PREDICTION_ARCHIVES.add('experiments/multisource_information_20261021/public_cell_metrics/archive.bin')
    chosen.update('experiments/multisource_information_20261021/public_cell_metrics/'+n for n in ['archive.bin','validation.json','decode.py'])

    # Formal multisource stage: compact metadata and scientific results only.
    compact2 = ROOT/'reports/legacy_evidence_lossless_multisource_stage2_20261021'
    chosen.difference_update(json.loads((compact2/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_evidence_lossless_multisource_stage2_20261021/archive.bin')
    chosen.update('reports/legacy_evidence_lossless_multisource_stage2_20261021/'+n for n in ['archive.bin','decode.py','validation.json','README.md'])
    chosen.update('data/processed/ISU_ILCC_Multisource_v1/'+n for n in ['asset_manifest.json','README_ZH.md'])
    chosen.update('reports/multisource_20261021_signals/'+n for n in ['cycling_all188_feature_manifest.json','all188_rpt_features_v1/manifest.json','cycle_asof_features.py','FEATURE_INTERPRETATION_ZH.md','sourcefeature_contract.json'])
    chosen.update('experiments/multisource_factorial_20261021/'+n for n in ['runner.py','protocol.json','features.py','postprocess_saved.py','ROOT_GO_FORMAL80_CLOCKSAFE.json','MULTISOURCE_FORMAL_2X2_80FITS_CLOCK_VALIDITY_REPAIR_20261021_receipt.json','ROOT_GO_PAIRED_SAVED.json','run2_clocksafe/summary.json','run2_clocksafe/arm_summary.csv','run2_clocksafe/factorial_interactions.csv','paired_saved_analysis_20261021/analysis_receipt.json','paired_saved_analysis_20261021/RESULTS_ZH.md'])
    chosen.update('reports/multisource_20261021_root/'+n for n in ['FORMAL_INFORMATION_RESULTS_ZH.md','formal_primary_per_cell.csv','formal_paired_all_stratum.csv'])
    chosen.update('reports/multisource_20261021_root/formal_information_figure/'+n for n in ['plot.py','ROOT_GO.json','figure_contract.json','figure_source.csv','formal_information.svg','alignment.json','collision.json','font_audit.json','VISUAL_QA.md'])
    chosen.update('reports/multisource_20261021_trajectory_review/'+n for n in ['TRAJECTORY_REVIEW_ZH.md','same_key_metrics.csv','paired_cell_bootstrap.csv','same_key_checks.json','stage_lead_metrics.csv','RECENT_COMPETITORS_ADDENDUM_ZH.md'])
    chosen.add('paper/multisource_dynamic_rul_20261021/PROBLEM_METHOD_DRAFT.md')

    # Temporal-update and held-condition science stage; original predictions stay on server.
    legacy3=ROOT/'reports/legacy_stage3_lossless_multisource_20261021_root'
    chosen.difference_update(json.loads((legacy3/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_stage3_lossless_multisource_20261021_root/archive.bin')
    chosen.update('reports/legacy_stage3_lossless_multisource_20261021_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    chosen.add('reports/multisource_20261021_root/RESEARCH_SYNTHESIS_ZH.md')
    chosen.update('experiments/multisource_factorial_20261021/'+n for n in ['off_rpt_grid_zerofit.py','ROOT_GO_OFF_RPT_SELF_TRANSPORT_RUN3.json','OFF_RPT_GRID_SAME_MODEL_TRANSPORT_20261021_RUN3_offgrid_receipt.json','off_rpt_grid_self_transport_run3/RESULTS_ZH.md','off_rpt_grid_self_transport_run3/no_new_report_summary.csv','off_rpt_grid_self_transport_run3/arm_summary.csv','off_rpt_grid_self_transport_run3/io_scope_receipt.json'])
    chosen.update('experiments/multisource_generalization_20261021/'+n for n in ['runner.py','condition_group_split.json','ROOT_GO_G_ISOLATION_32.json','C1C2_G_ISOLATION_32FIT_20261021_receipt.json','run1/RESULTS_ZH.md','run1/arm_summary.csv','run1/paired_panel_deltas.csv'])
    chosen.update('experiments/trajectory_multisource_nextcap_20261021/'+n for n in ['run_extension.py','PROTOCOL_ZH.md','ROOT_GO_18FIT.json','runs/nextcap18-9e7d9cb1c67f/receipt.json','runs/nextcap18-9e7d9cb1c67f/metrics_by_model_panel_arm.csv','runs/nextcap18-9e7d9cb1c67f/metrics_by_cell.csv','comparisons_B/PAIRED_NEXTCAP_B_REVIEW_ZH.md','comparisons_B/paired_cell_bootstrap.csv','comparisons_B/paired_metrics.csv','comparisons_B/metadata.json'])
    chosen.add('paper/multisource_dynamic_rul_20261021/METHOD_FLOW.md')
    chosen.add('reports/uconn_lfp_author_pulse_asset_20261021_root/ACCESS_LIMITATION_ZH.md')

    legacy4=ROOT/'reports/legacy_stage4_lossless_mechanisms_20261023_root'
    chosen.difference_update(json.loads((legacy4/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_stage4_lossless_mechanisms_20261023_root/archive.bin')
    chosen.update('reports/legacy_stage4_lossless_mechanisms_20261023_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    chosen.update('reports/codex_takeover_20261023_root/'+n for n in ['REVIEW_AND_NEXT_ACTION_ZH.md','compare_a2_all_trees.py','ROOT_GO_SAVED_REVIEW_RUN2.json','saved_a2_all_trees_run2/all_model_metrics.csv','saved_a2_all_trees_run2/paired_cell_bootstrap.csv','saved_a2_all_trees_run2/receipt.json'])
    chosen.update('reports/multisource_20261021_A2_state/'+n for n in ['RESULTS_ZH.md'])
    chosen.update('reports/multisource_20261021_B2_trajectory/'+n for n in ['RESULTS_ZH.md'])
    chosen.update('experiments/multirate_state_A2_20261022/'+n for n in ['README_A2_ZH.md','a2_model.py','a2_targets.py','a2_train.py','a2_train_v2.py','a2_fastdata.py','a2_fixtures.py','a2_fixtures_fast.py','a2_prep.py','a2_infer.py','receipts/prep_v2_20261022_receipt.json','receipts/c3_eval_v2_20261022_receipt.json','c3_eval_v2_20261022/summary.json'])
    chosen.update('experiments/multirate_state_A2_fullrefit_20261023/'+n for n in ['refit_all125.py','inference_once.py','PROTOCOL.md','ROOT_GO_RUN1.json','ROOT_GO_C3_RUN2.json','receipts/run1.json','ROOT_GO_COMPARE_RUN1.json','receipts/c3_eval_run2.json','receipts/c3_run1_preflight_failure.json','c3_eval_run2/summary.json','c3_eval_run2/receipt.json','same_key_compare_run1/summary.json','same_key_compare_run1/schema.json','same_key_compare_run1/all_model_metrics.csv','same_key_compare_run1/paired_cell_bootstrap.csv','same_key_compare_run1/per_cell_metrics.csv','same_key_compare_run1/receipt.json','RESULTS_ZH.md','run1/full/fit_report.json','run1/time/fit_report.json','run1/noRPTupdate/fit_report.json'])
    chosen.add('experiments/multirate_state_A3_rate_20261024/PROTOCOL.md')
    chosen.update('experiments/multirate_state_A3_rate_20261024/'+n for n in ['a3_model.py','a3_train.py','a3_fixtures.py','a3_infer.py','README_A3_ZH.md','README_A3_INFER_ZH.md','GO_A3_FIT_4ARM_20261024.json','GO_A3_C3_INFER_20261024_RUN2.json','GO_A3_COMPARE_20261024.json','RESULTS_ZH.md','run1_fits/fit_report_full.json','run1_fits/fit_report_time.json','run1_fits/fit_report_noRateUpdate.json','run1_fits/fit_report_noEll.json','run1_fits/consumption_record.json','c3_eval_a3_20261024_run2/summary.json','c3_eval_a3_20261024_run2/receipt.json','same_key_compare_run1/summary.json','same_key_compare_run1/all_model_metrics.csv','same_key_compare_run1/paired_cell_bootstrap.csv','same_key_compare_run1/per_cell_metrics.csv','same_key_compare_run1/schema.json','same_key_compare_run1/receipt.json','full_vs_time_paired.json'])
    chosen.add('experiments/state/consumed_gos.jsonl')
    chosen.add('experiments/multirate_state_A3_rate_20261024/R2_DATA_EFFICIENCY_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/a3_train_frac.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/README_A3_FRAC_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_FRAC_F25_20261024_RUN1.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_FRAC_F50_20261024_RUN1.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_FRAC_INFER_F25_20261024_RUN1.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_FRAC_INFER_F50_20261024_RUN1.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_DATA_EFFICIENCY_20261024.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/data_efficiency_compare_run1/all_model_metrics.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/data_efficiency_compare_run1/summary.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/data_efficiency_compare_run1/receipt.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/c3_eval_frac_f25_20261024/receipt.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/c3_eval_frac_f50_20261024/receipt.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/run_frac_f25_seed42/fit_report_full.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/run_frac_f50_seed42/fit_report_full.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/run_frac_f25_seed42/consumption_record.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/run_frac_f50_seed42/consumption_record.json')
    chosen.add('experiments/multirate_state_A2_20261022/a2_train_v3.py')
    chosen.add('experiments/multirate_state_A2_20261022/GO_A2_V3_BURNIN_FIX_20261024.json')
    chosen.add('experiments/multirate_state_A2_20261022/GO_A2V3_C3_INFER_20261024.json')
    chosen.add('experiments/multirate_state_A2_20261022/GO_A2V3_COMPARE_20261024.json')
    chosen.add('experiments/multirate_state_A2_20261022/compare_v3.py')
    chosen.add('experiments/multirate_state_A2_20261022/same_key_compare_v3_run1/all_model_metrics.csv')
    chosen.add('experiments/multirate_state_A2_20261022/same_key_compare_v3_run1/summary.json')
    chosen.add('experiments/multirate_state_A2_20261022/same_key_compare_v3_run1/receipt.json')
    chosen.add('experiments/multirate_state_A2_fullrefit_20261023/c3_eval_v3_20261024/receipt.json')
    chosen.add('experiments/multirate_state_A2_fullrefit_20261023/runs/a2v3_burnin_20261024/fit_report_full.json')
    chosen.add('experiments/multirate_state_A2_fullrefit_20261023/runs/a2v3_burnin_20261024/fit_report_time.json')
    chosen.add('experiments/multirate_state_A2_fullrefit_20261023/runs/a2v3_burnin_20261024/fit_report_noRPTupdate.json')
    chosen.add('docs/RESEARCH_GOAL_COMPETITIVE_20261024_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/E5_ENSEMBLE_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/compare_ens.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_ENSEMBLE_20261024.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ensemble_compare_run1/all_model_metrics.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ensemble_compare_run1/paired_cell_bootstrap.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ensemble_compare_run1/receipt.json')
    chosen.add('paper/multisource_dynamic_rul_20261021/FULL_DRAFT_V1.md')
    chosen.add('paper/multisource_dynamic_rul_20261021/PAPER_POSITIONING_ZH.md')
    chosen.add('paper/multisource_dynamic_rul_20261021/TABLES.md')
    chosen.add('paper/multisource_dynamic_rul_20261021/TABLES_manifest.json')
    chosen.add('paper/multisource_dynamic_rul_20261021/figures/figs_manifest.json')
    legacy8=ROOT/'reports/legacy_stage8_lossless_results_zh_20261024_root'
    chosen.difference_update(json.loads((legacy8/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_stage8_lossless_results_zh_20261024_root/archive.bin')
    chosen.update('reports/legacy_stage8_lossless_results_zh_20261024_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    chosen.add('experiments/multirate_state_A3_rate_20261024/R3_SCHEDULE_VALUE_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/V1_EXT_BASELINES_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/V3_CALIBRATION_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/V4_SEED_ROBUSTNESS_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/tree_frac.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/schedule_eval.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/a3_calibrate.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/compare_deg.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/compare_ext.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/compare_s43.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/cells_f25.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/cells_f50.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_FIT_SEED43_20261024.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_SEED43_C3_INFER_20261024.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_SEED43_COMPARE_20261024.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_TREE_FRAC_20261024_RUN3.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_A3_CALIBRATE_20261024_RUN2.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/GO_EXT_COMPARE_20261024.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/seed43_compare_run1/all_model_metrics.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/seed43_compare_run1/summary.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/degradation_curve_compare_run1/all_model_metrics.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/degradation_curve_compare_run1/summary.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_compare_run1/all_model_metrics.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_compare_run1/summary.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/run_schedule_eval_20261024/policy_table.csv')
    chosen.add('experiments/multirate_state_A3_rate_20261024/run_schedule_eval_20261024/schedule_summary.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/ext_baselines.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/a3_calibrate.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/README_EXT_BASELINES_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/README_A3_CALIBRATE_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/GO_EXT_BASELINES_20261024_RUN2.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/GO_A3_CALIBRATE_20261024_RUN2.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/runs/ext_run2_20261024/fit_report.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/receipts/EXT_BASELINES_20261024_RUN2_receipt.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/ext_baselines/receipts/A3_CALIBRATE_20261024_RUN2_receipt.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/receipts/A3_SEED43_ROBUSTNESS_20261024_RUN1_receipt.json')
    chosen.add('experiments/multirate_state_A3_rate_20261024/receipts/A3_VS_TREE_DEGRADATION_CURVE_20261024_RUN1_receipt.json')
    legacy7=ROOT/'reports/legacy_stage7_lossless_misc_tables_20261024_root'
    chosen.difference_update(json.loads((legacy7/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_stage7_lossless_misc_tables_20261024_root/archive.bin')
    chosen.update('reports/legacy_stage7_lossless_misc_tables_20261024_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    legacy6=ROOT/'reports/legacy_stage6_lossless_metric_tables_20261024_root'
    chosen.difference_update(json.loads((legacy6/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_stage6_lossless_metric_tables_20261024_root/archive.bin')
    chosen.update('reports/legacy_stage6_lossless_metric_tables_20261024_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    legacy5=ROOT/'reports/legacy_stage5_lossless_saved_metrics_20261024_root'
    chosen.difference_update(json.loads((legacy5/'paths.json').read_text()))
    BINARY_PREDICTION_ARCHIVES.add('reports/legacy_stage5_lossless_saved_metrics_20261024_root/archive.bin')
    chosen.update('reports/legacy_stage5_lossless_saved_metrics_20261024_root/'+n for n in ['archive.bin','validation.json','decode.py','README.md'])
    chosen.add('docs/INDEPENDENT_REVIEW_B2_A2_20261022.md')
    chosen.add('docs/ZCODE_CONTINUATION_20261024.json')
    chosen.add('docs/RESEARCH_GOAL_WIN_20261025_ZH.md')
    chosen.add('paper/multisource_dynamic_rul_20261021/COMPARISON_TABLE_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/V3_CALIBRATION_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/E5_ENSEMBLE_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/E6_THREE_SEED_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/E7_CALCE_ZEROSHOT_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/E8_C4_CONFIRM_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/hybrid/W1_HYB_ENSEMBLE_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/hybrid/hybrid_aug.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/hybrid/README_HYBRID_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/a3t/a3t_model.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/a3t/a3t_train.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/a3t/a3t_infer.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/a3t/README_A3T_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/calce_zero_shot/calce_zero_shot.py')
    chosen.add('experiments/multirate_state_A3_rate_20261024/calce_zero_shot/README_CALCE_ZH_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/calce_scout/CALCE_FEASIBILITY_ZH.md')
    chosen.add('experiments/multirate_state_A3_rate_20261024/tree_frac.py')
    chosen.add('experiments/multirate_state_A2_20261022/a2_train_v3.py')
    chosen.add('experiments/multirate_state_A2_20261022/GO_A2_V3_BURNIN_FIX_20261024.json')
    chosen.add('experiments/multirate_state_A2_20261022/same_key_compare_v3_run1/all_model_metrics.csv')
    b2='experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2/'
    chosen.update(b2+n for n in ['PROTOCOL_V2.md','model.py','target_builder.py','prep_runner.py','fit_runner.py','rollout.py','synthetic_check.py','infer_runner.py','eval_rul_compare.py','eval_nextjump.py'])

    chosen.discard('experiments/multirate_state_A2_20261022/c3_eval_v2_20261022/summary.json')
    chosen.update('experiments/trajectory_b2_joint_marked_renewal_20261021/candidate_v2/'+n for n in ['GO_PREP_V2_1.json','GO_FIT4_V2_1B.json','GO_C3_INFER_20261022T1005Z.json','GO_B2_RUL_COMPARE_20261022T1950Z.json','receipts/prep-v2_1-20261022T0545Z.json','receipts/fit4-20261022T0600Z.json','receipts/c3infer-20261022T1005Z.json','receipts/b2_rul_compare_20261022T1950Z_receipt.json'])
    legacy8_late = ROOT/'reports/legacy_stage8_lossless_results_zh_20261024_root'
    chosen.difference_update(json.loads((legacy8_late/'paths.json').read_text()))


    # 2026-10-26: RUL recovery allowlist; no raw payload, weights, or controller state.
    chosen.add('docs/RUL_TIME_RECOVERY_PLAN_20261026_ZH.md')
    chosen.update('experiments/rul_time_recovery_20261026/'+n for n in ['runner.py', 'p2_diagnostic.py', 'p2_clock.py', 'P2_CLOCK_PROTOCOL_ZH.md', 'INVALID_EVIDENCE_AUDIT.json', 'P1_RESULTS_ZH.md', 'P1_DECISION.json', 'P2_RESULTS_ZH.md', 'P2_DECISION.json', 'GO_P1_RUN1.json', 'GO_P2_DIAG_RUN1.json', 'GO_P2_CLOCK_RUN1.json', 'p1_run1/receipt.json', 'p1_run1/point_summary.csv', 'p1_run1/distribution_summary.csv', 'p1_run1/paired_per_cell.csv', 'p1_run1/independent_recompute.json', 'p2_diag_run1/receipt.json', 'p2_diag_run1/train_oof_error_bins.csv', 'p2_diag_run1/train_oof_correlations.csv', 'p2_diag_run1/PR_summary.csv', 'p2_diag_run1/PR_per_cell.csv', 'p2_clock_run1/receipt.json', 'p2_clock_run1/point_summary.csv', 'p2_clock_run1/distribution_summary.csv', 'p2_clock_run1/paired_per_cell.csv', 'p2_clock_run1/independent_contrasts.json'])

    # Lossless recovery per-cell tables, verified by byte SHA256.
    chosen.difference_update(['experiments/rul_time_recovery_20261026/p1_run1/paired_per_cell.csv', 'experiments/rul_time_recovery_20261026/p1_run1/distribution_per_cell.csv', 'experiments/rul_time_recovery_20261026/p2_diag_run1/PR_per_cell.csv', 'experiments/rul_time_recovery_20261026/p2_clock_run1/paired_per_cell.csv', 'experiments/rul_time_recovery_20261026/p2_clock_run1/distribution_per_cell.csv'])
    BINARY_PREDICTION_ARCHIVES.add('experiments/rul_time_recovery_20261026/public_per_cell_v1/archive.bin')
    chosen.update('experiments/rul_time_recovery_20261026/public_per_cell_v1/'+n for n in ['archive.bin', 'validation.json', 'decode.py', 'README.md'])

    # LZMA replaces v1 DEFLATE archive without losing any source table bytes.
    chosen.difference_update(['experiments/rul_time_recovery_20261026/public_per_cell_v1/archive.bin', 'experiments/rul_time_recovery_20261026/public_per_cell_v1/validation.json', 'experiments/rul_time_recovery_20261026/public_per_cell_v1/decode.py', 'experiments/rul_time_recovery_20261026/public_per_cell_v1/README.md'])
    BINARY_PREDICTION_ARCHIVES.add('experiments/rul_time_recovery_20261026/public_per_cell_v2/archive.bin')
    chosen.update('experiments/rul_time_recovery_20261026/public_per_cell_v2/'+n for n in ['archive.bin', 'validation.json', 'decode.py', 'README.md'])

    # Final lossless evidence package also includes verbose independent recomputes.
    chosen.difference_update(['experiments/rul_time_recovery_20261026/public_per_cell_v2/archive.bin', 'experiments/rul_time_recovery_20261026/public_per_cell_v2/validation.json', 'experiments/rul_time_recovery_20261026/public_per_cell_v2/decode.py', 'experiments/rul_time_recovery_20261026/public_per_cell_v2/README.md', 'experiments/rul_time_recovery_20261026/p1_run1/independent_recompute.json', 'experiments/rul_time_recovery_20261026/p2_clock_run1/independent_contrasts.json'])
    BINARY_PREDICTION_ARCHIVES.add('experiments/rul_time_recovery_20261026/public_per_cell_v3/archive.bin')
    chosen.update('experiments/rul_time_recovery_20261026/public_per_cell_v3/'+n for n in ['archive.bin', 'validation.json', 'decode.py', 'README.md'])

    # 2026-10-27 P3 results and lossless capacity-source compaction.
    chosen.difference_update(['experiments/multirate_state_A3_rate_20261024/a3_fixtures.py', 'experiments/multirate_state_A3_rate_20261024/a3_infer.py', 'experiments/multirate_state_A3_rate_20261024/a3_model.py', 'experiments/multirate_state_A3_rate_20261024/a3_train_frac.py', 'experiments/multirate_state_A3_rate_20261024/a3t/a3t_infer.py', 'experiments/multirate_state_A3_rate_20261024/calce_zero_shot/calce_zero_shot.py', 'experiments/multirate_state_A3_rate_20261024/ext_baselines/a3_calibrate.py', 'experiments/multirate_state_A3_rate_20261024/ext_baselines/ext_baselines.py', 'experiments/multirate_state_A3_rate_20261024/hybrid/hybrid_aug.py', 'experiments/multirate_state_A3_rate_20261024/schedule_eval.py', 'experiments/multirate_state_A3_rate_20261024/tree_frac.py'])
    chosen.update('experiments/rul_time_recovery_20261026/'+n for n in ['p3_calibration.py', 'P3_CALIBRATION_PROTOCOL_ZH.md', 'p3_peer.py', 'P3_PEER_PROTOCOL_ZH.md', 'P3_RESULTS_ZH.md', 'P3_DECISION.json', 'P4_HISTORY_PLAN_ZH.md', 'GO_P3_CALIBRATION_RUN1.json', 'GO_P3_PEER_RUN1.json', 'p3_calibration_run1/receipt.json', 'p3_calibration_run1/point_summary.csv', 'p3_calibration_run1/distribution_summary.csv', 'p3_peer_run1/receipt.json', 'p3_peer_run1/point_summary.csv', 'p3_peer_run1/distribution_summary.csv'])
    BINARY_PREDICTION_ARCHIVES.add('reports/rul_recovery_legacy_capacity_code_20261027/archive.bin')
    chosen.update('reports/rul_recovery_legacy_capacity_code_20261027/'+n for n in ['archive.bin', 'validation.json', 'decode.py', 'README.md'])
    BINARY_PREDICTION_ARCHIVES.add('experiments/rul_time_recovery_20261026/public_p3_evidence_v1/archive.bin')
    chosen.update('experiments/rul_time_recovery_20261026/public_p3_evidence_v1/'+n for n in ['archive.bin', 'validation.json', 'decode.py', 'README.md'])

    chosen.update('experiments/rul_time_recovery_20261026/'+n for n in ['p3_compare.py','GO_P3_COMPARE_RUN1.json'])
    # RULaaS fixed-model information gate; exact public evidence only.
    chosen.update('experiments/rulaas_value_gate_20261029/'+n for n in ['value_gate.py','PLAN_ZH.md','GO_RUN02.json','run02/RESULTS.md','run02/RESULTS_ZH.md','run02/summary.csv','run02/per_cell.csv','run02/paired_bootstrap.csv','run02/information_access.csv','run02/event_episodes.csv','run02/decision.json','run02/INDEPENDENT_RECOMPUTE.json','run02/excluded_cells.json'])
    chosen.update('experiments/rul_time_recovery_20261026/'+n for n in ['P4_RESULTS_ZH.md','P4_DECISION.json','p4_history.py','p4_history_run_20261027T1610Z/point_summary.csv','p4_history_run_20261027T1610Z/paired_bootstrap.csv','M2_RESULTS_ZH.md','M2_DECISION.json','P2_DIAGNOSIS_ZH.md'])
    # Finite recorded-window station pilot: summaries, executable source and explicit limits.
    chosen.update('experiments/rulaas_station_admission_20261029/'+n for n in ['run.py','review_saved_v2.py','PROTOCOL_ZH.md','GO_RUN01.json','METHOD_CONFLICT_CHECK_ZH.md','NEXT_GAIN_IDENTIFIABILITY_PLAN_ZH.md','run01/RESULTS_ZH.md','run01/summary.csv','run01/ROOT_DECISION.json','run01/INDEPENDENT_RECOMPUTE.json','run01/train_only_thresholds.json','run01/public_receipt.json'])
    chosen.update('experiments/rulaas_value_gate_20261029/'+n for n in ['support_timing_diagnosis.py','run02/SUPPORT_AND_TIMING_DIAGNOSIS.json','NEXT_STAGE_PROTOCOL_ZH.md'])
    contents, files, skipped, binary_blobs = {}, [], [], {}
    mapping = {'README.md': 'docs/GITHUB_README_ZH.md', 'agent.md': 'AGENTS.md'}
    mapping.update({rel: rel for rel in sorted(chosen)})
    for public_path, source_path in sorted(mapping.items()):
        path = ROOT / source_path
        if path.is_symlink() or not path.is_file():
            skipped.append({'path': source_path, 'reason': 'missing_or_symlink'})
            continue
        if not path.resolve().is_relative_to(ROOT):
            raise RuntimeError('Outside project: ' + source_path)
        if path.name.startswith('reading_part_') or (path.suffix.lower() not in EXT and source_path not in BINARY_PREDICTION_ARCHIVES) or '__pycache__' in path.parts or path.stat().st_size > 2000000:
            skipped.append({'path': source_path, 'reason': 'not_small_allowlisted_text'})
            continue
        raw = path.read_bytes()
        if source_path in BINARY_PREDICTION_ARCHIVES:
            # Only the two explicitly reviewed prediction archives are eligible.
            binary_blobs[public_path] = base64.b64encode(raw).decode('ascii')
            files.append({'path': public_path, 'source_path': source_path, 'bytes': len(raw),
                          'sha256': hashlib.sha256(raw).hexdigest()})
            continue
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            skipped.append({'path': source_path, 'reason': 'not_utf8'})
            continue
        if SECRET.search(text):
            raise RuntimeError('Possible credential in allowlist; not exported: ' + source_path)
        contents[public_path] = text
        files.append({'path': public_path, 'source_path': source_path, 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest()})
    if sum(x['bytes'] for x in files) > 12 * 1024 * 1024:
        raise RuntimeError('Snapshot exceeds 12MiB; narrow before publishing')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    OUT.mkdir(exist_ok=True)
    manifest_path = OUT / 'public_snapshot.json'
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    observed = old.get('snapshot_utc') if old.get('content_sha256') == digest else datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest = {'schema_version': 1, 'repository': 'enterzxk/battery-dynamic-rul',
                'snapshot_utc': observed, 'content_sha256': digest, 'file_count': len(files),
                'files': files, 'excluded_scope': ['raw battery data', 'checkpoints', 'paper fulltexts',
                'third-party repos', 'credentials', 'raw controller logs and model sessions'],
                'skipped_candidates': skipped,
                'note': 'Original scientific files retain their byte hashes; absent server references are not public evidence.'}
    contents['public_snapshot.json'] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    manifest_path.write_text(contents['public_snapshot.json'], encoding='utf-8')
    elements = [{'path': path, 'mode': '100644', 'type': 'blob', 'content': text} for path, text in sorted(contents.items())]
    bundle = {'repository_full_name': 'enterzxk/battery-dynamic-rul', 'content_sha256': digest,
              'snapshot_utc': observed, 'tree_elements': elements, 'binary_blobs': binary_blobs}
    bundle_path = OUT / 'bundle.json'
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'bundle_path': str(bundle_path), 'file_count': len(elements),
                      'source_bytes': sum(x['bytes'] for x in files), 'content_sha256': digest,
                      'snapshot_utc': observed, 'skipped_count': len(skipped)}))


