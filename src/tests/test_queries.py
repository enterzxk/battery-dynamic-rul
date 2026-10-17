import copy
import unittest
from rul_benchmark.queries import EOLRule, build_queries, exact_evaluation_row

class QueryContractTests(unittest.TestCase):
    def rows(self, capacities, offset=0):
        return [{'row_position_1based':i, 'actual_cycle_number':i+offset, 'capacity_Ah':x}
                for i,x in enumerate(capacities,1)]

    def build(self, capacities, grid, *, offset=0, space='actual_cycle_number', rule=None):
        return build_queries(self.rows(capacities,offset),grid,
            rule=rule or EOLRule('nominal',1.1),cycle_index_space=space,
            label_source_sha256='a'*64,future_policy_id='realized_lab_protocol_not_oracle')

    def test_offset_index_spaces_and_mixed_rejection(self):
        by_actual=self.build([1.1,1.0,.87],[3,4,5],offset=2)
        by_row=self.build([1.1,1.0,.87],[1,2,3],offset=2,space='row_position_1based')
        self.assertEqual(by_actual['observed_eol_cycle'],5)
        self.assertEqual(by_row['observed_eol_cycle'],3)
        self.assertEqual(by_actual['queries'][1]['label_metadata']['true_rul_cycles'],1)
        self.assertEqual(by_row['queries'][1]['label_metadata']['true_rul_cycles'],1)
        mixed=copy.deepcopy(by_actual['queries'][1])
        mixed['label_metadata']['eol_index_space']='row_position_1based'
        with self.assertRaisesRegex(ValueError,'Mixed'):
            exact_evaluation_row(mixed,1,physical_cell_id='A',source_cell_id='aliasA',dataset='HUST',role='test')

    def test_nominal_and_first_observed_denominators_are_separate(self):
        nominal=self.build([1.20,1.10,.95,.90],[1,2,3,4])
        first=self.build([1.20,1.10,.95,.90],[1,2,3,4],rule=EOLRule('first_observed_cycle'))
        self.assertEqual(nominal['label_status'],'right_censored')
        self.assertIsNone(nominal['observed_eol_cycle'])
        self.assertEqual(first['observed_eol_cycle'],3)
        self.assertNotEqual(nominal['eol_definition_id'],first['eol_definition_id'])
        last=nominal['queries'][-1]
        self.assertIsNone(last['label_metadata']['true_rul_cycles'])
        self.assertEqual(last['label_metadata']['rul_lower_bound_cycles'],0)
        with self.assertRaisesRegex(ValueError,'censored'):
            exact_evaluation_row(last,0,physical_cell_id='A',source_cell_id='aliasA',dataset='HUST',role='test')
        extrap=copy.deepcopy(first['queries'][0])
        extrap['label_metadata']['label_status']='extrapolated'
        with self.assertRaisesRegex(ValueError,'Extrapolated'):
            exact_evaluation_row(extrap,2,physical_cell_id='A',source_cell_id='aliasA',dataset='HUST',role='test')

    def test_post_query_change_does_not_change_features(self):
        a=self.build([1.1,1.0,.95,.90,.87],[1,2,3,4])
        b=self.build([1.1,1.0,.95,.70,.60],[1,2,3,4])
        self.assertEqual(a['queries'][1]['features'],b['queries'][1]['features'])
        self.assertNotEqual(a['queries'][1]['label_metadata']['true_rul_cycles'],
                            b['queries'][1]['label_metadata']['true_rul_cycles'])
        self.assertEqual(a['queries'][1]['features']['normalization']['fit_cell_ids'],[])

    def test_gaps_future_grid_and_at_risk_filter(self):
        rows=self.rows([1.1,1.0,.87])
        rows[1]['actual_cycle_number']=3;rows[2]['actual_cycle_number']=5
        r=build_queries(rows,[1,2,3,5,100],rule=EOLRule('nominal',1.1),
            cycle_index_space='actual_cycle_number',label_source_sha256='b'*64,future_policy_id='fixed_reference')
        self.assertEqual([q['features']['query_cycle'] for q in r['queries']],[1,3])
        self.assertEqual(r['queries'][1]['label_metadata']['true_rul_cycles'],2)
        self.assertEqual(len(r['omitted_queries']),3)
        with self.assertRaisesRegex(ValueError,'Explicit supported'):
            self.build([1.1,.8],[1],space='unknown')
        with self.assertRaises(ValueError):
            self.build([1.1,.8],[1,1])
        with self.assertRaises(ValueError):
            self.build([1.1,float('nan')],[1])

if __name__=='__main__':unittest.main()
