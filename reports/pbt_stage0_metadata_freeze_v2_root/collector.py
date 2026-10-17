#!/usr/bin/env python3
"""Bounded read-only PBT stage-0 metadata collector. Python stdlib only."""
import csv
import hashlib
import json
import os
import sys
import signal
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/yndx/zxk/rul')
ROOT_FD = None
OUT = ROOT / 'reports/pbt_stage0_metadata_freeze_v2_root/metadata_receipt.json'
MAX_FILES = 7
MAX_FILE_BYTES = 65536
MAX_TOTAL_BYTES = 131072
MAX_WALL_SECONDS = 10.0
START = time.monotonic()
EXPECTED = {
    'data/processed/audit_only/PBT_seed42/args.json': '461d0cd4acaa2bd3edb0b330ca94eea1aadf9811cde94bd0b5f203272c9f6ed6',
    'configs/experiments/pbt_hust_zeroshot_seed42_draft.json': 'c96426d7484264ee9d00d7620b012d536e113a9c1f552a862aa8656279ac08c6',
    'reports/pbt_checkpoint_metadata_audit/zenodo_pbt_checkpoint_metadata.json': '88f4fe379bfab049f909f3695986aff4664933484e584aa8733cf848a0a164c6',
    'reports/pbt_validation_loader_candidate_v3/restricted_decode_receipt.json': 'f6f1507589aa9f14ec1506500c150c90e87592288ea3fc215103312bbcd68912',
    'reports/pbt_val_pairing_static_v1_luna/existing_view_join_v2/join_receipt.json': 'cce7afcb6fb86a17df0539ebf4b112a0b35d415b77ac2e20abe3db3841a71a68',
    'reports/pbt_val_pairing_static_v1_luna/existing_view_join_v2/hustval15_static_pairing.csv': '143710b7f7b664eb1ceb2a11c4213e9c5674a3c3de389e85132d54324afaa75d',
    'reports/data_same_version_staging/hust_v11_source_content_audit.json': 'b5292c7cf6893f94ef79c10de11631ebce7bee2cefb34bb8a716c411ba071810',
}
CELLS = [
    'HUST_6-8.pkl', 'HUST_3-8.pkl', 'HUST_2-3.pkl', 'HUST_9-1.pkl', 'HUST_10-8.pkl',
    'HUST_7-4.pkl', 'HUST_2-8.pkl', 'HUST_8-3.pkl', 'HUST_5-2.pkl', 'HUST_10-1.pkl',
    'HUST_5-5.pkl', 'HUST_5-7.pkl', 'HUST_7-8.pkl', 'HUST_7-6.pkl', 'HUST_1-8.pkl',
]
EFFECTIVE_FIELDS = [
    'args_path', 'model', 'dataset', 'data', 'root_path', 'data_path', 'eval_dataset',
    'batch_size', 'num_workers', 'seq_len', 'early_cycle_threshold', 'eval_cycle_min',
    'eval_cycle_max', 'LLM_path', 'wo_DKPrompt', 'd_llm', 'task_name', 'd_ff', 'patch_len',
    'stride', 'n_heads', 'charge_discharge_length', 'd_model', 'e_layers', 'd_layers',
    'dropout', 'activation', 'cathode_experts', 'temperature_experts', 'format_experts',
    'anode_experts', 'num_general_experts', 'num_views', 'down_sample_ratio', 'gate_d_ff',
    'dk_factor', 'pca_path', 'd_ff_scale_factor', 'num_experts', 'output_num', 'topK',
    'use_dff_scale', 'min_d_ff', 'other_loader_mask_config_fields',
]

class StopClosed(Exception):
    pass

def deadline():
    if time.monotonic() - START >= MAX_WALL_SECONDS:
        raise StopClosed('wall-time cap exceeded')

def open_dir_parts(base_fd, parts):
    fd = os.dup(base_fd)
    try:
        for component in parts:
            if component in ('', '.', '..') or '/' in component:
                raise StopClosed('invalid path component')
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_text(rel, expected_sha, total):
    parts = Path(rel).parts
    if Path(rel).is_absolute() or not parts or any(x in ('', '.', '..') for x in parts):
        raise StopClosed('invalid fixed relative path')
    if Path(rel).suffix.lower() not in ('.json', '.csv', '.txt'):
        raise StopClosed('unsupported text suffix')
    deadline()
    parent = open_dir_parts(ROOT_FD, parts[:-1])
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, 'rb') as stream:
        st = os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
            raise StopClosed('non-regular or oversized fixed input: ' + rel)
        if total + st.st_size > MAX_TOTAL_BYTES:
            raise StopClosed('aggregate byte cap exceeded before read')
        raw = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
    if (len(raw) != st.st_size or len(raw) > MAX_FILE_BYTES or
        (st.st_size, st.st_mtime_ns, st.st_ctime_ns) !=
        (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise StopClosed('input changed during bounded read: ' + rel)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha:
        raise StopClosed('pinned input SHA-256 mismatch: ' + rel)
    text = raw.decode('utf-8', errors='strict')
    deadline()
    return text, {'path': rel, 'bytes': len(raw), 'sha256': digest}, total + len(raw)

def write_receipt(encoded):
    if len(encoded) > 262144:
        raise StopClosed('output byte cap exceeded')
    parts = OUT.relative_to(ROOT).parts
    parent = open_dir_parts(ROOT_FD, parts[:-1])
    pending = '.metadata_receipt.pending'
    created = False
    try:
        deadline()
        try:
            os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise StopClosed('create-only final output already exists')
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        deadline()
        os.link(pending, parts[-1], src_dir_fd=parent, dst_dir_fd=parent,
                follow_symlinks=False)
    finally:
        if created:
            os.unlink(pending, dir_fd=parent)
        os.close(parent)

def field(value, provenance, missing=False, note=None):
    item = {'value': value, 'provenance': provenance, 'missing': bool(missing)}
    if note:
        item['note'] = note
    return item

def main():
    if len(EXPECTED) != MAX_FILES:
        raise StopClosed('internal whitelist count mismatch')
    texts = {}
    input_records = []
    total = 0
    for rel, sha in EXPECTED.items():
        text, record, total = read_text(rel, sha, total)
        texts[rel] = text
        input_records.append(record)
    if time.monotonic() - START > MAX_WALL_SECONDS:
        raise StopClosed('wall-time cap exceeded')

    args_path = 'data/processed/audit_only/PBT_seed42/args.json'
    draft_path = 'configs/experiments/pbt_hust_zeroshot_seed42_draft.json'
    meta_path = 'reports/pbt_checkpoint_metadata_audit/zenodo_pbt_checkpoint_metadata.json'
    receipt_path = 'reports/pbt_validation_loader_candidate_v3/restricted_decode_receipt.json'
    join_path = 'reports/pbt_val_pairing_static_v1_luna/existing_view_join_v2/join_receipt.json'
    csv_path = 'reports/pbt_val_pairing_static_v1_luna/existing_view_join_v2/hustval15_static_pairing.csv'
    cycle_audit_path = 'reports/data_same_version_staging/hust_v11_source_content_audit.json'
    parsed = {p: json.loads(texts[p]) for p in EXPECTED if p.endswith('.json')}
    args = parsed[args_path]
    draft = parsed[draft_path]
    meta = parsed[meta_path]
    decode = parsed[receipt_path]
    join = parsed[join_path]
    cycle_audit = parsed[cycle_audit_path]
    deadline()
    if any(not isinstance(v, dict) for v in parsed.values()):
        raise StopClosed('all fixed JSON roots must be objects')
    if not isinstance(draft.get('dataset'), dict):
        raise StopClosed('draft dataset must be an object')
    structure = decode.get('decoded_structure')
    if not isinstance(structure, dict):
        raise StopClosed('decoded_structure must be object')
    if any(type(structure.get(k)) is not int or structure[k] != v for k,v in
           [('hust_validation_covered_count',15),('hust_validation_target_count',15),
            ('hust_validation_missing_count',0)]):
        raise StopClosed('aggregate DKP count schema/value mismatch')
    coverage = join.get('dkp_receipt_aggregate_coverage')
    if not isinstance(coverage, dict) or coverage.get('receipt_omits_names') is not True or any(
        type(coverage.get(k)) is not int or coverage[k] != v
        for k,v in [('covered',15),('target',15),('missing',0)]):
        raise StopClosed('join aggregate schema/value mismatch')
    if not isinstance(cycle_audit.get('changed_member_restricted_audit'), dict):
        raise StopClosed('historical cycle audit schema mismatch')
    csv_rows = list(csv.DictReader(texts[csv_path].splitlines()))
    if any(not {'file_name','dkp_key_by_pinned_loader_rule','eol_label'}.issubset(r) or None in r or any(v is None for v in r.values()) for r in csv_rows):
        raise StopClosed('missing/extra/malformed pairing CSV columns')
    if len(csv_rows) != 15 or [r.get('file_name') for r in csv_rows] != CELLS:
        raise StopClosed('pairing CSV is not the frozen exact 15 rows/order')

    source = {r['path']: r for r in input_records}
    args_prov = {'path': args_path, 'sha256': source[args_path]['sha256'], 'role': 'checkpoint-declared args candidate; not active evaluator Namespace'}
    draft_prov = {'path': draft_path, 'sha256': source[draft_path]['sha256'], 'role': 'proposed validation draft; not active evaluator Namespace'}
    effective_missing = {
        key: field(None, [args_prov, draft_prov], True,
                   'active checkpoint args plus actual CLI overrides/run invocation are not evidenced by this whitelist')
        for key in EFFECTIVE_FIELDS
    }
    declared = {key: field(value, [args_prov], False, 'declared checkpoint/config candidate only') for key, value in args.items()}
    ds = draft.get('dataset', {})
    proposed_values = {
        'dataset.name': ds.get('name'),
        'dataset.release': ds.get('release'),
        'dataset.candidate_target_partition': ds.get('candidate_target_partition'),
        'dataset.candidate_validation_cells': ds.get('candidate_validation_cells'),
        'training_authorized': draft.get('training_authorized'),
        'inference_authorized': draft.get('inference_authorized'),
    }
    proposed = {key: field(value, [draft_prov], value is None, 'proposal only; not effective runtime value') for key, value in proposed_values.items()}
    proposed['eval_cycle_min'] = field(None, [draft_prov], True, 'no explicit active CLI value in draft')
    proposed['eval_cycle_max'] = field(None, [draft_prov], True, 'no explicit active CLI value in draft')

    dkp_source = {'path': receipt_path, 'sha256': source[receipt_path]['sha256'], 'role': 'prior aggregate restricted-decoder receipt'}
    join_source = {'path': join_path, 'sha256': source[join_path]['sha256'], 'role': 'prior static join receipt'}
    pairing_source = {'path': csv_path, 'sha256': source[csv_path]['sha256'], 'role': 'static pairing rows; loader-rule key candidate only'}
    cycle_source = {'path': cycle_audit_path, 'sha256': source[cycle_audit_path]['sha256'], 'role': 'prior bounded source audit; one-cell historical count only'}
    rows = []
    for row in csv_rows:
        name = row['file_name']
        loader_key = row.get('dkp_key_by_pinned_loader_rule', '')
        rows.append({
            'cell': name,
            'dkp_key_exact_observed': field(None, [dkp_source, join_source, pairing_source], True,
                'aggregate coverage does not expose per-cell key; CSV loader-rule string is a derived candidate, not key-presence evidence'),
            'dkp_loader_rule_key_candidate': field(loader_key or None, [pairing_source], not bool(loader_key),
                'derived by pinned filename rule; does not prove the key exists in embedding mapping'),
            'valid_cycle_number': field(None, [join_source, cycle_source], True,
                'no exact per-cell data-loader length field in the bounded metadata inputs'),
            'prior_reported_cycle_count': field(None, [cycle_source], True,
                'no matching per-cell prior count in this audit; do not fill from label EOL or filename'),
            'declared_label_eol': field(row.get('eol_label') or None, [pairing_source], not bool(row.get('eol_label')),
                'label metadata only; not cycle_data length or runtime eligibility'),
        })
    one = cycle_audit.get('changed_member_restricted_audit', {})
    member = one.get('member')
    if member == 'HUST/HUST_1-8.pkl' and one.get('cycle_count') == 2285:
        target = next(r for r in rows if r['cell'] == 'HUST_1-8.pkl')
        target['prior_reported_cycle_count'] = field(2285, [cycle_source], False,
            'historical bounded restricted audit reported cycle_count=2285 for this member; not a new read and not an active loader runtime receipt')

    output = {
        'artifact': 'pbt_stage0_metadata_freeze_v2_root',
        'status': 'METADATA_ONLY_RECEIPT_STAGE0',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'input_scope': {'files': len(input_records), 'total_bytes': total, 'max_files': MAX_FILES,
                        'max_file_bytes': MAX_FILE_BYTES, 'max_total_bytes': MAX_TOTAL_BYTES,
                        'wall_seconds_cap': MAX_WALL_SECONDS, 'format_allowlist': ['UTF-8 JSON', 'UTF-8 CSV', 'UTF-8 TXT']},
        'input_sha256': input_records,
        'checkpoint_declared_args_candidate': declared,
        'proposed_validation_config': proposed,
        'effective_evaluator_namespace': effective_missing,
        'aggregate_dkp_evidence': {
            'value': decode.get('decoded_structure', {}).get('hust_validation_covered_count'),
            'target': decode.get('decoded_structure', {}).get('hust_validation_target_count'),
            'provenance': [dkp_source], 'missing': False,
            'limit': 'aggregate count only; exact 15 per-cell key identities/presence absent',
        },
        'static_join_dkp_receipt': field(join.get('dkp_receipt_aggregate_coverage'), [join_source], False,
                                         'receipt explicitly omits names and exact per-cell join is not provable'),
        'cells': rows,
        'execution_gates': {k: False for k in ['data_decode', 'model_construction', 'strict_load', 'forward', 'metrics', 'training', 'test_access']},
        'execution_counts': {k: 0 for k in ['binary_reads', 'new_decode', 'project_imports', 'model_construction', 'strict_load', 'forward', 'metrics', 'new_fits', 'optimizer_steps', 'test']},
        'stop_reasons': [],
    }
    deadline()
    encoded = (json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    deadline()
    write_receipt(encoded)
    print(json.dumps({'status': output['status'], 'output': str(OUT), 'sha256': hashlib.sha256(encoded).hexdigest(),
                      'input_files': len(input_records), 'input_bytes': total,
                      'elapsed_seconds': round(time.monotonic() - START, 4)}, ensure_ascii=False))

if __name__ == '__main__':
    try:
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, MAX_WALL_SECONDS)
        slash = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            ROOT_FD = open_dir_parts(slash, ROOT.parts[1:])
        finally:
            os.close(slash)
        main()
    except (StopClosed, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, csv.Error) as exc:
        print(json.dumps({'status': 'STOP_CLOSED', 'reason': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)

    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if ROOT_FD is not None:
            os.close(ROOT_FD)
