"""Export an allowlisted text snapshot; no model/data execution or network IO."""
import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('/home/yndx/zxk/rul')
OUT = ROOT / 'automation/github_export'
EXT = {'.py', '.md', '.json', '.jsonl', '.csv', '.yaml', '.yml', '.sha256'}
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|https?://[^\s/:]+:[^\s/@]+@)')


def main():
    chosen = {'AGENTS.md', 'PROJECT_PROGRESS.md', 'automation/bin/export_github_context.py'}
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

    contents, files, skipped = {}, [], []
    mapping = {'README.md': 'docs/GITHUB_README_ZH.md', 'agent.md': 'AGENTS.md'}
    mapping.update({rel: rel for rel in sorted(chosen)})
    for public_path, source_path in sorted(mapping.items()):
        path = ROOT / source_path
        if path.is_symlink() or not path.is_file():
            skipped.append({'path': source_path, 'reason': 'missing_or_symlink'})
            continue
        if not path.resolve().is_relative_to(ROOT):
            raise RuntimeError('Outside project: ' + source_path)
        if path.name.startswith('reading_part_') or path.suffix.lower() not in EXT or '__pycache__' in path.parts or path.stat().st_size > 2000000:
            skipped.append({'path': source_path, 'reason': 'not_small_allowlisted_text'})
            continue
        raw = path.read_bytes()
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
              'snapshot_utc': observed, 'tree_elements': elements}
    bundle_path = OUT / 'bundle.json'
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'bundle_path': str(bundle_path), 'file_count': len(elements),
                      'source_bytes': sum(x['bytes'] for x in files), 'content_sha256': digest,
                      'snapshot_utc': observed, 'skipped_count': len(skipped)}))


if __name__ == '__main__':
    main()
