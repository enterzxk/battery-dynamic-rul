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
    chosen.add('reports/p1_cpmlp_recipe_review_20261018_luna/review.json')
    for name in ['runner.py', 'config.json', 'ROOT_GO.json', 'stopping_check.json', 'deadline_boundary_check.json', 'failure_receipt.json', 'launch_receipt.json']:
        chosen.add('experiments/cpmlp_hust_recipe_adapt_seed42_v1/' + name)
    for name in ['runner.py', 'config.json', 'ROOT_GO.json', 'runtime_repair_review.json', 'completion_receipt.json', 'launch_receipt.json', 'run_manifest.json', 'epoch_metrics.jsonl', 'budget_ledger.jsonl', 'independent_metrics.json', 'root_result_decision.json', 'RESULTS_ZH.md', 'independent_metric_recompute.py', 'validation_predictions_epoch_003.csv']:
        chosen.add('experiments/cpmlp_hust_recipe_adapt_seed42_v2/' + name)
    for run in (ROOT / 'experiments').glob('*/fit_runs/*'):
        chosen.update(str(p.relative_to(ROOT)) for p in run.iterdir() if p.is_file())

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
