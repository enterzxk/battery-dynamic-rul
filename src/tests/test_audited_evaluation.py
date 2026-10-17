import copy,json,pathlib,subprocess,sys,unittest
from rul_benchmark.audited import evaluate_audited,validate_against_manifest,cell_bootstrap_mae
def rows():
    labels=dict(label_status="observed_crossing",eol_definition_id="fixture_nominal_80pct",cycle_index_space="actual_cycle_number",future_policy_id="fixture_realized",label_source_sha256="a"*64)
    return [dict(physical_cell_id="a",source_cell_id="source_a",dataset="fixture_only",role="test",query_cycle=10,true_rul_cycles=90,pred_rul_cycles=100,aging_condition="fixture",**labels),dict(physical_cell_id="b",source_cell_id="source_b",dataset="fixture_only",role="test",query_cycle=10,true_rul_cycles=190,pred_rul_cycles=190,aging_condition="fixture",**labels)]
def manifest():
    return {"cells":[dict(physical_cell_id="a",source_cell_id="source_a",dataset="fixture_only",role="test",identity_audit="verified"),dict(physical_cell_id="b",source_cell_id="source_b",dataset="fixture_only",role="test",identity_audit="verified")]}
def protocol(**updates):
    p=dict(evaluation_target="exact_observed_rul",eol_definition_id="fixture_nominal_80pct",cycle_index_space="actual_cycle_number",future_policy_id="fixture_realized",label_source_sha256_allowlist=["a"*64],query_grid=[10],query_grid_frozen_before_test=True)
    p.update(updates)
    return p
class AuditedEvaluationTest(unittest.TestCase):
    def test_train_alias_for_test_cell_is_rejected(self):
        m=manifest();m["cells"].append(dict(physical_cell_id="a",source_cell_id="different_name",dataset="other_source",role="train",identity_audit="verified"))
        with self.assertRaises(ValueError):validate_against_manifest(rows(),m)
    def test_unknown_or_conflicting_source_identity_is_rejected(self):
        r=rows();r[0]["source_cell_id"]="not_audited"
        with self.assertRaises(ValueError):validate_against_manifest(r,manifest())
        m=manifest();m["cells"].append(dict(physical_cell_id="different",source_cell_id="source_a",dataset="fixture_only",role="test",identity_audit="verified"))
        with self.assertRaises(ValueError):validate_against_manifest(rows(),m)
    def test_single_model_cluster_CI_and_stratified_threshold(self):
        p=protocol(overestimate_threshold_cycles=5,threshold_frozen_before_test=True,query_cycle_bin_edges=[0,50,100])
        r=evaluate_audited(rows(),manifest(),p,n_resamples=100)
        self.assertEqual(r["single_model_MAE_CI"]["point"],5)
        self.assertEqual(r["single_model_MAE_CI"]["ci"],[0,10])
        self.assertEqual(r["overestimate_exceedance"]["cell_macro_rate"],0.5)
        self.assertEqual(r["stratified"]["dataset"]["fixture_only"]["n_cells"],2)
    def test_posthoc_threshold_and_bins_not_accepted(self):
        for p in [protocol(overestimate_threshold_cycles=5),protocol(query_cycle_bin_edges=[0,100],query_grid_frozen_before_test=False)]:
            with self.assertRaises(ValueError):evaluate_audited(rows(),manifest(),p,n_resamples=100)
    def test_nonobserved_mixed_coordinate_and_unregistered_query_rejected(self):
        for key,value in [('label_status','right_censored'),('label_status','extrapolated'),
                          ('cycle_index_space','row_position_1based'),('eol_definition_id','other'),
                          ('label_source_sha256','b'*64),('query_cycle',11)]:
            r=copy.deepcopy(rows());r[0][key]=value
            with self.assertRaises(ValueError):evaluate_audited(r,manifest(),protocol(),n_resamples=100)
        with self.assertRaises(ValueError):evaluate_audited(rows(),manifest(),{},n_resamples=100)
    def test_manifest_required_and_single_cell_uncertainty_explicit(self):
        with self.assertRaises(ValueError):validate_against_manifest(rows(),{})
        self.assertIsNone(cell_bootstrap_mae(rows()[:1],n_resamples=100)["ci"])
    def test_cli_requires_manifest(self):
        q=subprocess.run([sys.executable,"-m","rul_benchmark.evaluation","--predictions","unused","--output","unused"],capture_output=True,text=True)
        self.assertEqual(q.returncode,2);self.assertIn("--manifest",q.stderr)
if __name__=="__main__":unittest.main()
