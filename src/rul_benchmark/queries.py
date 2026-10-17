"""动态查询与标签契约：观测EOL、截尾、索引空间和前缀可见性。
这里不拟合模型。标签离线使用完整轨迹；features 只包含查询时可见前缀。
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Optional

SPACES = {'row_position_1based', 'actual_cycle_number'}

def positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(name + ' must be a positive integer')
    return value

def number(value, name):
    if isinstance(value, bool):
        raise ValueError(name + ' cannot be boolean')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(name + ' must be finite')
    return value

@dataclass(frozen=True)
class EOLRule:
    reference_kind: str
    nominal_capacity_Ah: Optional[float] = None
    fraction: float = 0.8
    soc_window_width: float = 1.0
    crossing_rule: str = 'first_at_or_below'

    def validate(self):
        if self.reference_kind not in {'nominal', 'first_observed_cycle'}:
            raise ValueError('Unsupported capacity denominator')
        if not 0 < number(self.fraction, 'fraction') < 1:
            raise ValueError('fraction must be in (0,1)')
        if not 0 < number(self.soc_window_width, 'soc_window_width') <= 1:
            raise ValueError('soc_window_width must be in (0,1]')
        if self.crossing_rule != 'first_at_or_below':
            raise ValueError('Crossing rule must be declared; no implicit smoothing')
        if self.reference_kind == 'nominal':
            if self.nominal_capacity_Ah is None or number(self.nominal_capacity_Ah, 'nominal_capacity_Ah') <= 0:
                raise ValueError('Known nominal capacity is required')
        elif self.nominal_capacity_Ah is not None:
            raise ValueError('Do not mix nominal and first-observed capacity definitions')

    @property
    def definition_id(self):
        self.validate()
        raw = json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()
        return 'eol-' + hashlib.sha256(raw).hexdigest()[:20]

def validate_cycles(cycles):
    if not cycles:
        raise ValueError('Empty trajectory')
    result = []
    previous_cycle = None
    for i, row in enumerate(cycles, 1):
        position = positive_integer(row['row_position_1based'], 'row_position_1based')
        actual = positive_integer(row['actual_cycle_number'], 'actual_cycle_number')
        capacity = number(row['capacity_Ah'], 'capacity_Ah')
        if position != i or (previous_cycle is not None and actual <= previous_cycle):
            raise ValueError('Rows must be contiguous and actual cycle numbers strictly increasing')
        if capacity < 0:
            raise ValueError('capacity_Ah cannot be negative')
        result.append({'row_position_1based': position, 'actual_cycle_number': actual, 'capacity_Ah': capacity})
        previous_cycle = actual
    return result

def build_queries(cycles, query_grid, *, rule, cycle_index_space,
                  label_source_sha256, future_policy_id,
                  policy_known_at_query=False):
    """query_grid是预先声明的绝对观测循环，不允许用总寿命百分比生成。
    返回的features不含EOL、末周期或未来工况；label_metadata只用于标签/审计。
    """
    if cycle_index_space not in SPACES:
        raise ValueError('Explicit supported cycle_index_space is required')
    if not isinstance(label_source_sha256, str) or len(label_source_sha256) != 64 or any(c not in '0123456789abcdef' for c in label_source_sha256):
        raise ValueError('label_source_sha256 is required')
    if not isinstance(future_policy_id, str) or not future_policy_id.strip():
        raise ValueError('Explicit future policy target interpretation is required')
    if not isinstance(policy_known_at_query, bool):
        raise ValueError('policy_known_at_query must be boolean')
    grid = list(query_grid)
    if not grid or grid != sorted(set(grid)):
        raise ValueError('query_grid must be nonempty, unique and sorted')
    for q in grid:
        positive_integer(q, 'query coordinate')
    rule.validate()
    rows = validate_cycles(cycles)
    reference = (number(rule.nominal_capacity_Ah, 'nominal_capacity_Ah') * number(rule.soc_window_width, 'soc_window_width')
                 if rule.reference_kind == 'nominal' else rows[0]['capacity_Ah'])
    if reference <= 0:
        raise ValueError('Reference capacity must be positive')
    threshold = reference * number(rule.fraction, 'fraction')
    crossing = next((r for r in rows if r['capacity_Ah'] <= threshold), None)
    eol = crossing[cycle_index_space] if crossing is not None else None
    last = rows[-1][cycle_index_space]
    coordinates = {r[cycle_index_space] for r in rows}
    queries, omitted = [], []
    for q in grid:
        if q not in coordinates:
            omitted.append({'query_cycle': q, 'reason': 'no_observation_at_prespecified_coordinate'})
            continue
        if eol is not None and q >= eol:
            omitted.append({'query_cycle': q, 'reason': 'at_or_after_observed_eol'})
            continue
        prefix = [r for r in rows if r[cycle_index_space] <= q]
        # 原始容量保持原单位；不使用完整轨迹最大值或held-out拟合归一化。
        features = {'query_cycle': q,
                    'observed_coordinates': [r[cycle_index_space] for r in prefix],
                    'capacity_Ah_history': [r['capacity_Ah'] for r in prefix],
                    'reference_capacity_Ah': reference,
                    'normalization': {'kind': 'none_raw_Ah', 'fit_roles': [], 'fit_cell_ids': []}}
        label = {'query_cycle': q, 'query_index_space': cycle_index_space,
                 'eol_index_space': cycle_index_space, 'eol_definition_id': rule.definition_id,
                 'capacity_reference_kind': rule.reference_kind, 'reference_capacity_Ah': reference,
                 'capacity_threshold_Ah': threshold, 'crossing_rule': rule.crossing_rule,
                 'label_source_sha256': label_source_sha256,
                 'future_policy_id': future_policy_id, 'policy_known_at_query': policy_known_at_query,
                 'label_status': 'observed_crossing' if eol is not None else 'right_censored',
                 'eol_cycle': eol, 'true_rul_cycles': eol-q if eol is not None else None,
                 'rul_lower_bound_cycles': None if eol is not None else last-q,
                 'last_observed_cycle': last}
        queries.append({'features': features, 'label_metadata': label})
    return {'eol_definition_id': rule.definition_id, 'rule': asdict(rule),
            'cycle_index_space': cycle_index_space,
            'label_status': 'observed_crossing' if eol is not None else 'right_censored',
            'observed_eol_cycle': eol, 'last_observed_cycle': last,
            'queries': queries, 'omitted_queries': omitted}

def exact_evaluation_row(query, prediction, *, physical_cell_id, source_cell_id, dataset, role):
    """只有相同索引空间下的实际观测crossing能进入精确RUL MAE。"""
    label = query['label_metadata']
    if label.get('label_status') != 'observed_crossing':
        raise ValueError('Extrapolated/censored endpoints cannot enter exact observed-RUL MAE')
    if label.get('query_index_space') not in SPACES or label.get('eol_index_space') != label['query_index_space']:
        raise ValueError('Mixed query/EOL coordinate spaces are forbidden')
    q = positive_integer(label['query_cycle'], 'query_cycle')
    eol = positive_integer(label['eol_cycle'], 'eol_cycle')
    if eol <= q or label['true_rul_cycles'] != eol-q:
        raise ValueError('Inconsistent exact observed endpoint')
    pred = number(prediction, 'prediction')
    if pred < 0:
        raise ValueError('Prediction cannot be negative')
    if not physical_cell_id or not source_cell_id or not dataset or role not in {'train','validation','calibration','test'}:
        raise ValueError('Explicit identity, dataset and role are required')
    return {'physical_cell_id': physical_cell_id, 'source_cell_id': source_cell_id, 'dataset': dataset, 'role': role,
            'query_cycle': q, 'true_rul_cycles': eol-q, 'pred_rul_cycles': pred,
            'label_status': 'observed_crossing', 'cycle_index_space': label['query_index_space'],
            'eol_definition_id': label['eol_definition_id'],
            'label_source_sha256': label['label_source_sha256'],
            'future_policy_id': label['future_policy_id']}
